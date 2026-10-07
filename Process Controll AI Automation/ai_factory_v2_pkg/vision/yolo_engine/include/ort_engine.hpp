#pragma once
// =============================================================================
//  ort_engine.hpp : ONNX Runtime 엔진
//   - OpenVINO EP 포함 빌드면 Arc GPU, 아니면 CPU 로 자동 대체
// =============================================================================
#include "engine.hpp"

#include <onnxruntime_cxx_api.h>

namespace mfg {

class OrtEngine : public IEngine {
public:
    OrtEngine(const std::string& modelPath, const std::string& device,
              const std::string& cacheDir, int cpuThreads, int defaultSize);

    RawOutput   run(const cv::Mat& bgr) override;
    cv::Size    inputSize() const override { return inputSize_; }
    std::string name() const override { return "ONNXRuntime[" + epName_ + "]"; }

private:
    // 주의: env_ 가 session_ 보다 먼저 선언되어야 함 (파괴 순서)
    Ort::Env                      env_;
    Ort::SessionOptions           options_;
    std::unique_ptr<Ort::Session> session_;
    Ort::MemoryInfo               memInfo_{nullptr};
    std::vector<Ort::Value>       outputs_;   // 마지막 출력 (RawOutput 이 가리킴)

    std::string        inputName_, outputName_;
    std::vector<float> blob_;
    cv::Size           inputSize_;
    std::string        epName_ = "CPU";
};

}  // namespace mfg
