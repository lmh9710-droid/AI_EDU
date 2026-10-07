"""폴더 사진의 PatchCore 점수 + 색 덩어리 + 평균색:  uv run python score_dir.py <폴더> [PatchCore문턱] [색문턱px]"""
import glob, os, sys
import cv2, numpy as np, openvino as ov
folder = sys.argv[1] if len(sys.argv) > 1 else "samples/wsl"
TH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.164; BLOB = int(sys.argv[3]) if len(sys.argv) > 3 else 260
COLORS = {"red": [(0, 10), (170, 179)], "yellow": [(20, 35)], "green": [(40, 85)], "blue": [(95, 130)]}
S_MIN = {"blue": 50, "red": 80, "yellow": 80, "green": 70}
def blob(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV); h, s, v = cv2.split(hsv); best = (0, "-")
    for c, rs in COLORS.items():
        m = np.zeros(h.shape, bool)
        for lo, hi in rs: m |= (h >= lo) & (h <= hi)
        m = cv2.morphologyEx(((m & (s >= S_MIN[c]) & (v >= 30)) * 255).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(m)
        a = int(st[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
        if a > best[0]: best = (a, c)
    return best
core = ov.Core(); m = core.read_model("models/patchcore_v1/model.xml"); m.reshape([1, 3, 480, 640])
req = core.compile_model(m, "CPU").create_infer_request()
for p in sorted(glob.glob(os.path.join(folder, "*.jpg"))):
    img = cv2.resize(cv2.imread(p), (640, 480))
    req.infer({0: cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0})
    sc = float(np.asarray(req.get_tensor("pred_score").data).reshape(-1)[0]); a, c = blob(img); b, g, r = img.reshape(-1, 3).mean(0)
    print(f"{os.path.basename(p):14s} 점수 {sc:.3f}  색덩어리 {a:5d}px({c:6s})  평균색 B{b:4.0f} G{g:4.0f} R{r:4.0f}  → {'NG' if (sc > TH or a >= BLOB) else 'OK'}")
