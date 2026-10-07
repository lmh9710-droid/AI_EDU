"""시험 사진 점수로 문턱 정하기:  python score_check.py <사진폴더> [model.xml]"""
import glob, os, re, sys, collections
import numpy as np
from anomalib.deploy import OpenVINOInferencer

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/train/pc_data/bolt")
xmls = sorted(glob.glob("results/**/openvino/model.xml", recursive=True))
XML = sys.argv[2] if len(sys.argv) > 2 else (xmls[-1] if xmls else "")
EXT = (".jpg", ".jpeg", ".png", ".bmp")
files = lambda f: sorted(p for p in glob.glob(os.path.join(ROOT, f, "*")) if p.lower().endswith(EXT))
print("사진 위치:", ROOT); print("모델     :", XML or "(없음)")
counts = {f: len(files(f)) for f in ("good", "good_test", "defect")}; print("찾은 사진:", counts)
if not XML: sys.exit("✘ results 아래에 openvino/model.xml 이 없습니다")
if not counts["good_test"] or not counts["defect"]: sys.exit("✘ good_test 또는 defect 폴더에 사진이 없습니다")
inf = OpenVINOInferencer(path=XML, device="CPU")
score = lambda p: float(np.asarray(inf.predict(image=p).pred_score).reshape(-1)[0])
good = [(score(p), os.path.basename(p)) for p in files("good_test")]
bad = [(score(p), os.path.basename(p)) for p in files("defect")]
print(f"양품 {len(good)}장: 최고 점수 {max(good)[0]:.3f} ({max(good)[1]})")
print(f"불량 {len(bad)}장: 최저 점수 {min(bad)[0]:.3f} ({min(bad)[1]})")
gap = min(bad)[0] - max(good)[0]; print(f"여유(불량 최저 - 양품 최고): {gap:.3f}")
print(f"추천 문턱: {max(good)[0] + gap * 0.3:.3f}" if gap > 0 else "⚠ 겹침: 양품과 불량 점수가 겹칩니다")
by = collections.defaultdict(list)
for s, f in bad:
    m = re.match(r"[A-Za-z]+", f); by[m.group(0).lower() if m else "?"].append(s)
print("\n색깔별 최저 점수")
for k, v in sorted(by.items()): print(f"  {k:8s} {len(v)}장  최저 {min(v):.3f}  평균 {sum(v)/len(v):.3f}")
