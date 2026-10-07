#!/usr/bin/env bash
# 하드웨어 없이 전체 시스템 시험: 실제 펌웨어 코드를 PC 에서 실행해 가상 시리얼 4개를 만든다.
# 사용: ./sim_ports.sh  → 다른 터미널에서 env.sh 의 포트를 /tmp/sfsim/*.host 로 바꿔 실행
B="$(cd "$(dirname "$0")/../tools/sim/bin" && pwd)"; mkdir -p /tmp/sfsim
for n in Forging_Equipment RollForming_Machine Heat_Equipment conveyor_controll; do
  socat PTY,link=/tmp/sfsim/$n.host,raw,echo=0 EXEC:$B/$n 2>/tmp/sfsim/$n.err &
done
echo "가상 포트: /tmp/sfsim/{Forging_Equipment,RollForming_Machine,Heat_Equipment,conveyor_controll}.host"
echo "시나리오 주입 예: echo 'SCN HYD_LEAK 8' > /tmp/sfsim/Forging_Equipment.host"
wait
