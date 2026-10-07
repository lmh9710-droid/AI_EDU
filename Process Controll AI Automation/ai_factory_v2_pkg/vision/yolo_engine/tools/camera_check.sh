#!/usr/bin/env bash
# =============================================================================
#  camera_check.sh : WSL 에서 USB 카메라를 쓸 수 있는지 단계별 점검
#
#  사전 작업 (윈도우 PowerShell, 관리자 권한) - 아두이노 연결 때와 같은 방법
#     usbipd list                          ← 카메라 BUSID 확인
#     usbipd bind   --busid <BUSID>        ← 처음 한 번만
#     usbipd attach --wsl --busid <BUSID>  ← WSL 재시작/PC 재부팅마다
#
#  사용법 (WSL, 프로젝트 폴더):
#     bash scripts/wsl/camera_check.sh        ← 컬러 영상 장치를 자동으로 찾음 (권장)
#     bash scripts/wsl/camera_check.sh 4      ← /dev/video4 를 직접 지정
#
#  ※ RealSense 같은 깊이 카메라는 장치가 여러 개 생깁니다
#     (깊이 Z16 / 적외선 GREY / 컬러 YUYV / 메타데이터). YOLO 에는 '컬러' 장치가 필요합니다.
# =============================================================================
CAM="${1:-}"
PY="$HOME/yolo_libs/venv/bin/python"
ok()   { echo -e "  \033[1;32m[통과]\033[0m $*"; }
fail() { echo -e "  \033[1;31m[실패]\033[0m $*"; }
info() { echo -e "  \033[1;33m[참고]\033[0m $*"; }

echo "================ 카메라 점검 ================"

# 0) 도구 설치 (처음 한 번)
if ! command -v v4l2-ctl >/dev/null || ! command -v lsusb >/dev/null; then
    echo "  필요한 도구 설치 중 (v4l-utils, usbutils)..."
    sudo apt-get install -y -q v4l-utils usbutils >/dev/null
fi

# 1) USB 장치가 WSL 로 넘어왔는지
echo "--- 1. WSL 에 연결된 USB 장치 ---"
lsusb | grep -v "root hub" | sed 's/^/        /'
if lsusb | grep -qiE "cam|video|uvc|webcam|logitech|microdia|sonix|imaging|realsense|depth|basler|hikrobot"; then
    ok "카메라로 보이는 USB 장치가 있습니다"
else
    info "카메라 이름이 안 보입니다. 윈도우에서 usbipd attach 를 했는지 확인하세요"
fi

# 2) 드라이버(커널 모듈) : WSL 커널은 uvcvideo 를 기본으로 로드하지 않음
echo "--- 2. 카메라 드라이버(uvcvideo) ---"
if lsmod | grep -q uvcvideo; then
    ok "uvcvideo 로드됨"
elif sudo modprobe uvcvideo 2>/dev/null; then
    ok "uvcvideo 로드 완료"
    sleep 2
else
    fail "uvcvideo 모듈이 없는 커널입니다 → README_WSL.md '카메라 연결' 방법 B 사용"
    exit 1
fi

# 3) /dev/video* 조사 → 컬러 영상 장치 선택
echo "--- 3. 비디오 장치 조사 ---"
ls /dev/video* >/dev/null 2>&1 || { fail "/dev/video* 가 없습니다 → usbipd detach 후 다시 attach"; exit 1; }
if [ ! -r /dev/video0 ] || [ ! -w /dev/video0 ]; then
    info "접근 권한 부여 (다음 로그인부터는 video 그룹으로 자동 허용)"
    sudo chmod 666 /dev/video*
    sudo usermod -aG video "$USER"
fi

declare -A FMTS
for d in /dev/video*; do
    n="${d##*video}"
    card=$(v4l2-ctl -d "$d" --info 2>/dev/null | sed -n 's/.*Card type *: *//p')
    fmts=$(v4l2-ctl -d "$d" --list-formats 2>/dev/null | grep -oE "'[A-Za-z0-9 ]{4}'" | tr -d "'" | xargs)
    FMTS[$n]="$fmts"
    echo "        $d : ${card:-?} | 형식: ${fmts:-(없음 = 메타데이터 장치)}"
done

has_fmt() { echo " ${FMTS[$1]} " | grep -q " $2 "; }   # $1=장치번호 $2=형식

FMT=""
if [ -z "$CAM" ]; then
    # 우선순위: MJPG(압축) > YUYV(비압축) > RGB3/BGR3   (Z16=깊이, GREY=적외선 은 제외)
    for f in MJPG YUYV RGB3 BGR3; do
        for n in $(printf "%s\n" "${!FMTS[@]}" | sort -n); do
            if has_fmt "$n" "$f"; then CAM=$n; FMT=$f; break 2; fi
        done
    done
    [ -n "$CAM" ] || { fail "컬러 영상 장치를 찾지 못했습니다"; exit 1; }
    ok "컬러 영상 장치 자동 선택 → /dev/video$CAM (형식 $FMT)"
else
    for f in MJPG YUYV RGB3 BGR3; do
        if has_fmt "$CAM" "$f"; then FMT=$f; break; fi
    done
    [ -n "$FMT" ] || { fail "/dev/video$CAM 은 컬러 영상 장치가 아닙니다 (형식: ${FMTS[$CAM]:-없음})"; exit 1; }
    ok "지정한 장치 /dev/video$CAM (형식 $FMT)"
fi

# 비압축(YUYV 등)은 USBIP 대역폭 때문에 640x480 부터 시작
if [ "$FMT" = "MJPG" ]; then W=1280; H=720; else W=640; H=480; fi
echo "        지원 해상도 ($FMT):"
v4l2-ctl -d "/dev/video$CAM" --list-formats-ext 2>/dev/null \
    | awk -v f="'$FMT'" '/\[[0-9]+\]/{show=index($0,f)>0} show && /Size/' | head -8 | sed 's/^\s*/          /'

# 4) 실제 촬영 + FPS 측정 + 스냅샷
echo "--- 4. 실제 촬영 테스트 (/dev/video$CAM, $FMT ${W}x${H}, 3초) ---"
"$PY" - "$CAM" "$FMT" "$W" "$H" <<'PYCODE'
import sys, time, cv2
cam, fmt, w, h = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
cap = cv2.VideoCapture(cam, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fmt))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
cap.set(cv2.CAP_PROP_FPS, 30)
if not cap.isOpened():
    print("  [실패] 카메라를 열 수 없습니다 (다른 프로그램이 사용 중인지 확인)")
    sys.exit(1)
n, frame, t0 = 0, None, time.time()
while time.time() - t0 < 3:
    ok, f = cap.read()
    if ok:
        n += 1
        frame = f
if frame is None:
    print("  [실패] 영상이 들어오지 않음 → 해상도를 더 낮추거나(424x240) USB 포트를 바꿔 보세요")
    sys.exit(1)
cv2.imwrite("results_cam_check.jpg", frame)
print(f"  [통과] {frame.shape[1]}x{frame.shape[0]}, 약 {n / 3:.1f} fps 수신")
print("         스냅샷 저장 → results_cam_check.jpg  (explorer.exe . 로 확인)")
if n / 3 < 10:
    print("  [참고] fps 가 낮습니다 → USB 대역폭 부족 가능. 해상도를 더 낮춰 보세요")
PYCODE
RC=$?

echo "==================================================="
if [ "$RC" = "0" ]; then
    echo "  ▶ 실시간 검사 설정에 반영하려면 아래 한 줄을 실행하세요:"
    echo "    sed -i -e 's/^source:.*/source: \"$CAM\"/' -e 's/^camera_fourcc:.*/camera_fourcc: \"$FMT\"/' -e 's/^camera_width:.*/camera_width: $W/' -e 's/^camera_height:.*/camera_height: $H/' config/cam_cls.yaml config/cam_det.yaml"
fi
echo "  드라이버 자동 로드 : echo uvcvideo | sudo tee /etc/modules-load.d/uvcvideo.conf"
