#!/usr/bin/env bash
# 전체 빌드: C++ 미들웨어, Rust 허브, 펌웨어 PC 시뮬레이터, (있으면) 비전 엔진
#   최초 1회: sudo apt install -y build-essential libsqlite3-dev socat
#            Rust 1.80 이상: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$(dirname "$0")/_common.sh"
cd "$SF_ROOT" || exit 1
fail=0

echo "== 1. C++ 미들웨어"
[ -f /usr/include/sqlite3.h ] || _die "libsqlite3-dev 가 없습니다 → sudo apt install -y libsqlite3-dev"
./middleware/build.sh || fail=1

echo "== 2. Rust 인터록 허브"
[ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
command -v cargo >/dev/null || _die "cargo 가 없습니다 → rustup 설치 (위 주석 참고)"
ver=$(rustc --version | awk '{print $2}')
if [ "$(printf '%s\n1.80.0\n' "$ver" | sort -V | head -1)" != "1.80.0" ]; then
    _die "Rust $ver 은 너무 낮습니다 (1.80 이상 필요). apt 의 cargo 대신 rustup 을 쓰세요"
fi
(cd interlock_hub && cargo build --release --locked) || fail=1

echo "== 3. 펌웨어 PC 시뮬레이터 (하드웨어 없이 시험용)"
./tools/sim/build.sh || fail=1

echo "== 4. 비전 엔진 (선택)"
if [ -d "$HOME/yolo_libs" ] && [ -f vision/yolo_engine/CMakeLists.txt ]; then
    (cd vision/yolo_engine && cmake --preset release > /tmp/vision_cmake.log 2>&1 && cmake --build --preset release >> /tmp/vision_cmake.log 2>&1) \
        && echo "✔ vision/yolo_engine/build/release/yolo_mfg" \
        || { _warn "비전 엔진 빌드 실패 → tail -30 /tmp/vision_cmake.log"; fail=1; }
else
    _warn "~/yolo_libs 가 없어 비전 엔진 빌드를 건너뜁니다 (비전을 안 쓰면 무시)"
fi

[ $fail -eq 0 ] && echo -e "\033[1;32m✅ 전체 빌드 완료\033[0m" || _die "일부 빌드 실패 (위 로그 확인)"
