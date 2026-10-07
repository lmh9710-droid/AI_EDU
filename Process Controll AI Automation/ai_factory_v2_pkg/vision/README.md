# 비전 검사 연동 (vision_link.py)

비전 NG 판정은 기준표의 다른 불량과 같이 **라인정지 후 퇴출**로 처리됩니다.

```
비전 추론 → vision_link.record() ─┬─▶ SQLite tb_vision_inspection (모든 검사 기록)
                                  └─▶ NG 이면 Rust 허브 DEFECT → 4호기 CMD_DEFECT (정지 → 퇴출 → 정지 유지)
```

## 규칙
- **4호기 시리얼 포트에 직접 접근하지 않습니다.** 포트는 Rust 허브가 단독으로 소유합니다.
- `status` 는 `OK` 또는 `NG_` 로 시작하는 코드입니다 (예: `NG_VISION_CRACK`, `NG_VISION_THREAD`).
- 신뢰도가 `SF_VISION_MIN_CONF`(기본 0.5)보다 낮은 NG는 기록만 하고 라인을 세우지 않습니다. 이 경우 `hub_result` 는 `BELOW_MIN_CONF` 입니다.
- 라인이 이미 정지 상태면 허브가 중복 퇴출을 하지 않습니다 (`SUPPRESSED_...`).
- 허브에 연결할 수 없으면 콘솔에 🛑 를 출력하고 `hub_result` 를 `HUB_UNREACHABLE` 로 기록합니다.

## 사용
```python
import sys; sys.path.insert(0, "/home/user/ai_factory/vision")
from vision_link import VisionLink
vl = VisionLink(model_version="yolox-s-bolt-v1")        # 프로그램 시작 시 1회

# 부품 1개 검사마다
vl.record(status="NG_VISION_CRACK", defect_class="crack", confidence=0.91,
          bbox=[x1, y1, x2, y2], inference_ms=7.4, part_seq=1234, image_path="/data/ng/1234.jpg")
vl.record(status="OK", confidence=0.98, inference_ms=7.1, part_seq=1235)
```
실행 전에 `source ~/ai_factory/scripts/env.sh` 를 하면 DB 경로와 허브 소켓이 자동으로 맞춰집니다.

## 배선 시험
```bash
source ~/ai_factory/scripts/env.sh
python3 ~/ai_factory/vision/vision_link.py            # OK 기록만 (라인 영향 없음)
python3 ~/ai_factory/vision/vision_link.py TEST_NG    # ※ 실제로 4호기 정지 후 퇴출됨
~/ai_factory/scripts/operator.sh RESET                # 재가동
```

## DB 테이블
```sql
tb_vision_inspection (id, timestamp TEXT 'YYYY-MM-DD HH:MM:SS.mmm' KST, equipment_id, part_seq,
                      status, defect_class, confidence, bbox(JSON), inference_ms, model_version,
                      image_path, hub_result)
```
