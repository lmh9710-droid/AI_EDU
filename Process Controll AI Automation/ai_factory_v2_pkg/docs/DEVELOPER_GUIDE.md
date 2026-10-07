# 스마트팩토리 PdM + 안전 인터록 — 개발자 가이드

볼트·너트 라인(1호기 압조, 2호기 전조, 3호기 열처리, 4호기 컨베이어)의 예지보전·안전 인터록 시스템입니다. 이 시스템을 수정·운영하는 프로그래머가 알아야 할 내용을 정리했습니다. **코드를 고치기 전에 0장과 10장은 반드시 읽어 주세요.**

---

## 0. 절대 규칙

1. **코드는 요구 스펙 기준표와 일치해야 합니다.** 기준값은 아래 두 곳에만 있고, 두 곳은 항상 같아야 합니다.
   - `middleware/Common.h` 의 `namespace Spec`: 실측 판정
   - `ai_pdm/config.py` 의 `EQUIPMENT`: AI 예측 판정. 대시보드도 이 값을 읽습니다.
   
   기준표가 바뀌면 두 파일을 함께 고친 뒤 9장의 시험을 다시 하세요.
2. **4호기 컨베이어 시리얼 포트는 Rust 인터록 허브만 엽니다.** 다른 프로그램(비전 포함)은 허브 소켓(`SF_HUB_SOCK`)으로 요청만 보냅니다. 포트를 직접 열면 ACK와 상태 보고를 가로채 인터록이 깨집니다.
3. **같은 프로그램을 두 번 실행하지 않습니다.** 미들웨어가 둘이면 한 포트의 데이터를 나눠 읽어 누락이 생기고, 허브가 둘이면 4호기 포트가 충돌합니다. `scripts/run_*.sh` 가 잠금 파일(`/tmp/sf_<이름>.lock`)로 막아 주므로, **실행은 항상 스크립트로** 하세요.
4. **현장 설정 파일은 패키지로 덮어쓰지 않습니다.** 대상은 `scripts/env.sh`, `vision/config/*`, `vision/status_map.json`, `vision/models/*`, `data/*`, `ai_pdm/checkpoints/EQ_*.pt` 입니다. 업데이트는 `install.sh` 로만 하세요(7장).
5. **라인을 세우는 경로를 바꿨다면** 실측 불량 → 정지·퇴출, AI 예측 → 정지, 비전 NG → 정지·퇴출, 워치독, 작업자 RESET을 모두 다시 시험합니다(9장).

---

## 1. 시스템 구성

```
 1호기 압조 ┐                                                    ┌─▶ 대시보드 (읽기 전용, :8050)
 2호기 전조 ├─USB─▶ C++ 미들웨어 ──▶ SQLite (WAL) ──▶ Python AI ──┤
 3호기 열처리┘      수집·저장·판정        ▲           5분 선행 예측  │
                     │ DEFECT/WARN      │ 기록                    │ PRED_STOP/WARN
                     ▼                  │                         ▼
 카메라 ─▶ C++ 비전 엔진 ─@@EVENT─▶ vision_bridge ─▶ vision_link ─▶ Rust 인터록 허브 ─USB─▶ 4호기 컨베이어
           (OpenVINO, Arc GPU)                       DEFECT        (포트 단독 소유,       (정지·퇴출·경고등)
                                                                   ACK·재전송·워치독)
```

| 프로세스 | 언어 | 실행 | 하는 일 | 실행 순서 |
|---|---|---|---|---|
| 인터록 허브 | Rust | `scripts/run_hub.sh` | 4호기 포트 단독 소유, 정지 요청 정책 판단, ACK/재전송, 워치독, 이력 기록 | ① |
| 미들웨어 | C++ | `scripts/run_middleware.sh` | 1~3호기 수신(무손실), DB 저장, 기준표 판정, 허브 전달 | ② |
| AI 엔진 | Python (PyTorch) | `scripts/run_ai.sh` | 5분 뒤 값 예측(P10/P50/P90), 불량 예측 시 라인정지 요청 | ③ |
| 대시보드 | Python 표준 라이브러리 | `scripts/run_dashboard.sh` | 예측 vs 실측 화면, JSON API | 선택 |
| 비전 | C++ 엔진 + Python 브리지 | `vision/run_vision.sh [--live]` | 부품별 영상 판정, LIVE 시 NG → 정지·퇴출 | 선택 |

**언어를 나눈 이유**
- 1024Hz 실시간 수신은 C++이 맡습니다.
- 멈추거나 오작동하면 안 되는 안전 경로는 Rust가 맡습니다.
- 머신러닝과 연결 코드는 Python이 맡습니다.

Python 쪽은 정지를 **요청**만 하고, 실제로 4호기를 움직이는 결정은 Rust 허브가 합니다.

---

## 2. 폴더 구조

```
~/ai_factory/
├─ install.sh                 패키지 → 설치/업데이트 (현장 설정 보존, 실행 중이면 거부)
├─ README.md                  개요·빠른 시작
├─ scripts/
│  ├─ env.sh                  ★ 현장 설정 (포트, DB 경로). 업데이트가 덮어쓰지 않음
│  ├─ env.sh.example          env.sh 원본 양식
│  ├─ _common.sh              공통 검사 (env 로드, 예시 포트 감지, 권한, 중복 실행 잠금)
│  ├─ run_hub.sh / run_middleware.sh / run_ai.sh / run_dashboard.sh
│  ├─ operator.sh             작업자 명령 RESET | STOP | STATUS
│  ├─ send_sim.sh             가상 센서 보드에 시나리오·정비 명령
│  ├─ build_all.sh            전체 빌드
│  └─ sim_ports.sh            하드웨어 없이 가상 시리얼 4개 생성
├─ arduino/                   펌웨어 4개 (UNO R4 Minima)
├─ middleware/                C++ 미들웨어 (build.sh → smart_factory_middleware)
├─ interlock_hub/             Rust 허브 (Cargo.lock 포함, target/ 은 빌드 산출물)
├─ ai_pdm/                    AI 엔진 (checkpoints/pretrained_*.pt 포함)
├─ dashboard/                 대시보드 (API.md: 프론트엔드 연동 규격)
├─ vision/
│  ├─ vision_link.py          비전 → DB·허브 연동 모듈 (README.md 참고)
│  ├─ vision_bridge.py        C++ 엔진 출력(@@EVENT) → vision_link
│  ├─ run_vision.sh, status_map.json★, config/★, models/★, yolo_engine/ (C++ 소스)
│  └─ .vscode/, VSCODE_사용법.txt
├─ tools/sim/                 펌웨어를 PC 에서 그대로 실행 (실시간·가상시간)
├─ tools/eval/                AI 신뢰성 평가 (evaluate_ai.py)
├─ docs/                      이 문서, AI_EVALUATION.md, 불량테스트_명령어.txt
└─ data/                      ★ DB, 비전 결과
```
★ 표시는 현장 설정 또는 데이터입니다.

---

## 3. 데이터 흐름과 프로토콜

### 3.1 센서 보드 → 미들웨어 (시리얼 115200 8N1, 줄 단위)

```
[FORGING],<seq>,<pressure_ton>,<vibration>*<CS>       1024Hz (1초 = 1024줄)
[ROLLING],<seq>,<displacement_mm>,<ae_dB>*<CS>        0.8초 (부품 1개)
[HEAT],<seq>,<temperature_C>,<carbon_ratio>*<CS>      2초
[<TAG>_SIM],<seq>,<scenario>,<damage>*<CS>            1초 (시뮬레이션 정답, 판정·예측에 사용 안 함)
#...                                                    보드 메시지 (미들웨어 콘솔에 📟 로 표시)
```
- `<CS>` 는 `*` 앞 모든 바이트의 XOR이며, 16진 대문자 2자리입니다.
- `seq` 는 줄마다 1씩 증가합니다. 미들웨어는 이것으로 누락(lost), 손상(corrupt), 보드 재시작(resync)을 집계합니다.
- 포트를 연 직후 2초는 동기화 구간이라 seq 점프를 누락으로 세지 않습니다.
- **보드는 판정하지 않습니다.** 실제 센서처럼 값만 보내고, 판정은 미들웨어가 합니다.

**시뮬레이션 명령** (보드로 보냄. 직접 `echo` 하지 말고 `scripts/send_sim.sh` 사용 권장)

| 명령 | 의미 |
|---|---|
| `SCN <시나리오> <TTF분> [shape]` | 열화 시작. D=(경과/TTF)^shape, 진행 속도 ±30% 랜덤워크. D=1에서 평균이 기준표 한계 |
| `AUTO <0\|1> [평균간격분]` | 무작위 자동 발생 (TTF 15~45분) |
| `REPAIR` | 정비 (D=0). **고장은 저절로 낫지 않음** |
| `STATUS` | 현재 시나리오·손상도 |

| 보드 | 시나리오 | 현상 |
|---|---|---|
| 1호기 | `DIE_CRACK` | 350Hz 대역 RMS 증가 → 0.4 경고 → 0.8 파손 위험 |
| | `HYD_LEAK` / `VALVE_STICK` | 압력 하강(<48) / 상승(>52) |
| 2호기 | `DIE_WEAR` / `THERMAL_GROWTH` | 변위 하강(<3.95) / 상승(>4.05) |
| | `TOOL_CHIP` | AE 상승 + 히트 버스트 (>40) |
| 3호기 | `TC_DRIFT` | 온도 상승 (>870), 처음부터 서서히 |
| | `HEATER_AGING` | 제어기가 보상하다 출력 포화 후 온도 하강 (<830) |

### 3.2 허브 ↔ 4호기 컨베이어

```
허브 → 보드:  CMD_STOP|CMD_DEFECT|CMD_WARN|CMD_RESET|CMD_PING,<id>
보드 → 허브:  ACK,<id>,<CMD>,<STATE>   |   NAK,<id>,<reason>
보드 상태(1Hz): [CONVEYOR],<seq>,<STATE>,<warn 0|1>,<eject_count>*<CS>
STATE: RUNNING | STOPPING | EJECTING | STOPPED
```
- ACK가 300ms 안에 오지 않으면 **같은 ID로** 최대 3회 재전송합니다. 보드는 이미 ACK한 ID를 다시 실행하지 않습니다(중복 퇴출 방지).
- `CMD_DEFECT` 순서: 모터 정지(D8 LOW) → 0.5초 관성 정지 → 솔레노이드(D9) 0.3초 → STOPPED 유지
- `CMD_WARN`: 경고등(D10) 점등, 라인 계속 가동. RESET 시 소등
- `CMD_RESET`: 퇴출 중에는 `NAK,BUSY_EJECTING`

### 3.3 허브 소켓 (Unix 도메인, `SF_HUB_SOCK`, JSON 한 줄 요청 → 한 줄 응답)

```json
요청: {"src":"EQ_FORGING_01","kind":"DEFECT","code":"NG_PRESSURE_LOW","value":47.9,"detail":"..."}
응답: {"ok":true,"result":"ACKED(STOPPING)","line_state":"STOPPING","warn_lamp":false,"cmd_id":2,"eject_count":1}
```

| kind | 보내는 쪽 | 허브 동작 |
|---|---|---|
| `DEFECT` | 미들웨어, 비전 | 가동 중이면 `CMD_DEFECT` (정지 후 퇴출) |
| `PRED_STOP` | AI, 워치독, 작업자 STOP | 가동 중이면 `CMD_STOP` |
| `WARN` | 미들웨어, AI | 경고등이 꺼져 있으면 `CMD_WARN` |
| `RESET` | **`src=OPERATOR` 만** | `CMD_RESET` (다른 src 는 `REJECTED_NOT_OPERATOR`) |
| `HEARTBEAT` | `MIDDLEWARE`, `AI_*` | 생존 신호 (워치독용) |
| `STATUS` | 누구나 | 상태 조회만 |

- 이미 정지·경고 중이면 실행하지 않고 `SUPPRESSED_<상태>` 로 응답합니다(10초마다 건수만 출력).
- 그래서 **요청하는 쪽은 레벨 트리거로 보내도 됩니다.** 조건이 계속되는 동안 매번 보내도 됩니다.
- 라인 상태가 `UNKNOWN` 이면 가동 중으로 간주합니다(안전 쪽).
- 실행한 명령은 모두 `tb_interlock_event` 에 기록됩니다.

**워치독**

| 대상 | 기준 | 동작 |
|---|---|---|
| 미들웨어 하트비트 | 5초 끊김 | **라인 정지** (fail-safe) |
| AI 하트비트 | 10초 끊김 | 경보만 (실측 판정은 유지되므로) |
| 4호기 상태 보고 | 3초 끊김 | 경보 |

### 3.4 비전 엔진 → 브리지

엔진은 부품 1개당 한 줄을 표준출력으로 즉시 내보냅니다.
```
@@EVENT {"seq":12,"ts":"...","verdict":"OK|NG","task":"classify","top1":"Red","top1_score":0.91,
         "p_ok":0.02,"defect_class":"Red","defect_conf":0.91,"bbox":[x1,y1,x2,y2],
         "inference_ms":7.2,"frames":5,"image":"..."}
```
- 다른 엔진(예: PatchCore)도 이 형식만 지키면 브리지에 그대로 붙습니다.
- 브리지는 필드 누락이나 `nan` 이 있어도 죽지 않습니다. `verdict` 가 OK가 아니면 NG로 처리합니다.

### 3.5 대시보드 API
`GET /api/data?minutes=30` 입니다. 구조는 `dashboard/API.md` 에 있습니다. 시각은 **KST 벽시계를 그대로 epoch ms로** 담았으므로 JS에서 UTC 게터로 읽어야 합니다.

---

## 4. 판정 규칙

### 4.1 실측 판정 (미들웨어, 기준표 그대로)

| 설비 | 항목 (판정 단위) | 조건 | 코드 | 조치 |
|---|---|---|---|---|
| 1호기 | 압력 (1초 평균) | `< 48` / `> 52` | `NG_PRESSURE_LOW` / `NG_PRESSURE_HIGH` | 정지 후 퇴출 |
| | 350Hz 대역 RMS (1초 FFT, 340~360Hz, 실효값) | `0.4 ≤ x < 0.8` | `WARN_VIBE` | **경고등만** |
| | | `≥ 0.8` | `NG_VIBE_CRITICAL` | 정지 후 퇴출 |
| 2호기 | 변위 (부품마다) | `< 3.95` / `> 4.05` | `NG_UNDER_MOLDING` / `NG_OVER_MOLDING` | 정지 후 퇴출 |
| | AE (부품마다) | `> 40` | `NG_AE_FAULT` | 정지 후 퇴출 (AI 없음) |
| 3호기 | 온도 (2초마다) | `< 830` / `> 870` | `NG_TEMP_DROP` / `NG_OVER_HEAT` | 정지 후 퇴출 |
| | 탄소 농도 | — | — | **기록만** |

- 1호기 RMS는 파스발 정리로 `sqrt(2·Σ|X_k|²)/N` 입니다(k=340..360).
- 1초 윈도우 누락이 10%를 넘으면 `DATA_LOSS` 로 표시하고 판정하지 않습니다.

### 4.2 AI 예측 판정

- 대상은 1호기 RMS·압력, 2호기 변위, 3호기 온도입니다. AE와 탄소는 대상이 아닙니다.
- 입력은 최근 10분(10초 평균 60개)이고, 출력은 정확히 5분 뒤 10초 평균의 P10/P50/P90입니다.
- **라인 정지 요청** 조건: 예측이 VALID이고, `P50 ± 3·σ` 가 기준표 한계를 넘는 상태가 **15초 연속**일 때 → `PRED_STOP`
  - σ는 최근 1분 개별 측정값의 흩어짐입니다. 실측 판정이 개별값(부품·초) 단위이므로, 평균만 보면 늦게 잡기 때문입니다.
- **위험 경고**: RMS P50 ≥ 0.4가 15초 연속이면 `WARN`
- **예측 상태**: `VALID`, `INSUFFICIENT_HISTORY`(처음 10분), `DATA_GAP`, `DATA_STALE`, `NON_FINITE`, `OUT_OF_PHYSICAL_RANGE`, `LOW_CONFIDENCE`(P10~P90 폭이 규격 반폭 초과). **VALID가 아니면 정지하지 않습니다.**
- **학습**
  - 사전학습: 합성 열화 데이터로 `ai_pdm/pretrain.py` 가 만듭니다.
  - 온라인 학습: 10초마다 "5분 전 입력 → 현재 실측"으로 학습합니다. 현장 데이터 16개와 합성 데이터 16개를 섞어 학습합니다.
  - 학습된 모델은 10분마다 `checkpoints/EQ_*.pt` 에 저장됩니다.
- **성능 기록**: 매분 `tb_model_health` 에 남깁니다(목표 시각이 지난 예측의 MAE vs 현재값 유지, P10~P90 적중률).

### 4.3 비전 판정
- 엔진의 적극 판정: `good` 확률 ≥ 0.80일 때만 OK, 나머지는 NG입니다.
- 브리지가 NG를 `status_map.json` 의 코드(`NG_VISION_*`)로 바꿉니다.
- LIVE 모드에서는 `vision_link` 가 신뢰도 ≥ `SF_VISION_MIN_CONF`(기본 0.5)인 NG만 허브에 `DEFECT` 로 보냅니다 → **정지 후 퇴출**.
- 확신 부족 NG의 신뢰도는 `1 − good 확률` 입니다. 그래서 good 확률이 0.5~0.8이면 기록만 하고, 0.5 미만이면 정지합니다.

### 4.4 기준표만으로 정할 수 없어 정한 해석 (변경 가능)

| 항목 | 현재 동작 | 근거 | 바꾸는 곳 |
|---|---|---|---|
| 위험 경고 0.4~0.8 | 경고등만, 가동 유지 | 기준표 정상치(0~0.8) 범위 안 | `EquipmentNodes.cpp` 의 `reportWarn` → `reportDefect` |
| 정지 후 재가동 | 작업자 RESET만 | 안전 관례 (자동 재가동 금지) | 허브 정책 |
| AE > 40 | 실측 규칙으로 정지 후 퇴출, AI 예측 없음 | 요청 사항 | — |
| 탄소 농도 | 기록만 | 실제 열처리 중 측정 불가 | — |
| AI 예측 불량 | 정지만 (퇴출 없음) | 아직 불량품이 나오지 않았으므로 | 허브 정책 |
| 비전 NG | 정지 후 퇴출 | 2026-10-01 결정 | — |

---

## 5. DB 스키마 (SQLite, WAL, `SF_DB_PATH`)

모든 `timestamp` 는 **KST 문자열 `YYYY-MM-DD HH:MM:SS.mmm`** 입니다(시간대 표기 없음).

| 테이블 | 쓰는 곳 | 주기 | 주요 컬럼 |
|---|---|---|---|
| `tb_forging_telemetry` | 미들웨어 | 1초 | `pressure`(1초 평균), `defect_band_energy`(RMS), `status`, `seq_first`, `samples`, `lost_samples`, `pressure_min/max`, `raw_waveform`(BLOB, `SF_STORE_RAW=1` 일 때) |
| `tb_rolling_telemetry` | 미들웨어 | 0.8초 | `displacement`, `ae_signal`, `status`, `seq` |
| `tb_heat_telemetry` | 미들웨어 | 2초 | `temperature`, `carbon_ratio`, `status`, `seq` |
| `tb_sim_truth` | 미들웨어 | 설비당 1초 | `equipment_id`, `scenario`, `damage` (시뮬레이션 정답) |
| `tb_link_stats` | 미들웨어 | 10초 | `received`, `lost`, `corrupt`, `resyncs` |
| `tb_forging/rolling/heat_prediction` | AI | 항목당 1초 | `target`, `current_value`, `current_mean`, `predicted_value`(P50), `p10`, `p90`, `target_timestamp`(+300초), `prediction_status`, `invalid_reason`, `model_version`, 호환 컬럼 `predicted_energy/displacement/temperature` |
| `tb_model_health` | AI | 1분 | `target`, `n`, `mae_model`, `mae_persistence`, `coverage_p10_p90`, `online_updates` |
| `tb_interlock_event` | 허브(실행 이력), 미들웨어(`HUB_UNREACHABLE`) | 발생 시 | `source`, `kind`, `code`, `value`, `command`, `cmd_id`, `result`, `latency_ms` |
| `tb_vision_inspection` | vision_link (**LIVE 모드만**) | 부품마다 | `part_seq`, `status`, `defect_class`, `confidence`, `bbox`, `inference_ms`, `model_version`, `image_path`, `hub_result` |

**상세 규칙**
- `status`(텔레메트리)는 미들웨어 판정 결과입니다. `OK` 이거나 코드를 `|` 로 이은 값입니다(예: `NG_PRESSURE_LOW|WARN_VIBE`).
- 예측 테이블은 **항목마다 한 행**입니다. 1호기는 1초에 2행(RMS, 압력)이 쌓입니다. 비교할 실측은 `target_timestamp` 직전 10초 평균입니다.
- 기존 DB는 시작할 때 없는 컬럼만 자동으로 추가됩니다(`ALTER TABLE ADD COLUMN`).
- v1의 `tb_interlock_command`(DB 큐 방식)는 더 이상 쓰지 않습니다.
- **용량 참고**: 텔레메트리, 예측, 시뮬레이션 정답을 합쳐 하루 약 80만 행입니다. `SF_STORE_RAW=1` 이면 하루 약 350MB가 추가됩니다. 정기 백업과 정리 계획을 세우세요.

---

## 6. 설정

### 6.1 환경변수 (`scripts/env.sh`)

| 변수 | 기본 | 사용처 |
|---|---|---|
| `SF_PORT_FORGING/ROLLING/HEAT` | — | 미들웨어 (by-id 경로 사용) |
| `SF_PORT_CONVEYOR` | — | 허브 |
| `SF_DB_PATH` | `~/ai_factory/data/smart_factory_v2.db` | 전체 |
| `SF_HUB_SOCK` | `/tmp/sf_interlock.sock` | 전체 |
| `SF_STORE_RAW` | `0` | 미들웨어: 1호기 원시 파형 저장 |
| `SF_CSV_DIR`, `SF_CKPT_DIR` | `ai_pdm/predictions`, `ai_pdm/checkpoints` | AI |
| `SF_DASH_HOST`, `SF_DASH_PORT`, `SF_DASH_CORS` | `127.0.0.1`, `8050`, 없음 | 대시보드 (`run_dashboard.sh` 안에서 설정) |
| `SF_VISION_MIN_CONF` | `0.5` | vision_link |

### 6.2 코드 상수

| 위치 | 상수 | 값 |
|---|---|---|
| `middleware/Common.h` | `Spec::*` | 기준표 |
| `ai_pdm/config.py` | `EQUIPMENT` | 기준표, 정규화 (z = (x−center)/scale, 한계 = ±1) |
| | `BIN_SEC`, `N_IN_BINS`, `HORIZON_SEC` | 10, 60, 300 |
| | `K_SIGMA`, `ALARM_PERSIST_SEC`, `MAX_BAND_Z` | 3.0, 15, 1.0 |
| | `MAX_GAP_FRACTION`, `STALE_SEC` | 0.2, 5 |
| `interlock_hub/src/main.rs` | `ACK_TIMEOUT`, `MAX_SEND_ATTEMPTS` | 300ms, 3 |
| | `MIDDLEWARE/AI/CONVEYOR_WATCHDOG` | 5s, 10s, 3s |
| `vision/config/pdm_bolt.yaml` | `roi`, `conf_threshold`, `part_trigger*`, `device` | 현장 설정 |

---

## 7. 빌드·설치·업데이트

**필요한 것**
- Ubuntu 24.04 (WSL2), `build-essential libsqlite3-dev socat`
- **Rust 1.80 이상** (rustup 사용. apt의 cargo 1.75는 의존성 빌드 실패)
- Python 3.10+, `uv`
- 비전을 쓰는 경우: `~/yolo_libs` (OpenCV 5, OpenVINO, ONNX Runtime)

**설치/업데이트**
```bash
cd ~ && unzip -o ai_factory_v2_pkg.zip && bash ai_factory_v2_pkg/install.sh
```
- **실행 중인 프로그램이 있으면 설치를 거부합니다.** 모두 끄고 진행하세요.
- 바뀌는 코드는 `~/ai_factory/_backup/<시각>/` 에 원본을 보관합니다.
- 현장 설정은 보존합니다. 새 기본값이 다르면 옆에 `*.new` 로 저장합니다.
- 처음 설치하면 `env.sh` 를 예시로 만들고, 포트 수정을 요구합니다.
- 끝에 `scripts/build_all.sh` 를 실행합니다. `--no-build` 로 생략할 수 있습니다.

**펌웨어 업로드**
- Arduino IDE(Windows)에서 업로드합니다. 업로드 전에 `usbipd detach` 를 하세요.
- R4 Minima 4대는 USB ID가 같습니다(2341:0069). **한 대씩만 꽂고 업로드**해야 다른 보드에 덮어쓰지 않습니다.
- 업로드 후 시리얼 모니터에서 태그(`[FORGING]` 등)를 확인하고 **모니터를 닫은 뒤** attach 합니다.
- 4호기 D10에는 경고등을 연결합니다.

---

## 8. 운영 절차

**시작**: 터미널 4개에서 `run_hub.sh` → `run_middleware.sh` → `run_ai.sh` → (선택) `run_dashboard.sh`, `vision/run_vision.sh`
- AI는 시작 후 10분 동안 `INSUFFICIENT_HISTORY` 입니다(정상).

**불량 발생 후 복구**
1. 원인 설비를 정비합니다. 시뮬레이터라면 `scripts/send_sim.sh <1|2|3|all> REPAIR`
2. **3~5분 대기**합니다. AI 입력 10분 안에 고장 시절 데이터가 남아 있어, 바로 재가동하면 다시 정지할 수 있습니다. 대시보드에서 빨간 테두리가 사라질 때까지 기다리세요.
3. `scripts/operator.sh RESET` 실행 → `ACKED(RUNNING)` 확인

**상태 확인**
- `scripts/operator.sh STATUS`
- 대시보드 상단 띠와 "수신 품질"
- 시뮬레이션 상태: `docs/불량테스트_명령어.txt` 8번 참고

**종료**: 각 터미널에서 Ctrl+C. 미들웨어를 먼저 끄면 5초 뒤 워치독이 라인을 세웁니다(정상).

---

## 9. 시험·검증

| 목적 | 방법 |
|---|---|
| 하드웨어 없이 전체 실행 | `scripts/sim_ports.sh` 로 가상 포트를 만든 뒤, `env.sh` 포트를 `/tmp/sfsim/*.host` 로 지정. **실제 펌웨어 코드**가 PC에서 돕니다 |
| 불량 시나리오 | `docs/불량테스트_명령어.txt` (8종 + 비전 + 안전장치) |
| AI 신뢰성 | `tools/eval/evaluate_ai.py` (펌웨어를 가상시간으로 돌려 선행시간·오경보·정확도 측정, 약 10분) |
| 비전 연동 배선 | `python3 vision/vision_link.py TEST_NG` (**실제 4호기 정지·퇴출**) |
| 비전 모델 검증 | `python3 vision/tools/validate_model.py <정답 사진 폴더>` (현장과 같은 C++ 엔진으로 정확도·불량 놓침률·기준별 변화, 라인 영향 없음). 절차는 `docs/비전모델_검증방법.txt` |

**지금까지의 검증 결과**
- **수집**: 시뮬레이터 1024Hz 연속 수신(117만 샘플)에서 누락 0, 손상 0입니다. 실보드 + usbipd 경로에서도 1초 윈도우 1024/1024 수신을 확인했습니다.
- **인터록**: 실측 불량 → 정지·퇴출, AI → 정지, 비전 NG → 정지·퇴출, 정지 중 중복 요청 무시, 작업자 RESET, 미들웨어 종료 시 워치독 정지를 확인했습니다. 지연은 1ms 미만입니다.
- **AI** (`docs/AI_EVALUATION.md`)
  - 열화 21건 중 20건에서 실측 불량보다 먼저 정지했습니다. 선행시간은 중앙값 2.6분입니다(범위 -8초~14.6분).
  - 정상 운전 8시간(예측 항목 4개 합계 10시간) 동안 오경보 0건이었습니다.
  - 실보드 유압 누유 시험에서는 74초 선행했습니다.
- **설치·스크립트**: 현장 설정 보존, 실행 중 설치 거부, 중복 실행 차단, 예시 포트 감지를 확인했습니다.

---

## 10. 알려진 한계와 주의사항

1. **허브가 죽으면 라인을 세울 주체가 없습니다.** 4호기 펌웨어는 허브 생존을 확인하지 않습니다. 해결책은 4호기 펌웨어에 "허브 신호 N초 끊기면 자체 정지" 워치독을 넣는 것입니다(미구현).
2. **비전 프로세스는 허브가 감시하지 않습니다.** 브리지와 엔진이 함께 죽으면 그 뒤로 비전 불량은 걸러지지 않습니다. 브리지는 엔진 장애 시 자동 재시작합니다.
3. **재가동 직후 AI가 다시 정지시킬 수 있습니다** (8장 복구 절차). 의도적으로 그대로 둔 동작입니다.
4. **`HEATER_AGING` 은 AI 선행이 거의 없습니다.** 제어기가 열화를 숨기기 때문입니다. 개선하려면 히터 전류나 듀티 센서를 추가해야 합니다(기준표 밖 항목).
5. **비전 퇴출 위치**: 정지 순간 퇴출 장치 앞에 있는 부품이 퇴출됩니다. 카메라에서 퇴출 장치까지의 거리와 부품 간격을 현장에서 맞춰야 합니다.
6. **비전 그림자 모드는 DB에 기록하지 않습니다** (CSV만). 대시보드 비전 패널은 LIVE에서만 채워집니다.
7. **비전 클래스 의미**: `Black/Green/Red/White` 가 불량인지 품질팀 확인 전에는 LIVE를 쓰지 마세요. `roi` 도 지정해야 합니다(전체 화면이면 손·그림자도 부품으로 인식).
8. **디스크가 가득 차면 DB 기록이 멈춥니다.** 미들웨어는 데이터를 메모리 큐에 쌓으며 `쓰기 적체` 경고를 내고, AI는 정지합니다. 디스크 사용량을 감시하세요.
9. **WSL 재시작(`wsl --shutdown`)이나 PC 절전 시 usbipd 연결이 끊깁니다.** 다시 attach하고 프로그램을 재실행해야 합니다.
10. **`uv run` 은 Linux에서 CUDA 버전 torch(수 GB)를 받습니다.** 처음 실행은 오래 걸리고 디스크를 많이 씁니다.
11. **시간대**: 모든 기록은 KST 문자열입니다. 서버 시간대를 바꾸지 마세요.

---

## 11. 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `ambiguous redirect` | 그 터미널에서 env.sh를 안 불러옴 | `scripts/send_sim.sh` 사용, 또는 `source scripts/env.sh` |
| `✘ ... 예시값입니다` | env.sh에 XXXXXXXX가 남음 | `ls -l /dev/serial/by-id/` 로 확인 후 수정 |
| `Permission denied` (포트) | dialout 그룹 아님 | `sudo usermod -aG dialout $USER` 후 재로그인 |
| `이미 실행 중입니다` | 다른 터미널에서 실행 중 | 그 터미널 사용. 잠금은 프로세스 종료 시 자동 해제 |
| 정비했는데 라인이 계속 정지 | REPAIR가 보드에 안 감 / RESET 안 함 / AI 이력 대기 | 대시보드 "시뮬레이션 정답"이 NORMAL인지 확인 → 3~5분 대기 → RESET |
| 미들웨어 `🛑 HUB UNREACHABLE` | 허브 미실행 | `run_hub.sh` 먼저 |
| 허브 `ACK 없음 → 재전송` 이 계속 | 4호기 펌웨어 문제·포트 오지정 | 4호기 시리얼 모니터로 `[CONVEYOR]` 확인 |
| 링크 `누락` 증가 | CPU 과부하, USB 문제 | 비전을 GPU로 실행 중인지 확인, `tb_link_stats` 확인 |
| 모든 줄이 `손상` | 구형(v1) 펌웨어 | 펌웨어 재업로드 |
| AI가 계속 `INSUFFICIENT_HISTORY` | 시작 후 10분 미만, 데이터 공백 | 대기, 미들웨어 수신 확인 |
| `cargo` 빌드 `edition2024` 오류 | apt Rust 1.75 | rustup으로 1.80+ 설치 |
| 비전 `디바이스=CPU` | Arc GPU 미인식 | GPU 드라이버 확인. CPU면 미들웨어와 CPU 경쟁 |

---

## 12. 변경 이력 요약

- **v1 패치**: 원본 코드의 문법 오류, 누락 테이블, 도달 불가 임계값 등을 수정했습니다.
- **v2 재구축**
  - 기준표 기반 전면 재작성
  - 서서히 진행되는 열화 8종 펌웨어
  - seq·체크섬 무손실 미들웨어
  - Rust 인터록 허브
  - 분위수 LSTM (합성 사전학습 + 온라인 학습), 대시보드, 비전 연동
- **v2 견고화 (이번)**
  - 실행 스크립트: env 검사, 예시 포트 감지, 권한 검사, 중복 실행 차단
  - `send_sim.sh` 추가 (설정 미로드 오류 방지)
  - 안전한 `install.sh` (현장 설정 보존, 실행 중 거부, 백업)
  - 허브: 연결 직후 버퍼 정리로 첫 명령 재전송 제거
  - AI: 허브 장애 시 로그 폭주 방지
  - 비전 브리지: 이벤트 오류·nan 내성, 카메라 끊김 자동 재시작, 어떤 종료 방식에도 엔진이 남지 않음, 부품 번호 원자적 저장
  - 빌드: Rust 버전 검사, 비전 엔진 선택 빌드
