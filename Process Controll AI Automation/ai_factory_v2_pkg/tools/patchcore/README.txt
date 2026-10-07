PatchCore 실험 도구 (상태: 실험 중, 현장 미적용)
==================================================
양품 사진만으로 학습하는 이상 탐지. 2026-10-06~07 시험 결과와 사용법.

[결과 요약]
- 집 PC(anomalib 2.6, NVIDIA)에서 학습: 시험 사진 AUROC 1.0, 문턱 0.164 (v1 모델 전용)
- 파랑 테이프가 가장 약함 → 색 덩어리 규칙(문턱 260px, 640x480 기준)으로 보완하면 양쪽 모두 구분
- 현장 WSL 화면에서는 실패: 학습 사진을 Windows 카메라 앱으로 찍어 화면 처리 방식이 달랐음
  (WSL 양품도 0.30~0.47 → NG). 밝기를 맞춰도 해결 안 됨
- 다음: 현장 카메라 설정(노출·화이트밸런스 고정)을 정한 뒤 cap.py 로 WSL 에서 다시 찍어 재학습

[파일]
  집 PC (anomalib 환경)
    train_patchcore.py   학습 + OpenVINO 변환 (root 경로를 사진 폴더로)
    score_check.py       시험 사진 점수 → 양품 최고 / 불량 최저 / 추천 문턱
    color_check2.py      색 덩어리(가장 큰 유채색 영역) 크기 → 색 규칙 문턱 정하기
  현장 PC (uv 환경: openvino, opencv-python, numpy, pyyaml)
    check_model.py       OpenVINO 만으로 점수 계산, 장치별 속도 (anomalib 불필요)
    cap.py               WSL 카메라 원본 촬영 (s 저장, q/ESC 종료, 평균 밝기 표시)
    score_dir.py         폴더 사진의 PatchCore 점수 + 색 덩어리 + 평균색

[사진 폴더 구조]
  bolt/good/       학습용 양품 (60장 이상)
  bolt/good_test/  시험용 양품 (학습에 안 쓴 볼트)
  bolt/defect/     시험용 불량 (파일 이름 앞을 색 이름으로: blue1.jpg …)

[현장 uv 환경 만들기]
  cd ~/work/test && uv init --bare --python 3.12
  uv add "openvino==2026.4.0" opencv-python numpy pyyaml
  모델: models/patchcore_v1/model.xml, model.bin (집 PC weights/openvino 폴더 내용)
