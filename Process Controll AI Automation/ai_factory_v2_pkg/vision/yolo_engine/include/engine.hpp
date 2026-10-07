#pragma once
// =============================================================================
//  engine.hpp : 추론 엔진 공통 인터페이스 (OpenVINO / ONNX Runtime)
//
//  구조
//    [IEngine]  이미지(모델 입력 크기, BGR uint8) → 원시 출력 텐서
//       ├─ OpenVinoEngine
//       └─ OrtEngine
//    [작업(Task)] 엔진 위에서 전처리/후처리만 담당
//       ├─ YoloDetector   : 레터박스 → 박스 디코딩 + NMS      (yolo_tasks.hpp)
//       └─ YoloClassifier : 센터크롭 → Top-K 확률
//  → 백엔드 코드는 한 번만 작성하고, 검출/분류 모두에서 재사용합니다.
// =============================================================================
#include <opencv2/core.hpp>

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace mfg {

// 엔진 출력 (다음 run() 호출 전까지만 유효)
struct RawOutput {
    const float*         data = nullptr;
    std::vector<int64_t> shape;  // 검출 [1, 4+nc, 8400], 분류 [1, nc]
};

class IEngine {
public:
    virtual ~IEngine() = default;
    // bgr : CV_8UC3, 크기 = inputSize() (전처리는 Task 쪽에서 완료된 상태)
    virtual RawOutput   run(const cv::Mat& bgr) = 0;
    virtual cv::Size    inputSize() const = 0;
    virtual std::string name() const = 0;
};

// 설정값으로 엔진 생성 (main.cpp 에서 사용)
//   backend     : "openvino" | "onnxruntime"
//   device      : "GPU.1" 등 (AUTO_DGPU 는 미리 해석된 값이 들어옴)
//   defaultSize : 동적 입력 모델일 때 고정할 크기 (검출 640, 분류 224)
std::unique_ptr<IEngine> createEngine(const std::string& backend, const std::string& modelPath,
                                      const std::string& device, const std::string& cacheDir,
                                      int cpuThreads, int defaultSize);

}  // namespace mfg
