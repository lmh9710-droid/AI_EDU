import os
from ultralytics import YOLO

def main():
    # 1. 가중치 파일의 절대 경로 계산
    relative_path = "./runs/detect/Detection/yolov8_result/weights/best.pt"
    model_path = os.path.abspath(relative_path)
    
    print(f"🔍 가중치 파일 경로 확인: {model_path}")
    if not os.path.exists(model_path):
        print("❌ [경고] 해당 경로에 파일이 존재하지 않습니다!")
        return

    # 2. YOLO 모델 정의 (NameError 방지)
    model = YOLO(model_path)

    print(f"🔄 ONNX 포맷으로 변환을 시작합니다...")

    # 3. ONNX로 내보내기 (export)
    success_path = model.export(
        format="onnx",
        imgsz=640, 
        dynamic=True,          
        opset=12         
    )

    print(f"🎉 변환 완료! ONNX 파일 위치: {success_path}")

if __name__ == "__main__":
    main()
