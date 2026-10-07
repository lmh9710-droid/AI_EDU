#include "ort_engine.hpp"

#include "common.hpp"

#include <array>
#include <filesystem>
#include <iostream>
#include <unordered_map>

namespace mfg {

OrtEngine::OrtEngine(const std::string& modelPath, const std::string& device,
                     const std::string& cacheDir, int cpuThreads, int defaultSize)
    : env_(ORT_LOGGING_LEVEL_WARNING, "yolo_mfg"), inputSize_(defaultSize, defaultSize) {
    cv::TickMeter tm;
    tm.start();

    options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    options_.SetIntraOpNumThreads(cpuThreads);

    // OpenVINO EP 등록 시도 → 실패하면 CPU 로 계속
    if (device != "CPU") {
        try {
            std::unordered_map<std::string, std::string> ov;
            const std::string dev = (device == "AUTO_DGPU") ? "GPU" : device;
            ov["device_type"] = dev;
            if (dev.rfind("GPU", 0) == 0) ov["precision"] = "FP16";
            if (!cacheDir.empty()) ov["cache_dir"] = cacheDir;
            options_.AppendExecutionProvider_OpenVINO_V2(ov);
            epName_ = "OpenVINO-EP:" + dev;
        } catch (const Ort::Exception& e) {
            std::cerr << "[ONNXRuntime] OpenVINO EP 등록 실패 → CPU 로 실행합니다. (" << e.what() << ")\n";
            epName_ = "CPU";
        }
    }

    // Windows 는 wchar_t 경로가 필요 → filesystem::path 로 자동 처리
    const std::filesystem::path p(modelPath);
    session_ = std::make_unique<Ort::Session>(env_, p.c_str(), options_);

    Ort::AllocatorWithDefaultOptions alloc;
    inputName_  = session_->GetInputNameAllocated(0, alloc).get();
    outputName_ = session_->GetOutputNameAllocated(0, alloc).get();

    const auto inShape = session_->GetInputTypeInfo(0).GetTensorTypeAndShapeInfo().GetShape();
    if (inShape.size() == 4) {  // [1,3,H,W], 동적(-1)이면 defaultSize
        if (inShape[2] > 0) inputSize_.height = static_cast<int>(inShape[2]);
        if (inShape[3] > 0) inputSize_.width  = static_cast<int>(inShape[3]);
    }
    memInfo_ = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    tm.stop();
    std::cout << "[ONNXRuntime] 모델 로드 완료 : " << modelPath << "\n"
              << "              EP=" << epName_ << ", 입력=" << inputSize_.width << "x"
              << inputSize_.height << ", 소요=" << tm.getTimeMilli() << " ms\n";
}

RawOutput OrtEngine::run(const cv::Mat& bgr) {
    CV_Assert(bgr.type() == CV_8UC3 && bgr.size() == inputSize_);
    toNchwBlob(bgr, blob_);  // BGR→RGB, /255, NCHW (CPU 에서 처리)

    const std::array<int64_t, 4> shape{1, 3, inputSize_.height, inputSize_.width};
    Ort::Value input = Ort::Value::CreateTensor<float>(memInfo_, blob_.data(), blob_.size(),
                                                       shape.data(), shape.size());
    const char* inNames[]  = {inputName_.c_str()};
    const char* outNames[] = {outputName_.c_str()};
    outputs_ = session_->Run(Ort::RunOptions{nullptr}, inNames, &input, 1, outNames, 1);

    RawOutput r;
    r.data  = outputs_[0].GetTensorData<float>();
    r.shape = outputs_[0].GetTensorTypeAndShapeInfo().GetShape();
    return r;
}

}  // namespace mfg
