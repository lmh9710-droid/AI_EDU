#pragma once
#include <opencv2/opencv.hpp>
#include <cmath>
#include "config.hpp"

class MotionAnalyzer {
    private: 
      cv::Mat prev_frame, curr_frame, next_frame;
      cv::Rect roi_boundary;
    
    public: 
      MotionAnalyzer(const cv::Rect& roi) : roi_boundary(roi) {}

      cv::Mat getMotionMask(const cv::Mat& f1, const cv::Mat& f2, const cv::Mat& f3) {
        cv::Mat diff1, diff2, motion_mask;

        /*프레임 간 차이 계산*/
        cv::absdiff(f1, f2, diff1);
        cv::absdiff(f2, f3, diff2);

        /* 비트 연산 (AND) 및 이진화 */
        cv::bitwise_and(diff1, diff2, motion_mask);
        cv::threshold(motion_mask, motion_mask, 25, 255, cv::THRESH_BINARY);
       
        /* 노이즈 제거 */
        cv::dilate(motion_mask, motion_mask, cv::Mat(), cv::Point(-1, -1), 2);
        return motion_mask;
      }

      double calculatePenetration(const cv::Mat& motion_mask, 
                                  std::string& out_danger_level,
                                  cv::Scalar& out_color) {
        
        cv::Mat roi_mask = motion_mask(roi_boundary);
        std::vector<std::vector<cv::Point>> contours;
        cv:findContours(roi_mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
        
        int max_pixel_depth = 0;

        for(const auto& contour : contours) {
            cv::Rect bounding_box = cv::boundingRect(contour);
            /* 경계선 침투 깊이 측정(ROI 상단 기준 아래로 내려온 픽셀 개수) */
            int depth = bounding_box.y + bounding_box.height;
            if ( depth > max_pixel_depth ) {
                max_pixel_depth =depth;
            }
        }
       
        /* mm 단위 변환 */
        double penetration_mm = max_pixel_depth * SafetyGuard::MM_PER_PX;
        
        /* 위험 단계 및 UI 색상 결정 */
        if(penetration_mm >= SafetyGuard::DANGER_LEVEL_3) {
            out_danger_level ="CRITICAL";
            out_color = cv::Scalar(0, 0, 255); /* Red */
        } else if (penetration_mm >= SafetyGuard::DANGER_LEVEL_2) {
            out_danger_level = "WARNING";
            out_color = cv::Scalar(0, 255, 255); /* yellow */
        } else if (penetration_mm >= SafetyGuard::DANGER_LEVEL_1) {
            out_danger_level = "CAUTION";
            out_color = cv::Scalar(0, 165, 255); /* Orange */
        } else {
            out_danger_level = "SAFE";
            out_color = cv::Scalar(0, 255, 0); /* Green */
        }

        return penetration_mm;
                                 
     }


};