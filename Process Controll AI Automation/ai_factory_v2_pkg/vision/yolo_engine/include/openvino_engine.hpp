#pragma once
// =============================================================================
//  openvino_engine.hpp : OpenVINO Runtime 엔진
//   - .onnx / .xml 직접 로드
//   - BGR→RGB, /255, NHWC→NCHW 변환을 PrePostProcessor 로 모델에 내장 (GPU 에서 처리)
// =============================================================================
#include "engine.hpp"

#include <openvino/openvino.hpp>

namespace mfg {

// "AUTO_DGPU" → 외장 GPU(예: GPU.1) 이름으로 변환, 사용 가능한 디바이스 출력
std::string resolveOpenVinoDevice(const std::string& requested, bool verbose = true);

class OpenVinoEngine : public IEngine {
public:
    OpenVinoEngine(const std::string& modelPath, const std::string& device,
                   const std::string& cacheDir, int defaultSize);

    RawOutput   run(const cv::Mat& bgr) override;
    cv::Size    inputSize() const override { return inputSize_; }
    std::string name() const override { return "OpenVINO[" + device_ + "]"; }

private:
    ov::Core          core_;
    ov::CompiledModel compiled_;
    ov::InferRequest  request_;
    ov::Tensor        output_;   // 마지막 출력 (RawOutput 이 가리킴)
    cv::Size          inputSize_;
    std::string       device_;
};

}  // namespace mfg
