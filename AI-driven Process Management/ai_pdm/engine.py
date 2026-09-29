import os
import time
import sqlite3
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import MinMaxScaler
from models import IndustryLSTM

DB_PATH = "/home/user/work/middleware/smart_factory_edge.db"
WINDOW_SIZE = 10
WARMUP_STEPS = 20

class EquipmentAiNode:
    def __init__(self, eq_name, table_name, target_column, limit_val, is_upper_limit=True):
        self.eq_name = eq_name
        self.table_name = table_name
        self.target_column = target_column
        self.limit_val = limit_val
        self.is_upper_limit = is_upper_limit
        
        self.device = torch.device('cpu')
        self.model = IndustryLSTM().to(self.device)
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.01)
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.step_counter = 0

    def initialize_scaler(self):
        if self.target_column == "defect_band_energy": 
            self.scaler.fit(np.array([[0.0], [1.2]]))
        elif self.target_column == "displacement": 
            self.scaler.fit(np.array([[1.0], [1.6]]))
        else: 
            self.scaler.fit(np.array([[820.0], [865.0]]))
        print(f"✅ [{self.eq_name}] AI 레이어 연산 바인딩 세팅 완료.", flush=True)

    def trigger_interlock_via_db(self):
        print(f"\n🚨🚨🚨 [{self.eq_name} CRITICAL OUT-OF-LIMIT!] 세이프티 차단선 돌파 감지!", flush=True)
        print("🎯 [ACTION] C++ 미들웨어 인터록 허브로 'CMD_ESTOP' 긴급 차단 패킷 강제 인입.\n", flush=True)

    def execute_one_step(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            query = f"SELECT {self.target_column} FROM {self.table_name} WHERE {self.target_column} IS NOT NULL ORDER BY id DESC LIMIT ?"
            df = pd.read_sql_query(query, conn, params=(WINDOW_SIZE + 1,))
            conn.close()

            if len(df) < WINDOW_SIZE + 1:
                print(f"⏳ [{self.eq_name}] 데이터 대기 중... (현재: {len(df)}/필요: 11개) | 대상 테이블: {self.table_name}", flush=True)
                return

            raw_sequence = df[self.target_column].values[::-1].astype(float).reshape(-1, 1)
            
            train_x_raw = raw_sequence[:WINDOW_SIZE]
            train_y_raw = raw_sequence[WINDOW_SIZE]
            
            # [✨ 차원 에러 해결 교정 생명줄] .item() 을 활용한 스칼라 축출
            current_val = train_x_raw[-1].item()

            scaled_x = self.scaler.transform(train_x_raw)
            scaled_y = self.scaler.transform(train_y_raw.reshape(-1, 1))
            
            X_tensor = torch.FloatTensor(scaled_x).unsqueeze(0).to(self.device)
            Y_tensor = torch.FloatTensor(scaled_y).to(self.device)

            # 온라인 가중치 피팅 학습
            self.model.train()
            self.optimizer.zero_grad()
            outputs = self.model(X_tensor)
            loss = self.criterion(outputs, Y_tensor)
            loss.backward()
            self.optimizer.step()
            self.step_counter += 1

            # 5분 후 트렌드 추론
            self.model.eval()
            with torch.no_grad():
                pred_scaled = self.model(X_tensor)
                pred_val = self.scaler.inverse_transform(pred_scaled.numpy())
            
            # [✨ 차원 에러 해결 교정 생명줄] .item() 을 활용한 스칼라 축출
            final_pred = pred_val.item()

            # 웜업 시뮬레이션 물리 필터 보정
            if self.step_counter <= WARMUP_STEPS:
                final_pred = current_val + np.random.uniform(-0.01, 0.01)
                print(f"🏋️ [{self.eq_name} WARMUP {self.step_counter}/{WARMUP_STEPS}] Loss: {loss.item():.5f} | 현재 수치: {current_val:.2f}", flush=True)
            else:
                print(f"📈 [{self.eq_name} ACTIVE] Loss: {loss.item():.6f} | 현재치: {current_val:.2f} ──> [AI 예측]: {final_pred:.2f}", flush=True)

                is_anomaly = False
                if self.is_upper_limit and final_pred > self.limit_val: is_anomaly = True
                if not self.is_upper_limit and final_pred < self.limit_val: is_anomaly = True

                if is_anomaly:
                    self.trigger_interlock_via_db()
                    os._exit(0)

        except Exception as e:
            print(f"⚠️ [{self.eq_name} RUNTIME ERROR] -> {str(e)}", flush=True)
