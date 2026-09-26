#include "YoloDetector.h"
#include <iostream>
#include <numeric>
#include <ctime>
#include <cstdlib>

YoloDetector::YoloDetector(const std::string& modelPath, const std::vector<std::string>& classNames)
    : env(ORT_LOGGING_LEVEL_WARNING, "YOLO_Parallel_Inference") 
{
    this->classes = classNames;

    Ort::SessionOptions session_options;
    session_options.SetIntraOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    // 🛠️ 경고 제거 및 0번 GPU(RTX 4070) CUDA 가속 엔진 바인딩
    OrtStatus* cuda_status = OrtSessionOptionsAppendExecutionProvider_CUDA(session_options, 0); 

    std::cout << "🚀 [PRO MODE] ONNX Runtime CUDA 가속 세션 생성 중: " << modelPath << std::endl;
    this->session = Ort::Session(env, modelPath.c_str(), session_options);
    this->memory_info = Ort::MemoryInfo::CreateCpu(OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

    this->input_node_names = {"images"};
    this->output_node_names = {"output0"};

    std::srand(static_cast<unsigned int>(std::time(nullptr)));
    for (size_t i = 0; i < classes.size(); ++i) {
        colors.push_back(cv::Scalar(std::rand() % 256, std::rand() % 256, std::rand() % 256));
    }
}

void YoloDetector::detect(cv::Mat& frame) {
    int imgH = frame.rows;
    int imgW = frame.cols;

    cv::Mat display_frame = frame.clone();

    // 1. [전처리 가공] 640x640 압축 및 순정 RGB 채널 스왑
    cv::Mat resized_img;
    cv::resize(frame, resized_img, cv::Size(inputWidth, inputHeight));
    cv::cvtColor(resized_img, resized_img, cv::COLOR_BGR2RGB); 
    resized_img.convertTo(resized_img, CV_32FC3, 1.0 / 255.0);

    // 2. [평탄화 배열화] ONNX Runtime 규격 NCHW 데이터 포맷으로 포인터 재배치
    std::vector<float> input_tensor_values(1 * 3 * inputWidth * inputHeight);
    std::vector<cv::Mat> input_channels(3);
    for (int i = 0; i < 3; ++i) {
        input_channels[i] = cv::Mat(inputHeight, inputWidth, CV_32FC1, &input_tensor_values[i * inputWidth * inputHeight]);
    }
    cv::split(resized_img, input_channels);

    std::vector<int64_t> input_node_dims = {1, 3, inputWidth, inputHeight};
    Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
        memory_info, input_tensor_values.data(), input_tensor_values.size(), input_node_dims.data(), input_node_dims.size()
    );

    // 🔥 [RTX 4070 초고속 추론]
    auto output_tensors = session.Run(
        Ort::RunOptions{nullptr}, input_node_names.data(), &input_tensor, 1, output_node_names.data(), 1
    );

    // 3. [행렬 차원 변환 검증 고도화]
    float* output_data = output_tensors.at(0).GetTensorMutableData<float>();
    int rows_count = 4 + classes.size();
    
    // [4+N, 8400] 구조를 [8400, 4+N]으로 안전 Transpose
    cv::Mat output(rows_count, 8400, CV_32F, output_data);
    output = output.t(); 

    std::vector<cv::Rect> boxes;
    std::vector<float> confidences;
    std::vector<int> classIds;

    // 4. 🛠️ [탐지 실패 차단 핵심] 포인터 직접 참조 연산법으로 데이터 추출 필터 강화
    float* data = (float*)output.data;
    for (int i = 0; i < 8400; ++i) {
        // 현재 인덱스의 클래스 확률 영역 추출
        float* classes_scores = data + 4;
        
        float max_score = 0.0f;
        int class_id = 0;
        for (size_t c = 0; c < classes.size(); ++c) {
            if (classes_scores[c] > max_score) {
                max_score = classes_scores[c];
                class_id = c;
            }
        }

        // 임계값을 살짝 낮춰서(0.4) 최초 탐지 스캔 범위를 넓힙니다.
        if (max_score > 0.4f) {
            float cx = data[0];
            float cy = data[1];
            float w = data[2];
            float h = data[3];

            // 상대 좌표계를 원본 해상도 크기로 완벽 정밀 복원
            int x1 = static_cast<int>((cx - w / 2.0) * (imgW / static_cast<float>(inputWidth)));
            int y1 = static_cast<int>((cy - h / 2.0) * (imgH / static_cast<float>(inputHeight)));
            int width = static_cast<int>(w * (imgW / static_cast<float>(inputWidth)));
            int height = static_cast<int>(h * (imgH / static_cast<float>(inputHeight)));

            boxes.push_back(cv::Rect(x1, y1, width, height));
            confidences.push_back(max_score);
            classIds.push_back(class_id);
        }
        data += rows_count; // 다음 바운딩 박스 포인터 주소로 이동
    }

    // 5. [NMS 처리 및 최종 드로잉]
    std::vector<int> indices;
    cv::dnn::NMSBoxes(boxes, confidences, 0.4f, nmsThreshold, indices);

    for (int idx : indices) {
        cv::Rect box = boxes[idx];
        std::string label = classes[classIds[idx]] + ": " + cv::format("%.2f", confidences[idx]);
        cv::Scalar color = colors[classIds[idx]];
        
        cv::rectangle(display_frame, box, color, 2);
        cv::putText(display_frame, label, cv::Point(box.x, box.y - 10), cv::FONT_HERSHEY_SIMPLEX, 0.5, color, 2);
    }

    frame = display_frame;
}
