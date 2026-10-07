#pragma once
// =============================================================================
//  idetector.hpp : 검출기 공통 인터페이스
//  OpenVINO / ONNX Runtime 구현체가 이 인터페이스를 상속하므로,
//  main 쪽 코드는 어떤 백엔드인지 몰라도 동일하게 사용할 수 있습니다.
// =============================================================================
#include "common.hpp"

namespace mfg {

class IDetector {
public:
    virtual ~IDetector() = default;

    // BGR 8bit 이미지를 받아 원본 좌표계의 검출 결과를 반환
    virtual std::vector<Detection> detect(const cv::Mat& bgr, float confThreshold,
                                          float nmsThreshold) = 0;

    virtual std::string backendName() const = 0;  // 화면/로그 표시용
    virtual cv::Size    inputSize() const = 0;    // 모델 입력 크기 (예: 640x640)
};

}  // namespace mfg
