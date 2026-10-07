"""스마트팩토리 PdM AI 엔진 설정. 판정 기준은 C++ Common.h 의 Spec 과 반드시 동일하게 유지할 것."""
import os

DB_PATH = os.environ.get("SF_DB_PATH", os.path.expanduser("~/work/middleware/smart_factory_edge.db"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.environ.get("SF_CSV_DIR", os.path.join(BASE_DIR, "predictions"))
CKPT_DIR = os.environ.get("SF_CKPT_DIR", os.path.join(BASE_DIR, "checkpoints"))
HUB_SOCK = os.environ.get("SF_HUB_SOCK", "/tmp/sf_interlock.sock")

# ---------------------------------------------------------------- 시계열 구성
BIN_SEC = 10                 # 10초 구간 평균 (센서 주기가 달라도 같은 시간 해상도로 정렬)
N_IN_BINS = 60               # 입력: 최근 10분
HORIZON_SEC = 300            # 예측 선행 시간: 정확히 5분
HORIZON_BINS = HORIZON_SEC // BIN_SEC
MAX_GAP_FRACTION = 0.2       # 입력 구간의 20% 이상이 비어 있으면 예측 무효
STALE_SEC = 5.0              # 최신 데이터가 5초 이상 늦으면 예측 무효 (실시간 모드)
QUANTILES = (0.1, 0.5, 0.9)

# ---------------------------------------------------------------- 학습
LEARNING_RATE_ONLINE = 3e-4
ONLINE_BATCH_REAL = 16       # 미니배치 = 현장 데이터 16 + 합성 열화 데이터 16 (정상 데이터만 보고 '항상 평탄' 으로 망각하는 것 방지)
ONLINE_BATCH_SYNTH = 16
REPLAY_SIZE = 3000
CHECKPOINT_EVERY_SEC = 600

# ---------------------------------------------------------------- 신뢰성 게이트 / 알람
MAX_BAND_Z = 1.0             # P90-P10 폭이 규격 반폭보다 넓으면 LOW_CONFIDENCE (알람 제외)
K_SIGMA = 3.0                # 공정능력 기준: 예측 평균 ± 3σ(구간 내 개별 측정 산포)가 규격을 넘으면 불량 발생 예측
ALARM_PERSIST_SEC = 15       # P50 ± K_SIGMA·σ 의 규격 이탈 예측이 15초 연속일 때만 라인정지 요청
HEALTH_EVERY_SEC = 60        # 모델 성능(tb_model_health) 기록 주기
HEALTH_WINDOW_SEC = 1800

# ---------------------------------------------------------------- 대상 설비 / 기준표
# z = (x - center) / scale  →  규격 한계가 z = ±1 이 되도록 정규화
EQUIPMENT = [
    dict(equipment_id="EQ_FORGING_01", name="1호기_압조설비", table="tb_forging_telemetry",
         pred_table="tb_forging_prediction",
         targets=[
             dict(name="defect_band_energy", label="350Hz 대역 RMS", center=0.0, scale=0.8, nonneg=True,
                  lo=None, hi=0.8, hi_inclusive=True, phys=(0.0, 5.0), legacy_col="predicted_energy",
                  hi_code="PRED_NG_VIBE_CRITICAL", warn_hi=0.4, warn_code="PRED_WARN_VIBE", family="energy"),
             dict(name="pressure", label="압력", center=50.0, scale=2.0, nonneg=False,
                  lo=48.0, hi=52.0, hi_inclusive=False, phys=(0.0, 100.0), legacy_col=None,
                  lo_code="PRED_NG_PRESSURE_LOW", hi_code="PRED_NG_PRESSURE_HIGH", family="two_sided"),
         ]),
    dict(equipment_id="EQ_ROLLING_01", name="2호기_전조설비", table="tb_rolling_telemetry",
         pred_table="tb_rolling_prediction",
         targets=[   # ae_signal 은 AI 대상 아님 (미들웨어 규칙 판정만)
             dict(name="displacement", label="금형 변위", center=4.0, scale=0.05, nonneg=False,
                  lo=3.95, hi=4.05, hi_inclusive=False, phys=(3.0, 5.0), legacy_col="predicted_displacement",
                  lo_code="PRED_NG_UNDER_MOLDING", hi_code="PRED_NG_OVER_MOLDING", family="two_sided"),
         ]),
    dict(equipment_id="EQ_HEAT_01", name="3호기_열처리로", table="tb_heat_telemetry",
         pred_table="tb_heat_prediction",
         targets=[   # carbon_ratio 는 기록 전용
             dict(name="temperature", label="노내 온도", center=850.0, scale=20.0, nonneg=False,
                  lo=830.0, hi=870.0, hi_inclusive=False, phys=(0.0, 1200.0), legacy_col="predicted_temperature",
                  lo_code="PRED_NG_TEMP_DROP", hi_code="PRED_NG_OVER_HEAT", family="two_sided"),
         ]),
]

PRED_COLUMNS = ("timestamp TEXT NOT NULL", "target_timestamp TEXT NOT NULL", "equipment_id TEXT",
                "current_value REAL", "target TEXT", "current_mean REAL", "predicted_value REAL",
                "p10 REAL", "p90 REAL", "prediction_status TEXT", "invalid_reason TEXT", "model_version TEXT")
LEGACY_PRED_COL = {"tb_forging_prediction": "predicted_energy", "tb_rolling_prediction": "predicted_displacement",
                   "tb_heat_prediction": "predicted_temperature"}
