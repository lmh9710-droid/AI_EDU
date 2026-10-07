/*
 * 2호기 전조(Thread Rolling) 가상 센서 보드  —  Arduino UNO R4 Minima
 * ---------------------------------------------------------------------------
 * 출력 (부품 1개 = 0.8s 사이클):  [ROLLING],<seq>,<displacement_mm>,<ae_dB>*<XOR-HEX>
 * 진실값 (1Hz)                 :  [ROLLING_SIM],<seq>,<scenario>,<damage>*<XOR-HEX>
 *
 * 물리 모델 (정상)
 *   금형 변위 = 4.000 mm + 열적 변동(느린 AR, ±0.005) + 게이지 잡음(σ0.008)  → 규격 3.95~4.05 내 (Cpk≈1.9)
 *   초음파 AE = 22 dB + 잡음(σ1.8)                                          → 정상 15~30 내
 *
 * 열화 시나리오 (서서히 진행, REPAIR 전까지 회복 없음)
 *   DIE_WEAR        전조 다이스 마모: 성형 깊이 감소 → 변위 하강, D=1 에서 평균 3.95 (미성형)
 *   THERMAL_GROWTH  금형 열팽창/정렬 불량: 변위 상승, D=1 에서 평균 4.05 (과성형)
 *   TOOL_CHIP       다이 치핑/미세균열: AE 기저 상승(D=1 에서 40dB) + AE 히트 버스트 빈도 증가
 *                   → 30~40dB 회색 구간을 거쳐 40 초과 (초음파 불량)
 * 명령: SCN <DIE_WEAR|THERMAL_GROWTH|TOOL_CHIP> <TTF분> [shape] | AUTO <0|1> [분] | REPAIR | STATUS
 */
#include <Arduino.h>

#define CYCLE_MS 800
#define BOARD_TAG "ROLLING"

// ---------------- 공통 유틸 (보드별 스케치에 동일 복사) ----------------
static uint32_t rngState = 2463534242UL;
static inline uint32_t rngNext() { rngState ^= rngState << 13; rngState ^= rngState >> 17; rngState ^= rngState << 5; return rngState; }
static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
static inline float urand() { return (rngNext() >> 8) * (1.0f / 16777216.0f); }            // [0,1)
static inline float urandRange(float a, float b) { return a + (b - a) * urand(); }
static float gaussSpare = 0; static bool gaussHasSpare = false;
static float gauss() {                                                                    // N(0,1)
    if (gaussHasSpare) { gaussHasSpare = false; return gaussSpare; }
    float u1 = urand(); if (u1 < 1e-7f) u1 = 1e-7f;
    float u2 = urand();
    float r = sqrtf(-2.0f * logf(u1)), th = 2.0f * (float)PI * u2;
    gaussSpare = r * sinf(th); gaussHasSpare = true;
    return r * cosf(th);
}
static void emitLine(char* body) {                // body + "*CS" + CRLF, 한 번에 출력
    uint8_t cs = 0; for (char* p = body; *p; ++p) cs ^= (uint8_t)*p;
    size_t n = strlen(body);
    snprintf(body + n, 6, "*%02X", cs);
    Serial.println(body);
}
static char cmdBuf[64]; static uint8_t cmdLen = 0;
static bool pollCommand() {
    while (Serial.available() > 0) {
        int c = Serial.read(); if (c < 0) break;
        if (c == '\n' || c == '\r') { if (cmdLen) { cmdBuf[cmdLen] = 0; cmdLen = 0; return true; } }
        else if (cmdLen < sizeof(cmdBuf) - 1) cmdBuf[cmdLen++] = (char)c;
    }
    return false;
}
struct Degradation {
    int   scenario = 0;      // 0 = 정상
    float ttfSec = 0, shape = 2.0f, elapsed = 0, speed = 1.0f, damage = 0;
    void start(int s, float ttfMin, float shp) { scenario = s; ttfSec = ttfMin * 60.0f; shape = shp; elapsed = 0; speed = 1.0f; damage = 0; }
    void repair() { scenario = 0; damage = 0; elapsed = 0; }
    void step(float dt) {
        if (!scenario) return;
        speed += 0.02f * gauss() * sqrtf(dt);                 // 진행 속도 랜덤워크
        speed = clampf(speed, 0.7f, 1.3f);
        elapsed += dt * speed;
        damage = powf(elapsed / ttfSec, shape);
        if (damage > 1.6f) damage = 1.6f;                      // 고장 후 악화 상한
    }
};
static bool autoMode = false; static float autoMeanMin = 60.0f;
// ----------------------------------------------------------------------

enum { SC_NONE = 0, SC_DIE_WEAR, SC_THERMAL_GROWTH, SC_TOOL_CHIP, SC_COUNT };
static const char* SC_NAME[SC_COUNT] = {"NORMAL", "DIE_WEAR", "THERMAL_GROWTH", "TOOL_CHIP"};

static Degradation deg;
static unsigned long lastCycleMs = 0, lastSecMs = 0;
static uint32_t seqData = 0, seqSim = 0;
static float thermalWander = 0;

static void handleCommand(char* cmd) {
    char out[96];
    char* tok = strtok(cmd, " ");
    if (!tok) return;
    if (!strcmp(tok, "SCN")) {
        char* name = strtok(nullptr, " "); char* ttf = strtok(nullptr, " "); char* shp = strtok(nullptr, " ");
        int s = 0; for (int i = 1; i < SC_COUNT; ++i) if (name && !strcmp(name, SC_NAME[i])) s = i;
        float m = ttf ? (float)atof(ttf) : 0;
        if (!s || m <= 0) { Serial.println("#ERR usage: SCN <DIE_WEAR|THERMAL_GROWTH|TOOL_CHIP> <TTF_min> [shape]"); return; }
        deg.start(s, m, shp ? (float)atof(shp) : 2.0f);
        snprintf(out, sizeof(out), "#OK SCN %s ttf=%.1fmin shape=%.2f", SC_NAME[s], m, deg.shape); Serial.println(out);
    } else if (!strcmp(tok, "AUTO")) {
        char* on = strtok(nullptr, " "); char* mean = strtok(nullptr, " ");
        autoMode = on && atoi(on); if (mean) autoMeanMin = (float)atof(mean);
        snprintf(out, sizeof(out), "#OK AUTO %d mean=%.0fmin", autoMode ? 1 : 0, autoMeanMin); Serial.println(out);
    } else if (!strcmp(tok, "REPAIR")) {
        deg.repair(); Serial.println("#OK REPAIR (dies replaced/realigned)");
    } else if (!strcmp(tok, "STATUS")) {
        snprintf(out, sizeof(out), "#STATUS %s damage=%.3f elapsed=%.0fs auto=%d", SC_NAME[deg.scenario], deg.damage, deg.elapsed, autoMode ? 1 : 0);
        Serial.println(out);
    } else {
        Serial.println("#HELP SCN <DIE_WEAR|THERMAL_GROWTH|TOOL_CHIP> <TTF_min> [shape] | AUTO <0|1> [mean_min] | REPAIR | STATUS");
    }
}

void setup() {
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0 < 1500)) {}
    rngState ^= (uint32_t)analogRead(A1) * 2654435761UL ^ micros();
    if (!rngState) rngState = 1;
    lastCycleMs = lastSecMs = millis();
    Serial.println("#BOOT ROLLING virtual sensor ready");
}

void loop() {
    if (pollCommand()) handleCommand(cmdBuf);
    unsigned long now = millis();

    if (now - lastSecMs >= 1000) {                       // 1초 주기: 열화 진행 + 진실값
        lastSecMs += 1000;
        deg.step(1.0f);
        if (autoMode && deg.scenario == SC_NONE && urand() < 1.0f / (autoMeanMin * 60.0f)) {
            int s = 1 + (int)(urand() * (SC_COUNT - 1)); if (s >= SC_COUNT) s = SC_COUNT - 1;
            deg.start(s, urandRange(15.0f, 45.0f), urandRange(1.5f, 2.5f));
            char o[64]; snprintf(o, sizeof(o), "#AUTO start %s ttf=%.1fmin", SC_NAME[s], deg.ttfSec / 60); Serial.println(o);
        }
        thermalWander = 0.97f * thermalWander + 0.0010f * gauss();
        thermalWander = clampf(thermalWander, -0.005f, 0.005f);
        char body[80];
        snprintf(body, sizeof(body), "[%s_SIM],%lu,%s,%.4f", BOARD_TAG, (unsigned long)seqSim++, SC_NAME[deg.scenario], deg.damage);
        emitLine(body);
    }

    if (now - lastCycleMs < CYCLE_MS) return;            // 부품 1개 성형 완료 시점
    lastCycleMs += CYCLE_MS;

    float dWear  = deg.scenario == SC_DIE_WEAR ? deg.damage : 0;
    float dTherm = deg.scenario == SC_THERMAL_GROWTH ? deg.damage : 0;
    float dChip  = deg.scenario == SC_TOOL_CHIP ? deg.damage : 0;

    float disp = 4.000f + thermalWander - 0.05f * dWear + 0.05f * dTherm
               + 0.008f * (1.0f + 0.5f * (dWear + dTherm)) * gauss();
    float ae = 22.0f + 18.0f * dChip + 1.8f * (1.0f + 0.5f * dChip) * gauss();
    if (urand() < 0.4f * dChip) ae += urandRange(6.0f, 12.0f);   // 균열 진전 시 AE 히트

    char body[64];
    snprintf(body, sizeof(body), "[%s],%lu,%.3f,%.1f", BOARD_TAG, (unsigned long)seqData++, disp, ae);
    emitLine(body);
}
