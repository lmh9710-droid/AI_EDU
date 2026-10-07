#!/usr/bin/env bash
# sudo apt install -y libsqlite3-dev  (최초 1회)
set -e
cd "$(dirname "$0")"
g++ -std=c++14 -O2 -Wall -Wextra -pthread main.cpp DatabaseManager.cpp HubClient.cpp EquipmentNodes.cpp -lsqlite3 -o smart_factory_middleware
echo "✅ build ok -> $(pwd)/smart_factory_middleware"
