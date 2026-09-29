#pragma once
#include "BaseEquipment.h"

class ForgingNode : public BaseEquipment {
private:
    std::vector<double> vibration_window;
    void cooleyTukeyFFT(std::vector<std::complex<double>>& buffer);
    void processAndInsert(double pressure, double fft_energy, const std::string& status);
public:
    ForgingNode(std::string port, std::string id, std::shared_ptr<DatabaseManager> db);
    void startCaptureLoop() override;
};

class RollingNode : public BaseEquipment {
private:
    void insert(double disp, double ae, const std::string& status);
public:
    RollingNode(std::string port, std::string id, std::shared_ptr<DatabaseManager> db);
    void startCaptureLoop() override;
};

class HeatNode : public BaseEquipment {
private:
    void insert(double temp, double carbon, const std::string& status);
public:
    HeatNode(std::string port, std::string id, std::shared_ptr<DatabaseManager> db);
    void startCaptureLoop() override;
};

class ConveyorInterlockResponder {
private:
    std::string port_path;
    int serial_fd;
    int configureSerial();
public:
    ConveyorInterlockResponder(std::string port);
    ~ConveyorInterlockResponder();
    void startListening();
};
