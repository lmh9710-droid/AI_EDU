"""
합성 열화 데이터 (정규화 z 공간, 10초 구간 평균 단위).
특정 시뮬레이터 수식을 복제하지 않고 '서서히 진행되다 가속되는 열화'의 일반적인 형태를
무작위로 생성한다 (도메인 랜덤화). 모델은 이것으로 추세 외삽의 사전지식을 얻고,
현장 데이터로 온라인 미세조정된다.
"""
import numpy as np
import config as C


def synth_series(rng, family, length):
    two = family == "two_sided"
    base = rng.normal(0, 0.12) if two else rng.uniform(0.02, 0.08)
    noise = rng.uniform(0.01, 0.15) if two else rng.uniform(0.001, 0.02)
    phi = rng.uniform(0.9, 0.995)
    wstd = (rng.uniform(0.01, 0.2) if two else rng.uniform(0.0, 0.01))
    w = np.zeros(length)
    for i in range(1, length):
        w[i] = phi * w[i - 1] + wstd * np.sqrt(1 - phi ** 2) * rng.normal()
    level = base + w
    if rng.random() < 0.75:                                   # 열화 발생
        onset = rng.integers(-200, length)
        ttf = rng.uniform(18, 300)                            # 3분 ~ 50분 (구간 수)
        shape = rng.uniform(0.8, 3.0)
        direction = 1.0 if (not two or rng.random() < 0.5) else -1.0
        speed = np.exp(np.cumsum(rng.normal(0, 0.03, length)))   # 진행 속도 흔들림
        speed /= speed.mean()
        cum = np.cumsum(speed)
        t = np.arange(length)
        prog = np.where(t >= onset, cum - cum[onset], 0.0) if onset >= 0 else cum + (-onset)
        d = np.clip((prog / ttf) ** shape, 0, 1.6)
        start = base if two else 0.0
        level = level + direction * d * (1.0 - direction * start if two else 1.0)
        noise_t = noise * (1 + 0.6 * d)
        if not two:                                           # 충격 버스트 → 구간 평균 상승
            level = level + (rng.random(length) < 0.3 * d) * d * rng.uniform(0.05, 0.2, length)
        if rng.random() < 0.15:                               # 일부는 정비로 복귀
            fail = np.argmax(d >= 1.0) if (d >= 1.0).any() else None
            if fail is not None:
                rep = fail + rng.integers(10, 60)
                if rep < length:
                    level[rep:] = base + w[rep:]
                    noise_t[rep:] = noise
    else:
        noise_t = np.full(length, noise)
    z = level + noise_t * rng.normal(size=length)
    if not two:
        z = np.abs(z)
    return z


def synth_windows(rng, family, n):
    """(X: n×N_IN, y: n) 학습 쌍. y 는 입력 끝에서 HORIZON_BINS 뒤 값."""
    L = C.N_IN_BINS + C.HORIZON_BINS
    X, y = [], []
    while len(X) < n:
        s = synth_series(rng, family, 400)
        for _ in range(8):
            i = rng.integers(0, len(s) - L)
            X.append(s[i:i + C.N_IN_BINS]); y.append(s[i + L - 1])
    return np.array(X[:n], np.float32), np.array(y[:n], np.float32)
