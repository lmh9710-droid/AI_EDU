#include "yolo_tasks.hpp"

#ifdef USE_OPENVINO
#include "openvino_engine.hpp"
#endif
#ifdef USE_ONNXRUNTIME
#include "ort_engine.hpp"
#endif

#include <stdexcept>

namespace mfg {

// -----------------------------------------------------------------------------
std::unique_ptr<IEngine> createEngine(const std::string& backend, const std::string& modelPath,
                                      const std::string& device, const std::string& cacheDir,
                                      int cpuThreads, int defaultSize) {
    if (backend == "openvino") {
#ifdef USE_OPENVINO
        return std::make_unique<OpenVinoEngine>(modelPath, device, cacheDir, defaultSize);
#else
        throw std::runtime_error("OpenVINO 백엔드가 빌드에 없습니다. (-DENABLE_OPENVINO=ON)");
#endif
    }
    if (backend == "onnxruntime") {
#ifdef USE_ONNXRUNTIME
        return std::make_unique<OrtEngine>(modelPath, device, cacheDir, cpuThreads, defaultSize);
#else
        throw std::runtime_error("ONNX Runtime 백엔드가 빌드에 없습니다. (-DENABLE_ONNXRUNTIME=ON)");
#endif
    }
    throw std::runtime_error("알 수 없는 backend: " + backend + " (openvino | onnxruntime)");
}

// -----------------------------------------------------------------------------
std::vector<Detection> YoloDetector::detect(const cv::Mat& bgr, float confThreshold,
                                            float nmsThreshold) {
    // 검출 : 레터박스(비율 유지 + 회색 여백) → 추론 → 박스 디코딩 + NMS
    LetterboxInfo info;
    const cv::Mat lb = letterbox(bgr, engine_->inputSize(), info);
    const RawOutput o = engine_->run(lb);
    if (o.shape.size() != 3)
        throw std::runtime_error("검출 모델 출력이 3차원이 아닙니다. 분류 모델이면 task: \"classify\" 로 설정하세요.");
    return postprocessYolov8(o.data, static_cast<int>(o.shape[1]), static_cast<int>(o.shape[2]),
                             info, bgr.size(), confThreshold, nmsThreshold);
}

// -----------------------------------------------------------------------------
std::vector<Classification> YoloClassifier::classify(const cv::Mat& bgr, int k) {
    // 분류 : 짧은 변 리사이즈 + 센터크롭 → 추론 → 확률 Top-K
    const cv::Mat crop = centerCropResize(bgr, engine_->inputSize().width);
    const RawOutput o = engine_->run(crop);
    if (o.shape.size() != 2)
        throw std::runtime_error("분류 모델 출력이 [1, 클래스수] 가 아닙니다. 검출 모델이면 task: \"detect\" 로 설정하세요.");
    return topK(o.data, static_cast<int>(o.shape[1]), k);
}

}  // namespace mfg
