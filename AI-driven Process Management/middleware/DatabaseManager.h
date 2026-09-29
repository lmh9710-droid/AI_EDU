#pragma once
#include "Common.h"

class DatabaseManager {
private:
    std::string db_path;
public:
    DatabaseManager(const std::string& path);
    void initializeDatabase();
    sqlite3* getRawConnection();
};
