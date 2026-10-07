#!/usr/bin/env python3
"""
make_model_config.py : 품질팀 새 분류 모델(ONNX)용 설정 3종을 모델 정보에서 자동 생성

  ONNX 안에 저장된 클래스 이름·순서를 읽어서 아래 파일을 만듭니다. (기존 운영 파일은 건드리지 않음)
    config/bolt_classes_<V>.txt   클래스 순서
    config/pdm_bolt_<V>.yaml      시험용 엔진 설정 (기준 설정을 복사해 model·classes·defect_classes 만 교체)
    status_map_<V>.json           클래스 → 판정 코드 (good=양품, empty=판정 제외, 나머지=NG_VISION_대문자)

  사용 (vision 폴더에서, onnx 패키지가 있는 파이썬으로):
    cd ~/ai_factory/vision
    cp <받은파일>.onnx models/best_v7.onnx
    ~/yolo_libs/venv/bin/python tools/make_model_config.py v7
    ~/yolo_libs/venv/bin/python tools/make_model_config.py v7 --base config/pdm_bolt_v6.yaml   # 카메라·트리거 설정 이어받기
"""
import argparse, ast, hashlib, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("version", help="예: v7  → models/best_v7.onnx 를 읽음")
ap.add_argument("--base", default=None, help="이어받을 엔진 설정 (기본: config/pdm_bolt.yaml)")
ap.add_argument("--ok", default="good", help="양품 클래스 이름 (기본 good)")
ap.add_argument("--ignore", default="empty", help="판정 제외 클래스, 쉼표 구분 (기본 empty)")
a = ap.parse_args()

try:
    import onnx
except ImportError:
    sys.exit("✘ onnx 패키지가 필요합니다: ~/yolo_libs/venv/bin/python 으로 실행하세요")

V = a.version
model = f"models/best_{V}.onnx"
if not os.path.exists(model):
    sys.exit(f"✘ {model} 이 없습니다 (vision 폴더에서 실행했는지 확인)")
meta = {p.key: p.value for p in onnx.load(model).metadata_props}
if "names" not in meta:
    sys.exit("✘ 모델에 클래스 정보(names)가 없습니다. 품질팀에 클래스 순서를 받아 직접 작성하세요")
names = ast.literal_eval(meta["names"])
order = [names[i] for i in sorted(names)]
ignore = [c for c in a.ignore.split(",") if c and c in order]
if a.ok not in order:
    sys.exit(f"✘ 양품 클래스 '{a.ok}' 가 모델에 없습니다: {order}")
defects = [c for c in order if c != a.ok and c not in ignore]

open(f"config/bolt_classes_{V}.txt", "w", encoding="utf-8").write("\n".join(order) + "\n")

base = a.base or "config/pdm_bolt.yaml"
cfg = open(base, encoding="utf-8").read()
cfg = re.sub(r'^model: .*$', f'model: "{model}"', cfg, flags=re.M)
cfg = re.sub(r'^classes: .*$', f'classes: "config/bolt_classes_{V}.txt"', cfg, flags=re.M)
if re.search(r'^defect_classes:', cfg, flags=re.M):
    cfg = re.sub(r'^defect_classes: .*$', "defect_classes: [" + ", ".join(f'"{c}"' for c in defects) + "]", cfg, flags=re.M)
open(f"config/pdm_bolt_{V}.yaml", "w", encoding="utf-8").write(cfg)

sm = json.load(open("status_map.json", encoding="utf-8"))
sm["ok_classes"] = [a.ok]
sm["ignore_classes"] = ignore
sm["status_map"] = {c: "NG_VISION_" + re.sub(r"[^A-Z0-9]+", "_", c.upper()) for c in defects}
sm["model_version"] = f"{meta.get('task', 'model')}-{V}-" + hashlib.sha256(open(model, "rb").read()).hexdigest()[:8]
json.dump(sm, open(f"status_map_{V}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("모델      :", model, f"(task={meta.get('task')}, imgsz={meta.get('imgsz')})")
print("클래스    :", order)
print("불량 코드 :", sm["status_map"])
print("양품      :", sm["ok_classes"], "· 판정 제외:", sm["ignore_classes"])
print("기준 설정 :", base, "→", f"config/pdm_bolt_{V}.yaml")
print(f"\n실행: cd ~/ai_factory && ./vision/run_vision.sh --config config/pdm_bolt_{V}.yaml --map status_map_{V}.json")
