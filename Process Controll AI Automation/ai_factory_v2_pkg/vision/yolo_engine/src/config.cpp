#include "config.hpp"

#include <iostream>

namespace mfg {

bool loadConfig(const std::string& path, AppConfig& cfg) {
    cv::FileStorage fs;
    try {
        fs.open(path, cv::FileStorage::READ);
    } catch (const cv::Exception& e) {
        // 빈 파일, 첫 줄 %YAML:1.0 누락, 들여쓰기 오류 등
        std::cerr << "[오류] 설정 파일 형식이 잘못되었습니다: " << path << "\n"
                  << "       (빈 파일이 아닌지, 첫 줄이 %YAML:1.0 인지 확인)\n";
        return false;
    }
    if (!fs.isOpened()) {
        std::cerr << "[오류] 설정 파일을 열 수 없습니다: " << path << "\n";
        return false;
    }

    // 키가 없으면 기본값 유지하는 헬퍼들
    auto readStr = [&](const char* key, std::string& v) {
        const cv::FileNode n = fs[key];
        if (!n.empty()) v = static_cast<std::string>(n);
    };
    auto readInt = [&](const char* key, int& v) {
        const cv::FileNode n = fs[key];
        if (!n.empty()) v = static_cast<int>(n);
    };
    auto readFloat = [&](const char* key, float& v) {
        const cv::FileNode n = fs[key];
        if (!n.empty()) v = static_cast<float>(n);
    };
    auto readBool = [&](const char* key, bool& v) {
        const cv::FileNode n = fs[key];
        if (!n.empty()) v = static_cast<int>(n) != 0;
    };

    readStr("task", cfg.task);
    readInt("topk", cfg.topK);
    readStr("backend", cfg.backend);
    readStr("device", cfg.device);
    readStr("model", cfg.modelPath);
    readStr("classes", cfg.classesPath);
    readStr("cache_dir", cfg.cacheDir);
    readFloat("conf_threshold", cfg.confThreshold);
    readFloat("nms_threshold", cfg.nmsThreshold);
    readInt("cpu_threads", cfg.cpuThreads);

    readStr("source", cfg.source);
    readInt("camera_width", cfg.cameraWidth);
    readInt("camera_height", cfg.cameraHeight);
    readInt("camera_fps", cfg.cameraFps);
    readStr("camera_fourcc", cfg.cameraFourcc);
    readInt("ng_save_interval_ms", cfg.ngSaveIntervalMs);

    // roi: [x, y, w, h]
    const cv::FileNode roiNode = fs["roi"];
    if (roiNode.isSeq() && roiNode.size() == 4) {
        cfg.roi = cv::Rect(static_cast<int>(roiNode[0]), static_cast<int>(roiNode[1]),
                           static_cast<int>(roiNode[2]), static_cast<int>(roiNode[3]));
    }

    // defect_classes: [ "scratch", "dent" ]
    const cv::FileNode dc = fs["defect_classes"];
    if (dc.isSeq()) {
        cfg.defectClasses.clear();
        for (auto it = dc.begin(); it != dc.end(); ++it)
            cfg.defectClasses.push_back(static_cast<std::string>(*it));
    }
    readInt("min_box_area", cfg.minBoxArea);
    const cv::FileNode okc = fs["ok_classes"];
    if (okc.isSeq()) {
        cfg.okClasses.clear();
        for (auto it = okc.begin(); it != okc.end(); ++it)
            cfg.okClasses.push_back(static_cast<std::string>(*it));
    }

    readStr("part_trigger", cfg.partTrigger);
    readInt("trigger_bg_frames", cfg.trigger.bgFrames);
    readInt("trigger_diff_threshold", cfg.trigger.diffThreshold);
    { float r = static_cast<float>(cfg.trigger.presenceRatio); readFloat("trigger_presence_ratio", r); cfg.trigger.presenceRatio = r; }
    readInt("trigger_settle_frames", cfg.trigger.settleFrames);
    readInt("trigger_inspect_frames", cfg.trigger.inspectFrames);
    readInt("trigger_clear_frames", cfg.trigger.clearFrames);
    readBool("event_output", cfg.eventOutput);
    readStr("output_dir", cfg.outputDir);
    readBool("save_ng_images", cfg.saveNgImages);
    readBool("show_window", cfg.showWindow);
    return true;
}

void printConfig(const AppConfig& c) {
    std::cout << "================ 설정 ================\n"
              << " task           : " << c.task << "\n"
              << " backend        : " << c.backend << "\n"
              << " device         : " << c.device << "\n"
              << " model          : " << c.modelPath << "\n"
              << " classes        : " << c.classesPath << "\n"
              << " source         : " << c.source << "\n"
              << " conf / nms     : " << c.confThreshold << " / " << c.nmsThreshold << "\n"
              << " roi            : " << (c.roi.area() > 0 ? cv::format("%d,%d,%d,%d", c.roi.x, c.roi.y, c.roi.width, c.roi.height) : std::string("전체")) << "\n"
              << " defect classes : ";
    if (c.defectClasses.empty()) std::cout << "(전체 클래스)";
    for (const auto& s : c.defectClasses) std::cout << s << " ";
    if (!c.okClasses.empty()) {
        std::cout << "\n ok classes     : ";
        for (const auto& s : c.okClasses) std::cout << s << " ";
        std::cout << " (적극 판정: 이 클래스로 확신할 때만 OK)";
    }
    std::cout << "\n part_trigger   : " << c.partTrigger << (c.eventOutput ? "  (event_output ON)" : "")
              << "\n output_dir     : " << c.outputDir << "\n"
              << "======================================\n";
}

}  // namespace mfg
