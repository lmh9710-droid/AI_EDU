#pragma once
#include "Common.h"

// 단일 쓰기 전용 스레드 + 영속 연결 + 200ms 배치 트랜잭션.
// 시리얼 수신 스레드는 DB 를 절대 기다리지 않는다 (수신 버퍼 overflow 로 인한 데이터 손실 방지).
class DatabaseManager {
public:
    using Job = std::function<void(sqlite3*)>;
    explicit DatabaseManager(const std::string& path);
    ~DatabaseManager();
    bool initializeDatabase();
    void start();
    void stop();
    void enqueue(Job job);
    const std::string& path() const { return db_path; }
    size_t pending() { std::lock_guard<std::mutex> l(mtx); return q.size(); }

    // 공용 헬퍼: 준비문 실행
    static bool execStmt(sqlite3* db, const char* sql, const std::function<void(sqlite3_stmt*)>& bind);
private:
    std::string db_path;
    std::mutex mtx; std::condition_variable cv;
    std::deque<Job> q;
    std::thread worker;
    std::atomic<bool> running{false};
    void run();
};
