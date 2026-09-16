#include <iostream>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <opencv2/opencv.hpp>
#include "config.hpp"
#include "DatabaseManager.hpp"
#include "MotionAnalyzer.hpp"

// 현재 시간을 문자열로 포맷팅하는 헬퍼 함수
std::string getCurrentTimestamp() {
    auto now = std::chrono::system_clock::now();
    auto in_time_t = std::chrono::system_clock::to_time_t(now);
    std::stringstream ss;
    ss << std::put_time(std::localtime(&in_time_t), "%Y-%m-%d %H:%M:%S");
    return ss.str();
}

int main() {
    // 1. 카메라 초기화 (0번 웹캠 또는 동영상 경로)
    cv::VideoCapture cap(0);
    if (!cap.isOpened()) {
        std::cerr << "카메라를 열 수 없습니다." << std::endl;
        return -1;
    }

    // 2. 모듈 객체 생성 (ROI 설정: x=100, y=100, w=400, h=300)
    cv::Rect roi(100, 100, 400, 300);
    MotionAnalyzer analyzer(roi);
    DatabaseManager db("safety_guard.db");

    // 3. 3-Frame 차분을 위한 초기 프레임 버퍼링
    cv::Mat f1, f2, f3, gray1, gray2, gray3;
    cap >> f1; cap >> f2; cap >> f3;
    if(f1.empty() || f2.empty() || f3.empty()) return -1;

    cv::cvtColor(f1, gray1, cv::COLOR_BGR2GRAY);
    cv::cvtColor(f2, gray2, cv::COLOR_BGR2GRAY);
    cv::cvtColor(f3, gray3, cv::COLOR_BGR2GRAY);

    // 쿨다운 제어용 타이머 변수
    auto last_log_time = std::chrono::steady_clock::now();

    std::cout << "🛡 Safety Motion Guard 가동 중... (종료: ESC)" << std::endl;

    while (true) {
        cap >> f3;
        if (f3.empty()) break;
        cv::cvtColor(f3, gray3, cv::COLOR_BGR2GRAY);

        // [PROCESS] 3-Frame 차분 기반 움직임 마스크 생성
        cv::Mat motion_mask = analyzer.getMotionMask(gray1, gray2, gray3);

        // [PROCESS] 침투 분석 연산
        std::string danger_level = "SAFE";
        cv::Scalar UI_color = cv::Scalar(0, 255, 0);
        double penetration_mm = analyzer.calculatePenetration(motion_mask, danger_level, UI_color);

        // [UI RENDER] 라이브 뷰 화면에 정보 그리기
        cv::Mat display_frame = f2.clone();
        cv::rectangle(display_frame, roi, UI_color, 2); // ROI 경계 사각형
        
        std::string status_text = "Status: " + danger_level + " (" + std::to_string(penetration_mm).substr(0,4) + " mm)";
        cv::putText(display_frame, status_text, cv::Point(20, 40), cv::FONT_HERSHEY_SIMPLEX, 0.8, UI_color, 2);

        // [LOGGING] 위험 상황 발생 및 쿨다운 검증 시 DB 저장 및 캡처
        if (danger_level != "SAFE") {
            auto current_time = std::chrono::steady_clock::now();
            auto elapsed_seconds = std::chrono::duration_cast<std::chrono::seconds>(current_time - last_log_time).count();

            if (elapsed_seconds >= SafetyGuard::COOLDOWN_SECONDS) {
                std::string timestamp = getCurrentTimestamp();
                std::string img_name = "gallery/intrusion_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count()) + ".jpg";
                
                // 디렉토리 구조 검증 후 캡처 이미지 저장
                cv::imwrite(img_name, display_frame);

                // DB 로그 삽입
                SafetyGuard::IntrusionLog log{timestamp, penetration_mm, danger_level, img_name};
                if(db.insertLog(log)) {
                    std::cout << "🚨 [경보 추가] 단계: " << danger_level << " / 침투: " << penetration_mm << "mm" << std::endl;
                }
                last_log_time = current_time; // 타이머 리셋
            }
        }

        // [PANEL INTERACTION] 가로 병합 패널 시각화 (Live View | Motion Mask)
        cv::Mat mask_bgr;
        cv::cvtColor(motion_mask, mask_bgr, cv::COLOR_GRAY2BGR);
        cv::Mat combined_panel;
        cv::hconcat(display_frame, mask_bgr, combined_panel); // 가로 병합

        cv::imshow("Safety Motion Guard - Integrated Panel", combined_panel);

        // 프레임 시프트
        gray1 = gray2.clone();
        gray2 = gray3.clone();
        f2 = f3.clone();

        // ESC 키 입력 시 종료
        if (cv::waitKey(30) == 27) break;
    }

    cap.release();
    cv::destroyAllWindows();
    return 0;
}
