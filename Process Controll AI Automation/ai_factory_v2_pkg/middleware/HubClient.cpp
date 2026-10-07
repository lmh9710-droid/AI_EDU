#include "HubClient.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <map>

HubClient::HubClient(std::string sock_path, std::shared_ptr<DatabaseManager> d) : path(std::move(sock_path)), db(std::move(d)) {}
HubClient::~HubClient() { disconnect(); }

void HubClient::disconnect() { if (fd >= 0) { close(fd); fd = -1; } }

bool HubClient::ensureConnected() {
    if (fd >= 0) return true;
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return false;
    sockaddr_un addr{}; addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
    if (connect(fd, (sockaddr*)&addr, sizeof(addr)) != 0) { disconnect(); return false; }
    timeval tv{1, 0};                                   // 응답 최대 1초 (허브는 ACK 재시도 포함 ~1초 내 응답)
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    return true;
}

std::string HubClient::request(const std::string& line) {
    std::lock_guard<std::mutex> l(mtx);
    for (int attempt = 0; attempt < 2; ++attempt) {
        if (!ensureConnected()) continue;
        std::string msg = line + "\n";
        if (send(fd, msg.data(), msg.size(), MSG_NOSIGNAL) != (ssize_t)msg.size()) { disconnect(); continue; }
        std::string reply; char c;
        while (true) {
            ssize_t n = recv(fd, &c, 1, 0);
            if (n <= 0) { disconnect(); reply.clear(); break; }
            if (c == '\n') return reply;
            reply += c;
        }
    }
    return "";
}

void HubClient::post(const std::string& src, const std::string& kind, const std::string& code,
                     double value, const std::string& detail) {
    {
        std::lock_guard<std::mutex> l(qm);
        // 같은 출처/코드의 미전송 이벤트는 최신 값으로 덮어씀 (적체 방지, 레벨 트리거라 손실 없음)
        for (auto& e : q) if (e.src == src && e.kind == kind && e.code == code) {
            e.value = value; e.detail = detail; e.ts = get_precise_timestamp(); return;
        }
        q.push_back(Ev{src, kind, code, detail, value, get_precise_timestamp()});
    }
    qcv.notify_one();
}

void HubClient::senderLoop() {
    auto nextHb = std::chrono::steady_clock::now();
    while (system_active) {
        std::deque<Ev> batch;
        {
            std::unique_lock<std::mutex> l(qm);
            qcv.wait_until(l, nextHb, [this] { return !q.empty() || !system_active; });
            batch.swap(q);
        }
        for (auto& e : batch) sendEvent(e);
        if (std::chrono::steady_clock::now() >= nextHb) {
            sendEvent(Ev{"MIDDLEWARE", "HEARTBEAT", "ALIVE", "", 0, get_precise_timestamp()});
            nextHb = std::chrono::steady_clock::now() + std::chrono::seconds(1);
        }
    }
}

void HubClient::sendEvent(const Ev& ev) {
    const std::string& src = ev.src; const std::string& kind = ev.kind; const std::string& code = ev.code;
    const std::string& detail = ev.detail; double value = ev.value;
    std::ostringstream js;
    js.precision(10);
    js << "{\"src\":\"" << json_escape(src) << "\",\"kind\":\"" << kind << "\",\"code\":\"" << code
       << "\",\"value\":" << (std::isfinite(value) ? value : 0.0) << ",\"detail\":\"" << json_escape(detail)
       << "\",\"ts\":\"" << ev.ts << "\"}";
    std::string reply = request(js.str());
    if (!reply.empty()) return;
    if (kind == "HEARTBEAT") return;

    // 허브 미응답: 안전 경로 단절. 콘솔 경고 + DB 기록 (동일 코드는 5초에 1회)
    static std::mutex m; static std::map<std::string, std::chrono::steady_clock::time_point> last;
    auto now = std::chrono::steady_clock::now();
    {
        std::lock_guard<std::mutex> l(m);
        auto key = src + code;
        if (last.count(key) && now - last[key] < std::chrono::seconds(5)) return;
        last[key] = now;
    }
    std::cerr << "🛑 [HUB UNREACHABLE] " << src << " " << kind << " " << code
              << " 를 인터록 허브에 전달하지 못했습니다! (" << path << ")\n";
    std::string ts = ev.ts, s = src, k = kind, cd = code, dt = detail;
    db->enqueue([=](sqlite3* d) {
        DatabaseManager::execStmt(d,
            "INSERT INTO tb_interlock_event (timestamp, source, kind, code, value, detail, command, result) VALUES (?,?,?,?,?,?,NULL,'HUB_UNREACHABLE');",
            [&](sqlite3_stmt* st) {
                sqlite3_bind_text(st, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_text(st, 2, s.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_text(st, 3, k.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_text(st, 4, cd.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_double(st, 5, value);
                sqlite3_bind_text(st, 6, dt.c_str(), -1, SQLITE_TRANSIENT);
            });
    });
}

