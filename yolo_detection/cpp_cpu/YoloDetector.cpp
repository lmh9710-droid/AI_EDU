#include "YoloDetector.h"
#include <iostream>
#include <ctime>
#include <cstdlib>

YoloDetector::YoloDetector(const std::string& modelPath, 
                           const std::vector<std::string>& className)
                           : classes(className),
                             net(cv::dnn::readNetFromONNX(modelPath)) {
    
  std::cout << "ONNX 가중치 주입 개체 인스턴스" << modelPath << std::endl;
  
  net.setPreferableBackend(cv::dnn::DNN_BACKEND_CUDA);
  net.setPreferableTarget(cv::dnn::DNN_TARGET_CUDA);

  std::srand(static_cast<unsigned int>(std::time(nullptr)));
  for(size_t i = 0; i < classes.size(); ++i) {
     colors.push_back(cv::Scalar(std::rand() % 256, std::rand() % 256, std::rand() % 256));
  }
}

/* detect - realtime video frame process*/
void YoloDetector::detect(cv::Mat& frame) {
    int imgH = frame.rows;
    int imgW = frame.cols;

    cv::Mat blob;
    cv::dnn::blobFromImage(frame, blob, 1.0 / 255.0, cv::Size(inputWidth, inputHeight),
                           cv::Scalar(), true, false);
    
    net.setInput(blob);
    /*NN forward inference*/
    std::vector<cv::Mat> outputs;
    net.forward(outputs, net.getUnconnectedOutLayersNames());
    
    cv::Mat output = outputs.at(0);

    int rows_count = 4 + classes.size();

    if(output.dims == 3) {
        std::vector<int> target_sizes;
        target_sizes.push_back(rows_count);
        target_sizes.push_back(8400);

        output = cv::Mat(target_sizes.size(), target_sizes.data(), CV_32F, output.ptr<float>());
    } else if(output.dims == 2) {
        output = output.reshape(1, rows_count);
      }
    output = output.t();

    std::vector<cv::Rect> boxes;
    std::vector<float> confidences;
    std::vector<int> classIds;

    for (int i = 0; i < output.rows; ++i) {
        cv::Mat row = output.row(i);
        cv::Mat scores = row.colRange(4, output.cols);

        cv::Point classIdPoint;
        double score;

        cv::minMaxLoc(scores, nullptr, &score, nullptr, &classIdPoint);

        if(score > confThreshold) {
            float cx = row.at<float>(0);
            float cy = row.at<float>(1);
            float w = row.at<float>(2);
            float h = row.at<float>(3);

            int x1 = static_cast<int>((cx - w / 2.0) * (imgW / static_cast<float>(inputWidth)));
            int y1 = static_cast<int>((cy - h / 2.0) * (imgH / static_cast<float>(inputHeight)));
            int width = static_cast<int>(w * (imgW / static_cast<float>(inputWidth)));
            int height = static_cast<int>(h * (imgH / static_cast<float>(inputHeight)));

            boxes.push_back(cv::Rect(x1, y1, width, height));
            confidences.push_back(static_cast<float>(score));
            classIds.push_back(classIdPoint.x);
        }
    }

    std::vector<int> indices;
    cv::dnn::NMSBoxes(boxes, confidences, confThreshold, nmsThreshold, indices);

    for (int idx : indices) {
        cv::Rect box = boxes[idx];
        std::string label = classes[classIds[idx]] + ": " + cv::format("%.2f", confidences[idx]);
        cv::Scalar color = colors[classIds[idx]];

        cv::rectangle(frame, box, color, 2);
        cv::putText(frame, label, cv::Point(box.x, box.y - 10), cv::FONT_HERSHEY_SIMPLEX, 0.5, color, 2);
    }


}