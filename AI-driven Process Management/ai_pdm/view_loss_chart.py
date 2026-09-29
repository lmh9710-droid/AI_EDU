import os
import sqlite3
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt

# 글로벌 경로 고정
DB_PATH = "/home/user/work/middleware/smart_factory_edge.db"
WINDOW_SIZE = 10
TOTAL_PLOT_SAMPLES = 40  # 시인성을 위해 최근 40개 데이터 흐름 동안의 Loss 추이 스캔

class IndustryLSTM(nn.Module):
    def __init__(self, input_size=1, hidden_size=32, num_layers=2, output_size=1):
        super(IndustryLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        out, _ = self.lstm(x, (h0, c0))
        return self.fc(out[:, -1, :])

# 각 설비별 실시간 온라인 훈련을 재시뮬레이션하여 데이터 타임라인별 Loss 스택을 추적하는 함수
def trace_online_learning_loss(table_name, target_column, min_val, max_val):
    try:
        conn = sqlite3.connect(DB_PATH)
        # 시간 정방향 흐름 분석을 위해 전체 적재 데이터 쿼리
        query = f"SELECT {target_column} FROM {table_name} WHERE {target_column} IS NOT NULL ORDER BY id ASC"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) < WINDOW_SIZE + TOTAL_PLOT_SAMPLES:
            return None

        raw_vals = df[target_column].values[-TOTAL_PLOT_SAMPLES-WINDOW_SIZE:].astype(float).reshape(-1, 1)

        scaler = MinMaxScaler(feature_range=(0, 1))
        scaler.fit(np.array([[min_val], [max_val]]))
        scaled_data = scaler.transform(raw_vals)

        model = IndustryLSTM()
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.01)

        loss_history = []

        # 슬라이딩 윈도우 방식으로 온라인 백프로파게이션(오차역전파) 가중치 업데이트 추적
        for i in range(len(scaled_data) - WINDOW_SIZE):
            x_window = scaled_data[i : i + WINDOW_SIZE]
            y_true = scaled_data[i + WINDOW_SIZE]

            X_tensor = torch.FloatTensor(x_window).unsqueeze(0)
            Y_tensor = torch.FloatTensor(y_true).unsqueeze(0)

            model.train()
            optimizer.zero_grad()
            outputs = model(X_tensor)
            loss = criterion(outputs, Y_tensor)
            loss.backward()
            optimizer.step()

            # 인텔 차원 에러 우회용 스칼라 값 추출 (.item())
            loss_history.append(loss.item())

        return loss_history
    except Exception as e:
        print(f"오류: {e}")
        return None

def main():
    if not os.path.exists(DB_PATH):
        print(f"🛑 [ERROR] DB 파일을 찾을 수 없습니다: {DB_PATH}")
        return

    print("📊 [ANALYTICS] 3대 공정별 PyTorch LSTM 실시간 Loss 오차 수렴 추이 연산 중...")
    
    # 3개 설비의 실제 적재 로그 가중치 오차 추적
    loss_forging = trace_online_learning_loss("tb_forging_telemetry", "defect_band_energy", 0.0, 1.2)
    loss_rolling = trace_online_learning_loss("tb_rolling_telemetry", "displacement", 1.0, 1.6)
    loss_heat    = trace_online_learning_loss("tb_heat_telemetry", "temperature", 810.0, 890.0)

    if loss_forging is None or loss_rolling is None or loss_heat is None:
        print("⏳ [WARN] 데이터 적재량이 아직 부족합니다. 미들웨어를 구동하여 데이터를 조금 더 쌓아주세요.")
        return

    # PPT/보고서 와이드형(16:9) 배치 최적화 3단 종형 차트 레이아웃 설정
    fig, axes = plt.subplots(3, 1, figsize=(11, 9))
    plt.style.use('seaborn-v0_8-darkgrid' if 'seaborn-v0_8-darkgrid' in plt.style.available else 'default')

    steps = np.arange(1, len(loss_forging) + 1)

    # --- [SUBPLOT 1] 1호기 압조설비 진동 모델 Loss ---
    axes[0].plot(steps, loss_forging, color='#0288d1', marker='o', linewidth=1.5, label='Vibration LSTM Loss')
    axes[0].set_title("■ 1호기 압조설비 (진동 에너지) - PyTorch LSTM 실시간 Loss 수렴 추이", fontsize=11, fontweight='bold')
    axes[0].set_ylabel("MSE Loss")
    axes[0].legend(loc='upper right')
    axes[0].grid(True, alpha=0.3)

    # --- [SUBPLOT 2] 2호기 전조설비 금형변위 모델 Loss ---
    axes[1].plot(steps, loss_rolling, color='#388e3c', marker='s', linewidth=1.5, label='Displacement LSTM Loss')
    axes[1].set_title("■ 2호기 전조설비 (금형변위) - PyTorch LSTM 실시간 Loss 수렴 추이", fontsize=11, fontweight='bold')
    axes[1].set_ylabel("MSE Loss")
    axes[1].legend(loc='upper right')
    axes[1].grid(True, alpha=0.3)

    # --- [SUBPLOT 3] 3호기 열처리 설비 가열로 온도 모델 Loss ---
    axes[2].plot(steps, loss_heat, color='#7b1fa2', marker='^', linewidth=1.5, label='Temperature LSTM Loss')
    axes[2].set_title("■ 3호기 열처리로 (가열로 온도) - PyTorch LSTM 실시간 Loss 수렴 추이", fontsize=11, fontweight='bold')
    axes[2].set_xlabel("Online Learning Steps (Timeline Flow)", fontsize=11, labelpad=10)
    axes[2].set_ylabel("MSE Loss")
    axes[2].legend(loc='upper right')
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    output_filename = "multi_pdm_model_loss_trend.png"
    plt.savefig(output_filename, dpi=200) # 고화질 결과물 영구 보존 출력
    print(f"💾 [SUCCESS] 3대 설비 AI Loss 추세 검증 차트 저장 완료 -> {os.path.abspath(output_filename)}")
    plt.show()

if __name__ == "__main__":
    main()
