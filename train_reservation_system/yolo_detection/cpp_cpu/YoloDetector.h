#ifndef YOLO_DETECTOR_H
#define YOLO_DETECTOR_H

#include <opencv2/opencv.hpp>
#include <opencv2/dnn.hpp>
#include <vector>
#include <string>

class YoloDetector {
    private:
      cv::dnn::Net net;
      std::vector<std::string> classes;
      std::vector<cv::Scalar> colors;

      const float confThreshold = 0.5f;
      const float nmsThreshold = 0.4f;
      const int inputWidth = 640;
      const int inputHeight = 640;
      
    public:
      
      YoloDetector(const std::string& modelpath,
                   const std::vector<std::string>& className);
      
      void detect(cv::Mat& frame);
    
};



#endif /* YOLO_DETECTOR_H */