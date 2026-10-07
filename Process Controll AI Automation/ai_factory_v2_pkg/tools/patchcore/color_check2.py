"""색 덩어리 크기로 색 규칙 문턱 정하기:  python color_check2.py <사진폴더>"""
import cv2, glob, os, sys, re
import numpy as np
ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/train/pc_data/bolt")
COLORS = {"red": [(0, 10), (170, 179)], "yellow": [(20, 35)], "green": [(40, 85)], "blue": [(95, 130)]}
S_MIN = {"blue": 50, "red": 80, "yellow": 80, "green": 70}
V_MIN = 30
def blobs(path):
    hsv = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2HSV); h, s, v = cv2.split(hsv); out = {}
    for c, rs in COLORS.items():
        m = np.zeros(h.shape, bool)
        for lo, hi in rs: m |= (h >= lo) & (h <= hi)
        m = cv2.morphologyEx(((m & (s >= S_MIN[c]) & (v >= V_MIN)) * 255).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(m)
        out[c] = int(st[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
    return out
rows = {}
for folder in ("good", "good_test", "defect"):
    for p in sorted(glob.glob(os.path.join(ROOT, folder, "*"))):
        if not p.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")): continue
        name = os.path.basename(p); m = re.match(r"[A-Za-z]+", name)
        key = folder if folder != "defect" else (m.group(0).lower() if m else "?")
        rows.setdefault(key, []).append((blobs(p), name))
print(f"{'구분':10s} {'장수':>4s}   자기 색 덩어리 최소   아무 색 덩어리 최대")
for k, items in rows.items():
    any_max = max(max(b.values()) for b, _ in items)
    if k in COLORS:
        w = min(items, key=lambda t: t[0][k]); print(f"{k:10s} {len(items):4d}   {w[0][k]:8d}px ({w[1]})   {any_max:8d}px")
    else:
        w = max(items, key=lambda t: max(t[0].values())); print(f"{k:10s} {len(items):4d}   {'-':>16s}   {any_max:8d}px ({w[1]})")
