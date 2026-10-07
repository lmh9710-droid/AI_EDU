"""
변수 1개에 대한 5분 선행 예측기 (DB 와 무관한 순수 로직 → 실시간 엔진과 오프라인 평가가 공유).
"""
import os
from collections import deque

import numpy as np
import torch

import config as C
from features import SeriesBuffer
from models import QuantileLSTM, pinball_loss
from synth import synth_windows

torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))


def family_ckpt(family):
    return os.path.join(C.CKPT_DIR, f"pretrained_{family}.pt")


def pretrain_family(family, n=40000, epochs=6, seed=0, log=print):
    """합성 열화 데이터로 기본 모델 사전학습 → checkpoints/pretrained_<family>.pt"""
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    X, y = synth_windows(rng, family, n)
    Xv, yv = synth_windows(np.random.default_rng(seed + 99), family, 4000)
    model = QuantileLSTM(nonneg=(family == "energy"))
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    Xt, yt = torch.from_numpy(X).unsqueeze(-1), torch.from_numpy(y)
    Xvt, yvt = torch.from_numpy(Xv).unsqueeze(-1), torch.from_numpy(yv)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xt))
        for b in range(0, len(Xt), 256):
            sel = perm[b:b + 256]
            opt.zero_grad()
            loss = pinball_loss(model(Xt[sel]), yt[sel])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        sched.step()
        model.eval()
        with torch.no_grad():
            pv = model(Xvt)
            vl = pinball_loss(pv, yvt).item()
            cov = ((yvt >= pv[:, 0]) & (yvt <= pv[:, 2])).float().mean().item()
            mae = (pv[:, 1] - yvt).abs().mean().item()
            mae_p = (Xvt[:, -1, 0] - yvt).abs().mean().item()
        log(f"  [{family}] epoch {ep + 1}/{epochs} val_pinball={vl:.4f} MAE={mae:.4f} (persistence {mae_p:.4f}) P10-P90 coverage={cov:.2f}")
    os.makedirs(C.CKPT_DIR, exist_ok=True)
    torch.save({"state": model.state_dict(), "family": family, "version": f"pre-{family}-s{seed}"}, family_ckpt(family))
    return model


class TargetPredictor:
    def __init__(self, equipment_id, spec, ckpt_path=None, online=True, seed=0):
        self.eq = equipment_id
        self.spec = spec
        self.family = spec["family"]
        self.buf = SeriesBuffer(keep_sec=(C.N_IN_BINS + C.HORIZON_BINS) * C.BIN_SEC + 300)
        self.model = QuantileLSTM(nonneg=spec["nonneg"])
        self.version = "untrained"
        self.ckpt_path = ckpt_path
        self._load()
        self.online = online
        self.opt = torch.optim.Adam(self.model.parameters(), lr=C.LEARNING_RATE_ONLINE)
        self.replay = deque(maxlen=C.REPLAY_SIZE)
        self.rng = np.random.default_rng(seed)
        self.synth_pool = None
        self.updates = 0
        self.last_learn_t = None
        self.breach_since = None          # 알람 지속 시간 추적
        self.warn_since = None
        self.pending = deque()            # (pred_t, target_t, p10, p50, p90, persist)
        self.matured = deque()            # (target_t, actual, p10, p50, p90, persist)

    # ------------------------------------------------------------ 체크포인트
    def _load(self):
        for path in (self.ckpt_path, family_ckpt(self.family)):
            if path and os.path.exists(path):
                ck = torch.load(path, map_location="cpu", weights_only=False)
                self.model.load_state_dict(ck["state"])
                self.version = ck.get("version", os.path.basename(path))
                return
        raise FileNotFoundError(f"사전학습 모델 없음: {family_ckpt(self.family)} → `uv run pretrain.py` 먼저 실행")

    def save(self):
        if not self.ckpt_path:
            return
        os.makedirs(os.path.dirname(self.ckpt_path), exist_ok=True)
        if not self.version.endswith("+online"):
            self.version = self.version + "+online"
        torch.save({"state": self.model.state_dict(), "family": self.family, "version": self.version,
                    "updates": self.updates}, self.ckpt_path + ".tmp")
        os.replace(self.ckpt_path + ".tmp", self.ckpt_path)

    # ------------------------------------------------------------ 정규화
    def z(self, x):
        return (np.asarray(x, float) - self.spec["center"]) / self.spec["scale"]

    def unz(self, z):
        return np.asarray(z, float) * self.spec["scale"] + self.spec["center"]

    # ------------------------------------------------------------ 데이터
    def add(self, ts, vals):
        self.buf.extend(ts, vals)

    def window(self, end_t):
        means, gap = self.buf.bin_means(end_t, C.N_IN_BINS)
        return self.z(means), gap

    # ------------------------------------------------------------ 추론
    def predict(self, now_t):
        """반환 dict: status, reason, p10/p50/p90 (물리 단위), current_mean"""
        res = dict(status="VALID", reason="", p10=None, p50=None, p90=None, current_mean=None, sigma_w=None)
        if self.buf.latest_t is None or self.buf.t[0] > now_t - C.N_IN_BINS * C.BIN_SEC + C.BIN_SEC:
            res.update(status="INSUFFICIENT_HISTORY", reason="need 10 min of data")
            return res
        zw, gap = self.window(now_t)
        res["current_mean"] = float(self.unz(zw[-1]))
        # 최근 1분의 개별 측정 산포 (열화로 산포가 커지면 경보가 그만큼 빨라짐)
        res["sigma_w"] = self.buf.within_sigma(now_t, 6)
        if gap > C.MAX_GAP_FRACTION:
            res.update(status="DATA_GAP", reason=f"gap {gap:.0%} in input window")
            return res
        self.model.eval()
        with torch.no_grad():
            q = self.model(torch.from_numpy(zw.astype(np.float32)).view(1, -1, 1))[0].numpy()
        p10, p50, p90 = (float(v) for v in self.unz(q))
        res.update(p10=p10, p50=p50, p90=p90)
        lo, hi = self.spec["phys"]
        if not all(np.isfinite([p10, p50, p90])):
            res.update(status="NON_FINITE", reason="model output not finite")
        elif not (lo <= p50 <= hi):
            res.update(status="OUT_OF_PHYSICAL_RANGE", reason=f"p50 outside [{lo}, {hi}]")
        elif (q[2] - q[0]) > C.MAX_BAND_Z:
            res.update(status="LOW_CONFIDENCE", reason=f"P10-P90 band {p90 - p10:.4g} too wide")
        if res["status"] == "VALID":
            self.pending.append((now_t, now_t + C.HORIZON_SEC, p10, p50, p90, res["current_mean"]))
        return res

    # ------------------------------------------------------------ 알람 판정
    def breach(self, value, sigma=0.0):
        """예측 평균 ± K·σ_within 이 기준표 한계를 넘는지 (= 개별 측정이 불량으로 판정될 것인지)."""
        s = self.spec
        up, dn = value + C.K_SIGMA * sigma, value - C.K_SIGMA * sigma
        if s.get("hi") is not None and (up >= s["hi"] if s.get("hi_inclusive") else up > s["hi"]):
            return s["hi_code"]
        if s.get("lo") is not None and dn < s["lo"]:
            return s["lo_code"]
        return None

    def alarm(self, now_t, res):
        """(kind, code) 또는 None. VALID 예측의 P50±3σ 가 ALARM_PERSIST_SEC 동안 계속 규격 이탈일 때만.
        위험 경고(0.4)는 기준표상 평균 판정이므로 P50 만으로 본다."""
        code = self.breach(res["p50"], res["sigma_w"] or 0.0) if res["status"] == "VALID" else None
        if code:
            self.breach_since = self.breach_since if self.breach_since is not None else now_t
            if now_t - self.breach_since >= C.ALARM_PERSIST_SEC:
                return ("PRED_STOP", code)
            return None
        self.breach_since = None
        warn = self.spec.get("warn_hi")
        if warn is not None and res["status"] == "VALID" and res["p50"] >= warn:
            self.warn_since = self.warn_since if self.warn_since is not None else now_t
            if now_t - self.warn_since >= C.ALARM_PERSIST_SEC:
                return ("WARN", self.spec["warn_code"])
        else:
            self.warn_since = None
        return None

    # ------------------------------------------------------------ 지연 지도학습
    def learn(self, now_t):
        """5분 전 시점의 입력 윈도우 → 지금 실측 구간 평균. BIN_SEC 마다 1회."""
        if not self.online:
            return False
        if self.last_learn_t is not None and now_t - self.last_learn_t < C.BIN_SEC:
            return False
        self.last_learn_t = now_t
        t_in = now_t - C.HORIZON_SEC
        if self.buf.t[0] > t_in - C.N_IN_BINS * C.BIN_SEC + C.BIN_SEC:
            return False
        zw, gap = self.window(t_in)
        target, tgap = self.buf.bin_means(now_t, 1)
        if gap > C.MAX_GAP_FRACTION or tgap > 0:
            return False
        self.replay.append((zw.astype(np.float32), float(self.z(target[0]))))
        if self.synth_pool is None or len(self.synth_pool[0]) < C.ONLINE_BATCH_SYNTH:
            self.synth_pool = synth_windows(self.rng, self.family, 2000)
        k = min(C.ONLINE_BATCH_REAL - 1, len(self.replay) - 1)
        idx = self.rng.choice(len(self.replay) - 1, size=k, replace=False) if k > 0 else []
        real = [self.replay[-1]] + [self.replay[i] for i in idx]
        sx, sy = self.synth_pool
        si = self.rng.choice(len(sx), size=C.ONLINE_BATCH_SYNTH, replace=False)
        X = np.concatenate([np.stack([r[0] for r in real]), sx[si]])
        Y = np.concatenate([np.array([r[1] for r in real], np.float32), sy[si]])
        self.model.train()
        self.opt.zero_grad()
        loss = pinball_loss(self.model(torch.from_numpy(X).unsqueeze(-1)), torch.from_numpy(Y))
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.opt.step()
        self.updates += 1
        return True

    # ------------------------------------------------------------ 성능 감시
    def mature(self, now_t):
        """대상 시각이 지난 예측을 실측(대상 시각 직전 10초 평균)과 대조."""
        while self.pending and self.pending[0][1] <= now_t:
            pt, tt, p10, p50, p90, persist = self.pending.popleft()
            actual, g = self.buf.bin_means(tt, 1)
            if g == 0:
                self.matured.append((tt, float(actual[0]), p10, p50, p90, persist))
        while self.matured and self.matured[0][0] < now_t - C.HEALTH_WINDOW_SEC:
            self.matured.popleft()

    def health(self):
        if not self.matured:
            return None
        a = np.array([(m[1], m[2], m[3], m[4], m[5]) for m in self.matured])
        act, p10, p50, p90, per = a.T
        return dict(n=len(a), mae_model=float(np.abs(p50 - act).mean()),
                    mae_persistence=float(np.abs(per - act).mean()),
                    coverage=float(((act >= p10) & (act <= p90)).mean()))
