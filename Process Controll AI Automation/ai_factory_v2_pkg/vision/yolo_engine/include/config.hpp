#pragma once
// =============================================================================
//  config.hpp : config/app_config.yaml 설정 로드
//  (OpenCV FileStorage 사용 → 추가 라이브러리 불필요)
// =============================================================================
#include "part_trigger.hpp"

#include <opencv2/core.hpp>
#include <string>
#include <vector>

namespace mfg {

struct AppConfig {
    // ---- 추론 ----
    std::string task        = "detect";           // detect(검출) | classify(분류)
    int         topK        = 5;                  // 분류: 상위 몇 개까지 표시/기록할지
    std::string backend     = "openvino";         // openvino | onnxruntime
    std::string device      = "AUTO_DGPU";        // AUTO_DGPU | GPU.0 | GPU.1 | GPU | CPU
    std::string modelPath   = "models/best.onnx"; // .onnx 또는 .xml(OpenVINO IR)
    std::string classesPath = "config/classes.txt";
    std::string cacheDir    = "model_cache";
    float confThreshold = 0.35f;
    float nmsThreshold  = 0.45f;
    int   cpuThreads    = 6;

    // ---- 입력 ----
    std::string source = "0";   // 카메라 번호 / 영상 파일 / 이미지 파일 / 이미지 폴더
    int cameraWidth  = 1920;
    int cameraHeight = 1080;
    int cameraFps    = 30;
    std::string cameraFourcc = "MJPG";  // MJPG(압축) 권장: WSL usbipd 는 USB 대역폭이 좁아 YUYV 는 끊김

    // NG 이미지 저장 최소 간격(ms). 카메라는 초당 30장이라 매 프레임 저장하면 디스크가 금방 참
    int ngSaveIntervalMs = 1000;

    // ---- 검사(판정) ----
    cv::Rect roi;                            // 비어 있으면 전체 화면
    std::vector<std::string> defectClasses;  // 비어 있으면 모든 클래스를 불량으로 간주
    // 분류 전용 '적극 판정' : 지정하면 1순위가 이 클래스이고 확률 >= conf 일 때만 OK,
    // 그 외(불량 클래스, 확신 부족, 부품 없음 등)는 모두 NG → 애매한 부품이 양품으로 나가지 않음
    std::vector<std::string> okClasses;
    int minBoxArea = 0;                      // 이보다 작은 박스는 무시(노이즈 제거)

    // ---- 부품 감지 트리거 / PdM 연동 ----
    std::string   partTrigger = "none";   // none(프레임마다 판정) | background(부품 도착 시 1번 판정) | manual(s 키로 1번 판정)
    TriggerConfig trigger;                // background 트리거 세부값
    bool          eventOutput = false;    // 부품 판정마다 '@@EVENT {json}' 한 줄 출력 (vision_bridge.py 가 읽음)

    // ---- 출력 ----
    std::string outputDir = "results";
    bool saveNgImages = true;
    bool showWindow   = true;
};

bool loadConfig(const std::string& path, AppConfig& cfg);
void printConfig(const AppConfig& cfg);

}  // namespace mfg
