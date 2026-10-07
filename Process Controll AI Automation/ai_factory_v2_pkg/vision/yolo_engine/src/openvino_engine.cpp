#include "openvino_engine.hpp"

#include <iostream>

namespace mfg {

// -----------------------------------------------------------------------------
std::string resolveOpenVinoDevice(const std::string& requested, bool verbose) {
    ov::Core core;
    std::string firstGpu, discreteGpu;
    if (verbose) std::cout << "[OpenVINO] 사용 가능한 디바이스\n";

    for (const auto& d : core.get_available_devices()) {
        std::string fullName;
        try { fullName = core.get_property(d, ov::device::full_name); } catch (...) {}

        bool isDiscrete = false;
        if (d.rfind("GPU", 0) == 0) {  // "GPU", "GPU.0", "GPU.1" ...
            if (firstGpu.empty()) firstGpu = d;
            try {
                isDiscrete = core.get_property(d, ov::device::type) == ov::device::Type::DISCRETE;
            } catch (...) {}
            if (isDiscrete && discreteGpu.empty()) discreteGpu = d;
        }
        if (verbose)
            std::cout << "   - " << d << " : " << fullName << (isDiscrete ? "  [외장 GPU]" : "") << "\n";
    }

    if (requested != "AUTO_DGPU") return requested;  // 직접 지정한 경우 그대로
    if (!discreteGpu.empty()) return discreteGpu;    // 1순위: 외장 GPU (Arc A770)
    if (!firstGpu.empty()) {
        std::cout << "[경고] 외장 GPU를 찾지 못해 " << firstGpu << " 를 사용합니다.\n";
        return firstGpu;
    }
    std::cout << "[경고] GPU가 없어 CPU를 사용합니다. Arc 드라이버 설치를 확인하세요.\n";
    return "CPU";
}

// -----------------------------------------------------------------------------
OpenVinoEngine::OpenVinoEngine(const std::string& modelPath, const std::string& device,
                               const std::string& cacheDir, int defaultSize)
    : device_(device) {
    cv::TickMeter tm;
    tm.start();

    // [1] 컴파일 캐시: 두 번째 실행부터 GPU 로딩이 빨라짐
    if (!cacheDir.empty()) core_.set_property(ov::cache_dir(cacheDir));

    // [2] 모델 읽기 (.onnx / .xml)
    std::shared_ptr<ov::Model> model = core_.read_model(modelPath);
    if (model->inputs().size() != 1) throw std::runtime_error("입력이 1개인 모델만 지원합니다.");

    // [3] 동적 입력이면 고정 크기로 (검출 640, 분류 224)
    if (model->input().get_partial_shape().is_dynamic()) {
        std::cout << "[OpenVINO] 동적 입력 → [1,3," << defaultSize << "," << defaultSize << "] 로 고정\n";
        model->reshape(ov::PartialShape{1, 3, defaultSize, defaultSize});
    }
    const ov::Shape inShape = model->input().get_shape();  // [N, C, H, W]
    inputSize_ = cv::Size(static_cast<int>(inShape[3]), static_cast<int>(inShape[2]));

    // [4] 전처리를 모델에 내장 : uint8 NHWC BGR → float32 NCHW RGB 0~1
    ov::preprocess::PrePostProcessor ppp(model);
    ppp.input().tensor()
        .set_element_type(ov::element::u8)
        .set_layout("NHWC")
        .set_color_format(ov::preprocess::ColorFormat::BGR);
    ppp.input().preprocess()
        .convert_element_type(ov::element::f32)
        .convert_color(ov::preprocess::ColorFormat::RGB)
        .scale(255.0f);
    ppp.input().model().set_layout("NCHW");
    ppp.output(0).tensor().set_element_type(ov::element::f32);
    model = ppp.build();

    // [5] 컴파일 옵션 : 한 장씩 빠르게(LATENCY), GPU 는 FP16 연산
    ov::AnyMap config;
    config.insert(ov::hint::performance_mode(ov::hint::PerformanceMode::LATENCY));
    if (device_.rfind("GPU", 0) == 0) {
        // Arc GPU : FP16 연산이 매우 빠르고 정확도 손실은 대부분 무시할 수준
        config.insert(ov::hint::inference_precision(ov::element::f16));
    } else if (device_ == "CPU") {
        // CPU : 정밀도를 F32 로 고정. 일부 CPU(BF16 지원 Xeon 등)는 기본값이 BF16 이라
        //       PC 마다 결과가 미세하게 달라질 수 있음 → 라인 간 재현성을 위해 명시
        config.insert(ov::hint::inference_precision(ov::element::f32));
    }

    compiled_ = core_.compile_model(model, device_, config);
    request_  = compiled_.create_infer_request();

    tm.stop();
    std::cout << "[OpenVINO] 모델 로드 완료 : " << modelPath << "\n"
              << "           디바이스=" << device_ << ", 입력=" << inputSize_.width << "x"
              << inputSize_.height << ", 소요=" << tm.getTimeMilli() << " ms\n";
}

// -----------------------------------------------------------------------------
RawOutput OpenVinoEngine::run(const cv::Mat& bgr) {
    CV_Assert(bgr.type() == CV_8UC3 && bgr.size() == inputSize_);
    const cv::Mat in = bgr.isContinuous() ? bgr : bgr.clone();

    // Mat 메모리를 복사 없이 텐서로 감싸 전달 (동기 추론이라 in 이 살아 있는 동안 완료됨)
    ov::Tensor input(ov::element::u8,
                     ov::Shape{1, static_cast<size_t>(inputSize_.height),
                               static_cast<size_t>(inputSize_.width), 3},
                     in.data);
    request_.set_input_tensor(input);
    request_.infer();

    output_ = request_.get_output_tensor(0);
    RawOutput r;
    r.data = output_.data<float>();
    for (auto d : output_.get_shape()) r.shape.push_back(static_cast<int64_t>(d));
    return r;
}

}  // namespace mfg
