// Host runner for Arduino sketches.
//   SIM_VIRTUAL=1         가상시간 모드 (기본 0 = 실시간)
//   SIM_DURATION=<sec>    가상시간 모드 종료 시각
//   SIM_STEP_US=<us>      가상시간 모드 loop() 1회당 진행 시간 (기본 50us)
//   SIM_SCRIPT="t:cmd;t:cmd"  가상시간 t초에 시리얼 명령 주입
//   SIM_SEED=<n>          analogRead 잡음 시드 (펌웨어 PRNG 시드로 쓰임)
#include "Arduino.h"
#include <chrono>
#include <string>
#include <vector>
#include <deque>
#include <thread>
#include <unistd.h>
#include <fcntl.h>

void setup();
void loop();

SimSerial Serial;
static bool g_virtual = false;
static uint64_t g_vt_us = 0;
static uint64_t g_step_us = 50;
static std::deque<char> g_in;
static std::chrono::steady_clock::time_point g_t0;
static unsigned g_seed = 1;
struct ScriptCmd { double t; std::string cmd; };
static std::vector<ScriptCmd> g_script;
static size_t g_script_idx = 0;

static uint64_t now_us() {
    if (g_virtual) return g_vt_us;
    return (uint64_t)std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - g_t0).count();
}
// PC(64비트)에서는 unsigned long 이 64비트라서, 32비트로 자르면 펌웨어의 64비트 계산과 어긋나
// 71.6분 뒤 1호기(micros 기반 스케줄러)가 멈춘다. 자르지 않고 그대로 반환한다.
// (실제 아두이노는 시계와 계산이 모두 32비트라 되감김이 정상 처리되므로 해당 없음)
unsigned long micros() { return (unsigned long)now_us(); }
unsigned long millis() { return (unsigned long)(now_us() / 1000); }
void delay(unsigned long ms) {
    if (g_virtual) g_vt_us += (uint64_t)ms * 1000;
    else std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}
void pinMode(int, int) {}
void digitalWrite(int pin, int val) {
    if (!g_virtual) fprintf(stderr, "[PIN] D%d=%s\n", pin, val ? "HIGH" : "LOW");
}
int analogRead(int) { return (int)(rand_r(&g_seed) % 1024); }

static void pump_stdin() {
    if (g_virtual) {
        double t = g_vt_us / 1e6;
        while (g_script_idx < g_script.size() && g_script[g_script_idx].t <= t) {
            for (char c : g_script[g_script_idx].cmd) g_in.push_back(c);
            g_in.push_back('\n');
            fprintf(stderr, "[SIM %.1fs] inject: %s\n", t, g_script[g_script_idx].cmd.c_str());
            ++g_script_idx;
        }
        return;
    }
    char buf[256];
    ssize_t n = ::read(0, buf, sizeof(buf));
    for (ssize_t i = 0; i < n; ++i) g_in.push_back(buf[i]);
}
int SimSerial::available() { pump_stdin(); return (int)g_in.size(); }
int SimSerial::read() {
    if (g_in.empty()) return -1;
    char c = g_in.front(); g_in.pop_front(); return (unsigned char)c;
}
size_t SimSerial::print(const char* s) { return fwrite(s, 1, strlen(s), stdout); }
size_t SimSerial::println(const char* s) { size_t n = print(s); fwrite("\r\n", 1, 2, stdout); if (!g_virtual) fflush(stdout); return n + 2; }
void SimSerial::flush() { fflush(stdout); }

int main() {
    const char* v = getenv("SIM_VIRTUAL");
    g_virtual = v && atoi(v);
    double duration = getenv("SIM_DURATION") ? atof(getenv("SIM_DURATION")) : 0;
    if (getenv("SIM_STEP_US")) g_step_us = strtoull(getenv("SIM_STEP_US"), nullptr, 10);
    if (getenv("SIM_SEED")) g_seed = (unsigned)atoi(getenv("SIM_SEED"));
    if (const char* sc = getenv("SIM_SCRIPT")) {
        std::string s(sc); size_t pos = 0;
        while (pos < s.size()) {
            size_t end = s.find(';', pos); if (end == std::string::npos) end = s.size();
            std::string item = s.substr(pos, end - pos);
            size_t c = item.find(':');
            if (c != std::string::npos) g_script.push_back({atof(item.substr(0, c).c_str()), item.substr(c + 1)});
            pos = end + 1;
        }
    }
    if (g_virtual) setvbuf(stdout, nullptr, _IOFBF, 1 << 20);
    else fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK);
    g_t0 = std::chrono::steady_clock::now();
    setup();
    for (;;) {
        loop();
        if (g_virtual) {
            g_vt_us += g_step_us;
            if (duration > 0 && g_vt_us >= (uint64_t)(duration * 1e6)) break;
        } else {
            std::this_thread::sleep_for(std::chrono::microseconds(20));
        }
    }
    fflush(stdout);
    return 0;
}
