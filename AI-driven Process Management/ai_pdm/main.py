import os
import time

# [인텔 가속 데드락 원천 차단 치트키] 
# PyTorch와 인텔 OpenMP 라이브러리가 멀티스레딩 중 충돌하여 얼어붙는 현상을 방어합니다.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

from engine import EquipmentAiNode

def main():
    print("\n=======================================================")
    print("  🔮 PyTorch 3-Channel High-Performance Sync AI Engine  ")
    print("=======================================================\n")

    # 1~3호기 독립 에지 AI 노드 정의
    forging_ai = EquipmentAiNode("1호기_압조설비", "tb_forging_telemetry", "defect_band_energy", 0.8, is_upper_limit=True)
    rolling_ai = EquipmentAiNode("2호기_전조설비", "tb_rolling_telemetry", "displacement", 1.45, is_upper_limit=True)
    heat_ai    = EquipmentAiNode("3호기_열처리로", "tb_heat_telemetry", "temperature", 835.0, is_upper_limit=False)

    # 안전하게 하드웨어 스케일러 빌드 초기화
    forging_ai.initialize_scaler()
    rolling_ai.initialize_scaler()
    heat_ai.initialize_scaler()

    print("\n🖥️ [LAUNCH] 3대 공정 통합 직렬 파이프라인 감시 시작.\n", flush=True)

    # 단일 고속 루프 내에서 3개 공정을 안전하고 명확하게 순차 스캔 (데드락 0%)
    while True:
        try:
            forging_ai.execute_one_step()
            rolling_ai.execute_one_step()
            heat_ai.execute_one_step()
        except Exception as e:
            pass
        
        time.sleep(1) # 1초 주기로 전체 공정 모니터링 동기화

if __name__ == "__main__":
    main()
