#!/usr/bin/env bash
# 작업자 명령:  ./scripts/operator.sh RESET | STOP | STATUS
source "$(dirname "$0")/_common.sh"
sf_load_env
case "${1:-STATUS}" in RESET|STOP|STATUS|reset|stop|status) ;; *) _die "사용법: $0 RESET | STOP | STATUS" ;; esac
exec "$SF_ROOT/interlock_hub/target/release/sf-interlock-hub" send "${1:-STATUS}"
