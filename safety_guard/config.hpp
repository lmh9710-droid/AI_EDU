#pragma once
#include <string>
#include <opencv2/opencv.hpp>

namespace SafetyGuard {
    const double MM_PER_PX = 0.264; /*1 픽셀당 mm 환산값*/
    const int COOLDOWN_SECONDS =2;

    /* 위험 단계별 기준(mm) */
    const double DANGER_LEVEL_1 = 5.0;
    const double DANGER_LEVEL_2 =10.0;
    const double DANGER_LEVEL_3 = 20.0;

    /* 침투 Log*/
    struct IntrusionLog {
        std::string timestamp;
        double max_penetration_mm;
        std::string danger_level;
        std::string image_path;
    };

    
}