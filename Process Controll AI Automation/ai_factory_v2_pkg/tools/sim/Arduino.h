// ============================================================================
// Host-side Arduino shim: 펌웨어(.ino)를 수정 없이 PC에서 컴파일/실행하기 위한 최소 API
//   - 실시간 모드: socat 가상 시리얼과 연결해 미들웨어/허브를 하드웨어 없이 검증
//   - 가상시간 모드: 수 시간 분량 데이터를 수십 초 만에 생성 (AI 평가용)
// ============================================================================
#pragma once
#include <cstdint>
#include <cstddef>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>

#ifndef PI
#define PI 3.14159265358979323846
#endif
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT 0
#define A0 14
#define A1 15
#define A2 16
#define A3 17
#define F(x) (x)

unsigned long millis();
unsigned long micros();
void delay(unsigned long ms);
void pinMode(int pin, int mode);
void digitalWrite(int pin, int val);
int analogRead(int pin);

class SimSerial {
public:
    void begin(unsigned long) {}
    void setTimeout(unsigned long) {}
    int available();
    int read();
    size_t print(const char* s);
    size_t println(const char* s = "");
    void flush();
    explicit operator bool() const { return true; }
};
extern SimSerial Serial;
