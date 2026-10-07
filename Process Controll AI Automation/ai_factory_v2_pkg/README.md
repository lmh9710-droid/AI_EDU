# 스마트팩토리 PdM + 안전 인터록 v2

볼트·너트 라인(1호기 압조, 2호기 전조, 3호기 열처리, 4호기 컨베이어)의 시스템입니다. 구성은 다음과 같습니다.
- **가상 센서**: 서서히 진행되는 열화 8종
- **무손실 수집 미들웨어** (C++)
- **5분 선행 예측 AI** (LSTM)
- **Rust 안전 인터록 허브**
- **대시보드**
- **비전 연동**

| 문서 | 대상 |
|---|---|
| **`docs/DEVELOPER_GUIDE.md`** | 프로그래머 (구조, 프로토콜, DB, 판정 규칙, 한계, 문제 해결) |
| `docs/불량테스트_명령어.txt` | 시험 담당자 (그대로 복사해서 쓰는 명령) |
| `docs/AI_EVALUATION.md` | AI 신뢰성 평가 결과 |
| `dashboard/API.md` | 프론트엔드 연동 |
| `vision/README.md`, `vision/VSCODE_사용법.txt` | 비전 연동, VS Code |

## 기준표 (요구 스펙, 코드와 1:1)

| 설비 | 항목 | 불량 조건 | 조치 |
|---|---|---|---|
| 1호기 압조 | 압력 (ton) | `< 48` 압력 낮음, `> 52` 압력 높음 | 라인정지 후 퇴출 |
| | 350Hz 대역 RMS | `0.4 ≤ x < 0.8` 위험 경고 / `≥ 0.8` 설비 파손 위험 | 경고등 / 라인정지 후 퇴출 |
| 2호기 전조 | 금형 변위 (mm) | `< 3.95` 미성형, `> 4.05` 과성형 | 라인정지 후 퇴출 |
| | 초음파 AE (dB) | `> 40` 초음파 불량 (AI 없음) | 라인정지 후 퇴출 |
| 3호기 열처리 | 온도 (℃) | `< 830` 온도 드랍, `> 870` 과온도 | 라인정지 후 퇴출 |
| | 탄소 농도 | 판정 없음 (기록만) | — |
| AI 예측 | RMS·압력·변위·온도 | 5분 뒤 불량 예측 (P50 ± 3σ, 15초 지속) | 라인정지 |
| 비전 | 영상 판정 | NG (신뢰도 ≥ 0.5) | 라인정지 후 퇴출 |

정지 후 재가동은 작업자 RESET으로만 합니다. 기준값은 `middleware/Common.h` 와 `ai_pdm/config.py` 두 곳에만 있습니다.

## 빠른 시작

```bash
# 설치/업데이트 (패키지는 별도 폴더에 풀기. 실행 중인 프로그램은 먼저 종료)
cd ~ && unzip -o ai_factory_v2_pkg.zip && bash ai_factory_v2_pkg/install.sh

# 처음 설치라면 포트 지정
ls -l /dev/serial/by-id/
nano ~/ai_factory/scripts/env.sh

# 실행 (터미널마다 하나씩, 이 순서로)
cd ~/ai_factory
./scripts/run_hub.sh          # ① Rust 인터록 허브
./scripts/run_middleware.sh   # ② 미들웨어
./scripts/run_ai.sh           # ③ AI (10분 뒤부터 예측)
./scripts/run_dashboard.sh    # ④ 대시보드 → http://localhost:8050 (선택)

# 작업자
./scripts/operator.sh RESET | STOP | STATUS
./scripts/send_sim.sh 1 "SCN HYD_LEAK 20"     # 시험용 열화 주입
./scripts/send_sim.sh all REPAIR              # 정비
```

필요한 것: Ubuntu 24.04(WSL2), `build-essential libsqlite3-dev socat`, Rust 1.80+(rustup), Python 3.10+와 `uv`. 비전을 쓰는 경우 `~/yolo_libs` 가 필요합니다.

## 최근 변경과 다른 PC 설치
- 수정 이력: `docs/수정이력.md`
- 다른 컴퓨터 설치·실행: `docs/다른PC_설치_실행절차.txt`
- 다른 PC 에서 대시보드 보기: `docs/다른PC_대시보드_접속설정.txt`
