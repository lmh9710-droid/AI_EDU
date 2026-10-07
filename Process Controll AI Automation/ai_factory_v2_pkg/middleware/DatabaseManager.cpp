#include "DatabaseManager.h"

std::atomic<bool> system_active(true);

DatabaseManager::DatabaseManager(const std::string& path) : db_path(path) {}
DatabaseManager::~DatabaseManager() { stop(); }

static bool exec_or_log(sqlite3* db, const std::string& sql) {
    char* err = nullptr;
    if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err) != SQLITE_OK) {
        std::cerr << "❌ [DATABASE] " << (err ? err : "unknown") << "\n   -> " << sql << "\n";
        sqlite3_free(err); return false;
    }
    return true;
}

static void ensure_column(sqlite3* db, const char* table, const char* col, const char* type) {
    std::string q = std::string("PRAGMA table_info(") + table + ");";
    sqlite3_stmt* st = nullptr; bool found = false;
    if (sqlite3_prepare_v2(db, q.c_str(), -1, &st, nullptr) == SQLITE_OK)
        while (sqlite3_step(st) == SQLITE_ROW)
            if (!strcmp((const char*)sqlite3_column_text(st, 1), col)) found = true;
    sqlite3_finalize(st);
    if (!found) {
        exec_or_log(db, std::string("ALTER TABLE ") + table + " ADD COLUMN " + col + " " + type + ";");
        std::cout << "🔧 [DATABASE] 마이그레이션: " << table << "." << col << " 추가\n";
    }
}

bool DatabaseManager::initializeDatabase() {
    sqlite3* db = nullptr;
    if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
        std::cerr << "❌ [DATABASE] 열기 실패: " << db_path << "\n"; if (db) sqlite3_close(db); return false;
    }
    sqlite3_busy_timeout(db, 5000);
    bool ok = true;
    const char* ddl[] = {
        "PRAGMA journal_mode=WAL;",
        "CREATE TABLE IF NOT EXISTS tb_forging_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, pressure REAL, defect_band_energy REAL, status TEXT);",
        "CREATE TABLE IF NOT EXISTS tb_rolling_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, displacement REAL, ae_signal REAL, status TEXT);",
        "CREATE TABLE IF NOT EXISTS tb_heat_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, temperature REAL, carbon_ratio REAL, status TEXT);",
        "CREATE TABLE IF NOT EXISTS tb_sim_truth (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, equipment_id TEXT, scenario TEXT, damage REAL);",
        "CREATE TABLE IF NOT EXISTS tb_link_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, equipment_id TEXT, received INTEGER, lost INTEGER, corrupt INTEGER, resyncs INTEGER);",
        "CREATE TABLE IF NOT EXISTS tb_interlock_event (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, source TEXT, kind TEXT, code TEXT, value REAL, detail TEXT, command TEXT, cmd_id INTEGER, result TEXT, latency_ms REAL);",
    };
    for (const char* s : ddl) ok = exec_or_log(db, s) && ok;

    // 기존 DB 호환: 없는 컬럼만 추가
    ensure_column(db, "tb_forging_telemetry", "seq_first", "INTEGER");
    ensure_column(db, "tb_forging_telemetry", "samples", "INTEGER");
    ensure_column(db, "tb_forging_telemetry", "lost_samples", "INTEGER");
    ensure_column(db, "tb_forging_telemetry", "pressure_min", "REAL");
    ensure_column(db, "tb_forging_telemetry", "pressure_max", "REAL");
    ensure_column(db, "tb_forging_telemetry", "raw_waveform", "BLOB");
    ensure_column(db, "tb_rolling_telemetry", "seq", "INTEGER");
    ensure_column(db, "tb_heat_telemetry", "seq", "INTEGER");

    const char* idx[] = {
        "CREATE INDEX IF NOT EXISTS idx_forging_ts ON tb_forging_telemetry(timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_rolling_ts ON tb_rolling_telemetry(timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_heat_ts ON tb_heat_telemetry(timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_truth_ts ON tb_sim_truth(equipment_id, timestamp);",
    };
    for (const char* s : idx) ok = exec_or_log(db, s) && ok;
    sqlite3_close(db);
    if (ok) std::cout << "📥 [DATABASE] 스키마 준비 완료 (WAL) -> " << db_path << "\n";
    return ok;
}

void DatabaseManager::start() {
    running = true;
    worker = std::thread(&DatabaseManager::run, this);
}

void DatabaseManager::stop() {
    if (!running.exchange(false)) return;
    cv.notify_all();
    if (worker.joinable()) worker.join();
}

void DatabaseManager::enqueue(Job job) {
    { std::lock_guard<std::mutex> l(mtx); q.push_back(std::move(job)); }
    cv.notify_one();
}

bool DatabaseManager::execStmt(sqlite3* db, const char* sql, const std::function<void(sqlite3_stmt*)>& bind) {
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(db, sql, -1, &st, nullptr) != SQLITE_OK) {
        std::cerr << "❌ [DATABASE] prepare 실패: " << sqlite3_errmsg(db) << "\n"; return false;
    }
    bind(st);
    bool ok = sqlite3_step(st) == SQLITE_DONE;
    if (!ok) std::cerr << "❌ [DATABASE] step 실패: " << sqlite3_errmsg(db) << "\n";
    sqlite3_finalize(st);
    return ok;
}

void DatabaseManager::run() {
    sqlite3* db = nullptr;
    while (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
        std::cerr << "❌ [DATABASE] writer 연결 실패, 1초 후 재시도\n";
        if (db) { sqlite3_close(db); db = nullptr; }
        std::this_thread::sleep_for(std::chrono::seconds(1));
        if (!running) return;
    }
    sqlite3_busy_timeout(db, 5000);
    exec_or_log(db, "PRAGMA synchronous=NORMAL;");
    size_t warnAt = 5000;
    while (true) {
        std::deque<Job> batch;
        {
            std::unique_lock<std::mutex> l(mtx);
            cv.wait_for(l, std::chrono::milliseconds(200), [this] { return !q.empty() || !running; });
            batch.swap(q);
            if (batch.empty() && !running) break;
        }
        if (batch.empty()) continue;
        if (batch.size() > warnAt) { std::cerr << "⚠️ [DATABASE] 쓰기 적체 " << batch.size() << "건\n"; warnAt *= 2; }
        exec_or_log(db, "BEGIN;");
        for (auto& j : batch) j(db);
        exec_or_log(db, "COMMIT;");
    }
    sqlite3_close(db);
}
