"""작업자 명령 (Rust 인터록 허브 경유).
    uv run send_command.py RESET     정비 완료 후 라인 재가동
    uv run send_command.py STATUS    라인 상태 조회
    uv run send_command.py STOP      수동 라인 정지
"""
import json
import sys

from hub_client import HubClient

KIND = {"RESET": ("RESET", "OPERATOR_RESET"), "STATUS": ("STATUS", "QUERY"), "STOP": ("PRED_STOP", "OPERATOR_STOP")}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1].upper() not in KIND:
        print(__doc__); sys.exit(2)
    kind, code = KIND[sys.argv[1].upper()]
    r = HubClient().send("OPERATOR", kind, code, 0, "send_command.py")
    if r is None:
        print("❌ 인터록 허브에 연결할 수 없습니다 (허브 실행 여부 확인)"); sys.exit(1)
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r.get("ok") else 1)
