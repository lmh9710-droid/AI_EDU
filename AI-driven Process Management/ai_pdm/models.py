import torch
import torch.nn as nn

class IndustryLSTM(nn.Module):
    def __init__(self, input_size=1, hidden_size=32, num_layers=2, output_size=1):
        super(IndustryLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # 고속 시계열 특징 학습을 위한 스택형 LSTM
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        # 최종 미래 수치 출력을 위한 선형 회귀 레이어
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        # 인텔 CPU 연산에 최적화된 초기 은닉 상태 및 셀 상태 텐서 배정
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        out, _ = self.lstm(x, (h0, c0))
        return self.fc(out[:, -1, :]) # 마지막 시퀀스 타임스텝 데이터 반환
