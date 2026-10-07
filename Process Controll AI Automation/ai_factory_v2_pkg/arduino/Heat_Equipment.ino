/*
 * 3호기 열처리로(Heat Treatment Furnace) 가상 센서 보드  —  Arduino UNO R4 Minima
 * ---------------------------------------------------------------------------
 * 출력 (2s):  [HEAT],<seq>,<temperature_C>,<carbon_ratio>*<XOR-HEX>
 * 진실값(1Hz): [HEAT_SIM],<seq>,<scenario>,<damage>*<XOR-HEX>
 *
 * 물리 모델: 1차 열용량 모델 + PI 온도 제어 (0.1s 적분)
 *   C·dT/dt = Q_heater - k·(T - 25℃) - 장입 부하,  시정수 τ = C/k = 600s
 *   제어기는 '제어용 열전대'를 보고 850℃ 를 유지, 출력되는 온도는 별도 '감시용 열전대' 값
 *   부품 장입 시 수 ℃ 의 온도 강하가 무작위로 발생하고 제어기가 회복시킨다
 *   탄소 농도: 분위기 탄소 포텐셜 0.425 ± 느린 변동 (기록 전용, 판정 없음)
 *
 * 열화 시나리오 (서서히 진행, REPAIR 전까지 회복 없음)
 *   HEATER_AGING  히터 소선 열화로 최대 출력 감소. 여유가 남아 있는 동안 제어기가 보상해
 *                 온도는 정상으로 보이다가, 장입 후 회복이 점점 느려지고(전조), 출력이 포화되면
 *                 온도가 내려가기 시작 → D=1 에서 평형온도 830℃ (온도 드랍)
 *   TC_DRIFT      제어용 열전대 열화로 실제보다 낮게 지시 → 제어기가 실제 온도를 올림
 *                 → 감시 온도가 서서히 상승, D=1 에서 870℃ (과온도)
 * 명령: SCN <HEATER_AGING|TC_DRIFT> <TTF분> [shape] | AUTO <0|1> [분] | REPAIR | STATUS
 */
#include <Arduino.h>

#define REPORT_MS 2000
#define STEP_MS 100
#define BOARD_TAG "HEAT"

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

enum { SC_NONE = 0, SC_HEATER_AGING, SC_TC_DRIFT, SC_COUNT };
static const char* SC_NAME[SC_COUNT] = {"NORMAL", "HEATER_AGING", "TC_DRIFT"};

static Degradation deg;
static unsigned long lastStepMs = 0, lastReportMs = 0, lastSecMs = 0;
static uint32_t seqData = 0, seqSim = 0;

// 열 모델 상수 (k=1 로 정규화한 출력 단위)
static const float T_AMB = 25.0f, TAU = 600.0f, SETPOINT = 850.0f;
// 정상 소요 출력 = 열손실 825 + 평균 장입 부하 67 = 892
static const float Q_MAX_NEW = 1025.0f;                 // 신품 히터 최대 출력 (여유 15%)
static const float Q_MAX_AT_FAIL = 872.0f;              // D=1 에서 평균 평형온도 830℃ 가 되는 출력
static const float KP = 25.0f, KI = 0.25f;
static float Ttrue = SETPOINT, integ = 892.0f / KI, loadDip = 0, carbon = 0.425f;

static void handleCommand(char* cmd) {
    char out[96];
    char* tok = strtok(cmd, " ");
    if (!tok) return;
    if (!strcmp(tok, "SCN")) {
        char* name = strtok(nullptr, " "); char* ttf = strtok(nullptr, " "); char* shp = strtok(nullptr, " ");
        int s = 0; for (int i = 1; i < SC_COUNT; ++i) if (name && !strcmp(name, SC_NAME[i])) s = i;
        float m = ttf ? (float)atof(ttf) : 0;
        if (!s || m <= 0) { Serial.println("#ERR usage: SCN <HEATER_AGING|TC_DRIFT> <TTF_min> [shape]"); return; }
        deg.start(s, m, shp ? (float)atof(shp) : 1.0f);
        snprintf(out, sizeof(out), "#OK SCN %s ttf=%.1fmin shape=%.2f", SC_NAME[s], m, deg.shape); Serial.println(out);
    } else if (!strcmp(tok, "AUTO")) {
        char* on = strtok(nullptr, " "); char* mean = strtok(nullptr, " ");
        autoMode = on && atoi(on); if (mean) autoMeanMin = (float)atof(mean);
        snprintf(out, sizeof(out), "#OK AUTO %d mean=%.0fmin", autoMode ? 1 : 0, autoMeanMin); Serial.println(out);
    } else if (!strcmp(tok, "REPAIR")) {
        deg.repair(); Serial.println("#OK REPAIR (heater/thermocouple replaced)");
    } else if (!strcmp(tok, "STATUS")) {
        snprintf(out, sizeof(out), "#STATUS %s damage=%.3f elapsed=%.0fs auto=%d T=%.1f", SC_NAME[deg.scenario], deg.damage, deg.elapsed, autoMode ? 1 : 0, Ttrue);
        Serial.println(out);
    } else {
        Serial.println("#HELP SCN <HEATER_AGING|TC_DRIFT> <TTF_min> [shape] | AUTO <0|1> [mean_min] | REPAIR | STATUS");
    }
}

void setup() {
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0 < 1500)) {}
    rngState ^= (uint32_t)analogRead(A2) * 2654435761UL ^ micros();
    if (!rngState) rngState = 1;
    lastStepMs = lastReportMs = lastSecMs = millis();
    Serial.println("#BOOT HEAT virtual sensor ready");
}

static void physicsStep(float dt) {
    float dAge   = deg.scenario == SC_HEATER_AGING ? deg.damage : 0;
    float dDrift = deg.scenario == SC_TC_DRIFT ? deg.damage : 0;
    float qMax = Q_MAX_NEW - (Q_MAX_NEW - Q_MAX_AT_FAIL) * dAge;
    float tcControl = Ttrue - 20.0f * dDrift + 0.3f * gauss();   // 제어용 열전대 (드리프트 시 낮게 지시)
    float e = SETPOINT - tcControl;
    float u = KP * e + KI * integ;
    if (u > qMax) u = qMax; else if (u < 0) u = 0;
    else integ += e * dt;                                        // 포화 시 적분 정지 (anti-windup)
    loadDip *= expf(-dt / 20.0f);                                // 장입 부하는 20s 동안 흡수
    float dTdt = (u - (Ttrue - T_AMB) - loadDip) / TAU;
    Ttrue += dTdt * dt;
}

void loop() {
    if (pollCommand()) handleCommand(cmdBuf);
    unsigned long now = millis();

    while (now - lastStepMs >= STEP_MS) { lastStepMs += STEP_MS; physicsStep(STEP_MS / 1000.0f); }

    if (now - lastSecMs >= 1000) {
        lastSecMs += 1000;
        deg.step(1.0f);
        if (autoMode && deg.scenario == SC_NONE && urand() < 1.0f / (autoMeanMin * 60.0f)) {
            int s = 1 + (int)(urand() * (SC_COUNT - 1)); if (s >= SC_COUNT) s = SC_COUNT - 1;
            deg.start(s, urandRange(15.0f, 45.0f), 1.0f);
            char o[64]; snprintf(o, sizeof(o), "#AUTO start %s ttf=%.1fmin", SC_NAME[s], deg.ttfSec / 60); Serial.println(o);
        }
        if (urand() < 1.0f / 30.0f) loadDip += urandRange(60.0f, 140.0f);   // 평균 30s 마다 부품 장입
        carbon += 0.02f * (0.425f - carbon) + 0.0015f * gauss();
        char body[80];
        snprintf(body, sizeof(body), "[%s_SIM],%lu,%s,%.4f", BOARD_TAG, (unsigned long)seqSim++, SC_NAME[deg.scenario], deg.damage);
        emitLine(body);
    }

    if (now - lastReportMs < REPORT_MS) return;
    lastReportMs += REPORT_MS;
    float tMonitor = Ttrue + 0.4f * gauss();                     // 감시용 열전대
    float cMeas = carbon + 0.003f * gauss();
    char body[64];
    snprintf(body, sizeof(body), "[%s],%lu,%.1f,%.3f", BOARD_TAG, (unsigned long)seqData++, tMonitor, cMeas);
    emitLine(body);
}
