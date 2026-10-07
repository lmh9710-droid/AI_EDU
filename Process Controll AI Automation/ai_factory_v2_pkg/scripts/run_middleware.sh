#!/usr/bin/env bash
# ② C++ 미들웨어 (1~3호기 수집·저장·규격 판정). 허브를 먼저 실행하세요.
source "$(dirname "$0")/_common.sh"
sf_load_env
sf_check_port SF_PORT_FORGING "1호기 압조"
sf_check_port SF_PORT_ROLLING "2호기 전조"
sf_check_port SF_PORT_HEAT    "3호기 열처리"
BIN="$SF_ROOT/middleware/smart_factory_middleware"
[ -x "$BIN" ] || _die "미들웨어가 빌드되지 않았습니다 → ./scripts/build_all.sh"
[ -S "$SF_HUB_SOCK" ] || _warn "인터록 허브가 실행 중이 아닙니다 ($SF_HUB_SOCK). 불량 시 라인정지가 전달되지 않습니다 → run_hub.sh 먼저"
mkdir -p "$(dirname "$SF_DB_PATH")"
sf_single_instance middleware
exec "$BIN"
