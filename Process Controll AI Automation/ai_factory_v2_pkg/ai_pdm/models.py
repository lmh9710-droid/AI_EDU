import torch
import torch.nn as nn
import torch.nn.functional as F


class QuantileLSTM(nn.Module):
    """
    입력: (B, T, 1) 정규화 값 z 의 10초 구간 평균 시퀀스
    출력: (B, 3) 5분 뒤 z 의 P10 / P50 / P90

    - P50 = 마지막 구간값 + 예측 변화량  (변화량을 학습 → 수준이 달라도 일반화)
    - P10 = P50 - softplus(a), P90 = P50 + softplus(b)  → 분위수 역전 불가
    - nonneg=True (진동 RMS 처럼 음수가 물리적으로 불가능한 값):
      세 출력에 모두 단조증가 softplus 변환을 적용 → 모델 구조상 음수 출력 불가 (후처리 클리핑 아님)
    """

    def __init__(self, hidden_size=48, num_layers=2, nonneg=False, beta=12.0):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden_size, num_layers, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden_size + 1, hidden_size), nn.Tanh(), nn.Linear(hidden_size, 3))
        self.nonneg = nonneg
        self.beta = beta

    def forward(self, x):
        out, _ = self.lstm(x)
        last = x[:, -1, :]                                  # (B,1)
        h = torch.cat([out[:, -1, :], last], dim=1)
        m, a, b = self.head(h).unbind(dim=1)
        p50 = last.squeeze(1) + m
        p10 = p50 - F.softplus(a)
        p90 = p50 + F.softplus(b)
        q = torch.stack([p10, p50, p90], dim=1)
        if self.nonneg:
            q = F.softplus(q, beta=self.beta)
        return q


def pinball_loss(pred, target, quantiles=(0.1, 0.5, 0.9)):
    """pred (B,3), target (B,)"""
    losses = []
    for i, q in enumerate(quantiles):
        e = target - pred[:, i]
        losses.append(torch.maximum(q * e, (q - 1) * e))
    return torch.stack(losses, dim=1).mean()
