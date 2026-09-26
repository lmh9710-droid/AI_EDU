import os
from ultralytics import YOLO

def main():
    # 1. 기초 모델 로드 (가장 가볍고 빠른 Nano 모델 선택)
    # 자동으로 모델이 다운로드되며, GPU 메모리 부담이 적습니다.
    model = YOLO("yolov8n.pt") 

    # 2. 내 데이터셋의 data.yaml 절대 경로 자동 계산
    current_dir = os.getcwd()
    data_yaml_path = os.path.join(current_dir, "datasets", "data.yaml")

    print("=" * 60)
    print(f"🚀 YOLOv8 객체 탐지 학습을 시작합니다!")
    print(f"📂 데이터셋 설정 파일: {data_yaml_path}")
    print("=" * 60)

    # 3. 모델 학습 시작 (핵심 옵션 설정)
    model.train(
        data=data_yaml_path,  # data.yaml 절대 경로
        epochs=50,            # 전체 데이터를 50번 반복 학습 (기본 테스트용으로 적당)
        imgsz=640,            # 이미지 크기 (Roboflow 표준 640)
        batch=16,             # 한 번에 처리할 이미지 수 (OOM 에러 시 8이나 4로 줄이세요)
        device=0,             # WSL 내부의 0번 NVIDIA GPU 사용 (CPU로 하려면 'cpu')
        workers=4,            # 데이터 로딩 속도를 높이기 위한 프로세스 수
        project="Detection",  # 결과물이 저장될 폴더 이름
        name="yolov8_result", # 결과물 하위 폴더 이름
        exist_ok=True,        # 재실행 시 기존 폴더에 덮어쓰기 허용
        plots=True            # 학습 결과 그래프 및 예측 샘플 이미지 자동 생성
    )

    print("\n🎉 학습이 완료되었습니다!")
    print(f"📊 결과 저장 위치: {os.path.join(current_dir, 'Detection', 'yolov8_result')}")

if __name__ == "__main__":
    main()
