import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

# 1. 진짜 C++ 미들웨어 데이터베이스 파일 경로 지정
DB_PATH = "/home/user/work/middleware/smart_factory_edge.db"

if not os.path.exists(DB_PATH):
    print(f"🛑 [ERROR] 진짜 DB 파일을 찾을 수 없습니다. 경로를 확인하세요: {DB_PATH}")
    exit()

# 2. SQLite3 연결 및 각 공정별 테이블 데이터 가로채기
conn = sqlite3.connect(DB_PATH)
df_forging = pd.read_sql_query("SELECT id, timestamp, defect_band_energy FROM tb_forging_telemetry ORDER BY id ASC", conn)
df_rolling = pd.read_sql_query("SELECT id, timestamp, displacement FROM tb_rolling_telemetry ORDER BY id ASC", conn)
df_heat    = pd.read_sql_query("SELECT id, timestamp, temperature FROM tb_heat_telemetry ORDER BY id ASC", conn)
conn.close()

print(f"📊 [DATA] 1호기({len(df_forging)}건), 2호기({len(df_rolling)}건), 3호기({len(df_heat)}건) 수집 데이터 로드 완료.")

# 3. PPT 및 보고서 해상도에 맞춘 3단 통합 그래프 캔버스 드로잉 (16:9 와이드 규격)
fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=False)
plt.rcParams['font.family'] = 'sans-serif'

# --- [GRAPH 1] 1호기 압조 설비 진동 분석 ---
axes[0].plot(df_forging['id'], df_forging['defect_band_energy'], color='#0288d1', label='350Hz Defect Band Energy', linewidth=1.8)
axes[0].axhline(y=0.8, color='red', linestyle='--', alpha=0.8, label='Interlock Limit (0.8)')
axes[0].set_title("■ 1호기 압조 설비 - C++ FFT 주파수 대역 에너지 변동 추이", fontsize=11, fontweight='bold')
axes[0].set_ylabel("Energy (RMS)")
axes[0].legend(loc='upper left')
axes[0].grid(True, alpha=0.4)

# --- [GRAPH 2] 2호기 전조 설비 변위 분석 ---
axes[1].plot(df_rolling['id'], df_rolling['displacement'], color='#388e3c', label='Die Displacement (mm)', linewidth=1.8)
axes[1].set_title("■ 2호기 전조 설비 - 나사산 가공 금형 변위 센서 추이", fontsize=11, fontweight='bold')
axes[1].set_ylabel("Displacement (mm)")
axes[1].legend(loc='upper left')
axes[1].grid(True, alpha=0.4)

# --- [GRAPH 3] 3호기 열처리 설비 온도 및 AI 인터록 분석 ---
axes[2].plot(df_heat['id'], df_heat['temperature'], color='#f57c00', label='Furnace Temperature (℃)', linewidth=1.8)
axes[2].axhline(y=835.0, color='red', linestyle='--', alpha=0.8, label='LSTM E-STOP Limit (835℃)')
axes[2].set_title("■ 3호기 열처리 설비 - 가열로 온도 추이 및 PyTorch AI 세이프티 경계선", fontsize=11, fontweight='bold')
axes[2].set_xlabel("Data Sequence (Timeline)")
axes[2].set_ylabel("Temperature (℃)")
axes[2].legend(loc='upper left')
axes[2].grid(True, alpha=0.4)

# 4. 이미지 파일 파일 저장 및 디스플레이 시연
plt.tight_layout()
chart_output_name = "smart_factory_analytics.png"
plt.savefig(chart_output_name, dpi=200) # 고화질 PNG 출력 저장

print(f"💾 [SUCCESS] 3단 통합 공정 데이터 분석 차트가 영구 저장되었습니다 -> {os.path.abspath(chart_output_name)}")
plt.show()
