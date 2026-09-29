#pragma once
#include <iostream>
#include <string>
#include <vector>
#include <complex>
#include <cmath>
#include <sstream>
#include <thread>
#include <mutex>
#include <chrono>
#include <queue>
#include <condition_variable>
#include <memory>
#include <fcntl.h>   
#include <termios.h> 
#include <unistd.h>  
#include <sqlite3.h>
#include <stdexcept>

const double PI = 3.14159265358979323846;
const int SAMPLING_RATE = 1024;

// 전역 변수 외부 참조 선언
extern std::mutex db_mutex;
extern std::mutex interlock_mutex;
extern std::condition_variable interlock_cv;
extern std::queue<std::string> interlock_cmd_queue;
extern bool system_active;

// 인라인(static inline) 키워드를 붙여 컴파일러가 파일별로 중복 생성하는 에러 원천 방어
static inline std::string get_precise_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto ts_time_t = std::chrono::system_clock::to_time_t(now);
    auto ts_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    struct tm parts;
    localtime_r(&ts_time_t, &parts);
    char buf[128];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d %02d:%02d:%02d.%03d",
             parts.tm_year + 1900, parts.tm_mon + 1, parts.tm_mday,
             parts.tm_hour, parts.tm_min, parts.tm_sec, (int)ts_ms.count());
    return std::string(buf);
}

// 에러 방어용 문자열 변환 처리 치트키
static inline double SafeStod(const std::string& str, double default_val = 0.0) {
    if (str.empty()) return default_val;
    try {
        return std::stod(str);
    } catch (...) {
        return default_val;
    }
}
