#!/usr/bin/env bash
# ④ 예측 vs 실측 대시보드 → 브라우저에서 http://localhost:8050
#   (추가 설치 불필요: 시스템 python3 표준 라이브러리만 사용, DB 는 읽기 전용)
source "$(dirname "$0")/_common.sh"
sf_load_env
# 다른 PC 에서 보려면 아래 두 줄의 주석을 풀고 수정 (dashboard/API.md 참고)
# export SF_DASH_HOST=0.0.0.0
# export SF_DASH_CORS="http://<프론트PC IP>:<포트>"
sf_single_instance dashboard
exec python3 "$SF_ROOT/dashboard/server.py"
