"""WSL 카메라 원본 촬영:  uv run python cap.py <이름> [장치번호]   (s 저장 · q/ESC/창 닫기 종료)"""
import cv2, os, sys, threading
label = sys.argv[1] if len(sys.argv) > 1 else "img"
dev = int(sys.argv[2]) if len(sys.argv) > 2 else 4
WIN = "capture (s: save, q/ESC: quit)"
os.makedirs("samples/wsl", exist_ok=True)
cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480); cap.set(cv2.CAP_PROP_FPS, 30)
n = len([f for f in os.listdir("samples/wsl") if f.startswith(label)])
try:
    for _ in range(30): cap.read()                       # 자동 밝기가 자리 잡을 시간
    cv2.namedWindow(WIN); print("s = 원본 저장, q/ESC = 종료  (키는 창을 클릭한 뒤)")
    while True:
        ok, frame = cap.read()
        if not ok: print("카메라 읽기 실패"); break
        disp = frame.copy(); b, g, r = frame.reshape(-1, 3).mean(0)
        cv2.putText(disp, f"B{b:.0f} G{g:.0f} R{r:.0f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow(WIN, disp)                            # 표시만 글자, 저장은 원본
        k = cv2.waitKey(1) & 0xFF
        if k == ord("s"):
            n += 1; p = f"samples/wsl/{label}_{n:02d}.jpg"; cv2.imwrite(p, frame); print("저장:", p)
        elif k in (ord("q"), 27):
            break
except KeyboardInterrupt:
    pass
finally:
    t = threading.Thread(target=cap.release, daemon=True); t.start(); t.join(2.0)   # usbipd 에서 해제가 멈추는 경우 대비
    cv2.destroyAllWindows()
    print("카메라 종료" if not t.is_alive() else "카메라 해제 지연 → 강제 종료")
    os._exit(0)
