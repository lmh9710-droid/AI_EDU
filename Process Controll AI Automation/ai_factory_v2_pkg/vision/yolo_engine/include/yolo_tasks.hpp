#pragma once
// =============================================================================
//  yolo_tasks.hpp : 엔진 위에서 동작하는 작업(Task)
//   - YoloDetector   : YOLOv8/YOLO11 검출   (*.pt / *.onnx, 예: yolov8n.onnx)
//   - YoloClassifier : YOLOv8/YOLO11 분류   (*-cls, 예: yolo11n-cls.onnx)
// =============================================================================
#include "engine.hpp"
#include "idetector.hpp"

namespace mfg {

class YoloDetector : public IDetector {
public:
    explicit YoloDetector(std::unique_ptr<IEngine> engine) : engine_(std::move(engine)) {}

    std::vector<Detection> detect(const cv::Mat& bgr, float confThreshold,
                                  float nmsThreshold) override;
    std::string backendName() const override { return engine_->name(); }
    cv::Size    inputSize() const override { return engine_->inputSize(); }

private:
    std::unique_ptr<IEngine> engine_;
};

class YoloClassifier {
public:
    explicit YoloClassifier(std::unique_ptr<IEngine> engine) : engine_(std::move(engine)) {}

    // 이미지 전체(또는 ROI 로 잘라낸 부분)를 분류 → 확률 높은 순 Top-K
    std::vector<Classification> classify(const cv::Mat& bgr, int k);
    std::string backendName() const { return engine_->name(); }
    cv::Size    inputSize() const { return engine_->inputSize(); }

private:
    std::unique_ptr<IEngine> engine_;
};

}  // namespace mfg
