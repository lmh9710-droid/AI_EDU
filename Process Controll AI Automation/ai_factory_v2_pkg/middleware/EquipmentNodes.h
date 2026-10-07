#pragma once
#include "BaseEquipment.h"

class ForgingNode : public BaseEquipment {
    // 1024 샘플(1초) 윈도우를 seq 번호로 정렬해 조립 → 누락 샘플을 정확히 집계
    std::vector<double> vib, press; std::vector<uint8_t> filled;
    int64_t windowIdx = -1; bool firstWindow = true; bool storeRaw;
    void finalizeWindow();
    static void fft(std::vector<std::complex<double>>& a);
protected:
    void onData(const std::vector<std::string>& f, uint32_t seq) override;
    void onResync() override { windowIdx = -1; firstWindow = true; std::fill(filled.begin(), filled.end(), 0); }
public:
    ForgingNode(std::string port, std::shared_ptr<DatabaseManager> d, std::shared_ptr<HubClient> h);
};

class RollingNode : public BaseEquipment {
protected:
    void onData(const std::vector<std::string>& f, uint32_t seq) override;
public:
    RollingNode(std::string port, std::shared_ptr<DatabaseManager> d, std::shared_ptr<HubClient> h)
        : BaseEquipment(port, "EQ_ROLLING_01", "ROLLING", d, h) {}
};

class HeatNode : public BaseEquipment {
protected:
    void onData(const std::vector<std::string>& f, uint32_t seq) override;
public:
    HeatNode(std::string port, std::shared_ptr<DatabaseManager> d, std::shared_ptr<HubClient> h)
        : BaseEquipment(port, "EQ_HEAT_01", "HEAT", d, h) {}
};
