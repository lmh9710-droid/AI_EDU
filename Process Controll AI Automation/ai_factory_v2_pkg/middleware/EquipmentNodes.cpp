#include "EquipmentNodes.h"
#include <iomanip>

// =====================================================================
// 1호기 압조: 1024Hz 원시 진동 → 1초 윈도우 FFT → 350Hz 대역(340~360Hz) RMS
// =====================================================================
ForgingNode::ForgingNode(std::string port, std::shared_ptr<DatabaseManager> d, std::shared_ptr<HubClient> h)
    : BaseEquipment(port, "EQ_FORGING_01", "FORGING", d, h),
      vib(SAMPLING_RATE, 0.0), press(SAMPLING_RATE, 0.0), filled(SAMPLING_RATE, 0),
      storeRaw(getenv_or("SF_STORE_RAW", "0") == "1") {}

void ForgingNode::fft(std::vector<std::complex<double>>& a) {      // 반복형 radix-2 Cooley-Tukey
    const size_t n = a.size();
    for (size_t i = 1, j = 0; i < n; ++i) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (size_t len = 2; len <= n; len <<= 1) {
        std::complex<double> wl = std::polar(1.0, -2.0 * PI / (double)len);
        for (size_t i = 0; i < n; i += len) {
            std::complex<double> w(1.0, 0.0);
            for (size_t k = 0; k < len / 2; ++k) {
                auto u = a[i + k], v = a[i + k + len / 2] * w;
                a[i + k] = u + v; a[i + k + len / 2] = u - v; w *= wl;
            }
        }
    }
}

void ForgingNode::onData(const std::vector<std::string>& f, uint32_t seq) {
    double p, v;
    if (f.size() < 4 || !parse_double(f[2], p) || !parse_double(f[3], v)) { corrupt++; return; }
    int64_t widx = seq / SAMPLING_RATE; int pos = seq % SAMPLING_RATE;
    if (windowIdx < 0) { windowIdx = widx; firstWindow = (pos != 0); }
    if (widx > windowIdx) {                      // 이전 윈도우 마지막 샘플이 누락된 경우
        finalizeWindow();
        windowIdx = widx;
    }
    vib[pos] = v; press[pos] = p; filled[pos] = 1;
    if (pos == SAMPLING_RATE - 1) { finalizeWindow(); windowIdx = widx + 1; }
}

void ForgingNode::finalizeWindow() {
    int count = 0; for (auto x : filled) count += x;
    bool skip = firstWindow;                     // 연결 직후 중간부터 시작한 윈도우는 버림
    firstWindow = false;
    if (skip || count == 0) { std::fill(filled.begin(), filled.end(), 0); return; }

    // 누락 샘플은 직전 값 유지(hold)로 채움. 누락이 많으면 판정 보류.
    double pSum = 0, pMin = 1e9, pMax = -1e9, last = 0; int firstIdx = -1;
    for (int i = 0; i < SAMPLING_RATE; ++i) if (filled[i]) { firstIdx = i; last = vib[i]; break; }
    std::vector<std::complex<double>> buf(SAMPLING_RATE);
    for (int i = 0; i < SAMPLING_RATE; ++i) {
        if (filled[i]) {
            last = vib[i]; pSum += press[i];
            pMin = std::min(pMin, press[i]); pMax = std::max(pMax, press[i]);
        }
        buf[i] = std::complex<double>(i < firstIdx ? vib[firstIdx] : last, 0.0);
    }
    std::vector<float> raw; if (storeRaw) { raw.resize(SAMPLING_RATE); for (int i = 0; i < SAMPLING_RATE; ++i) raw[i] = (float)buf[i].real(); }
    fft(buf);
    double sumsq = 0;
    for (int k = Spec::FORGING_BAND_LOW_HZ; k <= Spec::FORGING_BAND_HIGH_HZ; ++k) sumsq += std::norm(buf[k]);
    double rms = std::sqrt(2.0 * sumsq) / SAMPLING_RATE;      // 파스발: 대역 성분의 실효값(RMS)
    double pMean = pSum / count;
    int lostSamples = SAMPLING_RATE - count;

    std::vector<std::string> codes;
    bool judged = lostSamples <= SAMPLING_RATE / 10;            // 10% 초과 누락 시 판정 보류
    if (!judged) codes.push_back("DATA_LOSS");
    else {
        if (pMean < Spec::FORGING_PRESSURE_LOW)  codes.push_back("NG_PRESSURE_LOW");
        if (pMean > Spec::FORGING_PRESSURE_HIGH) codes.push_back("NG_PRESSURE_HIGH");
        if (rms >= Spec::FORGING_VIBE_CRITICAL)  codes.push_back("NG_VIBE_CRITICAL");
        else if (rms >= Spec::FORGING_VIBE_WARN) codes.push_back("WARN_VIBE");
    }
    std::string status = joinCodes(codes), ts = get_precise_timestamp();
    int64_t seqFirst = windowIdx * SAMPLING_RATE;
    db->enqueue([=](sqlite3* d) {
        DatabaseManager::execStmt(d,
            "INSERT INTO tb_forging_telemetry (timestamp, pressure, defect_band_energy, status, seq_first, samples, lost_samples, pressure_min, pressure_max, raw_waveform) VALUES (?,?,?,?,?,?,?,?,?,?);",
            [&](sqlite3_stmt* st) {
                sqlite3_bind_text(st, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_double(st, 2, pMean);
                sqlite3_bind_double(st, 3, rms);
                sqlite3_bind_text(st, 4, status.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_int64(st, 5, seqFirst);
                sqlite3_bind_int(st, 6, count);
                sqlite3_bind_int(st, 7, lostSamples);
                sqlite3_bind_double(st, 8, pMin);
                sqlite3_bind_double(st, 9, pMax);
                if (raw.empty()) sqlite3_bind_null(st, 10);
                else sqlite3_bind_blob(st, 10, raw.data(), (int)(raw.size() * sizeof(float)), SQLITE_TRANSIENT);
            });
    });
    std::cout << "[1호기 압조] " << ts << " | 압력 " << std::fixed << std::setprecision(2) << pMean << " ton"
              << " | 350Hz 대역 RMS " << std::setprecision(4) << rms
              << " | 샘플 " << count << "/1024 | " << status << "\n" << std::defaultfloat;

    if (judged) {
        if (pMean < Spec::FORGING_PRESSURE_LOW)  reportDefect("NG_PRESSURE_LOW", pMean, "pressure < 48 ton (압력 낮음)");
        if (pMean > Spec::FORGING_PRESSURE_HIGH) reportDefect("NG_PRESSURE_HIGH", pMean, "pressure > 52 ton (압력 높음)");
        if (rms >= Spec::FORGING_VIBE_CRITICAL)  reportDefect("NG_VIBE_CRITICAL", rms, "350Hz band RMS >= 0.8 (설비 파손 위험)");
        else if (rms >= Spec::FORGING_VIBE_WARN) reportWarn("WARN_VIBE", rms, "0.4 <= 350Hz band RMS < 0.8 (위험 경고)");
        else clearWarn();
    }
    std::fill(filled.begin(), filled.end(), 0);
}

// =====================================================================
// 2호기 전조: 부품 1개 = 1 레코드
// =====================================================================
void RollingNode::onData(const std::vector<std::string>& f, uint32_t seq) {
    double disp, ae;
    if (f.size() < 4 || !parse_double(f[2], disp) || !parse_double(f[3], ae)) { corrupt++; return; }
    std::vector<std::string> codes;
    if (disp < Spec::ROLLING_DISP_MIN) codes.push_back("NG_UNDER_MOLDING");
    if (disp > Spec::ROLLING_DISP_MAX) codes.push_back("NG_OVER_MOLDING");
    if (ae > Spec::ROLLING_AE_MAX)     codes.push_back("NG_AE_FAULT");
    std::string status = joinCodes(codes), ts = get_precise_timestamp();
    db->enqueue([=](sqlite3* d) {
        DatabaseManager::execStmt(d, "INSERT INTO tb_rolling_telemetry (timestamp, displacement, ae_signal, status, seq) VALUES (?,?,?,?,?);",
            [&](sqlite3_stmt* st) {
                sqlite3_bind_text(st, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_double(st, 2, disp); sqlite3_bind_double(st, 3, ae);
                sqlite3_bind_text(st, 4, status.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_int64(st, 5, seq);
            });
    });
    std::cout << " [2호기 전조] " << ts << " | 금형변위 " << disp << " mm | 초음파AE " << ae << " dB | " << status << "\n";
    if (disp < Spec::ROLLING_DISP_MIN) reportDefect("NG_UNDER_MOLDING", disp, "displacement < 3.95 mm (미성형)");
    if (disp > Spec::ROLLING_DISP_MAX) reportDefect("NG_OVER_MOLDING", disp, "displacement > 4.05 mm (과성형)");
    if (ae > Spec::ROLLING_AE_MAX)     reportDefect("NG_AE_FAULT", ae, "ae_signal > 40 dB (초음파 불량)");
}

// =====================================================================
// 3호기 열처리: 온도만 판정, 탄소 농도는 기록 전용
// =====================================================================
void HeatNode::onData(const std::vector<std::string>& f, uint32_t seq) {
    double temp, carbon;
    if (f.size() < 4 || !parse_double(f[2], temp) || !parse_double(f[3], carbon)) { corrupt++; return; }
    std::vector<std::string> codes;
    if (temp < Spec::HEAT_TEMP_MIN) codes.push_back("NG_TEMP_DROP");
    if (temp > Spec::HEAT_TEMP_MAX) codes.push_back("NG_OVER_HEAT");
    std::string status = joinCodes(codes), ts = get_precise_timestamp();
    db->enqueue([=](sqlite3* d) {
        DatabaseManager::execStmt(d, "INSERT INTO tb_heat_telemetry (timestamp, temperature, carbon_ratio, status, seq) VALUES (?,?,?,?,?);",
            [&](sqlite3_stmt* st) {
                sqlite3_bind_text(st, 1, ts.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_double(st, 2, temp); sqlite3_bind_double(st, 3, carbon);
                sqlite3_bind_text(st, 4, status.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_int64(st, 5, seq);
            });
    });
    std::cout << " [3호기 열처리] " << ts << " | 노내온도 " << temp << " ℃ | 탄소농도 " << carbon << " (기록) | " << status << "\n";
    if (temp < Spec::HEAT_TEMP_MIN) reportDefect("NG_TEMP_DROP", temp, "temperature < 830 C (온도 드랍)");
    if (temp > Spec::HEAT_TEMP_MAX) reportDefect("NG_OVER_HEAT", temp, "temperature > 870 C (과온도)");
}
