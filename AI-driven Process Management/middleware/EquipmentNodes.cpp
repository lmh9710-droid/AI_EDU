#include "EquipmentNodes.h"

// ==========================================
// 1호기 압조 설비 소스코드
// ==========================================
ForgingNode::ForgingNode(std::string port, std::string id, std::shared_ptr<DatabaseManager> db)
    : BaseEquipment(port, id, db) {}

void ForgingNode::cooleyTukeyFFT(std::vector<std::complex<double>>& buffer) {
    int n = buffer.size(); if (n <= 1) return;
    std::vector<std::complex<double>> even(n / 2), odd(n / 2);
    for (int i = 0; i < n / 2; i++) {
        even[i] = buffer[2 * i]; odd[i] = buffer[2 * i + 1];
    }
    cooleyTukeyFFT(even); cooleyTukeyFFT(odd);
    for (int i = 0; i < n / 2; i++) {
        std::complex<double> t = std::polar(1.0, -2 * PI * i / n) * odd[i];
        buffer[i] = even[i] + t; buffer[i + n / 2] = even[i] - t;
    }
}

void ForgingNode::processAndInsert(double pressure, double fft_energy, const std::string& status) {
    std::lock_guard<std::mutex> lock(db_mutex);
    sqlite3* db = db_mgr->getRawConnection(); if (!db) return;
    const char* sql = "INSERT INTO tb_forging_telemetry (timestamp, pressure, defect_band_energy, status) VALUES (?, ?, ?, ?);";
    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        std::string ts = get_precise_timestamp();
        sqlite3_bind_text(stmt, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(stmt, 2, pressure);
        sqlite3_bind_double(stmt, 3, fft_energy);
        sqlite3_bind_text(stmt, 4, status.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);

        // /* [실시간 콘솔 출력] */
        std::cout << "[1호기 압조 적재] 타입스탬프: " << ts
                  << "| 압력: "<< pressure << "Ton"
                  << "| 350Hz 진동에너지: " << fft_energy
                  << "| 상태: " << status << "\n";
    }
    sqlite3_finalize(stmt); sqlite3_close(db);
}

void ForgingNode::startCaptureLoop() {
    serial_fd = configureSerial(); if (serial_fd < 0) return;
    std::cout << "🚀 [FORGING NODE ACTIVE] -> " << port_path << "\n";
    std::string line_buffer = ""; char ch;
    while (system_active) {
        if (read(serial_fd, &ch, 1) > 0) {
            if (ch == '\n' || ch == '\r') {
                if (!line_buffer.empty()) {
                    std::stringstream ss(line_buffer); std::string item; std::vector<std::string> tokens;
                    while (std::getline(ss, item, ',')) tokens.push_back(item);
                    
                    // 패킷 예시: [FORGING], 49.5, 0.1234, OK
                    if (tokens.size() >= 4) {
                        double pressure = SafeStod(tokens[1]); // 안전하게 1번 방 변환
                        double raw_vibe = SafeStod(tokens[2]); // 안전하게 2번 방 변환
                        std::string status = tokens[3];

                        // std::cout<< "[1호기 원시 신호] 입력:" << pressure << " Ton | 원시진동(시간축): " << raw_vibe << "\n";

                        vibration_window.push_back(raw_vibe);
                        if (vibration_window.size() >= SAMPLING_RATE) {
                            std::vector<std::complex<double>> fft_buf(SAMPLING_RATE);
                            for (int i = 0; i < SAMPLING_RATE; i++) fft_buf[i] = std::complex<double>(vibration_window[i], 0.0);
                            cooleyTukeyFFT(fft_buf);
                            
                            double band_sum = 0.0; int count = 0;
                            for (int i = 0; i < SAMPLING_RATE / 2; i++) {
                                if (i >= 340 && i <= 360) { band_sum += std::abs(fft_buf[i]) / SAMPLING_RATE; count++; }
                            }
                            double energy = band_sum / (count > 0 ? count : 1);
                            processAndInsert(pressure, energy, status);
                            
                            if (energy > 0.8) {
                                std::lock_guard<std::mutex> lock(interlock_mutex);
                                interlock_cmd_queue.push("CMD_ESTOP"); interlock_cv.notify_one();
                            }
                            vibration_window.clear();
                        }
                    }
                    line_buffer.clear();
                }
            } else { line_buffer += ch; }
        }
    }
}

// ==========================================
// 2호기 전조 설비 소스코드
// ==========================================
RollingNode::RollingNode(std::string port, std::string id, std::shared_ptr<DatabaseManager> db)
    : BaseEquipment(port, id, db) {}

void RollingNode::insert(double disp, double ae, const std::string& status) {
    std::lock_guard<std::mutex> lock(db_mutex);
    sqlite3* db = db_mgr->getRawConnection(); if (!db) return;
    const char* sql = "INSERT INTO tb_rolling_telemetry (timestamp, displacement, ae_signal, status) VALUES (?, ?, ?, ?);";
    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        std::string ts = get_precise_timestamp();
        sqlite3_bind_text(stmt, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(stmt, 2, disp);
        sqlite3_bind_double(stmt, 3, ae);
        sqlite3_bind_text(stmt, 4, status.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);

        /* [실시간 콘솔 출력] 2호기 전조 설비 모니터링 로그 */
        std::cout << " [2호기 전조 적재] 타임스탬프: " << ts 
                  << " | 금형변위: " << disp << " mm"
                  << " | 초음파AE: " << ae << " dB"
                  << " | 상태: " << status << "\n";
    
    }
    sqlite3_finalize(stmt); sqlite3_close(db);
}

void RollingNode::startCaptureLoop() {
    serial_fd = configureSerial(); if (serial_fd < 0) return;
    std::cout << "🚀 [ROLLING NODE ACTIVE] -> " << port_path << "\n";
    std::string line_buffer = ""; char ch;
    while (system_active) {
        if (read(serial_fd, &ch, 1) > 0) {
            if (ch == '\n' || ch == '\r') {
                if (!line_buffer.empty()) {
                    std::stringstream ss(line_buffer); std::string item; std::vector<std::string> tokens;
                    while (std::getline(ss, item, ',')) tokens.push_back(item);
                    
                    // 패킷 예시: [ROLLING], 1.20, 21, OK
                    if (tokens.size() >= 4) {
                        double disp = SafeStod(tokens[1]);
                        double ae   = SafeStod(tokens[2]);
                        insert(disp, ae, tokens[3]);
                    }
                    line_buffer.clear();
                }
            } else { line_buffer += ch; }
        }
    }
}

// ==========================================
// 3호기 열처리 설비 소스코드
// ==========================================
HeatNode::HeatNode(std::string port, std::string id, std::shared_ptr<DatabaseManager> db)
    : BaseEquipment(port, id, db) {}

void HeatNode::insert(double temp, double carbon, const std::string& status) {
    std::lock_guard<std::mutex> lock(db_mutex);
    sqlite3* db = db_mgr->getRawConnection(); if (!db) return;
    const char* sql = "INSERT INTO tb_heat_telemetry (timestamp, temperature, carbon_ratio, status) VALUES (?, ?, ?, ?);";
    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        std::string ts = get_precise_timestamp();
        sqlite3_bind_text(stmt, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(stmt, 2, temp);
        sqlite3_bind_double(stmt, 3, carbon);
        sqlite3_bind_text(stmt, 4, status.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);

        std::cout << " [3호기 열처리 적재] 타임스탬프: " << ts 
                  << " | 노내온도: " << temp << " ℃"
                  << " | 탄소농도: " << carbon << " %"
                  << " | 상태: " << status << "\n";
    }
    sqlite3_finalize(stmt); sqlite3_close(db);
}

void HeatNode::startCaptureLoop() {
    serial_fd = configureSerial(); if (serial_fd < 0) return;
    std::cout << "🚀 [HEAT NODE ACTIVE]    -> " << port_path << "\n";
    std::string line_buffer = ""; char ch;
    while (system_active) {
        if (read(serial_fd, &ch, 1) > 0) {
            if (ch == '\n' || ch == '\r') {
                if (!line_buffer.empty()) {
                    std::stringstream ss(line_buffer); std::string item; std::vector<std::string> tokens;
                    while (std::getline(ss, item, ',')) tokens.push_back(item);
                    
                    // 패킷 예시: [HEAT], 850.4, 0.42, OK
                    if (tokens.size() >= 4) {
                        double temp   = SafeStod(tokens[1]);
                        double carbon = SafeStod(tokens[2]);
                        insert(temp, carbon, tokens[3]);
                    }
                    line_buffer.clear();
                }
            } else { line_buffer += ch; }
        }
    }
}

// ==========================================
// 4호기 컨베이어 및 인터록 코어
// ==========================================
ConveyorInterlockResponder::ConveyorInterlockResponder(std::string port) : port_path(port), serial_fd(-1) {}
ConveyorInterlockResponder::~ConveyorInterlockResponder() { if (serial_fd >= 0) close(serial_fd); }

int ConveyorInterlockResponder::configureSerial() {
    int fd = open(port_path.c_str(), O_RDWR | O_NOCTTY);
    if (fd < 0) return -1;
    struct termios tty; if (tcgetattr(fd, &tty) != 0) return -1;
    cfsetospeed(&tty, B115200); cfsetispeed(&tty, B115200);
    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8; tty.c_lflag = 0; tty.c_oflag = 0;
    tty.c_iflag &= ~(IXON | IXOFF | IXANY); tty.c_cc[VMIN] = 1; tty.c_cc[VTIME] = 1;
    tty.c_cflag |= (CLOCAL | CREAD); tty.c_cflag &= ~(PARENB | PARODD | CSTOPB | CRTSCTS);
    if (tcsetattr(fd, TCSANOW, &tty) != 0) return -1;
    return fd;
}

void ConveyorInterlockResponder::startListening() {
    serial_fd = configureSerial(); if (serial_fd < 0) return;
    std::cout << "🔒 [INTERLOCK HUB ACTIVE] -> " << port_path << "\n";
    while (system_active) {
        std::unique_lock<std::mutex> lock(interlock_mutex);
        interlock_cv.wait(lock, [] { return !interlock_cmd_queue.empty() || !system_active; });
        if (!interlock_cmd_queue.empty()) {
            std::string cmd = interlock_cmd_queue.front(); interlock_cmd_queue.pop();
            std::string packet = cmd + "\n";
            write(serial_fd, packet.c_str(), packet.length());
            std::cout << "🎯 [INTERLOCK EMITTED] 4호기 마스터보드로 제어명령 발송: " << cmd << "\n";
        }
    }
}
