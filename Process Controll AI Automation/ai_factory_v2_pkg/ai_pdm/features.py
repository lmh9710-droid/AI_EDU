"""시계열 → 10초 구간 평균 시퀀스 (학습·추론·평가가 모두 같은 함수를 사용)."""
import numpy as np
import config as C


class SeriesBuffer:
    """한 변수의 (시각[s], 값) 버퍼. 누적합으로 임의 구간 평균을 O(log n) 에 계산."""

    def __init__(self, keep_sec=1500):
        self.keep_sec = keep_sec
        self.t = np.empty(0)
        self.v = np.empty(0)

    def extend(self, ts, vals):
        if len(ts) == 0:
            return
        self.t = np.concatenate([self.t, np.asarray(ts, float)])
        self.v = np.concatenate([self.v, np.asarray(vals, float)])
        cut = np.searchsorted(self.t, self.t[-1] - self.keep_sec)
        if cut > 0:
            self.t, self.v = self.t[cut:], self.v[cut:]

    @property
    def latest_t(self):
        return self.t[-1] if len(self.t) else None

    def bin_means(self, end_t, n_bins, bin_sec=C.BIN_SEC):
        """end_t 에서 끝나는 n_bins 개 구간 평균. 빈 구간은 직전 값으로 채움. (means, gap_fraction)"""
        edges = end_t - bin_sec * np.arange(n_bins, -1, -1)
        idx = np.searchsorted(self.t, edges, side="right")
        cs = np.concatenate([[0.0], np.cumsum(self.v)])
        cnt = np.diff(idx)
        sums = cs[idx[1:]] - cs[idx[:-1]]
        means = np.full(n_bins, np.nan)
        ok = cnt > 0
        means[ok] = sums[ok] / cnt[ok]
        gap = 1.0 - ok.mean()
        if not ok.any():
            return means, 1.0
        first = np.argmax(ok)
        means[:first] = means[first]
        for i in range(first + 1, n_bins):
            if not ok[i]:
                means[i] = means[i - 1]
        return means, gap

    def within_sigma(self, end_t, n_bins, bin_sec=C.BIN_SEC):
        """최근 n_bins 구간 각각의 내부 표준편차의 중앙값 = 개별 측정값의 단기 산포 (σ_within)."""
        edges = end_t - bin_sec * np.arange(n_bins, -1, -1)
        idx = np.searchsorted(self.t, edges, side="right")
        cs = np.concatenate([[0.0], np.cumsum(self.v)])
        cs2 = np.concatenate([[0.0], np.cumsum(self.v * self.v)])
        cnt = np.diff(idx)
        ok = cnt >= 2
        if not ok.any():
            return 0.0
        s1 = (cs[idx[1:]] - cs[idx[:-1]])[ok]
        s2 = (cs2[idx[1:]] - cs2[idx[:-1]])[ok]
        n = cnt[ok]
        var = np.maximum(s2 - s1 * s1 / n, 0) / (n - 1)
        return float(np.median(np.sqrt(var)))
