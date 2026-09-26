#include <iostream>
#include "YoloDetector.h"

int main(void) {
    
    std::string modelPath = "/home/m_ai/work/Detection/runs/detect/Detection/yolov8_result/weights/best.onnx";
    
    std::vector<std::string> labels = {"box"};

    YoloDetector detector(modelPath, labels);

    cv::VideoCapture cap(0);
    if(!cap.isOpened()) {
        std::cerr << "camera device not open(please usbipd port connect)";
        return -1;
    }

    cap.set(cv::CAP_PROP_FOURCC,  cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    // 카메라 해상도를 YOLO 표준인 640x480 또는 1280x720급 기본 비율로 고정합니다.
    cap.set(cv::CAP_PROP_FRAME_WIDTH, 640);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 480);

    std::cout << "================================================" << std::endl;
    std::cout << "개체 탐지 인고지능 루프 가동 완료(화면 종료 키: 'q')" << std::endl;
    std::cout << "================================================" << std::endl;
 
    cv::Mat frame;
    while(true) {
        cap >> frame; /* 카메라 센서로부터 이미지 1프레임 수집 */
        if(frame.empty()) break;

        detector.detect(frame);

        cv::imshow("C++ YOLO v8 (ONNX RUntime CUDA)", frame);

        if(cv::waitKey(1) == 'q') {
            break;
        }
    }

    cap.release();
    cv::destroyAllWindows();
    
    return 0;
}