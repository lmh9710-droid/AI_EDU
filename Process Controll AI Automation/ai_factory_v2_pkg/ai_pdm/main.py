import logging
import os
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import config as C  # noqa: E402
from engine import EquipmentNode, ensure_schema, open_db  # noqa: E402
from hub_client import HubClient  # noqa: E402
from predictor import family_ckpt, pretrain_family  # noqa: E402

log = logging.getLogger("pdm.main")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    kst = ZoneInfo("Asia/Seoul")
    logging.Formatter.converter = staticmethod(lambda ts: datetime.fromtimestamp(ts, kst).timetuple())

    print("\n=======================================================")
    print("  🔮 PdM AI Engine — 5분 선행 분위수 예측 (P10/P50/P90)")
    print("=======================================================")
    print(f"  DB  : {C.DB_PATH}\n  HUB : {C.HUB_SOCK}\n  CSV : {C.CSV_DIR}\n", flush=True)

    for fam in ("two_sided", "energy"):
        if not os.path.exists(family_ckpt(fam)):
            log.warning("사전학습 모델이 없어 지금 생성합니다 (%s, CPU 수 분 소요)", fam)
            pretrain_family(fam, log=log.info)

    conn = open_db()
    ensure_schema(conn)
    nodes = [EquipmentNode(eq) for eq in C.EQUIPMENT]
    for n in nodes:
        n.initialize(conn)
    hub = HubClient()
    if hub.send("AI_ENGINE", "HEARTBEAT", "ALIVE") is None:
        log.error("🛑 인터록 허브(%s)에 연결할 수 없습니다. 예측은 계속하지만 라인정지 요청이 전달되지 않습니다.", C.HUB_SOCK)

    print("\n🖥️ [LAUNCH] 실시간 예측 시작 (Ctrl+C 종료)\n", flush=True)
    try:
        while True:
            t0 = time.monotonic()
            hub.send("AI_ENGINE", "HEARTBEAT", "ALIVE")
            for n in nodes:
                try:
                    n.step(conn, hub)
                except sqlite3.Error:
                    log.exception("[%s] DB 오류 → 재연결", n.eq["name"])
                    conn.close(); conn = open_db()
                except Exception:
                    log.exception("[%s] 스텝 오류, 다음 주기 계속", n.eq["name"])
            time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        print("\n💾 모델 저장 후 종료", flush=True)
    finally:
        for n in nodes:
            n.save()
        conn.close()
        hub.close()


if __name__ == "__main__":
    main()
