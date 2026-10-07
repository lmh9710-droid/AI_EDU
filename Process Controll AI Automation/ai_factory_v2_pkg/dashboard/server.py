"""
예측값 vs 실제값 대시보드 서버 (Python 표준 라이브러리만 사용, DB 읽기 전용)

    python3 dashboard/server.py            → http://localhost:8050
    환경변수: SF_DB_PATH, SF_HUB_SOCK, SF_DASH_HOST(기본 127.0.0.1), SF_DASH_PORT(기본 8050)
              SF_DASH_CORS  다른 PC 의 프론트엔드가 /api/data 를 직접 호출할 때 허용할 출처
                            (예: "http://192.168.0.20:3000", 여러 개는 쉼표, 전체 허용은 "*")

판정 기준/대상은 ai_pdm/config.py 를 그대로 읽는다 (기준표와 단일 출처).
예측 P50 은 '목표 시각(target_timestamp)' 에 그려 실측 10초 평균과 직접 겹쳐 비교한다.
"""
import bisect
import calendar
import json
import os
import socket
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ai_pdm"))
import config as C  # noqa: E402

DB_PATH = C.DB_PATH
HUB_SOCK = C.HUB_SOCK
HOST = os.environ.get("SF_DASH_HOST", "127.0.0.1")
PORT = int(os.environ.get("SF_DASH_PORT", "8050"))
MAX_POINTS = 900
CORS = [o.strip() for o in os.environ.get("SF_DASH_CORS", "").split(",") if o.strip()]
CHART_CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"

UNITS = {"defect_band_energy": "RMS", "pressure": "ton", "displacement": "mm", "temperature": "℃"}
EQ_LABEL = {"EQ_FORGING_01": "1호기 압조", "EQ_ROLLING_01": "2호기 전조", "EQ_HEAT_01": "3호기 열처리"}


# ------------------------------------------------------------------ 유틸
def ts_ms(s):
    """'YYYY-MM-DD HH:MM:SS.mmm' (KST, tz 없음) → ms. 화면도 UTC 게터로 그대로 표시하므로 tz 변환 없음."""
    try:
        y, mo, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        h, mi, se = int(s[11:13]), int(s[14:16]), int(s[17:19])
        ms = int(s[20:23]) if len(s) >= 23 else 0
        return calendar.timegm((y, mo, d, h, mi, se, 0, 0, 0)) * 1000 + ms
    except (ValueError, TypeError):
        return None


def ms_ts(ms):
    t = time.gmtime(ms / 1000)
    return time.strftime("%Y-%m-%d %H:%M:%S", t) + f".{int(ms % 1000):03d}"


class Series:
    """시각 정렬된 실측 시계열 + 누적합 → 임의 구간 평균 O(log n)."""

    def __init__(self, rows):
        self.t = [r[0] for r in rows]
        self.v = [r[1] for r in rows]
        self.cs = [0.0]
        for x in self.v:
            self.cs.append(self.cs[-1] + x)

    def mean(self, t0, t1):
        i, j = bisect.bisect_right(self.t, t0), bisect.bisect_right(self.t, t1)
        return (self.cs[j] - self.cs[i]) / (j - i) if j > i else None


def within_sigma(act, end_t, n_bins=6, bin_ms=C.BIN_SEC * 1000):
    """AI 정지 판단에 쓰는 개별 측정 산포 σ (ai_pdm/features.py within_sigma 와 동일 정의)."""
    stds = []
    for k in range(n_bins):
        t1 = end_t - k * bin_ms
        vals = [v for t, v in act if t1 - bin_ms < t <= t1]
        if len(vals) >= 2:
            m = sum(vals) / len(vals)
            stds.append((sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5)
    if not stds:
        return 0.0
    stds.sort()
    mid = len(stds) // 2
    return stds[mid] if len(stds) % 2 else (stds[mid - 1] + stds[mid]) / 2


def downsample(points, n=MAX_POINTS):
    """[(t, v1, v2, ...)] 를 시간 구간 평균으로 n 개 이하로 축소 (None 은 제외하고 평균)."""
    if len(points) <= n:
        return points
    t0, t1 = points[0][0], points[-1][0]
    width = (t1 - t0) / n or 1
    out, bucket, edge = [], [], t0 + width
    for p in points:
        if p[0] > edge and bucket:
            out.append(_avg(bucket)); bucket = []
            while p[0] > edge:
                edge += width
        bucket.append(p)
    if bucket:
        out.append(_avg(bucket))
    return out


def _avg(bucket):
    res = [sum(p[0] for p in bucket) / len(bucket)]
    for k in range(1, len(bucket[0])):
        vals = [p[k] for p in bucket if p[k] is not None]
        res.append(sum(vals) / len(vals) if vals else None)
    return res


def r6(x):
    return None if x is None else round(x, 6)


def hub_status():
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(HUB_SOCK)
        s.sendall(b'{"src":"DASHBOARD","kind":"STATUS","code":"QUERY"}\n')
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(512)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode("utf-8"))
    except (OSError, ValueError):
        return None


def db_ro():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=3.0)
    conn.execute("PRAGMA busy_timeout=3000;")
    return conn


def table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


# ------------------------------------------------------------------ 데이터 조립
def build(minutes):
    conn = db_ro()
    try:
        latest = []
        for eq in C.EQUIPMENT:
            r = conn.execute(f"SELECT MAX(timestamp) FROM {eq['table']}").fetchone()
            if r and r[0]:
                latest.append(ts_ms(r[0]))
        if not latest:
            return {"empty": True, "db": DB_PATH}
        now = max(x for x in latest if x is not None)
        win_ms = minutes * 60_000
        since = ms_ts(now - win_ms - 20_000)
        pred_since = ms_ts(now - win_ms - C.HORIZON_SEC * 1000)
        targets = []
        for eq in C.EQUIPMENT:
            cols = [t["name"] for t in eq["targets"]]
            raw = conn.execute(f"SELECT timestamp, {', '.join(cols)} FROM {eq['table']} WHERE timestamp >= ? ORDER BY timestamp",
                               (since,)).fetchall()
            truth = None
            if table_exists(conn, "tb_sim_truth"):
                truth = conn.execute("SELECT scenario, damage FROM tb_sim_truth WHERE equipment_id=? ORDER BY id DESC LIMIT 1",
                                     (eq["equipment_id"],)).fetchone()
            has_pred = table_exists(conn, eq["pred_table"])
            for j, spec in enumerate(eq["targets"]):
                name = spec["name"]
                act = [(ts_ms(r[0]), r[1 + j]) for r in raw if r[1 + j] is not None]
                act = [a for a in act if a[0] is not None]
                ser = Series(act)
                # 실측 10초 평균 (AI 가 예측하는 대상과 같은 정의)
                mean10 = [(t, ser.mean(t - C.BIN_SEC * 1000, t)) for t, _ in act]
                preds, latest_pred, n_all, n_valid = [], None, 0, 0
                mae_m = mae_p = cover = 0.0
                n_cmp = 0
                if has_pred:
                    rows = conn.execute(
                        f"SELECT timestamp, target_timestamp, current_value, current_mean, predicted_value, p10, p90, "
                        f"prediction_status, invalid_reason FROM {eq['pred_table']} "
                        f"WHERE target = ? AND timestamp >= ? ORDER BY id", (name, pred_since)).fetchall()
                    for r in rows:
                        n_all += 1
                        if r[7] != "VALID" or r[4] is None:
                            continue
                        n_valid += 1
                        tt = ts_ms(r[1])
                        preds.append((tt, r[5], r[4], r[6]))
                        # 목표 시각이 지난 예측 → 실측과 대조
                        if tt is not None and act and tt <= act[-1][0]:
                            a = ser.mean(tt - C.BIN_SEC * 1000, tt)
                            if a is not None:
                                n_cmp += 1
                                mae_m += abs(r[4] - a)
                                mae_p += abs((r[3] if r[3] is not None else r[2]) - a)
                                cover += 1 if (r[5] <= a <= r[6]) else 0
                    if rows:
                        r = rows[-1]
                        latest_pred = dict(pred_ts=r[0], target_ts=r[1], current=r[2], current_mean=r[3], p50=r[4],
                                           p10=r[5], p90=r[6], status=r[7], reason=r[8])
                lo_view = now - win_ms
                tail = act[-200:]
                sigma_w = within_sigma(tail, tail[-1][0]) if tail else 0.0
                targets.append(dict(
                    eq_id=eq["equipment_id"], eq_label=EQ_LABEL.get(eq["equipment_id"], eq["name"]),
                    target=name, label=spec["label"], unit=UNITS.get(name, ""),
                    lo=spec.get("lo"), hi=spec.get("hi"), hi_inclusive=spec.get("hi_inclusive", False),
                    warn=spec.get("warn_hi"), center=spec["center"], scale=spec["scale"],
                    sigma_w=r6(sigma_w), k_sigma=C.K_SIGMA,
                    actual=[[t, r6(v)] for t, v in downsample([a for a in act if a[0] >= lo_view])],
                    mean10=[[t, r6(v)] for t, v in downsample([m for m in mean10 if m[0] >= lo_view])],
                    pred=[[t, r6(a), r6(b), r6(c)] for t, a, b, c in downsample([p for p in preds if p[0] >= lo_view])],
                    latest=latest_pred,
                    metrics=dict(n=n_cmp, mae_model=r6(mae_m / n_cmp) if n_cmp else None,
                                 mae_persist=r6(mae_p / n_cmp) if n_cmp else None,
                                 coverage=round(cover / n_cmp, 3) if n_cmp else None,
                                 valid_share=round(n_valid / n_all, 3) if n_all else None),
                    truth=dict(scenario=truth[0], damage=truth[1]) if truth else None,
                ))
        # 실측 전용 (AI 대상 아님)
        extras = []
        for table, col, label, unit, lo, hi, note in [
            ("tb_rolling_telemetry", "ae_signal", "2호기 초음파 AE", "dB", None, 40.0, "규칙 판정만 (> 40 불량)"),
            ("tb_heat_telemetry", "carbon_ratio", "3호기 탄소 농도", "", 0.40, 0.45, "기록 전용 (판정 없음)"),
        ]:
            rows = conn.execute(f"SELECT timestamp, {col} FROM {table} WHERE timestamp >= ? ORDER BY timestamp",
                                (ms_ts(now - win_ms),)).fetchall()
            pts = [(ts_ms(r[0]), r[1]) for r in rows if r[1] is not None]
            extras.append(dict(label=label, unit=unit, lo=lo, hi=hi, note=note,
                               ref_only=(col == "carbon_ratio"),
                               actual=[[t, r6(v)] for t, v in downsample(pts)]))
        events = []
        if table_exists(conn, "tb_interlock_event"):
            events = [dict(ts=r[0], source=r[1], kind=r[2], code=r[3], value=r[4], command=r[5], result=r[6])
                      for r in conn.execute("SELECT timestamp, source, kind, code, value, command, result "
                                            "FROM tb_interlock_event ORDER BY id DESC LIMIT 15")]
        vision = None
        if table_exists(conn, "tb_vision_inspection"):
            vs = ms_ts(now - win_ms)
            cnt = conn.execute("SELECT SUM(status='OK'), SUM(status LIKE 'NG_%'), COUNT(*), AVG(inference_ms) "
                               "FROM tb_vision_inspection WHERE timestamp >= ?", (vs,)).fetchone()
            ng = [dict(ts=r[0], part=r[1], status=r[2], cls=r[3], conf=r[4], hub=r[5]) for r in conn.execute(
                "SELECT timestamp, part_seq, status, defect_class, confidence, hub_result FROM tb_vision_inspection "
                "WHERE status LIKE 'NG_%' ORDER BY id DESC LIMIT 8")]
            vision = dict(ok=cnt[0] or 0, ng=cnt[1] or 0, total=cnt[2] or 0,
                          avg_ms=round(cnt[3], 2) if cnt[3] is not None else None, recent_ng=ng)
        link = []
        if table_exists(conn, "tb_link_stats"):
            for r in conn.execute("SELECT equipment_id, SUM(received), SUM(lost), SUM(corrupt), SUM(resyncs) "
                                  "FROM tb_link_stats WHERE timestamp >= ? GROUP BY equipment_id", (since,)):
                link.append(dict(eq_id=r[0], eq_label=EQ_LABEL.get(r[0], r[0]), received=r[1], lost=r[2], corrupt=r[3], resyncs=r[4]))
        return dict(empty=False, now=now, window_min=minutes, horizon_ms=C.HORIZON_SEC * 1000,
                    hub=hub_status(), targets=targets, extras=extras, events=events, link=link, vision=vision)
    finally:
        conn.close()


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        origin = self.headers.get("Origin")
        if not CORS or not origin:
            return
        if "*" in CORS:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in CORS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send(self, code, body, ctype):
        try:
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # 브라우저가 새로고침·탭 닫기 등으로 응답을 다 받기 전에 연결을 끊은 경우.
            # 보낼 상대가 없을 뿐 서버에는 문제가 없으므로 조용히 넘긴다.
            pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/static/chart.js":
            local = os.path.join(HERE, "static", "chart.umd.min.js")   # 인터넷 없는 현장: 이 파일을 직접 넣어두면 사용
            if os.path.exists(local):
                with open(local, "rb") as f:
                    return self._send(200, f.read(), "application/javascript")
            self.send_response(302); self.send_header("Location", CHART_CDN); self.end_headers(); return
        if u.path == "/api/data":
            q = parse_qs(u.query)
            minutes = max(5, min(720, int(q.get("minutes", ["30"])[0])))
            try:
                data = build(minutes)
                return self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except sqlite3.Error as e:
                return self._send(503, json.dumps({"error": f"DB 읽기 실패: {e}", "db": DB_PATH}, ensure_ascii=False).encode("utf-8"),
                                  "application/json; charset=utf-8")
        self._send(404, b"not found", "text/plain")


def ensure_indexes():
    """예측 테이블 조회 속도용 인덱스 (최초 1회, 실패해도 대시보드는 동작)."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=3.0)
        for eq in C.EQUIPMENT:
            if table_exists(conn, eq["pred_table"]):
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{eq['pred_table']}_tgt_ts ON {eq['pred_table']}(target, timestamp);")
        conn.commit(); conn.close()
    except sqlite3.Error as e:
        print(f"⚠️ 인덱스 생성 생략: {e}")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"❌ DB 가 없습니다: {DB_PATH}  (미들웨어를 먼저 실행하거나 SF_DB_PATH 확인)")
        sys.exit(1)
    ensure_indexes()
    print(f"📊 대시보드: http://{'localhost' if HOST in ('127.0.0.1', '0.0.0.0') else HOST}:{PORT}   (DB {DB_PATH})")
    if HOST == "0.0.0.0":
        print("🌐 다른 PC 접속 허용 모드 (읽기 전용, 인증 없음 → 사내망에서만 사용)")
    if CORS:
        print(f"🔓 CORS 허용 출처: {', '.join(CORS)}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
