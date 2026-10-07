"""
inspect_onnx.py : 외부에서 받은 ONNX 가 yolo_mfg(C++)에서 쓸 수 있는지 자동 점검

  사용법 (프로젝트 폴더에서):
    ~/yolo_libs/venv/bin/python scripts/inspect_onnx.py models/yolov8n.onnx
    ~/yolo_libs/venv/bin/python scripts/inspect_onnx.py models/yolov8n.onnx --write-config

  점검 항목
    [1] 파일 해시(SHA256)  - 배포처에 적힌 값과 비교해 위·변조/손상 확인
    [2] 입력 형식          - [1,3,H,W] float32 인지
    [3] 출력 형식          - YOLOv8/YOLO11 Detect [1, 4+nc, N] 또는 Classify [1, nc] 인지
                            (YOLOv5, YOLOX, NMS 내장형, 세그멘테이션 등 비호환 형식 판별)
    [4] 클래스 이름        - Ultralytics 메타데이터가 있으면 자동 추출
    [5] 실제 추론 테스트    - OpenVINO(CPU)로 한 번 돌려 박스 좌표 스케일 확인
  --write-config : config/test_config.yaml + 클래스 파일 자동 생성
"""
import argparse
import ast
import hashlib
import sys
from pathlib import Path

import numpy as np

try:
    import onnx
except ImportError:
    sys.exit("onnx 패키지가 필요합니다:  ~/yolo_libs/venv/bin/pip install onnx opencv-python-headless")

ROOT = Path(__file__).resolve().parent.parent
OK, NG, WARN = "\033[1;32m[통과]\033[0m", "\033[1;31m[불가]\033[0m", "\033[1;33m[주의]\033[0m"
COCO80_FILE = ROOT / "config" / "coco.txt"

p = argparse.ArgumentParser()
p.add_argument("model", help="점검할 .onnx 파일")
p.add_argument("--image", default=None, help="추론 테스트용 이미지 (기본: samples/ 의 첫 이미지)")
p.add_argument("--write-config", action="store_true", help="테스트용 설정 파일 자동 생성")
p.add_argument("--config-name", default="test_config.yaml", help="생성할 설정 파일 이름")
args = p.parse_args()

path = Path(args.model)
if not path.exists():
    sys.exit(f"파일이 없습니다: {path}")
fatal = False

# ---------------------------------------------------------------- [1] 해시
print(f"\n===== {path.name}  ({path.stat().st_size / 1e6:.1f} MB) =====")
sha = hashlib.sha256(path.read_bytes()).hexdigest()
print(f"[1] SHA256 : {sha}")
print("    → 다운로드 페이지에 적힌 SHA256 과 같은지 눈으로 비교하세요.")

model = onnx.load(str(path), load_external_data=False)
opset = max((o.version for o in model.opset_import if o.domain in ("", "ai.onnx")), default=0)
print(f"    opset {opset}, producer: {model.producer_name} {model.producer_version}")

meta = {m.key: m.value for m in model.metadata_props}
is_ultralytics = "names" in meta and ("Ultralytics" in meta.get("author", "") or "task" in meta)
task = "detect"

# ---------------------------------------------------------------- [2] 입력
init_names = {i.name for i in model.graph.initializer}
inputs = [i for i in model.graph.input if i.name not in init_names]


def shape_of(vi):
    return [d.dim_value if d.dim_value > 0 else (d.dim_param or "?") for d in vi.type.tensor_type.shape.dim]


DT = {1: "float32", 10: "float16", 2: "uint8"}
print("\n[2] 입력")
for i in inputs:
    print(f"    {i.name}: {shape_of(i)} {DT.get(i.type.tensor_type.elem_type, i.type.tensor_type.elem_type)}")
imgsz = 640
if len(inputs) != 1:
    print(f"    {NG} 입력이 {len(inputs)}개 → 단일 이미지 입력 모델만 지원"); fatal = True
else:
    s = shape_of(inputs[0])
    dt = inputs[0].type.tensor_type.elem_type
    if len(s) != 4 or s[1] != 3:
        print(f"    {NG} [1,3,H,W] 형식이 아님 (NHWC 모델일 수 있음)"); fatal = True
    else:
        if isinstance(s[2], int):
            imgsz = s[2]
            print(f"    {OK} 입력 크기 {s[3]}x{s[2]}")
        else:
            print(f"    {WARN} 동적 입력 → OpenVINO 는 640 으로 고정해 실행합니다")
    if dt == 10:
        print(f"    {WARN} float16 입력 모델 → OpenVINO 백엔드만 사용하세요 (ORT 백엔드는 float32 입력 전용)")
    elif dt != 1:
        print(f"    {NG} 입력 자료형이 float32 가 아님"); fatal = True

# ---------------------------------------------------------------- [3] 출력
print("\n[3] 출력")
outs = list(model.graph.output)
for o in outs:
    print(f"    {o.name}: {shape_of(o)}")
nc = None
o0 = shape_of(outs[0])
if len(outs) == 1 and len(o0) == 2 and isinstance(o0[1], int):
    # 분류 모델 : [1, 클래스수]
    task = "classify"
    nc = o0[1]
    print(f"    {OK} YOLO 분류(Classify) 형식, 클래스 {nc}개  → task: \"classify\"")
elif len(outs) > 1:
    print(f"    {NG} 출력이 {len(outs)}개 → 세그멘테이션/포즈 등 Detect 가 아닌 모델일 가능성 높음"); fatal = True
elif len(o0) != 3 or not all(isinstance(x, int) for x in o0[1:]):
    print(f"    {NG} 3차원 고정 출력이 아님"); fatal = True
else:
    a, b = o0[1], o0[2]
    ch, n = (a, b) if a < b else (b, a)
    v8_anchors = sum((imgsz // st) ** 2 for st in (8, 16, 32))  # 640 → 8400
    if ch in (6, 7) and n <= 1000:
        print(f"    {NG} [1,{n},{ch}] = NMS 내장(end-to-end) 형식 (YOLOv10/YOLO26 또는 nms=True export)")
        print("         → 코드가 NMS 후처리를 따로 하므로 호환 안 됨"); fatal = True
    elif n == 3 * v8_anchors:
        print(f"    {NG} 앵커 {n}개 = YOLOv5/v7 형식 (objectness 포함) → 호환 안 됨"); fatal = True
    elif n == v8_anchors and ch > 4 and a < b:
        nc = ch - 4
        print(f"    {OK} YOLOv8/YOLO11 Detect 형식, 채널 우선(표준), 클래스 {nc}개")
    elif n == v8_anchors and ch > 4:
        # [1, 8400, C] 앵커 우선 : 전치된 YOLOv8 일 수도 있지만 YOLOX 도 똑같은 모양!
        # YOLOX 는 objectness 점수가 따로 있고 전처리(/255 없음, 좌상단 패딩)도 달라 결과가 틀어짐
        if is_ultralytics and meta.get("task", "detect") == "detect":
            nc = ch - 4
            print(f"    {OK} 앵커 우선(전치형) YOLOv8 Detect, 클래스 {nc}개 (Ultralytics 메타데이터 확인)")
        else:
            print(f"    {NG} [1,{n},{ch}] 앵커 우선 형식인데 Ultralytics 메타데이터가 없음")
            print("         → YOLOX 등 다른 계열일 가능성이 높아 자동 판정 불가 (출처 확인 필요)")
            fatal = True
    else:
        print(f"    {WARN} 앵커 {n}개 (기대값 {v8_anchors}). 입력 크기와 출력이 맞는지 확인 필요")
        nc = ch - 4 if ch > 4 else None

# ---------------------------------------------------------------- [4] 클래스 이름
print("\n[4] 메타데이터")
names = None
for k in ("task", "imgsz", "description", "version"):
    if k in meta:
        print(f"    {k}: {meta[k]}")
if "names" in meta:
    try:
        d = ast.literal_eval(meta["names"])
        names = [d[i] for i in range(len(d))]
        print(f"    {OK} 클래스 이름 {len(names)}개 발견: {names[:8]}{' ...' if len(names) > 8 else ''}")
    except Exception:
        pass
if meta.get("task") not in (None, "detect", "classify"):
    print(f"    {NG} task={meta['task']} → detect / classify 모델만 지원"); fatal = True
elif meta.get("task") and meta["task"] != task:
    print(f"    {NG} 메타데이터 task={meta['task']} 와 출력 형식({task})이 다름"); fatal = True
if names is None:
    if task == "detect" and nc == 80 and COCO80_FILE.exists():
        names = COCO80_FILE.read_text(encoding="utf-8").split("\n")[:80]
        print(f"    {WARN} 이름 정보 없음 → 클래스 80개라 COCO 로 가정 (config/coco.txt)")
    else:
        print(f"    {WARN} 이름 정보 없음 → 배포처에서 클래스 목록을 받아 직접 작성하세요")
if names is not None and nc is not None and len(names) != nc:
    print(f"    {WARN} 이름 수({len(names)}) ≠ 출력 클래스 수({nc})")

# ---------------------------------------------------------------- [5] 추론 테스트
print("\n[5] OpenVINO(CPU) 추론 테스트")
if fatal:
    print("    (호환 불가 판정이라 생략)")
else:
    try:
        import cv2
        import openvino as ov

        img_path = args.image
        if img_path is None:
            cands = sorted(p for p in (ROOT / "samples").glob("*") if p.suffix.lower() in (".jpg", ".png", ".bmp"))
            img_path = str(cands[0]) if cands else None
        if img_path:
            img = cv2.imread(img_path)
        else:
            img = np.full((480, 640, 3), 114, np.uint8)
            print(f"    {WARN} samples/ 에 이미지가 없어 회색 이미지로 테스트 (검출 0개가 정상)")
        if task == "classify":
            # C++ centerCropResize 와 동일 : 짧은 변 리사이즈 → 가운데 자르기
            h, w = img.shape[:2]
            if w >= h: nw, nh = int(imgsz * w / h), imgsz
            else:      nw, nh = imgsz, int(imgsz * h / w)
            interp = cv2.INTER_AREA if min(h, w) > imgsz else cv2.INTER_LINEAR
            rs = cv2.resize(img, (nw, nh), interpolation=interp)
            x0, y0 = round((nw - imgsz) / 2), round((nh - imgsz) / 2)
            crop = rs[y0:y0 + imgsz, x0:x0 + imgsz]
            blob = crop[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
            core = ov.Core()
            m = core.read_model(str(path))
            if m.input().get_partial_shape().is_dynamic:
                m.reshape([1, 3, imgsz, imgsz])
            prob = core.compile_model(m, "CPU", {"INFERENCE_PRECISION_HINT": "f32"})([blob])[0][0].astype(np.float64)
            print(f"    이미지: {img_path or '(회색)'}")
            print(f"    확률 합계 {prob.sum():.4f}, 범위 {prob.min():.4f} ~ {prob.max():.4f}")
            if abs(prob.sum() - 1.0) > 0.01:
                print(f"    {WARN} softmax 가 없는 모델 → C++ 에서 자동으로 softmax 를 적용합니다")
                prob = np.exp(prob - prob.max()); prob /= prob.sum()
            print(f"    {OK} Top-5")
            for c in prob.argsort()[::-1][:5]:
                nm = names[c] if names and c < len(names) else f"cls{c}"
                print(f"         - {nm:25s} {prob[c] * 100:5.1f}%")
            raise StopIteration  # 검출용 테스트 건너뛰기
        # C++ 코드와 동일한 레터박스 전처리
        r = min(imgsz / img.shape[1], imgsz / img.shape[0])
        nw, nh = round(img.shape[1] * r), round(img.shape[0] * r)
        canvas = np.full((imgsz, imgsz, 3), 114, np.uint8)
        px, py = (imgsz - nw) // 2, (imgsz - nh) // 2
        canvas[py:py + nh, px:px + nw] = cv2.resize(img, (nw, nh))
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        core = ov.Core()
        m = core.read_model(str(path))
        if m.input().get_partial_shape().is_dynamic:
            m.reshape([1, 3, imgsz, imgsz])
        out = core.compile_model(m, "CPU", {"INFERENCE_PRECISION_HINT": "f32"})([blob])[0]
        out = out[0] if out.shape[1] < out.shape[2] else out[0].T  # → [4+nc, N]
        boxes, scores = out[:4], out[4:]
        print(f"    이미지: {img_path or '(회색)'}")
        print(f"    박스 좌표 최댓값 {boxes.max():.1f}, 점수 범위 {scores.min():.3f} ~ {scores.max():.3f}")
        if boxes.max() <= 1.5:
            print(f"    {NG} 박스가 0~1 정규화 좌표 → 이 코드(픽셀 좌표 기대)와 맞지 않음"); fatal = True
        if scores.max() > 1.0 or scores.min() < 0.0:
            print(f"    {NG} 점수가 0~1 범위 밖 → sigmoid 가 빠진 모델"); fatal = True
        if not fatal:
            best = scores.max(axis=0)
            keep = best > 0.35
            print(f"    {OK} 신뢰도 0.35 이상 후보 {int(keep.sum())}개 (NMS 전)")
            for c in np.unique(scores[:, keep].argmax(axis=0))[:10]:
                nm = names[c] if names and c < len(names) else f"cls{c}"
                print(f"         - {nm}")
    except StopIteration:
        pass
    except ImportError:
        print(f"    {WARN} openvino/opencv 가 없어 생략  (pip install opencv-python-headless)")

# ---------------------------------------------------------------- 결론 + 설정 생성
print("\n" + ("=" * 60))
if fatal:
    print("\033[1;31m 결론: 이 ONNX 는 yolo_mfg 에서 사용할 수 없습니다.\033[0m")
    print(" → YOLOv8/YOLO11 'detect' 모델을 nms=False 로 export 한 파일을 구하세요.")
    sys.exit(1)
print("\033[1;32m 결론: 사용 가능합니다.\033[0m")

if args.write_config:
    cls_file = ROOT / "config" / f"{path.stem}_classes.txt"
    if names:
        cls_file.write_text("\n".join(names) + "\n", encoding="utf-8")
    base = (ROOT / "config" / "app_config.yaml").read_text(encoding="utf-8")
    import re
    rel = path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path.resolve()
    repl = {
        r"^task: .*$": f'task: "{task}"',
        r"^model: .*$": f'model: "{rel}"',
        r"^classes: .*$": f'classes: "config/{cls_file.name}"',
        r"^defect_classes: .*$": "defect_classes: []          # 테스트: 아무거나 검출되면 NG",
        r"^output_dir: .*$": 'output_dir: "results_test"',
    }
    for k, v in repl.items():
        base = re.sub(k, v, base, flags=re.M)
    out_cfg = ROOT / "config" / args.config_name
    out_cfg.write_text(base, encoding="utf-8")
    print(f" 설정 생성 → {out_cfg.relative_to(ROOT)}  /  클래스 → config/{cls_file.name}")
print("=" * 60)
