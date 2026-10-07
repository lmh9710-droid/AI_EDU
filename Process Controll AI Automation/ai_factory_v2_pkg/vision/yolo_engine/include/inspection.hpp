#pragma once
// =============================================================================
//  inspection.hpp : 제조 현장용 기능
//   - OK / NG 판정 (ROI, 불량 클래스, 최소 면적)
//   - 생산 통계 (총 수량 / OK / NG)
//   - CSV 검사 이력 로그 (엑셀에서 한글이 깨지지 않도록 UTF-8 BOM 기록)
//   - 결과 화면 그리기
// =============================================================================
#include "common.hpp"

#include <fstream>
#include <map>
#include <set>

namespace mfg {

struct InspectionResult {
    bool ok = true;                      // 최종 판정
    std::vector<Detection> detections;   // ROI 안의 유효 검출 전체
    std::vector<Detection> defects;      // 그중 불량 클래스
    std::map<int, int> countPerClass;    // 클래스별 개수
    std::vector<Classification> topk;    // 분류 모드: 확률 상위 K개 (검출 모드에서는 비어 있음)
};

struct ProductionStats {
    long long total = 0, ok = 0, ng = 0;
    double ngRate() const { return total ? 100.0 * ng / total : 0.0; }
};

class Inspector {
public:
    // defectIds 가 비어 있으면 모든 클래스를 불량으로 간주
    Inspector(const cv::Rect& roi, std::set<int> defectIds, int minBoxArea,
              std::set<int> okIds = {});

    InspectionResult judge(const std::vector<Detection>& dets, const cv::Size& frameSize) const;

    // 분류 모드 판정: 1순위 클래스가 불량 클래스이고 확률 >= conf 이면 NG
    //   ※ 분류에서 defect_classes 가 비어 있으면 판정 없이 기록만 함 (항상 OK)
    InspectionResult judgeClassification(const std::vector<Classification>& topk,
                                         const cv::Rect& roi, float confThreshold) const;

    // ROI 가 비어 있거나 화면 밖이면 전체/잘린 영역 반환
    cv::Rect effectiveRoi(const cv::Size& frameSize) const;

private:
    cv::Rect      roi_;
    std::set<int> defectIds_;
    int           minBoxArea_;
    std::set<int> okIds_;  // 분류 적극 판정용 (비어 있으면 기존 방식)
};

class CsvLogger {
public:
    bool open(const std::string& path);
    void log(long long frameIdx, const InspectionResult& r, const std::vector<std::string>& names,
             double inferMs, const std::string& imagePath);

private:
    std::ofstream ofs_;
};

struct OverlayInfo {
    std::string     backend;
    double          inferMs = 0;
    double          fps     = 0;    // 처리 속도: 1프레임 처리 시간 기준 (이 PC가 감당 가능한 최대치)
    double          inputFps = 0;   // 입력 속도: 실제로 프레임이 들어오는 간격 기준 (카메라가 상한)
    ProductionStats stats;
    std::string     banner;      // 비어 있지 않으면 OK/NG 대신 이 문구를 회색 배너로 (예: READY)
    std::string     extraLine;   // 추가 정보 한 줄 (예: 트리거 상태)
};

void drawOverlay(cv::Mat& img, const InspectionResult& r, const std::vector<std::string>& names,
                 const cv::Rect& roi, const OverlayInfo& info);

}  // namespace mfg
