#pragma once
#include <iostream>
#include <string>
#include <vector>
#include <complex>
#include <cmath>
#include <sstream>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <deque>
#include <functional>
#include <condition_variable>
#include <memory>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <cerrno>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <sqlite3.h>

const double PI = 3.14159265358979323846;
const int SAMPLING_RATE = 1024;

// =====================================================================
// 불량 판정 기준표 (요구 스펙 원본 그대로. Python config.py 와 동일해야 함)
// =====================================================================
namespace Spec {
    // 1호기 압조
    constexpr double FORGING_PRESSURE_LOW   = 48.0;   // pressure < 48      → 압력 낮음
    constexpr double FORGING_PRESSURE_HIGH  = 52.0;   // pressure > 52      → 압력 높음
    constexpr double FORGING_VIBE_WARN      = 0.4;    // 0.4 <= rms < 0.8   → 위험 경고
    constexpr double FORGING_VIBE_CRITICAL  = 0.8;    // rms >= 0.8         → 설비 파손 위험
    constexpr int    FORGING_BAND_LOW_HZ    = 340;    // 350Hz 대역 정의
    constexpr int    FORGING_BAND_HIGH_HZ   = 360;
    // 2호기 전조
    constexpr double ROLLING_DISP_MIN = 3.95;         // displacement < 3.95 → 미성형
    constexpr double ROLLING_DISP_MAX = 4.05;         // displacement > 4.05 → 과성형
    constexpr double ROLLING_AE_MAX   = 40.0;         // ae_signal > 40      → 초음파 불량 (규칙 판정만, AI 없음)
    // 3호기 열처리 (carbon_ratio 는 기록만, 판정 없음)
    constexpr double HEAT_TEMP_MIN = 830.0;           // temperature < 830   → 온도 드랍
    constexpr double HEAT_TEMP_MAX = 870.0;           // temperature > 870   → 과온도
}

extern std::atomic<bool> system_active;

// 로컬 시각 (프로세스 TZ = Asia/Seoul) 밀리초 정밀
static inline std::string get_precise_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto tt = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    struct tm p; localtime_r(&tt, &p);
    char buf[64];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d %02d:%02d:%02d.%03d",
             p.tm_year + 1900, p.tm_mon + 1, p.tm_mday, p.tm_hour, p.tm_min, p.tm_sec, (int)ms.count());
    return buf;
}

static inline bool parse_double(const std::string& s, double& out) {
    if (s.empty()) return false;
    char* end = nullptr; out = std::strtod(s.c_str(), &end);
    return end && *end == '\0' && std::isfinite(out);
}
static inline bool parse_u32(const std::string& s, uint32_t& out) {
    if (s.empty()) return false;
    char* end = nullptr; unsigned long v = std::strtoul(s.c_str(), &end, 10);
    if (!end || *end != '\0') return false;
    out = (uint32_t)v; return true;
}
static inline std::string getenv_or(const char* key, const std::string& fallback) {
    const char* v = std::getenv(key);
    return (v && *v) ? std::string(v) : fallback;
}
static inline std::string json_escape(const std::string& s) {
    std::string o; o.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += c; }
        else if ((unsigned char)c < 0x20) o += ' ';
        else o += c;
    }
    return o;
}

// 115200 8N1 raw, VMIN=0/VTIME=1 (최대 100ms 대기 후 반환 → 종료 신호 확인 가능)
static inline int open_serial_115200(const std::string& path) {
    int fd = open(path.c_str(), O_RDWR | O_NOCTTY);
    if (fd < 0) return -1;
    struct termios tty;
    if (tcgetattr(fd, &tty) != 0) { close(fd); return -1; }
    cfmakeraw(&tty);
    cfsetospeed(&tty, B115200); cfsetispeed(&tty, B115200);
    tty.c_cflag |= (CLOCAL | CREAD);
    tty.c_cflag &= ~(PARENB | PARODD | CSTOPB | CRTSCTS);
    tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 1;
    if (tcsetattr(fd, TCSANOW, &tty) != 0) { close(fd); return -1; }
    tcflush(fd, TCIFLUSH);
    return fd;
}
