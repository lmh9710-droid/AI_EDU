"""OpenVINO 만으로 PatchCore 점수·장치별 속도 확인:  uv run python check_model.py [문턱]
   사진: samples/good/*, samples/defect/*   모델: models/patchcore_v1/model.xml"""
import glob, os, sys, time
import cv2, numpy as np, openvino as ov
MODEL = "models/patchcore_v1/model.xml"; TH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.164
core = ov.Core()
for d in core.available_devices: print(f"{d:6s} {core.get_property(d, 'FULL_DEVICE_NAME')}")
paths = [p for p in sorted(glob.glob("samples/good/*") + glob.glob("samples/defect/*")) if p.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))]
if not paths: sys.exit("✘ samples/good, samples/defect 에 사진이 없습니다.")
h, w = cv2.imread(paths[0]).shape[:2]
def prep(p):
    img = cv2.imread(p); img = cv2.resize(img, (w, h)) if img.shape[:2] != (h, w) else img
    return (cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
for dev in core.available_devices:
    m = core.read_model(MODEL); m.reshape([1, 3, h, w])
    try: req = core.compile_model(m, dev).create_infer_request()
    except Exception as e: print(f"\n[{dev}] 컴파일 실패: {e}"); continue
    req.infer({0: prep(paths[0])}); print(f"\n[{dev}]"); times = []
    for p in paths:
        x = prep(p); t = time.perf_counter(); req.infer({0: x}); times.append((time.perf_counter() - t) * 1000)
        s = float(np.asarray(req.get_tensor("pred_score").data).reshape(-1)[0])
        print(f"  {os.path.basename(p):18s} 점수 {s:.3f}  → {'NG' if s > TH else 'OK'}")
    print(f"  평균 판정 시간 {sum(times)/len(times):.1f} ms/장")
