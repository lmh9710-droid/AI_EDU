#!/usr/bin/env bash
# =============================================================================
#  install.sh : 패키지 → ~/ai_factory 설치/업데이트
#
#    cd ~ && unzip -o ai_factory_v2_pkg.zip && bash ai_factory_v2_pkg/install.sh [--no-build]
#
#  규칙
#   - 실행 중인 프로그램이 있으면 설치하지 않음 (실행 파일 교체 실패·불일치 방지)
#   - 현장 설정은 절대 덮어쓰지 않음:
#       scripts/env.sh, vision/config/*, vision/status_map.json, vision/models/*, data/*,
#       ai_pdm/checkpoints/EQ_*.pt (현장에서 학습된 모델)
#     → 새 기본값이 다르면 옆에 *.new 로 저장
#   - 바뀌는 코드 파일은 ~/ai_factory/_backup/<시각>/ 에 원본 보관 후 교체
#   - 패키지에 없는 기존 파일은 지우지 않음
# =============================================================================
set -u
PKG="$(cd "$(dirname "$0")" && pwd)"
DST="${AI_FACTORY:-$HOME/ai_factory}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$DST/_backup/$STAMP"
TEST_MODELS="$HOME/work/infer_acceleration/yolo_mfg/models"
MODEL_SHA="34d34b4c046be60bcac2b2dd1158121d794179ff2e612b913031992a2e65da2f"
ok()   { echo -e "  \033[1;32m✔\033[0m $*"; }
warn() { echo -e "  \033[1;33m⚠\033[0m $*"; }
die()  { echo -e "  \033[1;31m✘\033[0m $*"; exit 1; }

echo "================ ai_factory 설치/업데이트 ================"
echo "  패키지 : $PKG"
echo "  설치   : $DST"
[ "$PKG" = "$DST" ] && die "패키지 폴더와 설치 폴더가 같습니다. 패키지는 별도 폴더에 풀어 주세요"

# 0) 실행 중인 프로그램 확인
running=""
for pat in sf-interlock-hub smart_factory_middleware yolo_mfg vision_bridge.py dashboard/server.py; do
    pgrep -f "$pat" >/dev/null 2>&1 && running="$running $pat"
done
for pid in $(pgrep -f "main.py" 2>/dev/null); do
    [ "$(readlink -f /proc/$pid/cwd 2>/dev/null)" = "$DST/ai_pdm" ] && running="$running ai_pdm/main.py"
done
[ -n "$running" ] && die "실행 중인 프로그램이 있습니다:$running → 모두 종료(Ctrl+C) 후 다시 실행하세요"

mkdir -p "$DST"
is_site_file() {   # 현장 설정·데이터 (덮어쓰지 않음)
    case "$1" in
        scripts/env.sh|vision/config/*|vision/status_map.json|vision/models/*|data/*|ai_pdm/checkpoints/EQ_*) return 0 ;;
    esac
    return 1
}

echo "--- 1. 파일 복사"
n_new=0; n_upd=0; n_same=0; n_keep=0
while IFS= read -r -d '' f; do
    rel="${f#$PKG/}"
    case "$rel" in install.sh|_backup/*) continue ;; esac
    dst="$DST/$rel"
    if [ ! -e "$dst" ]; then
        mkdir -p "$(dirname "$dst")"; cp -p "$f" "$dst"; n_new=$((n_new+1))
    elif cmp -s "$f" "$dst"; then
        n_same=$((n_same+1))
    elif is_site_file "$rel"; then
        cp -p "$f" "$dst.new"; n_keep=$((n_keep+1)); warn "현장 설정 유지: $rel  (새 기본값 → $rel.new)"
    else
        mkdir -p "$BACKUP/$(dirname "$rel")"; cp -p "$dst" "$BACKUP/$rel"; cp -p "$f" "$dst"; n_upd=$((n_upd+1))
    fi
done < <(find "$PKG" -type f -print0)
cp -p "$PKG/install.sh" "$DST/install.sh"
ok "새 파일 $n_new, 갱신 $n_upd, 변경 없음 $n_same, 현장 설정 유지 $n_keep"
[ -d "$BACKUP" ] && ok "이전 버전 보관: $BACKUP"
chmod +x "$DST"/scripts/*.sh "$DST"/middleware/build.sh "$DST"/tools/sim/build.sh "$DST"/vision/run_vision.sh 2>/dev/null

echo "--- 2. 현장 설정"
if [ ! -f "$DST/scripts/env.sh" ]; then
    cp "$DST/scripts/env.sh.example" "$DST/scripts/env.sh"
    warn "scripts/env.sh 를 새로 만들었습니다 → 포트 4개를 반드시 수정하세요 (ls -l /dev/serial/by-id/)"
else
    ok "scripts/env.sh 유지"
    grep -q 'XXXXXXXX\|YYYYYYYY\|ZZZZZZZZ' "$DST/scripts/env.sh" && warn "env.sh 에 예시 포트값이 남아 있습니다"
fi
mkdir -p "$DST/data/vision" "$DST/vision/models"
if [ ! -f "$DST/vision/models/best.onnx" ] && [ -f "$TEST_MODELS/best.onnx" ]; then
    cp "$TEST_MODELS/best.onnx" "$DST/vision/models/" && ok "비전 모델 복사 ($TEST_MODELS)"
fi
if [ -f "$DST/vision/models/best.onnx" ]; then
    sha=$(sha256sum "$DST/vision/models/best.onnx" | cut -d" " -f1)
    [ "$sha" = "$MODEL_SHA" ] && ok "vision/models/best.onnx (품질팀 원본 SHA256 일치)" \
                              || warn "vision/models/best.onnx 가 품질팀 원본과 다릅니다 → status_map.json 의 model_version 확인"
else
    warn "vision/models/best.onnx 없음 (비전을 쓸 때 넣으세요)"
fi

if [ "${1:-}" = "--no-build" ]; then
    echo "--- 3. 빌드 생략 (--no-build)"
else
    echo "--- 3. 빌드"
    bash "$DST/scripts/build_all.sh" || die "빌드 실패. 위 로그를 확인하세요 (설치된 파일은 그대로 유지됨)"
fi
echo "=========================================================="
echo "  완료. 실행 순서: run_hub.sh → run_middleware.sh → run_ai.sh → (선택) run_dashboard.sh, vision/run_vision.sh"
