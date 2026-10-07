"""
비전 검사 ↔ 스마트팩토리 연동 모듈 (Python 표준 라이브러리만 사용)

  - 검사 결과를 SQLite tb_vision_inspection 에 기록
  - NG 판정이면 Rust 인터록 허브에 DEFECT 전송 → 4호기 '라인정지 후 퇴출'
    (4호기 시리얼 포트에는 절대 직접 접근하지 않는다. 포트는 허브 단독 소유)

사용 예 (비전 추론 코드 안에서):
    from vision_link import VisionLink
    vl = VisionLink(model_version="yolox-s-bolt-v1")
    vl.record(status="NG_VISION_CRACK", defect_class="crack", confidence=0.91,
              bbox=[x1, y1, x2, y2], inference_ms=7.4, part_seq=1234, image_path="/data/ng/1234.jpg")
    vl.record(status="OK", confidence=0.98, inference_ms=7.1, part_seq=1235)

환경변수 (scripts/env.sh 를 source 하면 자동 적용):
    SF_DB_PATH          DB 경로
    SF_HUB_SOCK         허브 소켓 (기본 /tmp/sf_interlock.sock)
    SF_VISION_MIN_CONF  이 신뢰도 미만의 NG 는 기록만 하고 라인을 세우지 않음 (기본 0.5)
"""
import json
import os
import socket
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

SCHEMA = """CREATE TABLE IF NOT EXISTS tb_vision_inspection (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, equipment_id TEXT,
    part_seq INTEGER, status TEXT, defect_class TEXT, confidence REAL, bbox TEXT,
    inference_ms REAL, model_version TEXT, image_path TEXT, hub_result TEXT);"""


def now_kst():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class VisionLink:
    def __init__(self, equipment_id="EQ_VISION_01", model_version="unknown",
                 db_path=None, hub_sock=None, min_conf=None):
        self.eq = equipment_id
        self.model_version = model_version
        self.db_path = db_path or os.environ.get("SF_DB_PATH", os.path.expanduser("~/ai_factory/data/smart_factory_v2.db"))
        self.hub_sock = hub_sock or os.environ.get("SF_HUB_SOCK", "/tmp/sf_interlock.sock")
        self.min_conf = float(min_conf if min_conf is not None else os.environ.get("SF_VISION_MIN_CONF", "0.5"))
        self.conn = sqlite3.connect(self.db_path, timeout=5.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute(SCHEMA)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_vision_ts ON tb_vision_inspection(timestamp);")
        self.conn.commit()

    # ------------------------------------------------------------ 허브
    def _send_hub(self, kind, code, value, detail):
        msg = json.dumps({"src": "VISION_" + self.eq, "kind": kind, "code": code,
                          "value": float(value or 0.0), "detail": detail}, ensure_ascii=False) + "\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect(self.hub_sock)
                s.sendall(msg.encode("utf-8"))
                line = s.makefile("r", encoding="utf-8").readline()
                return json.loads(line) if line else None
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------ 기록 + 인터록
    def record(self, status, defect_class=None, confidence=None, bbox=None, inference_ms=None,
               part_seq=None, image_path=None):
        """
        status: "OK" 또는 "NG_" 로 시작하는 코드 (예: NG_VISION_CRACK, NG_VISION_THREAD)
        반환: 허브 응답 문자열 (OK 이면 None)
        """
        is_ng = isinstance(status, str) and status.startswith("NG_")
        hub_result = None
        if is_ng:
            if confidence is not None and confidence < self.min_conf:
                hub_result = f"BELOW_MIN_CONF({self.min_conf})"
            else:
                detail = f"vision {defect_class or status} conf={confidence} part={part_seq} model={self.model_version}"
                r = self._send_hub("DEFECT", status, confidence, detail)
                if r is None:
                    hub_result = "HUB_UNREACHABLE"
                    print(f"🛑 [VISION] {status} 를 인터록 허브에 전달하지 못함! ({self.hub_sock})", flush=True)
                else:
                    hub_result = r.get("result")
                    if not str(hub_result).startswith("SUPPRESSED"):
                        print(f"📷🚨 [VISION] {status} conf={confidence} → 허브 {hub_result}", flush=True)
        self.conn.execute(
            "INSERT INTO tb_vision_inspection (timestamp, equipment_id, part_seq, status, defect_class, confidence, "
            "bbox, inference_ms, model_version, image_path, hub_result) VALUES (?,?,?,?,?,?,?,?,?,?,?);",
            (now_kst(), self.eq, part_seq, status, defect_class, confidence,
             json.dumps(bbox) if bbox is not None else None, inference_ms, self.model_version, image_path, hub_result))
        self.conn.commit()
        return hub_result

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    # 배선 시험: python3 vision_link.py TEST_NG  → 실제로 4호기가 정지 후 퇴출됩니다
    import sys
    vl = VisionLink(model_version="wiring-test")
    if len(sys.argv) > 1 and sys.argv[1] == "TEST_NG":
        print("결과:", vl.record("NG_VISION_TEST", defect_class="test", confidence=0.99, inference_ms=0, part_seq=0))
    else:
        print("결과:", vl.record("OK", confidence=0.99, inference_ms=0, part_seq=0), "(OK 는 허브에 보내지 않음, DB 기록만)")
        print("정지 배선 시험은: python3 vision_link.py TEST_NG")
