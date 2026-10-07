#!/usr/bin/env bash
# 아두이노 펌웨어를 PC 시뮬레이터 바이너리로 빌드: tools/sim/bin/<sketch>
set -e
cd "$(dirname "$0")"; mkdir -p bin
for ino in ../../arduino/*.ino; do
  name=$(basename "$ino" .ino)
  g++ -std=c++14 -O2 -Wall -I. -x c++ "$ino" -x none sim_main.cpp -o "bin/$name" -lm
  echo "built bin/$name"
done
