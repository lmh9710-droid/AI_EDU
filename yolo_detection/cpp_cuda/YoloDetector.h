#ifndef YOLO_DETECTOR_H
#define YOLO_DETECTOR_H

#include <opencv2/opencv.hpp>
#include <onnxruntime_cxx_api.h>
#include <vector>
#include <string>

class YoloDetector {
    private:
      Ort::Env env;
      Ort::Session session{nullptr};
      Ort::MemoryInfo memory_info{nullptr};

      std::vector<std::string> classes;
      std::vector<cv::Scalar> colors;

      const float confThreshold = 0.5f;
      const float nmsThreshold = 0.4f;
      const int inputWidth = 640;
      const int inputHeight = 640;

      std::vector<const char*> input_node_names;
      std::vector<const char*> output_node_names;
      
    public:
      
      YoloDetector(const std::string& modelPath,
                   const std::vector<std::string>& className);
      
      void detect(cv::Mat& frame);
    
};



#endif /* YOLO_DETECTOR_H */