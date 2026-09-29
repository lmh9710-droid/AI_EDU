#include "DatabaseManager.h"

// 전역 변수 실체화 (Instantiation)
std::mutex db_mutex;
std::mutex interlock_mutex;
std::condition_variable interlock_cv;
std::queue<std::string> interlock_cmd_queue;
bool system_active = true;

DatabaseManager::DatabaseManager(const std::string& path) : db_path(path) {}

void DatabaseManager::initializeDatabase() {
    sqlite3* db;
    if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) return;

    const char* sql_forging = "CREATE TABLE IF NOT EXISTS tb_forging_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, pressure REAL, defect_band_energy REAL, status TEXT);";
    const char* sql_rolling = "CREATE TABLE IF NOT EXISTS tb_rolling_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, displacement REAL, ae_signal REAL, status TEXT);";
    const char* sql_heat    = "CREATE TABLE IF NOT EXISTS tb_heat_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, temperature REAL, carbon_ratio REAL, status TEXT);";

    sqlite3_exec(db, sql_forging, nullptr, nullptr, nullptr);
    sqlite3_exec(db, sql_rolling, nullptr, nullptr, nullptr);
    sqlite3_exec(db, sql_heat, nullptr, nullptr, nullptr);
    sqlite3_close(db);
    std::cout << "📥 [DATABASE] 스마트팩토리 개별 테이블 구축 완료.\n";
}

sqlite3* DatabaseManager::getRawConnection() {
    sqlite3* db;
    if (sqlite3_open(db_path.c_str(), &db) == SQLITE_OK) return db;
    return nullptr;
}
