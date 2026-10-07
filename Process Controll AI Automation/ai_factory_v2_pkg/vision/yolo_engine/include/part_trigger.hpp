#pragma once
// =============================================================================
//  part_trigger.hpp : 소프트웨어 부품 감지 트리거 (배경 차분 방식)
//
//  원리
//   1) 시작 시 ROI 가 비어 있는 상태의 '배경'을 학습
//   2) 매 프레임 ROI 를 배경과 비교 → 바뀐 픽셀 비율이 기준 이상이면 "부품 있음"
//   3) 부품 있음이 연속 settle 프레임 → 검사 프레임 inspect 장 수집 → 최종 판정 1번
//   4) 부품이 빠져나갈 때까지(빈 상태 연속 clear 프레임) 다음 부품을 기다림
//  → "부품 1개 = 판정 1번" 보장, 빈 컨베이어는 판정하지 않음
//  ※ 광전 센서 같은 하드웨어 트리거가 생기면 이 클래스만 교체하면 됩니다.
// =============================================================================
#include <opencv2/core.hpp>

#include <string>

namespace mfg {

struct TriggerConfig {
    int    bgFrames      = 15;    // 배경 학습에 쓸 프레임 수 (시작 시 ROI 를 비워 둘 것)
    int    diffThreshold = 25;    // 픽셀 밝기 차이 기준 (0~255)
    double presenceRatio = 0.03;  // 바뀐 픽셀 비율이 이 이상이면 "부품 있음" (3%)
    int    settleFrames  = 3;     // 부품 있음이 연속 몇 프레임이면 검사 시작 (흔들림 방지)
    int    inspectFrames = 5;     // 부품 1개당 판정에 쓰는 프레임 수 (평균)
    int    clearFrames   = 5;     // 빈 상태가 연속 몇 프레임이면 부품이 떠난 것으로 판단
    double bgUpdateAlpha = 0.02;  // 빈 상태일 때 배경을 천천히 갱신 (조명 변화 대응)
};

enum class TriggerState { Learning, Empty, Settling, Capturing, WaitLeave };

struct TriggerStep {
    bool inspect  = false;  // 이 프레임을 판정에 사용
    bool finalize = false;  // 이 프레임을 끝으로 부품 1개 판정을 마감
};

class PartTrigger {
public:
    explicit PartTrigger(const TriggerConfig& cfg) : cfg_(cfg) {}

    TriggerStep  step(const cv::Mat& roiBgr);  // 매 프레임 호출 (ROI 영역 이미지)
    void         relearn();                    // 배경 다시 학습 ('b' 키)
    TriggerState state() const { return state_; }
    double       changeRatio() const { return ratio_; }
    std::string  stateText() const;

private:
    cv::Mat prepare(const cv::Mat& roiBgr) const;

    TriggerConfig cfg_;
    TriggerState  state_ = TriggerState::Learning;
    cv::Mat       bg_;        // 배경 (CV_32F, 축소된 흑백)
    int           learned_ = 0, streak_ = 0, captured_ = 0;
    double        ratio_ = 0.0;
};

}  // namespace mfg
