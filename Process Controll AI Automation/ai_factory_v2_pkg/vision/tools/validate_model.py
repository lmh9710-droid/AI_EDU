#!/usr/bin/env python3
"""
validate_model.py : 품질팀 ONNX 모델을 '정답이 있는 사진'으로 검증 (라인 영향 없음, DB 기록 없음)

  실제 현장과 같은 C++ 엔진(OpenVINO, 같은 전처리·같은 판정 규칙)으로 사진을 한 장씩 판정하고
  정답과 비교해 정확도, 혼동행렬, 불량 놓침률, 양품 오판정률, 판정 기준(conf_threshold)별 변화를 보고합니다.

  준비: 클래스 이름과 같은 폴더에 사진을 나눠 담기 (학습에 쓰지 않은 사진이어야 함)
      testset/
        good/   *.jpg
        Black/  *.jpg
        Red/    ...

  실행 (~/ai_factory 에서):
      python3 vision/tools/validate_model.py ~/testset
      python3 vision/tools/validate_model.py ~/testset --device CPU     # GPU 결과와 비교할 때

  결과: ~/ai_factory/data/vision/validation/<시각>/  (summary.txt, per_image.csv, 엔진 로그)
"""
import argparse
import csv
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VISION = Path(__file__).resolve().parent.parent                 # ~/ai_factory/vision
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}    # 엔진과 동일
THRESHOLDS = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]


def read_list(text, key):
    m = re.search(rf'^\s*{key}\s*:\s*\[(.*?)\]', text, re.M)
    return [s.strip().strip('"') for s in m.group(1).split(",") if s.strip()] if m else []


def read_val(text, key):
    m = re.search(rf'^\s*{key}\s*:\s*"?([^"#\n]*?)"?\s*(#.*)?$', text, re.M)
    return m.group(1).strip() if m else None


def set_key(text, key, value):
    line = f"{key}: {value}"
    if re.search(rf'^\s*{key}\s*:', text, re.M):
        return re.sub(rf'^\s*{key}\s*:.*$', line, text, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def parse_topk(s):
    out = {}
    for item in (s or "").split(";"):
        if ":" in item:
            k, v = item.rsplit(":", 1)
            try:
                out[k] = float(v)
            except ValueError:
                pass
    return out


def main():
    ap = argparse.ArgumentParser(description="품질팀 ONNX 모델 정답 사진 검증")
    ap.add_argument("testset", help="클래스 이름별 하위 폴더에 사진이 든 폴더")
    ap.add_argument("--config", default=str(VISION / "config/pdm_bolt.yaml"), help="기준 설정 (모델·클래스·판정 기준)")
    ap.add_argument("--exe", default=str(VISION / "yolo_engine/build/release/yolo_mfg"))
    ap.add_argument("--device", default=None, help="AUTO_DGPU | GPU | CPU (기본: 설정 파일 값)")
    ap.add_argument("--keep-roi", action="store_true", help="설정의 ROI 를 그대로 사용 (기본: 사진 전체)")
    a = ap.parse_args()

    testset = Path(a.testset).expanduser().resolve()
    exe = Path(a.exe)
    if not exe.exists():
        sys.exit(f"✘ 엔진이 없습니다: {exe}  → ./scripts/build_all.sh")
    base = Path(a.config).read_text(encoding="utf-8")
    model = read_val(base, "model")
    if not model or not (VISION / model).exists():
        sys.exit(f"✘ 모델이 없습니다: {VISION / (model or '?')}")
    classes_file = VISION / (read_val(base, "classes") or "config/bolt_classes.txt")
    names = [l.strip() for l in classes_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok_classes = read_list(base, "ok_classes") or ["good"]
    thr_now = float(read_val(base, "conf_threshold") or 0.8)
    folders = sorted(d for d in testset.iterdir() if d.is_dir())
    if not folders:
        sys.exit(f"✘ {testset} 안에 클래스 폴더가 없습니다 (예: good/, Red/)")
    unknown = [d.name for d in folders if d.name not in names]
    if unknown:
        print(f"⚠ 클래스 목록({classes_file.name})에 없는 폴더: {unknown} → 정확도 계산에서는 '불량'으로만 취급")

    out = VISION.parent / "data/vision/validation" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in folders:
        imgs = sorted(str(p) for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT)
        if not imgs:
            print(f"  - {d.name}: 사진 없음, 건너뜀"); continue
        cfg = base
        for k, v in [("source", f'"{d}"'), ("output_dir", f'"{out / ("run_" + d.name)}"'), ("show_window", "0"),
                     ("part_trigger", '"none"'), ("event_output", "0"), ("save_ng_images", "0")]:
            cfg = set_key(cfg, k, v)
        if not a.keep_roi:
            cfg = set_key(cfg, "roi", "[0, 0, 0, 0]")
        if a.device:
            cfg = set_key(cfg, "device", f'"{a.device}"')
        cfg_path = out / f"cfg_{d.name}.yaml"
        cfg_path.write_text(cfg, encoding="utf-8")
        print(f"  ▶ {d.name}: {len(imgs)}장 판정 중 ...", flush=True)
        log = out / f"engine_{d.name}.log"
        with open(log, "w", encoding="utf-8") as lf:
            rc = subprocess.run([str(exe), str(cfg_path)], cwd=VISION, stdout=lf, stderr=subprocess.STDOUT,
                                timeout=max(120, len(imgs) * 5)).returncode
        csvs = sorted((out / ("run_" + d.name)).glob("inspection_*.csv"))
        if rc != 0 or not csvs:
            sys.exit(f"✘ 엔진 실행 실패 ({d.name}, 코드 {rc}) → {log}")
        with open(csvs[-1], encoding="utf-8-sig") as f:
            res = list(csv.DictReader(f))
        if len(res) != len(imgs):
            print(f"  ⚠ {d.name}: 사진 {len(imgs)}장인데 결과 {len(res)}건 (읽지 못한 사진 확인: {log})")
        for img, r in zip(imgs, res):
            topk = parse_topk(r.get("detections"))
            top1 = max(topk, key=topk.get) if topk else ""
            p_ok = max((topk.get(c, 0.0) for c in ok_classes), default=0.0)
            rows.append(dict(file=img, truth=d.name, top1=top1, top1_score=topk.get(top1, 0.0), p_ok=p_ok,
                             verdict=r.get("result", ""), infer_ms=float(r.get("infer_ms") or 0)))

    with open(out / "per_image.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    # ---------------- 요약
    L = []
    P = lambda s="": L.append(s)
    P(f"품질팀 모델 검증  {datetime.now():%Y-%m-%d %H:%M:%S}")
    P(f"모델 {model}   클래스 {names}   양품 클래스 {ok_classes}   현재 판정 기준 {thr_now}")
    P(f"사진 {len(rows)}장  ({testset})   장치 {a.device or read_val(base, 'device')}")
    P(f"평균 추론 {sum(r['infer_ms'] for r in rows) / len(rows):.2f} ms/장")
    P()
    labeled = [r for r in rows if r["truth"] in names]
    if labeled:
        acc = sum(r["top1"] == r["truth"] for r in labeled) / len(labeled)
        P(f"[1] 분류 정확도 (1순위 = 정답 폴더): {acc * 100:.1f}%  ({len(labeled)}장)")
        cols = names
        P("    혼동행렬 (행=정답 폴더, 열=모델 1순위)")
        P("    " + "".join(f"{c[:8]:>9}" for c in ["정답\\예측"] + cols))
        for t in sorted({r['truth'] for r in labeled}):
            P("    " + f"{t[:8]:>9}" + "".join(f"{sum(1 for r in labeled if r['truth'] == t and r['top1'] == c):>9}" for c in cols))
        P()
    good = [r for r in rows if r["truth"] in ok_classes]
    bad = [r for r in rows if r["truth"] not in ok_classes]
    P(f"[2] 현장 판정 (현재 기준 {thr_now}: '{'/'.join(ok_classes)}' 확률 ≥ 기준일 때만 OK)")
    if bad:
        miss = [r for r in bad if r["verdict"] == "OK"]
        P(f"    불량 놓침률   {len(miss) / len(bad) * 100:6.2f}%  ({len(miss)}/{len(bad)})   ← 불량이 양품으로 통과 (가장 중요)")
    if good:
        fr = [r for r in good if r["verdict"] != "OK"]
        P(f"    양품 오판정률 {len(fr) / len(good) * 100:6.2f}%  ({len(fr)}/{len(good)})   ← 양품인데 라인 정지·퇴출")
    P()
    P("[3] 판정 기준(conf_threshold)별 변화  ※ 기준이 높을수록 놓침↓ 오판정↑")
    P("      기준   불량 놓침률   양품 오판정률")
    for th in THRESHOLDS:
        ok_at = lambda r: r["top1"] in ok_classes and r["p_ok"] >= th
        m = (sum(ok_at(r) for r in bad) / len(bad) * 100) if bad else float("nan")
        f_ = (sum(not ok_at(r) for r in good) / len(good) * 100) if good else float("nan")
        P(f"      {th:.2f}   {m:9.2f}%   {f_:11.2f}%" + ("   ← 현재" if abs(th - thr_now) < 1e-9 else ""))
    P()
    wrong = [r for r in rows if (r["truth"] in ok_classes) != (r["verdict"] == "OK")]
    P(f"[4] 현장 판정이 틀린 사진 {len(wrong)}장 (상위 30장, 전체는 per_image.csv)")
    for r in wrong[:30]:
        P(f"    {r['truth']:>8} → {r['verdict']:2} (1순위 {r['top1']} {r['top1_score']:.3f}, 양품확률 {r['p_ok']:.3f})  {Path(r['file']).name}")
    text = "\n".join(L)
    (out / "summary.txt").write_text(text + "\n", encoding="utf-8")
    print("\n" + text + f"\n\n결과 폴더: {out}")


if __name__ == "__main__":
    main()
