#pragma once
#include "Common.h"
#include "DatabaseManager.h"
#include "HubClient.h"

// 공통 수신 프레임워크
//   - 패킷: [TAG],<seq>,f1,f2*<XOR-HEX>  /  진실값: [TAG_SIM],<seq>,<scenario>,<damage>*<XOR-HEX>
//   - 체크섬 불일치 → corrupt, seq 건너뜀 → lost, seq 역행(보드 리셋) → resync
//   - '#' 로 시작하는 줄은 보드 메시지 (콘솔 출력)
class BaseEquipment {
protected:
    std::string port_path, equipment_id, tag;
    std::shared_ptr<DatabaseManager> db;
    std::shared_ptr<HubClient> hub;
    int serial_fd = -1;

    // 링크 통계
    uint64_t received = 0, lost = 0, corrupt = 0, resyncs = 0;
    uint64_t lastRx = 0, lastLost = 0, lastCorrupt = 0, lastResync = 0;
    bool haveSeq = false; uint32_t expectedSeq = 0;
    std::chrono::steady_clock::time_point lastStats = std::chrono::steady_clock::now();
    std::string lastWarnCode;
    // 포트를 연 직후 2초는 '동기화 구간': 열기 전 쌓였다가 버려진 데이터 때문에 생기는 seq 점프는
    // 전송 누락이 아니므로 lost 가 아닌 resync 로 집계한다.
    std::chrono::steady_clock::time_point syncUntil{};

    static bool verifyChecksum(const std::string& line, std::string& body) {
        size_t star = line.rfind('*');
        if (star == std::string::npos || star + 3 != line.size()) return false;
        uint8_t cs = 0; for (size_t i = 0; i < star; ++i) cs ^= (uint8_t)line[i];
        unsigned v = 0;
        if (sscanf(line.c_str() + star + 1, "%2x", &v) != 1) return false;
        body = line.substr(0, star);
        return v == cs;
    }
    static std::vector<std::string> split(const std::string& s) {
        std::vector<std::string> t; std::stringstream ss(s); std::string it;
        while (std::getline(ss, it, ',')) t.push_back(it);
        return t;
    }

    // 판정 결과 전달: 불량은 DEFECT(라인정지 후 퇴출), 위험 경고는 WARN
    void reportDefect(const std::string& code, double value, const std::string& detail) {
        std::cout << "🚨 [" << equipment_id << "] " << code << " = " << value << "  (" << detail << ")\n";
        hub->post(equipment_id, "DEFECT", code, value, detail);
    }
    void reportWarn(const std::string& code, double value, const std::string& detail) {
        if (lastWarnCode != code) std::cout << "⚠️ [" << equipment_id << "] " << code << " = " << value << "  (" << detail << ")\n";
        lastWarnCode = code;
        hub->post(equipment_id, "WARN", code, value, detail);
    }
    void clearWarn() { lastWarnCode.clear(); }

    static std::string joinCodes(const std::vector<std::string>& codes) {
        if (codes.empty()) return "OK";
        std::string s; for (size_t i = 0; i < codes.size(); ++i) { if (i) s += "|"; s += codes[i]; }
        return s;
    }

    virtual void onData(const std::vector<std::string>& f, uint32_t seq) = 0;
    virtual void onResync() {}

    void onSimTruth(const std::vector<std::string>& f) {
        double dmg; if (f.size() < 4 || !parse_double(f[3], dmg)) return;
        std::string ts = get_precise_timestamp(), id = equipment_id, sc = f[2];
        db->enqueue([=](sqlite3* d) {
            DatabaseManager::execStmt(d, "INSERT INTO tb_sim_truth (timestamp, equipment_id, scenario, damage) VALUES (?,?,?,?);",
                [&](sqlite3_stmt* st) {
                    sqlite3_bind_text(st, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
                    sqlite3_bind_text(st, 2, id.c_str(), -1, SQLITE_TRANSIENT);
                    sqlite3_bind_text(st, 3, sc.c_str(), -1, SQLITE_TRANSIENT);
                    sqlite3_bind_double(st, 4, dmg);
                });
        });
    }

    void handleLine(const std::string& line) {
        if (line[0] == '#') { std::cout << "📟 [" << equipment_id << " 보드] " << line << "\n"; return; }
        std::string body;
        if (!verifyChecksum(line, body)) { corrupt++; return; }
        auto f = split(body);
        if (f.size() < 2) { corrupt++; return; }
        if (f[0] == "[" + tag + "_SIM]") { onSimTruth(f); return; }
        if (f[0] != "[" + tag + "]") { corrupt++; return; }
        uint32_t seq; if (!parse_u32(f[1], seq)) { corrupt++; return; }
        bool syncing = std::chrono::steady_clock::now() < syncUntil;
        if (haveSeq) {
            if (seq > expectedSeq && syncing) { resyncs++; onResync(); }
            else if (seq > expectedSeq) lost += seq - expectedSeq;
            else if (seq < expectedSeq) { resyncs++; std::cout << "🔄 [" << equipment_id << "] 보드 재시작 감지 (seq " << expectedSeq << " → " << seq << ")\n"; onResync(); }
        }
        haveSeq = true; expectedSeq = seq + 1; received++;
        onData(f, seq);
    }

    void flushStats(bool force = false) {
        auto now = std::chrono::steady_clock::now();
        if (!force && now - lastStats < std::chrono::seconds(10)) return;
        lastStats = now;
        uint64_t r = received - lastRx, l = lost - lastLost, c = corrupt - lastCorrupt, s = resyncs - lastResync;
        lastRx = received; lastLost = lost; lastCorrupt = corrupt; lastResync = resyncs;
        if (l || c) std::cout << "⚠️ [" << equipment_id << " 링크] 10초간 수신 " << r << " / 누락 " << l << " / 손상 " << c << "\n";
        std::string ts = get_precise_timestamp(), id = equipment_id;
        db->enqueue([=](sqlite3* d) {
            DatabaseManager::execStmt(d, "INSERT INTO tb_link_stats (timestamp, equipment_id, received, lost, corrupt, resyncs) VALUES (?,?,?,?,?,?);",
                [&](sqlite3_stmt* st) {
                    sqlite3_bind_text(st, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
                    sqlite3_bind_text(st, 2, id.c_str(), -1, SQLITE_TRANSIENT);
                    sqlite3_bind_int64(st, 3, (sqlite3_int64)r); sqlite3_bind_int64(st, 4, (sqlite3_int64)l);
                    sqlite3_bind_int64(st, 5, (sqlite3_int64)c); sqlite3_bind_int64(st, 6, (sqlite3_int64)s);
                });
        });
    }

    void runLineLoop() {
        std::string buf; char chunk[4096];
        while (system_active) {
            ssize_t n = read(serial_fd, chunk, sizeof(chunk));
            if (n < 0) {
                std::cerr << "❌ [" << equipment_id << "] 시리얼 read 오류: " << strerror(errno) << " → 재연결 시도\n";
                close(serial_fd); serial_fd = -1;
                while (system_active && (serial_fd = open_serial_115200(port_path)) < 0)
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                haveSeq = false; buf.clear(); onResync();
                syncUntil = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                continue;
            }
            for (ssize_t i = 0; i < n; ++i) {
                char ch = chunk[i];
                if (ch == '\n' || ch == '\r') { if (!buf.empty()) { handleLine(buf); buf.clear(); } }
                else if (buf.size() < 200) buf += ch;
                else { buf.clear(); corrupt++; }
            }
            flushStats();
        }
        flushStats(true);
    }

public:
    BaseEquipment(std::string port, std::string id, std::string t,
                  std::shared_ptr<DatabaseManager> d, std::shared_ptr<HubClient> h)
        : port_path(std::move(port)), equipment_id(std::move(id)), tag(std::move(t)), db(std::move(d)), hub(std::move(h)) {}
    virtual ~BaseEquipment() { if (serial_fd >= 0) close(serial_fd); }

    void startCaptureLoop() {
        while (system_active && (serial_fd = open_serial_115200(port_path)) < 0) {
            std::cerr << "❌ [" << equipment_id << "] 포트 열기 실패: " << port_path << " (" << strerror(errno) << "), 3초 후 재시도\n";
            for (int i = 0; i < 30 && system_active; ++i) std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        if (!system_active) return;
        std::cout << "🚀 [" << equipment_id << " ACTIVE] -> " << port_path << "\n";
        syncUntil = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        runLineLoop();
    }
};
