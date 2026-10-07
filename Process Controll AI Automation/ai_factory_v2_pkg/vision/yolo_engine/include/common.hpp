#pragma once
// =============================================================================
//  common.hpp : 백엔드(OpenVINO / ONNX Runtime)와 무관한 공통 기능
//   - Detection 구조체
//   - 레터박스(Letterbox) 전처리
//   - YOLOv8 출력 디코딩 + NMS 후처리
//   - 클래스 이름 로드, 시간 문자열 등 유틸
// =============================================================================
#include <opencv2/core.hpp>
#include <string>
#include <vector>

namespace mfg {

// 검출 결과 1개
struct Detection {
    int      classId    = -1;   // 클래스 번호 (classes.txt 의 줄 번호, 0부터)
    float    confidence = 0.f;  // 신뢰도 (0~1)
    cv::Rect box;               // 원본 이미지 좌표계의 박스
};

// 분류 결과 1개 (Top-K 중 하나)
struct Classification {
    int   classId = -1;
    float score   = 0.f;   // 확률 (0~1)
};

// 레터박스 변환 정보 (결과 좌표를 원본으로 되돌릴 때 필요)
struct LetterboxInfo {
    float scale = 1.f;  // 원본 → 모델입력 배율
    int   padX  = 0;    // 좌측 여백(px)
    int   padY  = 0;    // 상단 여백(px)
};

// -----------------------------------------------------------------------------
// 레터박스: 원본 비율을 유지한 채 target 크기에 맞추고 남는 부분은 회색(114)으로 채움.
// YOLOv8 학습 시 사용된 방식과 동일해야 정확도가 유지됩니다.
// -----------------------------------------------------------------------------
cv::Mat letterbox(const cv::Mat& src, const cv::Size& target, LetterboxInfo& info,
                  const cv::Scalar& padColor = cv::Scalar(114, 114, 114));

// -----------------------------------------------------------------------------
// 분류 모델 전처리 (Ultralytics classify_transforms 와 동일한 방식)
//   1) 짧은 변을 size 로 리사이즈 (비율 유지)  2) 가운데를 size x size 로 자르기
// 레터박스(회색 여백)를 쓰는 검출 모델과 전처리가 다르므로 주의!
// -----------------------------------------------------------------------------
cv::Mat centerCropResize(const cv::Mat& src, int size);

// 확률 배열에서 상위 K개 추출. 합이 1이 아니면(softmax 없는 모델) softmax 를 적용
std::vector<Classification> topK(const float* probs, int numClasses, int k);

// -----------------------------------------------------------------------------
// BGR(uint8) 이미지를 RGB, 0~1 float, NCHW 배열로 변환 (ONNX Runtime 입력용)
// blob 은 재사용되므로 매 프레임 메모리 할당이 일어나지 않습니다.
// -----------------------------------------------------------------------------
void toNchwBlob(const cv::Mat& bgr, std::vector<float>& blob);

// -----------------------------------------------------------------------------
// YOLOv8 출력 디코딩 + NMS
//   data       : 출력 텐서 포인터
//   dim1, dim2 : 출력 shape [1, dim1, dim2]
//                기본 YOLOv8 = [1, 4+클래스수, 8400] (자동으로 전치 여부 판별)
//   lb         : 레터박스 정보, origSize : 원본 이미지 크기
// -----------------------------------------------------------------------------
std::vector<Detection> postprocessYolov8(const float* data, int dim1, int dim2,
                                         const LetterboxInfo& lb, const cv::Size& origSize,
                                         float confThreshold, float nmsThreshold,
                                         int maxDetections = 300);

// 클래스별(Class-aware) NMS : 같은 클래스끼리만 겹침을 제거
std::vector<Detection> nms(std::vector<Detection> dets, float iouThreshold, int maxDetections);

// classes.txt 로드 (한 줄에 클래스 이름 하나)
std::vector<std::string> loadClassNames(const std::string& path);

// 클래스 이름 안전 조회 (범위 밖이면 "cls{id}")
std::string className(const std::vector<std::string>& names, int id);

// 현재 시각 문자열. withMillis=true 이면 ".123" 밀리초 추가
std::string nowString(const char* fmt = "%Y-%m-%d %H:%M:%S", bool withMillis = false);

// 흑백(산업용 모노 카메라)/BGRA 입력을 3채널 BGR 로 통일
void ensureBgr(cv::Mat& frame);

}  // namespace mfg
