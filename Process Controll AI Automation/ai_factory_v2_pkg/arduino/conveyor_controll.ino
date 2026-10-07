/*
 * 4호기 컨베이어 마스터 제어 보드  —  Arduino UNO R4 Minima
 * ---------------------------------------------------------------------------
 * 명령은 Rust 인터록 허브만 보낸다. 모든 명령에 ID 가 붙고 즉시 ACK 로 응답한다.
 *   CMD_STOP,<id>    라인 정지 (AI 불량 예측 / 워치독)              → STOPPED
 *   CMD_DEFECT,<id>  라인 정지 후 퇴출 (실측 불량)
 *                    모터 정지 → 벨트 관성 정지 대기 0.5s → 에어 솔레노이드 0.3s 분사 → STOPPED
 *                    이미 STOPPED 이면 정지 상태에서 바로 퇴출만 수행
 *   CMD_WARN,<id>    경고등 점등 (위험 경고), 라인은 계속 가동. RESET 시 소등
 *   CMD_RESET,<id>   작업자 재가동 (퇴출 동작 중에는 거부)
 *   CMD_PING,<id>    상태 확인
 * 응답:   ACK,<id>,<CMD>,<STATE>   /   NAK,<id>,<reason>
 *         같은 ID 재전송(ACK 유실 시 허브 재시도)은 실행하지 않고 ACK 만 다시 보낸다
 * 상태 보고 (1Hz): [CONVEYOR],<seq>,<STATE>,<warn 0|1>,<eject_count>*<XOR-HEX>
 * STATE: RUNNING | STOPPING | EJECTING | STOPPED
 */
#include <Arduino.h>

#define PIN_CONVEYOR_MOTOR 8   // 컨베이어 모터/인버터 운전 릴레이
#define PIN_AIR_REJECTOR   9   // 불량 퇴출 에어 솔레노이드
#define PIN_WARN_LAMP      10  // 경고등 (위험 경고)

const unsigned long COAST_STOP_MS   = 500;   // 모터 정지 후 벨트가 멈출 때까지
const unsigned long REJECTOR_ON_MS  = 300;   // 솔레노이드 분사 시간

enum State { RUNNING, STOPPING, EJECTING, STOPPED };
static const char* STATE_NAME[] = {"RUNNING", "STOPPING", "EJECTING", "STOPPED"};
static State state = RUNNING;
static bool warnLamp = false, ejectPending = false;
static unsigned long phaseStartMs = 0, lastReportMs = 0;
static uint32_t seq = 0, ejectCount = 0;

static char cmdBuf[48]; static uint8_t cmdLen = 0;
static bool pollCommand() {
    while (Serial.available() > 0) {
        int c = Serial.read(); if (c < 0) break;
        if (c == '\n' || c == '\r') { if (cmdLen) { cmdBuf[cmdLen] = 0; cmdLen = 0; return true; } }
        else if (cmdLen < sizeof(cmdBuf) - 1) cmdBuf[cmdLen++] = (char)c;
    }
    return false;
}
static void emitLine(char* body) {
    uint8_t cs = 0; for (char* p = body; *p; ++p) cs ^= (uint8_t)*p;
    size_t n = strlen(body); snprintf(body + n, 6, "*%02X", cs);
    Serial.println(body);
}
static char lastId[12] = "";     // 허브가 ACK 유실로 같은 ID 를 재전송해도 중복 실행하지 않음
static void ack(const char* id, const char* cmd) {
    strncpy(lastId, id, sizeof(lastId) - 1);   // 실행 완료(ACK)된 ID 만 기억 (NAK 은 재시도 허용)
    char o[64]; snprintf(o, sizeof(o), "ACK,%s,%s,%s", id, cmd, STATE_NAME[state]); Serial.println(o);
}
static void nak(const char* id, const char* why) {
    char o[64]; snprintf(o, sizeof(o), "NAK,%s,%s", id, why); Serial.println(o);
}
static void motor(bool on) { digitalWrite(PIN_CONVEYOR_MOTOR, on ? HIGH : LOW); }

static void beginStop(bool withEject) {
    if (state == RUNNING) {
        motor(false);
        state = STOPPING; phaseStartMs = millis();
        ejectPending = withEject;
    } else if (state == STOPPING) {
        ejectPending = ejectPending || withEject;
    } else if (state == STOPPED && withEject) {
        state = EJECTING; phaseStartMs = millis();
        digitalWrite(PIN_AIR_REJECTOR, HIGH);
    }
    // EJECTING 중이면 이미 퇴출 진행 중
}

static void handleCommand(char* line) {
    char* cmd = strtok(line, ",");
    char* id = strtok(nullptr, ",");
    if (!cmd) return;
    if (!id) id = (char*)"0";
    if (strcmp(id, "0") != 0 && !strcmp(id, lastId)) { ack(id, cmd); return; }
    if (!strcmp(cmd, "CMD_STOP"))        { beginStop(false); ack(id, cmd); }
    else if (!strcmp(cmd, "CMD_DEFECT")) { beginStop(true);  ack(id, cmd); }
    else if (!strcmp(cmd, "CMD_WARN"))   { warnLamp = true; digitalWrite(PIN_WARN_LAMP, HIGH); ack(id, cmd); }
    else if (!strcmp(cmd, "CMD_RESET")) {
        if (state == EJECTING || state == STOPPING) { nak(id, "BUSY_EJECTING"); return; }
        state = RUNNING; ejectPending = false; motor(true);
        warnLamp = false; digitalWrite(PIN_WARN_LAMP, LOW);
        ack(id, cmd);
    }
    else if (!strcmp(cmd, "CMD_PING"))   { ack(id, cmd); }
    else nak(id, "UNKNOWN_CMD");
}

void setup() {
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0 < 1500)) {}
    pinMode(PIN_CONVEYOR_MOTOR, OUTPUT); pinMode(PIN_AIR_REJECTOR, OUTPUT); pinMode(PIN_WARN_LAMP, OUTPUT);
    digitalWrite(PIN_AIR_REJECTOR, LOW); digitalWrite(PIN_WARN_LAMP, LOW);
    motor(true);
    lastReportMs = millis();
    Serial.println("#BOOT CONVEYOR master online, RUNNING");
}

void loop() {
    if (pollCommand()) handleCommand(cmdBuf);
    unsigned long now = millis();

    if (state == STOPPING && now - phaseStartMs >= COAST_STOP_MS) {
        if (ejectPending) {
            state = EJECTING; phaseStartMs = now; ejectPending = false;
            digitalWrite(PIN_AIR_REJECTOR, HIGH);
            Serial.println("#EVENT belt stopped -> ejecting defect");
        } else {
            state = STOPPED;
            Serial.println("#EVENT belt stopped (line stop)");
        }
    } else if (state == EJECTING && now - phaseStartMs >= REJECTOR_ON_MS) {
        digitalWrite(PIN_AIR_REJECTOR, LOW);
        state = STOPPED; ejectCount++;
        Serial.println("#EVENT defect ejected, line held STOPPED (operator RESET required)");
    }

    if (now - lastReportMs >= 1000) {
        lastReportMs += 1000;
        char body[64];
        snprintf(body, sizeof(body), "[CONVEYOR],%lu,%s,%d,%lu", (unsigned long)seq++, STATE_NAME[state], warnLamp ? 1 : 0, (unsigned long)ejectCount);
        emitLine(body);
    }
}
