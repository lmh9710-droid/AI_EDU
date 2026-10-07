#!/usr/bin/env bash
# =============================================================================
#  run_vision.sh : ai_factory 비전 검사 실행 (엔진 + vision_link 브리지)
#     bash ~/ai_factory/vision/run_vision.sh            ← 그림자 모드 (라인 영향 없음, 기본)
#     bash ~/ai_factory/vision/run_vision.sh --live     ← 실제 연동 (NG 시 4호기 정지·퇴출)
#  종료: 검사 창에서 ESC, 또는 터미널에서 Ctrl+C
# =============================================================================
source "$(dirname "$0")/../scripts/_common.sh"
sf_load_env
cd "$SF_ROOT/vision" || exit 1
[ -x yolo_engine/build/release/yolo_mfg ] || _die "검사 엔진이 빌드되지 않았습니다 → ./scripts/build_all.sh (~/yolo_libs 필요)"
[ -f models/best.onnx ] || _die "모델이 없습니다 → vision/models/best.onnx 를 넣으세요"
if [ "${1:-}" = "--live" ]; then
    [ -S "$SF_HUB_SOCK" ] || _die "LIVE 모드인데 인터록 허브가 실행 중이 아닙니다 → run_hub.sh 먼저"
fi
sf_single_instance vision
exec python3 vision_bridge.py "$@"
