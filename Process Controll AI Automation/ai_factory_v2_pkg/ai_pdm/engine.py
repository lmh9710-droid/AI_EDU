import csv
import logging
import os
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

import config as C
from predictor import TargetPredictor

log = logging.getLogger("pdm.engine")
KST = ZoneInfo("Asia/Seoul")


def ts_to_sec(ts_list):
    """'YYYY-MM-DD HH:MM:SS.mmm' (KST, tz 없음) → 초. 차이만 쓰므로 tz 해석 없이 그대로 사용."""
    return np.array([s.replace(" ", "T") for s in ts_list], dtype="datetime64[ms]").astype("int64") / 1000.0


def sec_to_ts(sec):
    return str(np.datetime64(int(round(sec * 1000)), "ms")).replace("T", " ")


def kst_wall_sec():
    return ts_to_sec([datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]])[0]


def open_db():
    conn = sqlite3.connect(C.DB_PATH, timeout=5.0)
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def ensure_schema(conn):
    for eq in C.EQUIPMENT:
        t = eq["pred_table"]
        conn.execute(f"CREATE TABLE IF NOT EXISTS {t} (id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(C.PRED_COLUMNS)});")
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        for col in C.PRED_COLUMNS + (f"{C.LEGACY_PRED_COL[t]} REAL",):
            name, typ = col.split()[0], " ".join(col.split()[1:]).replace(" NOT NULL", "")
            if name not in have:
                conn.execute(f"ALTER TABLE {t} ADD COLUMN {name} {typ};")
                log.info("🔧 마이그레이션: %s.%s 추가", t, name)
    conn.execute("""CREATE TABLE IF NOT EXISTS tb_model_health (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
                    equipment_id TEXT, target TEXT, n INTEGER, mae_model REAL, mae_persistence REAL, coverage_p10_p90 REAL,
                    online_updates INTEGER, model_version TEXT);""")
    conn.commit()


class EquipmentNode:
    def __init__(self, eq):
        self.eq = eq
        self.id = eq["equipment_id"]
        self.preds = {t["name"]: TargetPredictor(self.id, t, ckpt_path=os.path.join(C.CKPT_DIR, f"{self.id}_{t['name']}.pt"))
                      for t in eq["targets"]}
        self.cols = [t["name"] for t in eq["targets"]]
        self.last_id = None
        self.latest_raw = {}
        self.last_pred_t = None
        self.last_health = time.monotonic()
        self.last_ckpt = time.monotonic()
        self.last_hub_err = 0.0
        os.makedirs(C.CSV_DIR, exist_ok=True)
        self.csv_path = os.path.join(C.CSV_DIR, f"{eq['pred_table']}.csv")

    def _fetch(self, conn, where, params):
        cols = ", ".join(self.cols)
        return conn.execute(f"SELECT id, timestamp, {cols} FROM {self.eq['table']} WHERE {where} ORDER BY id", params).fetchall()

    def initialize(self, conn):
        row = conn.execute(f"SELECT MAX(id), MAX(timestamp) FROM {self.eq['table']}").fetchone()
        if row[0] is None:
            self.last_id = 0
        else:
            keep = (C.N_IN_BINS + C.HORIZON_BINS) * C.BIN_SEC + 120
            since = sec_to_ts(ts_to_sec([row[1]])[0] - keep)
            first = conn.execute(f"SELECT MIN(id) FROM {self.eq['table']} WHERE timestamp >= ?", (since,)).fetchone()[0]
            self.last_id = (first or row[0]) - 1
            self._ingest(self._fetch(conn, "id > ?", (self.last_id,)))
        for name, p in self.preds.items():
            log.info("✅ [%s/%s] 모델 %s 로드, 이력 %.0f초 확보", self.eq["name"], name, p.version,
                     (p.buf.t[-1] - p.buf.t[0]) if len(p.buf.t) else 0)

    def _ingest(self, rows):
        if not rows:
            return False
        self.last_id = rows[-1][0]
        t = ts_to_sec([r[1] for r in rows])
        for j, name in enumerate(self.cols):
            v = np.array([r[2 + j] for r in rows], dtype=float)
            ok = np.isfinite(v)
            self.preds[name].add(t[ok], v[ok])
            if ok.any():
                self.latest_raw[name] = (rows[int(np.nonzero(ok)[0][-1])][1], float(v[ok][-1]))
        return True

    def step(self, conn, hub):
        if not self._ingest(self._fetch(conn, "id > ?", (self.last_id,))):
            return
        now_t = max(p.buf.latest_t for p in self.preds.values() if p.buf.latest_t is not None)
        if self.last_pred_t is not None and now_t - self.last_pred_t < 1.0:
            return
        self.last_pred_t = now_t
        stale = kst_wall_sec() - now_t > C.STALE_SEC
        rows = []
        for name, p in self.preds.items():
            p.learn(now_t)
            res = p.predict(now_t)
            if stale and res["status"] == "VALID":
                res.update(status="DATA_STALE", reason="latest sample older than 5s")
            p.mature(now_t)
            ts_str, cur = self.latest_raw.get(name, (sec_to_ts(now_t), None))
            target_ts = sec_to_ts(ts_to_sec([ts_str])[0] + C.HORIZON_SEC)
            rows.append((name, p, res, ts_str, target_ts, cur))
            alarm = p.alarm(now_t, res)
            if alarm and hub is not None:
                kind, code = alarm
                spec = p.spec
                limit = spec.get("hi") if code == spec.get("hi_code") else spec.get("lo") if code == spec.get("lo_code") else spec.get("warn_hi")
                detail = (f"5분 뒤 {spec['label']} P50={res['p50']:.5g} (P10 {res['p10']:.5g} ~ P90 {res['p90']:.5g}), "
                          f"개별산포 3σ={3 * (res['sigma_w'] or 0):.3g}, 기준 {limit}")
                r = hub.send(f"AI_{self.id}", kind, code, res["p50"], detail)
                icon = "🔮🚨" if kind == "PRED_STOP" else "🔮⚠️"
                if r is None:
                    if time.monotonic() - self.last_hub_err >= 10:   # 허브 장애 시 로그 폭주 방지 (10초에 1번)
                        self.last_hub_err = time.monotonic()
                        log.error("🛑 [%s] %s %s 를 인터록 허브에 전달하지 못함! 라인이 정지되지 않습니다 (%s)",
                                  self.eq["name"], kind, code, C.HUB_SOCK)
                elif not str(r.get("result", "")).startswith("SUPPRESSED"):
                    log.warning("%s [%s] %s → 허브 %s | %s", icon, self.eq["name"], code, r.get("result"), detail)
        self._write(conn, rows)
        self._health_and_ckpt(conn)

    def _write(self, conn, rows):
        legacy = C.LEGACY_PRED_COL[self.eq["pred_table"]]
        for name, p, res, ts_str, target_ts, cur in rows:
            leg = res["p50"] if p.spec.get("legacy_col") == legacy else None
            conn.execute(
                f"INSERT INTO {self.eq['pred_table']} (timestamp, target_timestamp, equipment_id, target, current_value, current_mean, "
                f"predicted_value, p10, p90, prediction_status, invalid_reason, model_version, {legacy}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);",
                (ts_str, target_ts, self.id, name, cur, res["current_mean"], res["p50"], res["p10"], res["p90"],
                 res["status"], res["reason"], p.version, leg))
            if res["status"] == "VALID":
                log.info("📈 [%s/%s] 현재 %s → 5분 뒤(%s) P50 %.6g [P10 %.6g ~ P90 %.6g]", self.eq["name"], p.spec["label"],
                         cur, target_ts[11:19], res["p50"], res["p10"], res["p90"])
            else:
                log.info("⏸️ [%s/%s] %s %s", self.eq["name"], p.spec["label"], res["status"], res["reason"])
        conn.commit()
        new = not os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["equipment_id", "target", "timestamp", "current_value", "current_mean", "predicted_value",
                            "p10", "p90", "target_timestamp", "prediction_status", "invalid_reason", "model_version"])
            for name, p, res, ts_str, target_ts, cur in rows:
                w.writerow([self.id, name, ts_str, repr(cur) if cur is not None else "", res["current_mean"],
                            "" if res["p50"] is None else repr(res["p50"]), res["p10"], res["p90"], target_ts,
                            res["status"], res["reason"], p.version])

    def _health_and_ckpt(self, conn):
        now = time.monotonic()
        if now - self.last_health >= C.HEALTH_EVERY_SEC:
            self.last_health = now
            ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            for name, p in self.preds.items():
                h = p.health()
                if h:
                    conn.execute("INSERT INTO tb_model_health (timestamp, equipment_id, target, n, mae_model, mae_persistence, "
                                 "coverage_p10_p90, online_updates, model_version) VALUES (?,?,?,?,?,?,?,?,?);",
                                 (ts, self.id, name, h["n"], h["mae_model"], h["mae_persistence"], h["coverage"], p.updates, p.version))
                    log.info("🩺 [%s/%s] 최근 30분 대조 %d건: MAE 모델 %.4g / 현재값유지 %.4g, P10~P90 적중 %.0f%%",
                             self.eq["name"], name, h["n"], h["mae_model"], h["mae_persistence"], h["coverage"] * 100)
            conn.commit()
        if now - self.last_ckpt >= C.CHECKPOINT_EVERY_SEC:
            self.last_ckpt = now
            self.save()

    def save(self):
        for p in self.preds.values():
            p.save()
