#pragma once
#include "Common.h"
#include "DatabaseManager.h"

// Rust 인터록 허브(Unix 도메인 소켓)로 JSON 한 줄 이벤트를 보내고 한 줄 응답을 받는다.
class HubClient {
public:
    HubClient(std::string sock_path, std::shared_ptr<DatabaseManager> db);
    ~HubClient();
    // kind: DEFECT | WARN | HEARTBEAT
    // 논블로킹: 큐에 넣고 즉시 반환 (시리얼 수신 스레드에서 호출해도 안전)
    void post(const std::string& src, const std::string& kind, const std::string& code,
              double value, const std::string& detail);
    void senderLoop();     // 전용 스레드: 큐 전송 + 1초 하트비트
private:
    struct Ev { std::string src, kind, code, detail; double value; std::string ts; };
    std::mutex qm; std::condition_variable qcv; std::deque<Ev> q;
    void sendEvent(const Ev& e);
private:
    std::string path; std::shared_ptr<DatabaseManager> db;
    std::mutex mtx; int fd = -1;
    std::chrono::steady_clock::time_point lastFailLog{};
    std::string request(const std::string& line);   // 실패 시 ""
    bool ensureConnected();
    void disconnect();
};
