// =============================================================================
//  yolo_mfg : 제조업용 YOLOv8 개체탐지(검사) 프로그램 - 메인
//
//  실행:  yolo_mfg [설정파일.yaml] [--bench]
//         설정의 task 로 모드 선택 : detect(검출, 박스) | classify(분류, 부품 단위 OK/NG)
//         --bench : 첫 프레임으로 200회 추론 속도만 측정하고 종료
//
//  전체 흐름
//   ① 설정 로드 → ② 클래스 로드 → ③ 검출기 생성(OpenVINO/ORT) → ④ 워밍업
//   → ⑤ 입력 열기(카메라/영상/이미지) → ⑥ [프레임 읽기 → 추론 → 판정 → 기록 → 표시] 반복
//
//  키 조작:  ESC/q = 종료,  SPACE = 일시정지,  s = 현재 화면 저장
// =============================================================================
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>  // 콘솔 UTF-8 출력용
#endif

#include "common.hpp"
#include "config.hpp"
#include "inspection.hpp"
#include "yolo_tasks.hpp"

#ifdef USE_OPENVINO
#include "openvino_engine.hpp"   // resolveOpenVinoDevice()
#endif

#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/videoio.hpp>

#include <chrono>

#include <algorithm>
#include <filesystem>
#include <functional>
#include <map>
#include <iostream>
#include <memory>

using namespace mfg;
namespace fs = std::filesystem;

// =============================================================================
//  FrameSource : 카메라 / 영상 / 단일 이미지 / 이미지 폴더를 하나의 방식으로 읽기
//  ※ Basler, HIKROBOT 등 산업용 카메라는 제조사 SDK 로 이 클래스를 교체하면 됩니다.
// =============================================================================
class FrameSource {
public:
    bool open(const std::string& src, int camW, int camH, int camFps, const std::string& fourcc) {
        static const std::vector<std::string> imgExt = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"};
        auto isImage = [&](const fs::path& p) {
            std::string e = p.extension().string();
            std::transform(e.begin(), e.end(), e.begin(), ::tolower);
            return std::find(imgExt.begin(), imgExt.end(), e) != imgExt.end();
        };

        // (1) 숫자만 → 카메라 번호
        if (!src.empty() && std::all_of(src.begin(), src.end(), ::isdigit)) {
#ifdef _WIN32
            cap_.open(std::stoi(src), cv::CAP_MSMF);
#else
            cap_.open(std::stoi(src), cv::CAP_V4L2);  // 리눅스/WSL: /dev/videoN
#endif
            if (!cap_.isOpened()) return false;
            // 순서 중요: 압축 형식(FOURCC)을 먼저 정해야 고해상도가 허용되는 카메라가 많음
            if (fourcc.size() == 4)
                cap_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc(fourcc[0], fourcc[1], fourcc[2], fourcc[3]));
            cap_.set(cv::CAP_PROP_FRAME_WIDTH, camW);
            cap_.set(cv::CAP_PROP_FRAME_HEIGHT, camH);
            cap_.set(cv::CAP_PROP_FPS, camFps);
            cap_.set(cv::CAP_PROP_BUFFERSIZE, 1);  // 지연 최소화(지원 카메라 한정)

            // 카메라가 실제로 수락한 값 출력 (요청값과 다를 수 있음)
            const int f = static_cast<int>(cap_.get(cv::CAP_PROP_FOURCC));
            const std::string got{static_cast<char>(f & 0xFF), static_cast<char>((f >> 8) & 0xFF),
                                  static_cast<char>((f >> 16) & 0xFF), static_cast<char>((f >> 24) & 0xFF)};
            std::cout << "[입력] 카메라 " << src << " : " << cap_.get(cv::CAP_PROP_FRAME_WIDTH) << "x"
                      << cap_.get(cv::CAP_PROP_FRAME_HEIGHT) << " @" << cap_.get(cv::CAP_PROP_FPS)
                      << "fps, 형식=" << got << "\n";

            // 첫 프레임 확인 (WSL 에서 열리기만 하고 영상이 안 오는 경우를 바로 알림)
            cv::Mat probe;
            for (int i = 0; i < 30 && probe.empty(); ++i) cap_.read(probe);
            if (probe.empty()) {
                std::cerr << "[오류] 카메라가 열렸지만 영상이 들어오지 않습니다. "
                             "camera_width/height 를 640x480 으로 낮추거나 camera_fourcc 를 확인하세요.\n";
                return false;
            }
            return true;
        }
        // (2) 폴더 → 폴더 안의 이미지 전부
        if (fs::is_directory(src)) {
            for (const auto& e : fs::directory_iterator(src))
                if (e.is_regular_file() && isImage(e.path())) images_.push_back(e.path().string());
            std::sort(images_.begin(), images_.end());
            useImages_ = true;
            std::cout << "[입력] 이미지 폴더 : " << images_.size() << "장\n";
            return !images_.empty();
        }
        // (3) 단일 이미지
        if (isImage(src)) {
            images_   = {src};
            useImages_ = true;
            return fs::exists(src);
        }
        // (4) 그 외 → 영상 파일 / RTSP 주소
        cap_.open(src);
        std::cout << "[입력] 영상 : " << src << "\n";
        return cap_.isOpened();
    }

    bool read(cv::Mat& frame) {
        if (useImages_) {
            while (idx_ < images_.size()) {
                currentName_ = images_[idx_++];
                frame = cv::imread(currentName_, cv::IMREAD_UNCHANGED);
                if (!frame.empty()) return true;
                std::cerr << "[경고] 이미지를 읽을 수 없음: " << currentName_ << "\n";
            }
            return false;
        }
        return cap_.read(frame);
    }

    bool isStillImage() const { return useImages_; }

private:
    cv::VideoCapture         cap_;
    std::vector<std::string> images_;
    size_t                   idx_ = 0;
    bool                     useImages_ = false;
    std::string              currentName_;
};

// =============================================================================
//  추론 엔진 생성 (설정의 backend / device)
// =============================================================================
static std::unique_ptr<IEngine> makeEngine(const AppConfig& cfg) {
    std::string device = cfg.device;
#ifdef USE_OPENVINO
    // 디바이스 목록 출력 + AUTO_DGPU → GPU.1 등 외장 GPU 이름으로 변환
    device = resolveOpenVinoDevice(cfg.device, true);
#endif
    const int defaultSize = (cfg.task == "classify") ? 224 : 640;
    return createEngine(cfg.backend, cfg.modelPath, device, cfg.cacheDir, cfg.cpuThreads, defaultSize);
}

// =============================================================================
//  속도 측정 모드 (전처리 + 추론 + 후처리 포함 시간)
// =============================================================================
static void runBenchmark(const std::string& backendName, const std::function<void()>& once,
                         int iters = 200) {
    std::cout << "[벤치마크] " << backendName << " / " << iters << "회 측정 중...\n";
    std::vector<double> times;
    times.reserve(iters);
    for (int i = 0; i < iters; ++i) {
        cv::TickMeter tm;
        tm.start();
        once();
        tm.stop();
        times.push_back(tm.getTimeMilli());
    }
    std::sort(times.begin(), times.end());
    double sum = 0;
    for (double t : times) sum += t;
    std::cout << cv::format("  평균 %.2f ms (%.1f FPS) | 최소 %.2f | 중앙 %.2f | 99%% %.2f ms\n",
                            sum / iters, 1000.0 * iters / sum, times.front(), times[iters / 2],
                            times[static_cast<size_t>(iters * 0.99)]);
    std::cout << "  (전처리 + 추론 + 후처리 포함 시간)\n";
}

// =============================================================================
int main(int argc, char** argv) {
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);  // 콘솔 한글 깨짐 방지
#endif

    // ---------------------------------------------------------------- ① 인자/설정
    std::string cfgPath = "config/app_config.yaml";
    bool bench = false;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--bench") bench = true;
        else cfgPath = a;
    }

    AppConfig cfg;
    if (!loadConfig(cfgPath, cfg)) return 1;
    printConfig(cfg);

    // ---------------------------------------------------------------- ② 클래스
    const auto names = loadClassNames(cfg.classesPath);
    std::cout << "[클래스] " << names.size() << "개 로드\n";

    // 불량 클래스 이름 → 번호 변환
    std::set<int> defectIds;
    for (const auto& dn : cfg.defectClasses) {
        auto it = std::find(names.begin(), names.end(), dn);
        if (it != names.end()) defectIds.insert(static_cast<int>(it - names.begin()));
        else std::cerr << "[경고] defect_classes 의 '" << dn << "' 가 classes.txt 에 없습니다.\n";
    }

    // 출력 폴더
    const std::string ngDir = cfg.outputDir + "/ng_images";
    fs::create_directories(ngDir);
    if (!cfg.cacheDir.empty()) fs::create_directories(cfg.cacheDir);

    // ---------------------------------------------------------------- ③ 모델 (검출 또는 분류)
    const bool isClassify = (cfg.task == "classify");
    if (!isClassify && cfg.task != "detect") {
        std::cerr << "[오류] task 는 detect 또는 classify 여야 합니다: " << cfg.task << "\n";
        return 1;
    }
    std::unique_ptr<YoloDetector>   detector;
    std::unique_ptr<YoloClassifier> classifier;
    std::string backendName;
    try {
        auto engine = makeEngine(cfg);
        if (isClassify) {
            classifier  = std::make_unique<YoloClassifier>(std::move(engine));
            backendName = classifier->backendName() + " / classify";
        } else {
            detector    = std::make_unique<YoloDetector>(std::move(engine));
            backendName = detector->backendName() + " / detect";
        }
    } catch (const std::exception& e) {
        std::cerr << "[오류] 모델 생성 실패: " << e.what() << "\n";
        return 1;
    }

    std::set<int> okIds;  // 분류 적극 판정 클래스 (ok_classes)
    for (const auto& on : cfg.okClasses) {
        auto it = std::find(names.begin(), names.end(), on);
        if (it != names.end()) okIds.insert(static_cast<int>(it - names.begin()));
        else std::cerr << "[경고] ok_classes 의 '" << on << "' 가 클래스 파일에 없습니다.\n";
    }
    Inspector inspector(cfg.roi, defectIds, cfg.minBoxArea, okIds);

    // 프레임 1장을 검사하는 함수 (모드에 따라 내부 처리만 다름)
    //  - 검출 : 프레임 전체에서 불량 위치를 찾고, ROI 안의 박스로 판정
    //  - 분류 : ROI 영역(없으면 전체)을 잘라 부품 하나로 보고 OK/NG 분류
    auto inspect = [&](const cv::Mat& frame) -> InspectionResult {
        if (isClassify) {
            const cv::Rect roi = inspector.effectiveRoi(frame.size());
            return inspector.judgeClassification(classifier->classify(frame(roi), cfg.topK), roi,
                                                 cfg.confThreshold);
        }
        return inspector.judge(detector->detect(frame, cfg.confThreshold, cfg.nmsThreshold),
                               frame.size());
    };

    // ---------------------------------------------------------------- ④ 워밍업
    // GPU 는 첫 몇 번의 추론이 느리므로 미리 돌려 둠 (첫 제품 판정 지연 방지)
    {
        const cv::Mat dummy(cv::Size(640, 480), CV_8UC3, cv::Scalar(114, 114, 114));
        for (int i = 0; i < 5; ++i) inspect(dummy);
        std::cout << "[준비] 워밍업 완료\n";
    }

    // ---------------------------------------------------------------- ⑤ 입력
    FrameSource source;
    if (!source.open(cfg.source, cfg.cameraWidth, cfg.cameraHeight, cfg.cameraFps, cfg.cameraFourcc)) {
        std::cerr << "[오류] 입력을 열 수 없습니다: " << cfg.source << "\n";
        return 1;
    }

    if (bench) {
        cv::Mat f;
        if (!source.read(f) || f.empty()) { std::cerr << "[오류] 프레임 없음\n"; return 1; }
        ensureBgr(f);
        runBenchmark(backendName, [&] { inspect(f); });
        return 0;
    }
    CsvLogger logger;
    logger.open(cfg.outputDir + "/inspection_" + nowString("%Y%m%d_%H%M%S") + ".csv");

    const std::string winName = "YOLOv8 Manufacturing Inspection";
    if (cfg.showWindow) cv::namedWindow(winName, cv::WINDOW_NORMAL);

    // ---------------------------------------------------------------- 트리거 / 이벤트 설정
    const bool useTrigger    = (cfg.partTrigger == "background");   // 화면 변화로 부품 감지
    const bool manualTrigger = (cfg.partTrigger == "manual");       // 's' 키를 누를 때만 판정
    const bool partMode      = useTrigger || manualTrigger;         // 부품 1개 = 판정 1번
    if (!partMode && cfg.partTrigger != "none") {
        std::cerr << "[오류] part_trigger 는 none / background / manual 중 하나여야 합니다: " << cfg.partTrigger << "\n";
        return 1;
    }
    bool eventOutput = cfg.eventOutput;
    if (eventOutput && !partMode) {
        // 안전장치: 프레임마다 이벤트를 내보내면 빈 화면·같은 부품이 반복 NG → 라인이 계속 정지
        std::cerr << "[경고] event_output 은 part_trigger: background 일 때만 사용됩니다. (이벤트 끔)\n";
        eventOutput = false;
    }
    PartTrigger trigger(cfg.trigger);
    if (useTrigger)
        std::cout << "[트리거] 배경 학습 중... 처음 " << cfg.trigger.bgFrames
                  << "프레임 동안 ROI 를 비워 두세요. (다시 학습: 'b' 키)\n";
    if (manualTrigger)
        std::cout << "[수동 판정] 부품을 놓고 검사 창에서 's' 키를 누르면 " << cfg.trigger.inspectFrames
                  << "장을 찍어 1번 판정합니다. (화면 저장: 'c' 키)\n";
    int manualRemaining = 0;  // 수동 판정: 남은 촬영 장수

    // 부품 1개 동안 모은 프레임 결과 → 최종 판정 1개
    std::vector<InspectionResult> partResults;
    std::vector<cv::Mat>          partImages;
    double                        partInferMs = 0.0;
    long long                     partSeq = 0;
    InspectionResult              lastPart;      // 화면에 표시할 마지막 부품 판정
    bool                          hasPart = false;

    auto aggregate = [&](const cv::Rect& roi, size_t& pickIdx) -> InspectionResult {
        pickIdx = partResults.size() - 1;
        if (isClassify) {
            // 분류: 프레임별 확률을 평균 → 평균 확률로 최종 판정 (한 프레임 흔들림에 강함)
            std::map<int, double> sum;
            for (const auto& r : partResults)
                for (const auto& c : r.topk) sum[c.classId] += c.score;
            std::vector<Classification> avg;
            for (const auto& [id, v] : sum) avg.push_back({id, static_cast<float>(v / partResults.size())});
            std::sort(avg.begin(), avg.end(), [](auto& a, auto& b) { return a.score > b.score; });
            if (static_cast<int>(avg.size()) > cfg.topK) avg.resize(cfg.topK);
            return inspector.judgeClassification(avg, roi, cfg.confThreshold);
        }
        // 검출: 절반 이상의 프레임이 NG 면 NG, 그중 불량 신뢰도가 가장 높은 프레임을 대표로
        size_t ngCount = 0;
        float  best = -1.f;
        for (size_t i = 0; i < partResults.size(); ++i) {
            if (partResults[i].ok) continue;
            ++ngCount;
            if (partResults[i].defects.front().confidence > best) { best = partResults[i].defects.front().confidence; pickIdx = i; }
        }
        if (ngCount * 2 >= partResults.size() && ngCount > 0) return partResults[pickIdx];
        for (size_t i = partResults.size(); i-- > 0;)
            if (partResults[i].ok) { pickIdx = i; return partResults[i]; }
        return partResults.back();
    };

    auto jsonStr = [](const std::string& v) {
        std::string o = "\"";
        for (char c : v) { if (c == '"' || c == '\\') o += '\\'; o += c; }
        return o + "\"";
    };

    // ---------------------------------------------------------------- ⑥ 메인 루프
    cv::Mat frame, display;
    ProductionStats stats;
    long long frameIdx = 0;
    double fpsEma = 0.0;       // 처리 속도 (추론~기록, 카메라 대기 제외)
    double inputFpsEma = 0.0;  // 입력 속도 (프레임 도착 간격 = 실제 카메라 속도)
    auto lastFrameAt = std::chrono::steady_clock::time_point{};
    bool paused = false;
    auto lastNgSave = std::chrono::steady_clock::time_point{};  // NG 이미지 저장 간격 제한용

    while (true) {
        if (!paused) {
            if (!source.read(frame) || frame.empty()) {
                std::cout << "[종료] 입력 끝\n";
                break;
            }
            ensureBgr(frame);

            // 실제 입력 속도: 직전 프레임 도착 후 이번 프레임 도착까지의 간격
            const auto arrivedAt = std::chrono::steady_clock::now();
            if (lastFrameAt.time_since_epoch().count() != 0) {
                const double gapMs = std::chrono::duration<double, std::milli>(arrivedAt - lastFrameAt).count();
                const double inNow = 1000.0 / std::max(gapMs, 1e-3);
                inputFpsEma = (inputFpsEma == 0.0) ? inNow : 0.9 * inputFpsEma + 0.1 * inNow;
            }
            lastFrameAt = arrivedAt;

            cv::TickMeter tmLoop;
            tmLoop.start();
            const cv::Rect roiNow = inspector.effectiveRoi(frame.size());

            // (a) 추론 + (b) 판정
            //   트리거 없음  : 매 프레임 판정 → 프레임 1장 = 판정 1번 (기존 방식)
            //   트리거 있음  : 부품이 도착했을 때만 판정 → 부품 1개 = 판정 1번
            bool             partDone = false;  // 이번 프레임에서 판정 1건이 확정되었는가
            InspectionResult done;               // 확정된 판정
            cv::Mat          doneImage;          // 확정 판정의 대표 이미지
            double           inferMs = 0.0;
            try {
                if (manualTrigger) {
                    if (manualRemaining > 0) {
                        cv::TickMeter tm; tm.start();
                        partResults.push_back(inspect(frame));
                        tm.stop();
                        inferMs = tm.getTimeMilli();
                        partInferMs += inferMs;
                        partImages.push_back(frame.clone());
                        if (--manualRemaining == 0) {
                            size_t pick = 0;
                            done      = aggregate(roiNow, pick);
                            doneImage = partImages[pick];
                            inferMs   = partInferMs / partResults.size();
                            partDone  = true;
                        }
                    }
                } else if (!useTrigger) {
                    cv::TickMeter tm; tm.start();
                    done = inspect(frame);
                    tm.stop();
                    inferMs = tm.getTimeMilli();
                    doneImage = frame;
                    partDone = true;
                } else {
                    const TriggerStep st = trigger.step(frame(roiNow));
                    if (st.inspect) {
                        cv::TickMeter tm; tm.start();
                        partResults.push_back(inspect(frame));
                        tm.stop();
                        inferMs = tm.getTimeMilli();
                        partInferMs += inferMs;
                        partImages.push_back(frame.clone());
                    }
                    if (st.finalize && !partResults.empty()) {
                        size_t pick = 0;
                        done      = aggregate(roiNow, pick);
                        doneImage = partImages[pick];
                        inferMs   = partInferMs / partResults.size();
                        partDone  = true;
                    }
                }
            } catch (const std::exception& e) {
                std::cerr << "[오류] 추론 실패: " << e.what() << "\n";
                continue;  // 한 프레임 실패로 라인이 멈추지 않도록 계속 진행
            }

            const int framesUsed = partMode ? static_cast<int>(partResults.size()) : 1;
            if (partDone) {
                stats.total++;
                done.ok ? stats.ok++ : stats.ng++;
                lastPart = done;
                hasPart  = true;
                ++partSeq;
            }

            // (c) 화면 그리기 : 마지막 확정 판정을 표시
            display = frame.clone();
            OverlayInfo info{backendName, inferMs, fpsEma, inputFpsEma, stats};
            if (manualTrigger) {
                if (!hasPart) info.banner = "PRESS S";
                info.extraLine = manualRemaining > 0
                                     ? cv::format("Manual: INSPECTING %d/%d", cfg.trigger.inspectFrames - manualRemaining,
                                                  cfg.trigger.inspectFrames)
                                     : cv::format("Manual: press S to inspect  parts %lld", partSeq);
            }
            if (useTrigger) {
                if (!hasPart) info.banner = trigger.state() == TriggerState::Learning ? "LEARN" : "READY";
                info.extraLine = cv::format("Trigger: %s  change %.1f%%  parts %lld", trigger.stateText().c_str(),
                                            trigger.changeRatio() * 100.0, partSeq);
            }
            drawOverlay(display, hasPart ? lastPart : InspectionResult{}, names, roiNow, info);

            if (partDone) {
                // (d) NG 이미지 저장 : 트리거 모드는 부품마다, 프레임 모드는 최소 간격 제한
                std::string savedPath;
                const auto now = std::chrono::steady_clock::now();
                const bool saveAllowed = partMode || source.isStillImage() ||
                    std::chrono::duration_cast<std::chrono::milliseconds>(now - lastNgSave).count() >= cfg.ngSaveIntervalMs;
                if (!done.ok && cfg.saveNgImages && saveAllowed) {
                    lastNgSave = now;
                    const std::string base = ngDir + "/NG_" + nowString("%Y%m%d_%H%M%S", true) +
                                             (partMode ? "_p" + std::to_string(partSeq) : "_f" + std::to_string(frameIdx));
                    cv::imwrite(base + "_raw.jpg", doneImage);
                    cv::imwrite(base + "_vis.jpg", display);
                    savedPath = fs::absolute(base + "_raw.jpg").lexically_normal().string();
                }

                // (e) CSV 기록 (트리거 모드: 부품 번호, 프레임 모드: 프레임 번호)
                logger.log(partMode ? partSeq : frameIdx, done, names, inferMs, savedPath);

                // (f) PdM 연동 이벤트 : '@@EVENT ' + JSON 한 줄 → vision_bridge.py 가 읽어 vision_link 로 전달
                if (eventOutput) {
                    std::string top1;
                    float top1Score = 0.f, pOk = 0.f;
                    for (const auto& c : done.topk) {
                        if (top1.empty()) { top1 = className(names, c.classId); top1Score = c.score; }
                        if (okIds.count(c.classId)) pOk = std::max(pOk, c.score);
                    }
                    cv::Rect bb = roiNow;
                    std::string defectClass;
                    float defectConf = 0.f;
                    if (!done.defects.empty()) {
                        bb = done.defects.front().box;
                        defectClass = className(names, done.defects.front().classId);
                        defectConf = done.defects.front().confidence;
                    }
                    std::cout << "@@EVENT {"
                              << "\"seq\":" << partSeq << ",\"ts\":" << jsonStr(nowString("%Y-%m-%d %H:%M:%S", true))
                              << ",\"verdict\":" << jsonStr(done.ok ? "OK" : "NG") << ",\"task\":" << jsonStr(cfg.task)
                              << ",\"top1\":" << jsonStr(top1) << ",\"top1_score\":" << top1Score
                              << ",\"p_ok\":" << pOk << ",\"defect_class\":" << jsonStr(defectClass)
                              << ",\"defect_conf\":" << defectConf
                              << ",\"bbox\":[" << bb.x << "," << bb.y << "," << bb.x + bb.width << "," << bb.y + bb.height << "]"
                              << ",\"inference_ms\":" << cv::format("%.2f", inferMs) << ",\"frames\":" << framesUsed
                              << ",\"image\":" << jsonStr(savedPath) << "}" << std::endl;  // endl = 즉시 전달(flush)
                }

                if (partMode) {  // 다음 부품 준비
                    partResults.clear();
                    partImages.clear();
                    partInferMs = 0.0;
                }
            }

            // (g) FPS (지수이동평균으로 부드럽게)
            tmLoop.stop();
            const double fpsNow = 1000.0 / std::max(tmLoop.getTimeMilli(), 1e-3);
            fpsEma = (fpsEma == 0.0) ? fpsNow : 0.9 * fpsEma + 0.1 * fpsNow;

            // 화면이 없을 때는 콘솔에 요약 출력 (트리거 모드는 부품마다)
            const bool printNow = partMode ? partDone : (frameIdx % 30 == 0 || source.isStillImage());
            if (!cfg.showWindow && printNow) {
                std::string top1;
                if (!done.topk.empty())
                    top1 = cv::format("  top1=%s(%.1f%%)", className(names, done.topk[0].classId).c_str(),
                                      done.topk[0].score * 100.0);
                std::cout << cv::format("[%lld] %s  infer=%.1fms  proc=%.0ffps  input=%.1ffps%s%s\n",
                                        partMode ? partSeq : frameIdx, done.ok ? "OK" : "NG", inferMs, fpsEma,
                                        inputFpsEma, top1.c_str(),
                                        partMode ? cv::format("  frames=%d", framesUsed).c_str() : "");
            }
            ++frameIdx;
        }

        // ---------------------------------------------------------- 키 입력
        if (cfg.showWindow) {
            cv::imshow(winName, display);
            // 이미지 모드: 키를 누르면 다음 장 / 영상·카메라: 1ms 대기
            const int key = cv::waitKey(source.isStillImage() && !paused ? 0 : (paused ? 30 : 1)) & 0xFF;
            if (key == 27 || key == 'q') break;
            if (key == ' ') paused = !paused;
            if (key == 'b' && useTrigger) {
                trigger.relearn();
                std::cout << "[트리거] 배경 다시 학습 (ROI 를 비워 두세요)\n";
            }
            if (key == 's' && manualTrigger) {          // 수동 판정 시작
                if (manualRemaining == 0) {
                    partResults.clear();
                    partImages.clear();
                    partInferMs     = 0.0;
                    manualRemaining = std::max(1, cfg.trigger.inspectFrames);
                    std::cout << "[수동 판정] 촬영 시작 (" << manualRemaining << "장)\n";
                }
            } else if (key == 's' || key == 'c') {      // 화면 저장 (수동 모드에서는 'c')
                const std::string p = cfg.outputDir + "/capture_" + nowString("%Y%m%d_%H%M%S") + ".jpg";
                cv::imwrite(p, display);
                std::cout << "[저장] " << p << "\n";
            }

        }
    }

    std::cout << cv::format("\n[결과] 총 %lld개  OK %lld  NG %lld  (NG율 %.2f%%)\n", stats.total,
                            stats.ok, stats.ng, stats.ngRate());
    cv::destroyAllWindows();
    return 0;
}
