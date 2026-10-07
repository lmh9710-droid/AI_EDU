#include "inspection.hpp"

#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <iostream>
#include <sstream>

namespace mfg {

// =============================================================================
//  Inspector : OK / NG 판정
// =============================================================================
Inspector::Inspector(const cv::Rect& roi, std::set<int> defectIds, int minBoxArea,
                     std::set<int> okIds)
    : roi_(roi), defectIds_(std::move(defectIds)), minBoxArea_(minBoxArea), okIds_(std::move(okIds)) {}

cv::Rect Inspector::effectiveRoi(const cv::Size& frameSize) const {
    const cv::Rect full(0, 0, frameSize.width, frameSize.height);
    if (roi_.area() <= 0) return full;
    const cv::Rect r = roi_ & full;  // 화면 밖으로 나간 부분 잘라내기
    return r.area() > 0 ? r : full;
}

InspectionResult Inspector::judge(const std::vector<Detection>& dets,
                                  const cv::Size& frameSize) const {
    InspectionResult res;
    const cv::Rect roi = effectiveRoi(frameSize);

    for (const auto& d : dets) {
        // 1) 너무 작은 박스는 노이즈로 간주
        if (d.box.area() < minBoxArea_) continue;

        // 2) 박스 중심이 ROI 안에 있어야 유효 (컨베이어 가장자리 오검출 방지)
        const cv::Point center(d.box.x + d.box.width / 2, d.box.y + d.box.height / 2);
        if (!roi.contains(center)) continue;

        res.detections.push_back(d);
        res.countPerClass[d.classId]++;

        // 3) 불량 클래스 여부
        const bool isDefect = defectIds_.empty() || defectIds_.count(d.classId) > 0;
        if (isDefect) res.defects.push_back(d);
    }

    // 불량이 하나라도 있으면 NG
    // ※ '부품 누락 검사'처럼 반대 로직이 필요하면 여기를 수정하세요.
    //    예) 나사가 4개 검출되어야 OK → res.ok = (res.countPerClass[screwId] == 4);
    res.ok = res.defects.empty();
    return res;
}

InspectionResult Inspector::judgeClassification(const std::vector<Classification>& topk,
                                                const cv::Rect& roi, float confThreshold) const {
    InspectionResult res;
    res.topk = topk;
    if (topk.empty()) return res;

    const Classification& top1 = topk.front();
    res.countPerClass[top1.classId] = 1;

    bool ng;
    if (!okIds_.empty()) {
        // 적극 판정: "양품이라고 확신할 때만 OK". 불량 클래스·확신 부족·부품 없음 → 모두 NG
        ng = !(okIds_.count(top1.classId) > 0 && top1.score >= confThreshold);
    } else {
        // 기존 방식: 불량 클래스를 확신할 때만 NG (애매하면 OK 로 통과되므로 품질 검사엔 비권장)
        ng = !defectIds_.empty() && defectIds_.count(top1.classId) > 0 && top1.score >= confThreshold;
    }
    if (ng) {
        Detection d;            // 분류는 위치가 없으므로 검사 영역(ROI) 전체를 박스로 기록
        d.classId    = top1.classId;
        d.confidence = top1.score;
        d.box        = roi;
        res.defects.push_back(d);
    }
    res.ok = res.defects.empty();
    return res;
}

// =============================================================================
//  CsvLogger : 검사 이력 저장
// =============================================================================
bool CsvLogger::open(const std::string& path) {
    ofs_.open(path, std::ios::out | std::ios::binary);
    if (!ofs_) {
        std::cerr << "[경고] CSV 로그 파일을 만들 수 없습니다: " << path << "\n";
        return false;
    }
    ofs_ << "\xEF\xBB\xBF";  // UTF-8 BOM (엑셀 한글 깨짐 방지)
    ofs_ << "timestamp,frame,result,defect_count,detections,infer_ms,image\n";
    std::cout << "[로그] " << path << "\n";
    return true;
}

void CsvLogger::log(long long frameIdx, const InspectionResult& r,
                    const std::vector<std::string>& names, double inferMs,
                    const std::string& imagePath) {
    if (!ofs_) return;
    // detections 열 예: "scratch:2;dent:1"
    std::ostringstream det;
    bool first = true;
    if (!r.topk.empty()) {
        // 분류 모드 예: "good:0.912;crack:0.071;thread:0.017"
        for (const auto& c : r.topk) {
            if (!first) det << ';';
            det << className(names, c.classId) << ':' << cv::format("%.3f", c.score);
            first = false;
        }
    } else {
        // 검출 모드 예: "scratch:2;dent:1"
        for (const auto& [cls, cnt] : r.countPerClass) {
            if (!first) det << ';';
            det << className(names, cls) << ':' << cnt;
            first = false;
        }
    }
    ofs_ << nowString("%Y-%m-%d %H:%M:%S", true) << ',' << frameIdx << ','
         << (r.ok ? "OK" : "NG") << ',' << r.defects.size() << ',' << det.str() << ','
         << cv::format("%.2f", inferMs) << ',' << imagePath << '\n';
    ofs_.flush();  // 프로그램이 비정상 종료돼도 기록 보존
}

// =============================================================================
//  drawOverlay : 결과 시각화
// =============================================================================
static cv::Scalar classColor(int id) {
    static const cv::Scalar palette[] = {
        {56, 56, 255},  {151, 157, 255}, {31, 112, 255}, {29, 178, 255}, {49, 210, 207},
        {10, 249, 72},  {23, 204, 146},  {134, 219, 61}, {52, 147, 26},  {187, 212, 0}};
    return palette[id % 10];
}

void drawOverlay(cv::Mat& img, const InspectionResult& r, const std::vector<std::string>& names,
                 const cv::Rect& roi, const OverlayInfo& info) {
    // 해상도에 따라 글자/선 두께 자동 조절
    const double fs    = std::max(0.5, img.cols / 1600.0);
    const int    thick = std::max(1, static_cast<int>(std::round(fs * 2)));
    const int    font  = cv::FONT_HERSHEY_SIMPLEX;

    // 1) ROI (노란색)
    cv::rectangle(img, roi, cv::Scalar(0, 255, 255), thick);

    // 2) 검출 박스 + 라벨
    for (const auto& d : r.detections) {
        const bool isDefect = std::any_of(r.defects.begin(), r.defects.end(),
                                          [&](const Detection& x) { return x.box == d.box; });
        const cv::Scalar color = classColor(d.classId);
        cv::rectangle(img, d.box, color, isDefect ? thick * 2 : thick);

        const std::string label = className(names, d.classId) + cv::format(" %.2f", d.confidence);
        int base = 0;
        const cv::Size ts = cv::getTextSize(label, font, fs * 0.6, thick, &base);
        const int ty = std::max(d.box.y, ts.height + 4);
        cv::rectangle(img, cv::Point(d.box.x, ty - ts.height - 4),
                      cv::Point(d.box.x + ts.width + 4, ty), color, cv::FILLED);
        cv::putText(img, label, cv::Point(d.box.x + 2, ty - 3), font, fs * 0.6,
                    cv::Scalar(255, 255, 255), thick, cv::LINE_AA);
    }

    // 3) 좌상단 OK/NG 배너
    const std::string verdict = !info.banner.empty() ? info.banner : (r.ok ? "OK" : "NG");
    const cv::Scalar  vColor  = !info.banner.empty() ? cv::Scalar(120, 120, 120)
                              : (r.ok ? cv::Scalar(0, 200, 0) : cv::Scalar(0, 0, 255));
    int base = 0;
    const cv::Size vs = cv::getTextSize(verdict, font, fs * 2.0, thick * 2, &base);
    cv::rectangle(img, cv::Rect(10, 10, vs.width + 30, vs.height + 30), vColor, cv::FILLED);
    cv::putText(img, verdict, cv::Point(25, 10 + vs.height + 15), font, fs * 2.0,
                cv::Scalar(255, 255, 255), thick * 2, cv::LINE_AA);

    // 4) 상태 정보 (한글은 putText 에서 깨지므로 영문 표기)
    const std::vector<std::string> lines = {
        info.backend,
        cv::format("Infer: %.1f ms  Proc: %.0f fps  Input: %.1f fps", info.inferMs, info.fps, info.inputFps),
        cv::format("Total: %lld  OK: %lld  NG: %lld (%.1f%%)", info.stats.total, info.stats.ok,
                   info.stats.ng, info.stats.ngRate())};
    std::vector<std::string> all = lines;
    if (!info.extraLine.empty()) all.push_back(info.extraLine);
    int y = 10 + vs.height + 30 + static_cast<int>(30 * fs);
    for (const auto& s : all) {
        cv::putText(img, s, cv::Point(12, y), font, fs * 0.6, cv::Scalar(0, 0, 0), thick + 2, cv::LINE_AA);
        cv::putText(img, s, cv::Point(12, y), font, fs * 0.6, cv::Scalar(255, 255, 255), thick, cv::LINE_AA);
        y += static_cast<int>(28 * fs);
    }

    // 5) 분류 모드: Top-K 결과 목록 (1순위는 크게, 노란색)
    for (size_t i = 0; i < r.topk.size(); ++i) {
        const auto& c = r.topk[i];
        const std::string s = cv::format("%zu. %s  %.1f%%", i + 1, className(names, c.classId).c_str(),
                                         c.score * 100.0);
        const double     scale = (i == 0) ? fs * 0.9 : fs * 0.6;
        const cv::Scalar color = (i == 0) ? cv::Scalar(0, 255, 255) : cv::Scalar(255, 255, 255);
        y += static_cast<int>((i == 0 ? 14 : 0) * fs);
        cv::putText(img, s, cv::Point(12, y), font, scale, cv::Scalar(0, 0, 0), thick + 2, cv::LINE_AA);
        cv::putText(img, s, cv::Point(12, y), font, scale, color, thick, cv::LINE_AA);
        y += static_cast<int>((i == 0 ? 40 : 28) * fs);
    }
}

}  // namespace mfg
