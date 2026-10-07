#!/usr/bin/env bash
# =============================================================================
#  setup_wsl.sh : WSL2(Ubuntu 24.04)에서 yolo_mfg 개발환경을 한 번에 설치
#
#  사용법 (프로젝트 폴더에서):
#     bash vision/yolo_engine/tools/setup_wsl.sh all        ← 처음엔 이것만 실행하면 됩니다
#
#  단계별로 따로 실행할 수도 있습니다:
#     bash vision/yolo_engine/tools/setup_wsl.sh base        # 1) 컴파일러, CMake, 디버거 등 기본 도구
#     bash vision/yolo_engine/tools/setup_wsl.sh gpu         # 2) Intel Arc GPU 런타임 (OpenCL / Level Zero)
#     bash vision/yolo_engine/tools/setup_wsl.sh openvino    # 3) Python 가상환경 + OpenVINO (C++ 헤더 포함)
#     bash vision/yolo_engine/tools/setup_wsl.sh opencv      # 4) OpenCV 5.0.0 소스 빌드 (가장 오래 걸림)
#     bash vision/yolo_engine/tools/setup_wsl.sh onnxruntime # 5) ONNX Runtime (C++ 라이브러리)
#     bash vision/yolo_engine/tools/setup_wsl.sh ultralytics # 6) (선택) 모델 변환용 ultralytics (CPU 버전 torch)
#
#  모든 라이브러리는 ~/yolo_libs 아래에 설치됩니다. (시스템을 더럽히지 않음)
# =============================================================================
set -euo pipefail

LIBS="$HOME/yolo_libs"
OPENCV_VERSION="5.0.0"
ORT_VERSION="1.30.0"
JOBS="$(nproc)"

# ---- 보기 좋은 출력용 ----
say()  { echo -e "\n\033[1;36m[yolo_mfg] $*\033[0m"; }
ok()   { echo -e "\033[1;32m  ✔ $*\033[0m"; }
warn() { echo -e "\033[1;33m  ⚠ $*\033[0m"; }
die()  { echo -e "\033[1;31m  ✘ $*\033[0m"; exit 1; }

mkdir -p "$LIBS"

# -----------------------------------------------------------------------------
step_base() {
    say "1/5 기본 개발 도구 설치 (sudo 비밀번호를 물어보면 Ubuntu 비밀번호 입력)"
    sudo apt-get update
    sudo apt-get install -y \
        build-essential cmake ninja-build gdb git pkg-config wget curl unzip \
        python3 python3-venv python3-pip \
        libgtk-3-dev \
        libavcodec-dev libavformat-dev libswscale-dev \
        libjpeg-dev libpng-dev libtiff-dev \
        software-properties-common clinfo
    ok "기본 도구 설치 완료 ($(cmake --version | head -1))"
}

# -----------------------------------------------------------------------------
step_gpu() {
    say "2/5 Intel GPU 런타임 설치 (OpenCL + Level Zero)"
    # WSL 에서는 '드라이버'는 윈도우 쪽 Arc 드라이버가 담당하고,
    # 우분투에는 '사용자 공간 런타임'만 설치하면 됩니다.
    if [ ! -e /dev/dxg ]; then
        warn "/dev/dxg 가 없습니다. WSL2 가 아니거나 윈도우 GPU 드라이버가 WSL 을 지원하지 않습니다."
        warn "윈도우에서 'wsl --update' 실행 후, Arc 드라이버를 최신으로 설치하세요."
    fi
    sudo add-apt-repository -y ppa:kobuk-team/intel-graphics
    sudo apt-get update
    sudo apt-get install -y intel-opencl-icd libze-intel-gpu1 libze1 clinfo
    # GPU 접근 권한 (WSL 에서는 대부분 필요 없지만 네이티브 리눅스 대비)
    sudo usermod -aG render,video "$USER" || true

    echo "  --- OpenCL 디바이스 목록 ---"
    clinfo -l || true
    if clinfo -l 2>/dev/null | grep -qi "arc\|graphics"; then
        ok "GPU 런타임 확인됨"
    else
        warn "GPU 가 보이지 않습니다. README_WSL.md 의 '문제 해결'을 확인하세요. (CPU 로는 계속 사용 가능)"
    fi
}

# -----------------------------------------------------------------------------
step_openvino() {
    say "3/5 Python 가상환경 + OpenVINO 설치"
    # pip 로 설치하는 OpenVINO 안에 C++ 헤더 / CMake 설정 / GPU 플러그인이 모두 들어 있습니다.
    if [ ! -d "$LIBS/venv" ]; then
        python3 -m venv "$LIBS/venv"
    fi
    "$LIBS/venv/bin/pip" install --upgrade pip
    "$LIBS/venv/bin/pip" install --upgrade openvino

    # 파이썬 버전에 상관없이 같은 경로로 찾을 수 있게 바로가기(심볼릭 링크) 생성
    OV_PKG="$("$LIBS/venv/bin/python" -c 'import openvino, os; print(os.path.dirname(openvino.__file__))')"
    ln -sfn "$OV_PKG" "$LIBS/openvino"
    [ -f "$LIBS/openvino/cmake/OpenVINOConfig.cmake" ] || die "OpenVINO CMake 설정을 찾을 수 없습니다."

    ok "OpenVINO $("$LIBS/venv/bin/python" -c 'import openvino; print(openvino.__version__)') 설치 완료"
    echo "  --- OpenVINO 가 인식한 디바이스 ---"
    "$LIBS/venv/bin/python" - <<'EOF'
import openvino as ov
core = ov.Core()
for d in core.available_devices:
    name = core.get_property(d, "FULL_DEVICE_NAME")
    print(f"   {d:8s}: {name}")
EOF
}

# -----------------------------------------------------------------------------
step_opencv() {
    say "4/5 OpenCV ${OPENCV_VERSION} 빌드 (CPU 코어 ${JOBS}개 사용, 10~40분 소요)"
    if [ -f "$LIBS/opencv5/.installed_${OPENCV_VERSION}" ]; then
        ok "이미 설치되어 있습니다. 건너뜁니다. (다시 하려면 ~/yolo_libs/opencv5 삭제)"
        return
    fi
    cd "$LIBS"
    rm -rf opencv_src
    git clone --depth 1 -b "$OPENCV_VERSION" https://github.com/opencv/opencv.git opencv_src
    cmake -S opencv_src -B opencv_src/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$LIBS/opencv5" \
        -DBUILD_LIST=core,imgproc,imgcodecs,videoio,highgui \
        -DWITH_GTK=ON -DWITH_FFMPEG=ON \
        -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF \
        -DBUILD_opencv_apps=OFF -DBUILD_opencv_python3=OFF -DBUILD_JAVA=OFF
    cmake --build opencv_src/build -j "$JOBS"
    cmake --install opencv_src/build
    touch "$LIBS/opencv5/.installed_${OPENCV_VERSION}"
    rm -rf opencv_src   # 소스 삭제 (용량 확보)
    ok "OpenCV ${OPENCV_VERSION} 설치 완료 → $LIBS/opencv5"
}

# -----------------------------------------------------------------------------
step_onnxruntime() {
    say "5/5 ONNX Runtime ${ORT_VERSION} 설치 (Microsoft 공식 C++ 배포판)"
    # 참고: 공식 배포판에는 OpenVINO EP 가 없어 CPU 로 동작합니다.
    #       Arc GPU 가속은 OpenVINO 백엔드(backend: openvino)를 사용하세요.
    #       ORT 로도 GPU 를 쓰고 싶다면 README_WSL.md '고급: ORT OpenVINO EP 빌드' 참고.
    cd "$LIBS"
    local pkg="onnxruntime-linux-x64-${ORT_VERSION}"
    if [ ! -d "$pkg" ]; then
        wget -q --show-progress \
            "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/${pkg}.tgz"
        tar xzf "${pkg}.tgz" && rm "${pkg}.tgz"
    fi
    ln -sfn "$LIBS/$pkg" "$LIBS/onnxruntime"
    ok "ONNX Runtime 설치 완료 → $LIBS/onnxruntime"
}

# -----------------------------------------------------------------------------
step_ultralytics() {
    say "(선택) ultralytics 설치 - 모델 변환용"
    [ -d "$LIBS/venv" ] || python3 -m venv "$LIBS/venv"
    # GPU용 torch 는 수 GB 이므로 변환 전용으로 가벼운 CPU 버전 설치
    "$LIBS/venv/bin/pip" install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    "$LIBS/venv/bin/pip" install ultralytics onnx onnxslim nncf
    ok "ultralytics 설치 완료"
}

# -----------------------------------------------------------------------------
summary() {
    say "설치 요약"
    [ -d "$LIBS/openvino" ]    && ok "OpenVINO     : $LIBS/openvino"    || warn "OpenVINO 없음"
    [ -d "$LIBS/opencv5" ]     && ok "OpenCV       : $LIBS/opencv5"     || warn "OpenCV 없음"
    [ -d "$LIBS/onnxruntime" ] && ok "ONNX Runtime : $LIBS/onnxruntime" || warn "ONNX Runtime 없음"
    echo
    echo "  다음 단계: 프로젝트 폴더에서  code .  → VS Code 가 열리면 README_WSL.md 6단계부터 진행"
}

case "${1:-all}" in
    base)        step_base ;;
    gpu)         step_gpu ;;
    openvino)    step_openvino ;;
    opencv)      step_opencv ;;
    onnxruntime) step_onnxruntime ;;
    ultralytics) step_ultralytics ;;
    all)         step_base; step_gpu; step_openvino; step_opencv; step_onnxruntime; summary ;;
    summary)     summary ;;
    *) die "알 수 없는 단계: $1  (all|base|gpu|openvino|opencv|onnxruntime|ultralytics)" ;;
esac
