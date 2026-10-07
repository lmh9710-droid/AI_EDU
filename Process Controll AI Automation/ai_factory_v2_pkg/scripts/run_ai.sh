#!/usr/bin/env bash
# ③ AI 예측 엔진. 미들웨어가 DB 를 만든 뒤 실행하세요.
source "$(dirname "$0")/_common.sh"
sf_load_env
[ -f "$SF_DB_PATH" ] || _die "DB 가 아직 없습니다 ($SF_DB_PATH) → 미들웨어를 먼저 실행하세요"
[ -S "$SF_HUB_SOCK" ] || _warn "인터록 허브가 실행 중이 아닙니다. AI 예측 정지가 전달되지 않습니다"
sf_single_instance ai
cd "$SF_ROOT/ai_pdm" || exit 1
if command -v uv >/dev/null 2>&1; then exec uv run main.py
else _warn "uv 가 없어 시스템 python3 로 실행합니다 (torch, numpy 필요)"; exec python3 main.py; fi
