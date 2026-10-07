"""
YOLOv8 모델(.pt) → ONNX / OpenVINO IR 변환 스크립트

[처음 동작 확인용 - 학습된 모델이 없어도 됨]
    python scripts/export_yolov8.py --weights yolov8n.pt --demo
    → yolov8n(COCO 80클래스) 자동 다운로드 → models/yolov8n.onnx
    → config/coco.txt, samples/bus.jpg 생성 → config/demo_config.yaml 로 바로 실행 가능

[내 모델 변환]  검출(detect)·분류(-cls) 모두 가능, 입력 크기는 모델 종류에 맞춰 자동 선택
    python scripts/export_yolov8.py --weights models/best.pt
    → models/best.onnx, models/best_openvino_model/best.xml, config/best_classes.txt

    (선택) INT8:  --int8 --data 경로/data.yaml
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent   # 프로젝트 폴더
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

p = argparse.ArgumentParser()
p.add_argument("--weights", default="models/best.pt", help="YOLOv8 가중치 (.pt)")
p.add_argument("--imgsz", type=int, default=None, help="입력 크기 (생략 시 검출 640 / 분류 224)")
p.add_argument("--demo", action="store_true", help="동작 확인용 샘플 이미지/클래스 파일도 생성")
p.add_argument("--no-ir", action="store_true", help="OpenVINO IR 변환 생략")
p.add_argument("--int8", action="store_true", help="OpenVINO INT8 양자화도 생성 (--data 필요)")
p.add_argument("--data", default=None, help="INT8 보정용 data.yaml")
args = p.parse_args()


def move_into_models(src: Path) -> Path:
    """export 결과를 models/ 폴더로 옮김 (이미 models/ 안이면 그대로)"""
    src = Path(src)
    dst = MODELS / src.name
    if src.resolve() != dst.resolve():
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        shutil.move(str(src), str(dst))
    return dst


model = YOLO(args.weights)
if args.imgsz is None:
    # 학습 때 크기가 가중치에 저장돼 있으면 그 값을, 없으면 종류별 기본값 사용
    saved = (getattr(model, "overrides", {}) or {}).get("imgsz")
    args.imgsz = saved if isinstance(saved, int) else (224 if model.task == "classify" else 640)
print(f"[정보] 종류={model.task}, 입력={args.imgsz}, 클래스 {len(model.names)}개: "
      f"{list(model.names.values())[:10]} ...")

# 1) ONNX : 고정 입력(dynamic=False)이 GPU 에서 가장 빠름. NMS 는 C++ 에서 처리
onnx_path = move_into_models(model.export(format="onnx", imgsz=args.imgsz, opset=17,
                                          dynamic=False, simplify=True))
print(f"[완료] ONNX  → {onnx_path.relative_to(ROOT)}")

# 2) OpenVINO IR (FP16) : OpenVINO 백엔드에서 로딩이 더 빠름
if not args.no_ir:
    ir_dir = move_into_models(model.export(format="openvino", imgsz=args.imgsz, half=True,
                                           dynamic=False))
    xml = next(ir_dir.glob("*.xml"))
    print(f"[완료] IR    → {xml.relative_to(ROOT)}")

# 3) (선택) INT8
if args.int8:
    if not args.data:
        raise SystemExit("--int8 은 --data data.yaml 이 필요합니다.")
    ir8 = move_into_models(model.export(format="openvino", imgsz=args.imgsz, int8=True,
                                        data=args.data))
    print(f"[완료] INT8  → {ir8.relative_to(ROOT)}")

# 4) 클래스 파일 자동 생성 (학습 순서 그대로)
stem = Path(args.weights).stem
names_file = ROOT / "config" / ("coco.txt" if args.demo else f"{stem}_classes.txt")
names_file.write_text("\n".join(model.names[i] for i in range(len(model.names))) + "\n",
                      encoding="utf-8")
print(f"[완료] 클래스 → {names_file.relative_to(ROOT)}")

# 5) 데모용 샘플 이미지
if args.demo:
    from ultralytics.utils import ASSETS
    (ROOT / "samples").mkdir(exist_ok=True)
    for img in ASSETS.glob("*.jpg"):
        shutil.copy(img, ROOT / "samples" / img.name)
    print("[완료] 샘플 이미지 → samples/  (config/demo_config.yaml 로 실행하세요)")
