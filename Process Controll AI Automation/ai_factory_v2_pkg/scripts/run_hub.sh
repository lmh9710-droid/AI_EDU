#!/usr/bin/env bash
# ① 가장 먼저 실행: Rust 인터록 허브 (4호기 컨베이어 단독 제어)
source "$(dirname "$0")/_common.sh"
sf_load_env
sf_check_port SF_PORT_CONVEYOR "4호기 컨베이어"
BIN="$SF_ROOT/interlock_hub/target/release/sf-interlock-hub"
[ -x "$BIN" ] || _die "허브가 빌드되지 않았습니다 → ./scripts/build_all.sh"
mkdir -p "$(dirname "$SF_DB_PATH")"
sf_single_instance hub
exec "$BIN"
