#include "common.hpp"

#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace mfg {

// -----------------------------------------------------------------------------
cv::Mat letterbox(const cv::Mat& src, const cv::Size& target, LetterboxInfo& info,
                  const cv::Scalar& padColor) {
    // 1) 가로/세로 중 더 많이 줄여야 하는 쪽 기준으로 배율 결정 (비율 유지)
    const float r = std::min(target.width / static_cast<float>(src.cols),
                             target.height / static_cast<float>(src.rows));
    const int newW = static_cast<int>(std::round(src.cols * r));
    const int newH = static_cast<int>(std::round(src.rows * r));

    info.scale = r;
    info.padX  = (target.width - newW) / 2;   // 좌우 여백을 균등하게
    info.padY  = (target.height - newH) / 2;  // 상하 여백을 균등하게

    // 2) 리사이즈
    cv::Mat resized;
    if (newW != src.cols || newH != src.rows)
        cv::resize(src, resized, cv::Size(newW, newH), 0, 0, cv::INTER_LINEAR);
    else
        resized = src;

    // 3) 회색 캔버스 가운데에 붙여넣기
    cv::Mat out(target, src.type(), padColor);
    resized.copyTo(out(cv::Rect(info.padX, info.padY, newW, newH)));
    return out;
}

// -----------------------------------------------------------------------------
cv::Mat centerCropResize(const cv::Mat& src, int size) {
    // torchvision Resize(int) 규칙: 짧은 변 = size, 긴 변 = int(size * 긴변 / 짧은변)
    const bool wide = src.cols >= src.rows;
    const int  shortSide = wide ? src.rows : src.cols;
    const int  longSide  = wide ? src.cols : src.rows;
    const int  newLong   = static_cast<int>(static_cast<double>(size) * longSide / shortSide);
    const cv::Size newSize = wide ? cv::Size(newLong, size) : cv::Size(size, newLong);

    // 축소는 INTER_AREA (PIL 의 안티에일리어싱과 비슷한 결과), 확대는 INTER_LINEAR
    cv::Mat resized;
    const int interp = (shortSide > size) ? cv::INTER_AREA : cv::INTER_LINEAR;
    cv::resize(src, resized, newSize, 0, 0, interp);

    // torchvision CenterCrop 규칙: 시작점 = round((크기 - size) / 2)
    const int x = static_cast<int>(std::round((resized.cols - size) / 2.0));
    const int y = static_cast<int>(std::round((resized.rows - size) / 2.0));
    return resized(cv::Rect(x, y, size, size)).clone();
}

std::vector<Classification> topK(const float* probs, int numClasses, int k) {
    std::vector<float> p(probs, probs + numClasses);

    // Ultralytics 분류 모델은 softmax 가 포함돼 있음. 없는 모델(로짓 출력) 대비 자동 보정
    double sum = 0.0;
    bool inRange = true;
    for (float v : p) { sum += v; if (v < 0.f || v > 1.f) inRange = false; }
    if (!inRange || std::abs(sum - 1.0) > 0.01) {
        const float mx = *std::max_element(p.begin(), p.end());
        double s = 0.0;
        for (float& v : p) { v = std::exp(v - mx); s += v; }
        for (float& v : p) v = static_cast<float>(v / s);
    }

    std::vector<int> idx(numClasses);
    for (int i = 0; i < numClasses; ++i) idx[i] = i;
    k = std::min(k, numClasses);
    std::partial_sort(idx.begin(), idx.begin() + k, idx.end(),
                      [&](int a, int b) { return p[a] > p[b]; });

    std::vector<Classification> out;
    for (int i = 0; i < k; ++i) out.push_back({idx[i], p[idx[i]]});
    return out;
}

// -----------------------------------------------------------------------------
void toNchwBlob(const cv::Mat& bgr, std::vector<float>& blob) {
    const int H = bgr.rows, W = bgr.cols;
    blob.resize(static_cast<size_t>(3) * H * W);

    // BGR → RGB, 0~255 → 0~1
    cv::Mat rgbF;
    cv::cvtColor(bgr, rgbF, cv::COLOR_BGR2RGB);
    rgbF.convertTo(rgbF, CV_32FC3, 1.0 / 255.0);

    // HWC → CHW : blob 메모리를 가리키는 Mat 3개를 만들고 split 으로 바로 써넣음
    std::vector<cv::Mat> channels(3);
    for (int c = 0; c < 3; ++c)
        channels[c] = cv::Mat(H, W, CV_32FC1, blob.data() + static_cast<size_t>(c) * H * W);
    cv::split(rgbF, channels);
}

// -----------------------------------------------------------------------------
static float iou(const cv::Rect& a, const cv::Rect& b) {
    const float inter = static_cast<float>((a & b).area());
    const float uni   = static_cast<float>(a.area() + b.area()) - inter;
    return uni > 0.f ? inter / uni : 0.f;
}

std::vector<Detection> nms(std::vector<Detection> dets, float iouThreshold, int maxDetections) {
    // 신뢰도 내림차순 정렬 → 높은 것부터 채택하고, 겹치는 같은 클래스 박스는 제거
    std::sort(dets.begin(), dets.end(),
              [](const Detection& a, const Detection& b) { return a.confidence > b.confidence; });

    std::vector<Detection> keep;
    std::vector<char> removed(dets.size(), 0);
    for (size_t i = 0; i < dets.size(); ++i) {
        if (removed[i]) continue;
        keep.push_back(dets[i]);
        if (static_cast<int>(keep.size()) >= maxDetections) break;
        for (size_t j = i + 1; j < dets.size(); ++j) {
            if (removed[j] || dets[j].classId != dets[i].classId) continue;
            if (iou(dets[i].box, dets[j].box) > iouThreshold) removed[j] = 1;
        }
    }
    return keep;
}

// -----------------------------------------------------------------------------
std::vector<Detection> postprocessYolov8(const float* data, int dim1, int dim2,
                                         const LetterboxInfo& lb, const cv::Size& origSize,
                                         float confThreshold, float nmsThreshold,
                                         int maxDetections) {
    // YOLOv8 출력 형식
    //   채널 우선 : [1, 4+nc, N]  ← Ultralytics 기본 export
    //   앵커 우선 : [1, N, 4+nc]  ← 일부 변환 도구
    // 앵커 수(N=8400)가 채널 수보다 항상 크므로 작은 쪽을 채널로 판단합니다.
    const bool channelsFirst = dim1 < dim2;
    const int  numCh         = channelsFirst ? dim1 : dim2;
    const int  numAnchors    = channelsFirst ? dim2 : dim1;
    const int  numClasses    = numCh - 4;  // 앞 4개 = cx, cy, w, h
    if (numClasses <= 0) return {};

    auto at = [&](int ch, int i) -> float {
        return channelsFirst ? data[static_cast<size_t>(ch) * numAnchors + i]
                             : data[static_cast<size_t>(i) * numCh + ch];
    };

    std::vector<Detection> candidates;
    candidates.reserve(256);

    for (int i = 0; i < numAnchors; ++i) {
        // 1) 가장 점수가 높은 클래스 찾기 (YOLOv8 은 objectness 가 없음)
        int   bestCls   = -1;
        float bestScore = confThreshold;
        for (int c = 0; c < numClasses; ++c) {
            const float s = at(4 + c, i);
            if (s > bestScore) { bestScore = s; bestCls = c; }
        }
        if (bestCls < 0) continue;

        // 2) 박스 좌표 (모델 입력 좌표계, 중심점 기준)
        const float cx = at(0, i), cy = at(1, i), w = at(2, i), h = at(3, i);

        // 3) 레터박스 역변환 → 원본 좌표계
        float x0 = (cx - 0.5f * w - lb.padX) / lb.scale;
        float y0 = (cy - 0.5f * h - lb.padY) / lb.scale;
        float x1 = (cx + 0.5f * w - lb.padX) / lb.scale;
        float y1 = (cy + 0.5f * h - lb.padY) / lb.scale;

        // 4) 이미지 경계로 자르기
        x0 = std::clamp(x0, 0.f, static_cast<float>(origSize.width - 1));
        y0 = std::clamp(y0, 0.f, static_cast<float>(origSize.height - 1));
        x1 = std::clamp(x1, 0.f, static_cast<float>(origSize.width - 1));
        y1 = std::clamp(y1, 0.f, static_cast<float>(origSize.height - 1));

        Detection d;
        d.classId    = bestCls;
        d.confidence = bestScore;
        d.box        = cv::Rect(cv::Point(cvRound(x0), cvRound(y0)),
                                cv::Point(cvRound(x1), cvRound(y1)));
        if (d.box.area() > 0) candidates.push_back(d);
    }

    return nms(std::move(candidates), nmsThreshold, maxDetections);
}

// -----------------------------------------------------------------------------
std::vector<std::string> loadClassNames(const std::string& path) {
    std::vector<std::string> names;
    std::ifstream ifs(path);
    if (!ifs) {
        std::cerr << "[경고] 클래스 파일을 열 수 없습니다: " << path << "\n";
        return names;
    }
    std::string line;
    while (std::getline(ifs, line)) {
        // Windows 줄바꿈(\r) 및 앞뒤 공백 제거
        line.erase(std::remove(line.begin(), line.end(), '\r'), line.end());
        const auto b = line.find_first_not_of(" \t");
        const auto e = line.find_last_not_of(" \t");
        if (b == std::string::npos) continue;  // 빈 줄 무시
        names.push_back(line.substr(b, e - b + 1));
    }
    return names;
}

std::string className(const std::vector<std::string>& names, int id) {
    if (id >= 0 && id < static_cast<int>(names.size())) return names[id];
    return "cls" + std::to_string(id);
}

// -----------------------------------------------------------------------------
std::string nowString(const char* fmt, bool withMillis) {
    const auto now = std::chrono::system_clock::now();
    const std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
#ifdef _WIN32
    localtime_s(&tm, &t);
#else
    localtime_r(&t, &tm);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm, fmt);
    if (withMillis) {
        const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                            now.time_since_epoch()).count() % 1000;
        oss << '.' << std::setw(3) << std::setfill('0') << ms;
    }
    return oss.str();
}

void ensureBgr(cv::Mat& frame) {
    if (frame.channels() == 1)      cv::cvtColor(frame, frame, cv::COLOR_GRAY2BGR);
    else if (frame.channels() == 4) cv::cvtColor(frame, frame, cv::COLOR_BGRA2BGR);
    if (frame.depth() != CV_8U)     frame.convertTo(frame, CV_8U);  // 16bit 카메라 대비
}

}  // namespace mfg
