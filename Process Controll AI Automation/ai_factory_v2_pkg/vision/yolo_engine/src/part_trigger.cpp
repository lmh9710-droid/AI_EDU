#include "part_trigger.hpp"

#include <opencv2/imgproc.hpp>

namespace mfg {

cv::Mat PartTrigger::prepare(const cv::Mat& roiBgr) const {
    // 속도와 노이즈 대책: 폭 160px 로 축소 → 흑백 → 블러
    cv::Mat small, gray, f;
    const double s = 160.0 / std::max(1, roiBgr.cols);
    cv::resize(roiBgr, small, cv::Size(), std::min(1.0, s), std::min(1.0, s), cv::INTER_AREA);
    cv::cvtColor(small, gray, cv::COLOR_BGR2GRAY);
    cv::GaussianBlur(gray, gray, cv::Size(5, 5), 0);
    gray.convertTo(f, CV_32F);
    return f;
}

void PartTrigger::relearn() {
    state_ = TriggerState::Learning;
    bg_.release();
    learned_ = streak_ = captured_ = 0;
}

TriggerStep PartTrigger::step(const cv::Mat& roiBgr) {
    TriggerStep out;
    const cv::Mat cur = prepare(roiBgr);

    // [학습] 시작 직후 bgFrames 장을 평균내 배경으로 삼음
    if (state_ == TriggerState::Learning) {
        if (bg_.empty() || bg_.size() != cur.size()) { bg_ = cur.clone(); learned_ = 1; }
        else cv::accumulateWeighted(cur, bg_, 1.0 / (++learned_));
        if (learned_ >= cfg_.bgFrames) state_ = TriggerState::Empty;
        return out;
    }

    // 배경 대비 바뀐 픽셀 비율
    cv::Mat diff, mask;
    cv::absdiff(cur, bg_, diff);
    cv::threshold(diff, mask, cfg_.diffThreshold, 255, cv::THRESH_BINARY);
    ratio_ = cv::countNonZero(mask) / static_cast<double>(mask.total());
    const bool present = ratio_ >= cfg_.presenceRatio;

    switch (state_) {
        case TriggerState::Empty:
            if (present) { state_ = TriggerState::Settling; streak_ = 1; }
            else cv::accumulateWeighted(cur, bg_, cfg_.bgUpdateAlpha);  // 조명 변화 천천히 반영
            break;
        case TriggerState::Settling:
            if (!present) { state_ = TriggerState::Empty; streak_ = 0; break; }
            if (++streak_ >= cfg_.settleFrames) { state_ = TriggerState::Capturing; captured_ = 0; }
            break;
        case TriggerState::Capturing:
            if (!present) {  // 다 모으기 전에 부품이 지나감 → 모은 만큼으로 마감
                out.finalize = captured_ > 0;
                state_ = TriggerState::Empty;
                break;
            }
            out.inspect = true;
            if (++captured_ >= cfg_.inspectFrames) {
                out.finalize = true;
                state_ = TriggerState::WaitLeave;
                streak_ = 0;
            }
            break;
        case TriggerState::WaitLeave:  // 같은 부품을 두 번 판정하지 않도록 떠날 때까지 대기
            streak_ = present ? 0 : streak_ + 1;
            if (streak_ >= cfg_.clearFrames) state_ = TriggerState::Empty;
            break;
        default: break;
    }
    return out;
}

std::string PartTrigger::stateText() const {
    switch (state_) {
        case TriggerState::Learning:  return "LEARNING BG";
        case TriggerState::Empty:     return "EMPTY";
        case TriggerState::Settling:  return "PART ARRIVING";
        case TriggerState::Capturing: return "INSPECTING";
        case TriggerState::WaitLeave: return "WAIT LEAVE";
    }
    return "?";
}

}  // namespace mfg
