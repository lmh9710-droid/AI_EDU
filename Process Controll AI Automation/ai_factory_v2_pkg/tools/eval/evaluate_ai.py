"""
AI 신뢰성 평가: 실제 아두이노 펌웨어 코드(PC 빌드)를 가상시간으로 돌려 열화 에피소드를 만들고,
실시간 엔진과 동일한 TargetPredictor(온라인 학습 포함)로 재생하여 측정한다.

  - 선행시간: 실측값이 처음 규격을 벗어난 시각 - AI 라인정지 요청 시각 (양수 = AI 가 먼저)
  - 오경보: 정상 운전 장시간 재생 중 PRED_STOP 발생 건수
  - 정확도: 5분 뒤 실측 10초 평균 대비 MAE (모델 vs '현재값 유지'), P10~P90 적중률

사용: python3 evaluate_ai.py [--quick]
"""
import os, sys, json, time, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "ai_pdm"))
import config as C                                    # noqa: E402
from predictor import TargetPredictor                 # noqa: E402
from firmware_stream import run_firmware, forging_records, simple_records   # noqa: E402

SPEC = {t["name"]: (eq["equipment_id"], t) for eq in C.EQUIPMENT for t in eq["targets"]}
PRE_NORMAL = 1500   # 열화 시작 전 정상 운전 25분


def series_for(fw, lines):
    if fw == "Forging_Equipment":
        r, _, _ = forging_records(lines)
        return {"defect_band_energy": (r[:, 0], r[:, 2]), "pressure": (r[:, 0], r[:, 1])}
    if fw == "RollForming_Machine":
        r, _ = simple_records(lines, "ROLLING", 0.8)
        return {"displacement": (r[:, 0], r[:, 1])}
    r, _ = simple_records(lines, "HEAT", 2.0)
    return {"temperature": (r[:, 0], r[:, 1])}


def measured_violation(spec, v):
    hi, lo = spec.get("hi"), spec.get("lo")
    bad = np.zeros(len(v), bool)
    if hi is not None:
        bad |= (v >= hi) if spec.get("hi_inclusive") else (v > hi)
    if lo is not None:
        bad |= v < lo
    return bad


def replay(name, t, v, seed=0):
    eq, spec = SPEC[name]
    p = TargetPredictor(eq, spec, ckpt_path=None, online=True, seed=seed)
    first_stop = first_warn = None
    n_stop = 0; statuses = {}
    last_pred = -1e9; i0 = 0
    stop_times = []
    for i in range(len(t)):
        if t[i] - last_pred < 1.0 and i < len(t) - 1:
            continue
        p.add(t[i0:i + 1], v[i0:i + 1]); i0 = i + 1
        now = t[i]; last_pred = now
        p.learn(now)
        res = p.predict(now)
        p.mature(now)
        statuses[res["status"]] = statuses.get(res["status"], 0) + 1
        a = p.alarm(now, res)
        if a and a[0] == "PRED_STOP":
            n_stop += 1; stop_times.append(now)
            first_stop = first_stop if first_stop is not None else (now, a[1])
        if a and a[0] == "WARN" and first_warn is None:
            first_warn = now
    return dict(first_stop=first_stop, first_warn=first_warn, n_stop=n_stop, stop_times=stop_times,
                statuses=statuses, health=p.health(), updates=p.updates)


def episode(fw, scen, ttf, seed, targets):
    dur = PRE_NORMAL + ttf * 60 * 1.3 + 300
    lines = run_firmware(fw, dur, f"{PRE_NORMAL}:SCN {scen} {ttf}", seed=seed, step_us=50 if fw == "Forging_Equipment" else 500)
    ser = series_for(fw, lines)
    out = []
    for name in targets:
        t, v = ser[name]
        bad = measured_violation(SPEC[name][1], v)
        t_viol = float(t[np.argmax(bad)]) if bad.any() else None
        r = replay(name, t, v, seed)
        lead = None
        if r["first_stop"] and t_viol is not None:
            lead = t_viol - r["first_stop"][0]
        pre_alarm_false = sum(1 for s in r["stop_times"] if s < PRE_NORMAL)
        out.append(dict(fw=fw, scenario=scen, ttf_min=ttf, seed=seed, target=name,
                        onset_s=PRE_NORMAL, measured_violation_s=t_viol,
                        ai_stop_s=r["first_stop"][0] if r["first_stop"] else None,
                        ai_code=r["first_stop"][1] if r["first_stop"] else None,
                        lead_time_s=lead, false_stops_before_onset=pre_alarm_false,
                        valid_share=r["statuses"].get("VALID", 0) / max(1, sum(r["statuses"].values())),
                        health=r["health"]))
    return out


def normal_run(fw, dur, seed, targets):
    lines = run_firmware(fw, dur, "", seed=seed, step_us=50 if fw == "Forging_Equipment" else 500)
    ser = series_for(fw, lines)
    out = []
    for name in targets:
        t, v = ser[name]
        r = replay(name, t, v, seed)
        out.append(dict(fw=fw, scenario="NORMAL", hours=dur / 3600, target=name, false_stops=r["n_stop"],
                        warn=r["first_warn"] is not None, statuses=r["statuses"], health=r["health"]))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); ap.add_argument("--out", default="/tmp/eval_results.jsonl")
    a = ap.parse_args()
    plan = [
        ("Forging_Equipment", "DIE_CRACK", ["defect_band_energy"]),
        ("Forging_Equipment", "HYD_LEAK", ["pressure"]),
        ("Forging_Equipment", "VALVE_STICK", ["pressure"]),
        ("RollForming_Machine", "DIE_WEAR", ["displacement"]),
        ("RollForming_Machine", "THERMAL_GROWTH", ["displacement"]),
        ("Heat_Equipment", "HEATER_AGING", ["temperature"]),
        ("Heat_Equipment", "TC_DRIFT", ["temperature"]),
    ]
    ttfs = [20] if a.quick else [15, 30, 45]
    f = open(a.out, "w")
    for fw, sc, tg in plan:
        for k, ttf in enumerate(ttfs):
            t0 = time.time()
            for r in episode(fw, sc, ttf, seed=11 + k, targets=tg):
                f.write(json.dumps(r) + "\n"); f.flush()
                print(f"{sc:15s} TTF {ttf:2d}m {r['target']:18s} 실측이탈 {r['measured_violation_s']} AI정지 {r['ai_stop_s']} "
                      f"선행 {r['lead_time_s']} 사전오경보 {r['false_stops_before_onset']} VALID {r['valid_share']:.2f} "
                      f"health {r['health']} ({time.time() - t0:.0f}s)", flush=True)
    for fw, tg, dur in [("Forging_Equipment", ["defect_band_energy", "pressure"], 7200),
                        ("RollForming_Machine", ["displacement"], 10800),
                        ("Heat_Equipment", ["temperature"], 10800)]:
        for r in normal_run(fw, dur if not a.quick else 3600, 77, tg):
            f.write(json.dumps(r) + "\n"); f.flush()
            print(f"NORMAL {r['hours']:.1f}h {r['target']:18s} 오경보(PRED_STOP) {r['false_stops']} 경고 {r['warn']} {r['statuses']} health {r['health']}", flush=True)
