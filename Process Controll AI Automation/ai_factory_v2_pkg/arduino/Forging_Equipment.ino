/*
 * 1호기 압조(Forging) 가상 센서 보드  —  Arduino UNO R4 Minima
 * ---------------------------------------------------------------------------
 * 출력 (1024Hz, 샘플당 1줄):  [FORGING],<seq>,<pressure_ton>,<vibration>*<XOR-HEX>
 * 진실값 (1Hz)            :  [FORGING_SIM],<seq>,<scenario>,<damage>*<XOR-HEX>
 *   - seq 는 줄마다 1씩 증가 → 미들웨어가 누락을 검출
 *   - XOR 체크섬은 '*' 앞 모든 바이트의 XOR → 미들웨어가 손상을 검출
 *   - 불량 판정은 하지 않는다. 판정은 미들웨어가 기준표대로 수행 (실제 센서처럼)
 *
 * 물리 모델 (정상)
 *   진동 = 60Hz 모터 험(0.012) + 120Hz 고조파(0.004) + 광대역 잡음(σ0.02)
 *        + 350Hz 금형 공진 성분 (대역 RMS 약 0.025)
 *   압력 = 50 ton + 유압 맥동/유온 변동(느린 AR, ±0.3) + 측정 잡음(σ0.25)
 *
 * 열화 시나리오 (서서히 진행, 저절로 회복되지 않음 → REPAIR 필요)
 *   DIE_CRACK   금형 균열 성장: 350Hz 대역 RMS 증가, 충격 버스트 빈도 증가
 *               손상도 D=1 에서 대역 RMS 평균 0.8 (설비 파손 위험) 도달
 *   HYD_LEAK    유압 누유/펌프 마모: 압력 평균 하강, 맥동 증가 → D=1 에서 48 ton
 *   VALVE_STICK 릴리프 밸브 고착: 압력 평균 상승, 간헐 스파이크 → D=1 에서 52 ton
 *   손상도 D(t) = (경과/TTF)^shape  (shape>1: 초기엔 느리고 고장 직전 가속, Paris 법칙 유사)
 *   진행 속도 자체도 ±30% 느린 랜덤워크로 흔들려 매번 다르게 진행
 *
 * 명령 (줄 단위, 115200):
 *   SCN <DIE_CRACK|HYD_LEAK|VALVE_STICK> <TTF분> [shape]   시나리오 시작
 *   AUTO <0|1> [평균발생간격분]                             무작위 자동 발생
 *   REPAIR                                                  정비 완료 (손상 0)
 *   STATUS / HELP
 *   응답은 '#' 로 시작 (미들웨어가 데이터로 오인하지 않음)
 */
#include <Arduino.h>

#define SAMPLE_RATE_HZ 1024
#define BOARD_TAG "FORGING"

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

enum { SC_NONE = 0, SC_DIE_CRACK, SC_HYD_LEAK, SC_VALVE_STICK, SC_COUNT };
static const char* SC_NAME[SC_COUNT] = {"NORMAL", "DIE_CRACK", "HYD_LEAK", "VALVE_STICK"};

static Degradation deg;
static unsigned long scheduleOriginUs = 0;
static uint32_t sampleIndex = 0, seqData = 0, seqSim = 0;
static float ph60 = 0, ph120 = 0, ph350 = 0, f350 = 350.0f;
static float pressWander = 0;
static float burstLeft = 0;      // 균열 충격 버스트 남은 시간 [s]
static float spikeLeft = 0;      // 밸브 고착 압력 스파이크 남은 시간 [s]

static void handleCommand(char* cmd) {
    char out[96];
    char* tok = strtok(cmd, " ");
    if (!tok) return;
    if (!strcmp(tok, "SCN")) {
        char* name = strtok(nullptr, " "); char* ttf = strtok(nullptr, " "); char* shp = strtok(nullptr, " ");
        int s = 0; for (int i = 1; i < SC_COUNT; ++i) if (name && !strcmp(name, SC_NAME[i])) s = i;
        float m = ttf ? (float)atof(ttf) : 0;
        if (!s || m <= 0) { Serial.println("#ERR usage: SCN <DIE_CRACK|HYD_LEAK|VALVE_STICK> <TTF_min> [shape]"); return; }
        deg.start(s, m, shp ? (float)atof(shp) : 2.0f);
        snprintf(out, sizeof(out), "#OK SCN %s ttf=%.1fmin shape=%.2f", SC_NAME[s], m, deg.shape); Serial.println(out);
    } else if (!strcmp(tok, "AUTO")) {
        char* on = strtok(nullptr, " "); char* mean = strtok(nullptr, " ");
        autoMode = on && atoi(on); if (mean) autoMeanMin = (float)atof(mean);
        snprintf(out, sizeof(out), "#OK AUTO %d mean=%.0fmin", autoMode ? 1 : 0, autoMeanMin); Serial.println(out);
    } else if (!strcmp(tok, "REPAIR")) {
        deg.repair(); Serial.println("#OK REPAIR (die/hydraulics restored)");
    } else if (!strcmp(tok, "STATUS")) {
        snprintf(out, sizeof(out), "#STATUS %s damage=%.3f elapsed=%.0fs auto=%d", SC_NAME[deg.scenario], deg.damage, deg.elapsed, autoMode ? 1 : 0);
        Serial.println(out);
    } else {
        Serial.println("#HELP SCN <DIE_CRACK|HYD_LEAK|VALVE_STICK> <TTF_min> [shape] | AUTO <0|1> [mean_min] | REPAIR | STATUS");
    }
}

void setup() {
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0 < 1500)) {}
    rngState ^= (uint32_t)analogRead(A0) * 2654435761UL ^ micros();
    if (!rngState) rngState = 1;
    scheduleOriginUs = micros();
    Serial.println("#BOOT FORGING virtual sensor ready");
}

void loop() {
    if (pollCommand()) handleCommand(cmdBuf);

    // 1024Hz 절대 스케줄 (n * 15625/16 us, 누적 오차 없음, micros 래핑 안전)
    unsigned long dueUs = scheduleOriginUs + (unsigned long)(((uint64_t)sampleIndex * 15625ULL) / 16ULL);
    if ((long)(micros() - dueUs) < 0) return;
    sampleIndex++;
    const float dt = 1.0f / SAMPLE_RATE_HZ;

    // ---- 1초마다: 열화 진행, 자동 발생, 진실값 출력 ----
    if (sampleIndex % SAMPLE_RATE_HZ == 0) {
        deg.step(1.0f);
        if (autoMode && deg.scenario == SC_NONE && urand() < 1.0f / (autoMeanMin * 60.0f)) {
            int s = 1 + (int)(urand() * (SC_COUNT - 1)); if (s >= SC_COUNT) s = SC_COUNT - 1;
            deg.start(s, urandRange(15.0f, 45.0f), urandRange(1.5f, 2.5f));
            char o[64]; snprintf(o, sizeof(o), "#AUTO start %s ttf=%.1fmin", SC_NAME[s], deg.ttfSec / 60); Serial.println(o);
        }
        pressWander = 0.98f * pressWander + 0.06f * gauss();          // 유온/맥동에 의한 느린 변동
        pressWander = clampf(pressWander, -0.4f, 0.4f);
        f350 += 0.05f * gauss(); f350 = clampf(f350, 347, 353);  // 공진 주파수 미세 이동
        float dCrack = deg.scenario == SC_DIE_CRACK ? deg.damage : 0;
        float dValve = deg.scenario == SC_VALVE_STICK ? deg.damage : 0;
        if (burstLeft <= 0 && urand() < 0.35f * dCrack) burstLeft = urandRange(0.15f, 0.5f);  // 균열 충격음
        if (spikeLeft <= 0 && urand() < 0.25f * dValve) spikeLeft = urandRange(0.1f, 0.3f);    // 밸브 채터링
        char body[80];
        snprintf(body, sizeof(body), "[%s_SIM],%lu,%s,%.4f", BOARD_TAG, (unsigned long)seqSim++, SC_NAME[deg.scenario], deg.damage);
        emitLine(body);
    }

    // ---- 진동 파형 ----
    ph60  += 2.0f * (float)PI * 60.0f  * dt; if (ph60  > 2 * PI) ph60  -= 2 * (float)PI;
    ph120 += 2.0f * (float)PI * 120.0f * dt; if (ph120 > 2 * PI) ph120 -= 2 * (float)PI;
    ph350 += 2.0f * (float)PI * f350   * dt; if (ph350 > 2 * PI) ph350 -= 2 * (float)PI;
    float dCrack = deg.scenario == SC_DIE_CRACK ? deg.damage : 0;
    float bandRms = 0.025f + 0.775f * dCrack;                        // D=1 → 0.8 RMS
    if (burstLeft > 0) { bandRms *= 1.35f; burstLeft -= dt; }
    float vib = 0.012f * sinf(ph60) + 0.004f * sinf(ph120)
              + 1.41421356f * bandRms * sinf(ph350)
              + 0.02f * gauss();

    // ---- 압력 ----
    float dLeak  = deg.scenario == SC_HYD_LEAK ? deg.damage : 0;
    float dValve = deg.scenario == SC_VALVE_STICK ? deg.damage : 0;
    float press = 50.0f + pressWander - 2.0f * dLeak + 2.0f * dValve
                + (0.25f + 0.35f * dLeak + 0.2f * dValve) * gauss();
    if (spikeLeft > 0) { press += 1.5f * dValve; spikeLeft -= dt; }

    char body[64];
    snprintf(body, sizeof(body), "[%s],%lu,%.2f,%.4f", BOARD_TAG, (unsigned long)seqData++, press, vib);
    emitLine(body);
}
