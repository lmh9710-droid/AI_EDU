"""합성 열화 데이터로 기본 모델을 사전학습한다 (최초 1회, CPU 수 분)."""
import time
from predictor import pretrain_family

if __name__ == "__main__":
    for fam in ("two_sided", "energy"):
        t = time.time()
        print(f"▶ 사전학습: {fam}")
        pretrain_family(fam)
        print(f"  완료 ({time.time() - t:.0f}s)")
