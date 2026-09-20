#pragma once 
#include <sqlite3.h>
#include "config.hpp"

class DatabaseManager {
    private: 
      sqlite3* db;

    public: 
      DatabaseManager(const std::string& db_path) {
        if(sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
            std::cerr << "DB 오픈 실패" << sqlite3_errmsg(db) <<std::endl; 
        }  else { 
            createTable(); 
        }
      } 
      
      ~DatabaseManager() {
          sqlite3_close(db);
      }

      void createTable() {
          const char* sql = "CREATE TABLE IF NOT EXISTS intrusion_logs ("
                          "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "timestamp TEXT, "
                          "max_penetration_mm REAL, "
                          "danger_level TEXT, "
                          "image_path TEXT);";
          char* errMsg = nullptr;
          if(sqlite3_exec(db, sql, nullptr, nullptr, &errMsg) !=SQLITE_OK) {
            std::cerr << "테이블 생성 실패: " <<errMsg << std::endl;
            sqlite3_free(errMsg);
          }
      }


      bool insertLog(const SafetyGuard::IntrusionLog& log) {
        const char* sql = "INSERT INTO intrusion_logs ("
                          "timestamp, max_penetration_mm," 
                          "danger_level, image_path)"
                          "VALUES (?, ?, ?, ?);";
        
        sqlite3_stmt* stmt;
        
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) !=SQLITE_OK) return false;

        sqlite3_bind_text(stmt, 1, log.timestamp.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_double(stmt, 2, log.max_penetration_mm);
        sqlite3_bind_text(stmt, 3, log.danger_level.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 4, log.image_path.c_str(), -1, SQLITE_STATIC);

        bool success = (sqlite3_step(stmt) == SQLITE_DONE);
        sqlite3_finalize(stmt);
        return success;
      }
};
