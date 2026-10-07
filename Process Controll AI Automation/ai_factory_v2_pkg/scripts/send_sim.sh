#!/usr/bin/env bash
# 가상 센서 보드에 명령 보내기 (설정 자동 로드 → "ambiguous redirect" 오류 방지)
#   ./scripts/send_sim.sh 1 "SCN HYD_LEAK 20"     1호기에 유압 누유 20분
#   ./scripts/send_sim.sh 2 REPAIR                2호기 정비
#   ./scripts/send_sim.sh all REPAIR              1~3호기 모두 정비
#   ./scripts/send_sim.sh all "AUTO 0"            자동 발생 모두 끄기
source "$(dirname "$0")/_common.sh"
sf_load_env
[ $# -eq 2 ] || _die "사용법: $0 <1|2|3|all> \"명령\"   (예: $0 1 \"SCN HYD_LEAK 20\")"
case "$1" in
  1) targets=(SF_PORT_FORGING) ;; 2) targets=(SF_PORT_ROLLING) ;; 3) targets=(SF_PORT_HEAT) ;;
  all) targets=(SF_PORT_FORGING SF_PORT_ROLLING SF_PORT_HEAT) ;;
  *) _die "설비 번호는 1, 2, 3, all 중 하나입니다" ;;
esac
for v in "${targets[@]}"; do
    sf_check_port "$v" "$v"
    printf '%s\n' "$2" > "${!v}" || _die "${!v} 에 쓰기 실패"
    echo "✔ $v ← $2   (결과는 미들웨어 화면의 📟 줄)"
done
