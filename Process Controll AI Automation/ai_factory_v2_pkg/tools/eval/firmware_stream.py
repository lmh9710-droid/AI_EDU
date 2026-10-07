"""가상시간 펌웨어 실행 + 미들웨어와 동일한 계산으로 시계열 생성 (평가/검증용)."""
import os, subprocess, numpy as np

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim", "bin")
BAND = (340, 360)

def run_firmware(name, duration_s, script="", seed=1, step_us=50):
    env = dict(os.environ, SIM_VIRTUAL="1", SIM_DURATION=str(duration_s), SIM_SCRIPT=script,
               SIM_SEED=str(seed), SIM_STEP_US=str(step_us))
    out = subprocess.run([os.path.join(BIN, name)], env=env, capture_output=True, text=True, check=True).stdout
    return out.splitlines()

def checksum_ok(line):
    if "*" not in line: return False
    body, cs = line.rsplit("*", 1)
    x = 0
    for ch in body.encode(): x ^= ch
    return f"{x:02X}" == cs.strip()

def band_rms(window):
    X = np.fft.rfft(window)
    k0, k1 = BAND
    return float(np.sqrt(2.0 * np.sum(np.abs(X[k0:k1 + 1]) ** 2)) / len(window))

def forging_records(lines):
    """1024샘플 윈도우마다 (t, pressure_mean, band_rms). t = 윈도우 끝 시각(s)."""
    seqs, press, vib, truth = [], [], [], []
    for ln in lines:
        if ln.startswith("[FORGING],") and checksum_ok(ln):
            _, s, p, v = ln.split("*")[0].split(",")
            seqs.append(int(s)); press.append(float(p)); vib.append(float(v))
        elif ln.startswith("[FORGING_SIM],") and checksum_ok(ln):
            _, s, sc, d = ln.split("*")[0].split(","); truth.append((int(s) + 1.0, sc, float(d)))
    press, vib = np.array(press), np.array(vib)
    n = len(vib) // 1024
    recs = [((i + 1) * 1.0, press[i*1024:(i+1)*1024].mean(), band_rms(vib[i*1024:(i+1)*1024])) for i in range(n)]
    return np.array(recs), truth, len(seqs)

def simple_records(lines, tag, period_s):
    recs, truth = [], []
    for ln in lines:
        if ln.startswith(f"[{tag}],") and checksum_ok(ln):
            f = ln.split("*")[0].split(",")
            recs.append(((int(f[1]) + 1) * period_s, float(f[2]), float(f[3])))
        elif ln.startswith(f"[{tag}_SIM],") and checksum_ok(ln):
            _, s, sc, d = ln.split("*")[0].split(","); truth.append((int(s) + 1.0, sc, float(d)))
    return np.array(recs), truth
