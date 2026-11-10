# ConveyorTwin: 컨베이어 라인 디지털트윈

Unity로 만든 **컨베이어 라인 디지털트윈**과 **가상 시운전(Virtual Commissioning)** 학습 프로젝트입니다.
박스가 컨베이어를 타고 흐르다가 불량품(빨간 박스)이 감지되면 라인을 멈추고 푸셔로 밀어냅니다.
설비와 제어 로직을 실제 PLC 구조(입력 X, 출력 Y, 데이터 레지스터 D)로 나눠서, 나중에 MELSEC PLC(GX Works2 / GX Simulator2)로 바꿔 끼울 수 있게 만들었습니다.

<img width="1919" height="1006" alt="스크린샷 2026-11-10 190738" src="https://github.com/user-attachments/assets/a2407e95-5c75-4ac7-92e9-1d58d81a3ed7" />

*Unity 에디터 화면. 컨베이어 위에 출구 센서와 불량 판정 센서가 있고(초록 선이 감지 레이), 벨트 옆에 푸셔(파란색)가 있습니다.*

## 개발 환경

| 항목 | 버전 |
|---|---|
| Unity | 6.6 (URP 템플릿) |
| IDE | Visual Studio Community (Unity를 사용한 게임 개발 워크로드) |
| 입력 | Input System (새 입력 시스템) |

## 실행 방법

1. 이 저장소를 클론합니다.
2. Unity Hub → **Add → Add project from disk**로 클론한 폴더를 엽니다. (처음 열 때 Library 폴더를 다시 만드느라 몇 분 걸립니다.)
3. `Assets/Scenes/SampleScene`을 열고 **▶ Play**를 누릅니다.
4. Game 창을 한 번 클릭한 뒤 키보드로 조작합니다.

| 키 | 동작 |
|---|---|
| **1** (누르고 있는 동안) | 기동 버튼 (X0) |
| **2** (누르고 있는 동안) | 정지 버튼 (X1) |

기동 버튼을 눌렀다 떼면 자기유지 회로로 운전이 계속됩니다.

## 시스템 구조

실제 PLC 시스템처럼 **설비 / I/O 이미지 / 제어 로직**을 분리했습니다.

```
[설비]                        [I/O 이미지]          [제어 로직]
PhotoSensor, Pusher  ──X 쓰기──▶  PlcIo     ◀──읽기/쓰기──  LadderLogic
Conveyor             ◀──Y 읽기──  X[] Y[] D[]               (PLC 1스캔 = FixedUpdate 1회)
OperatorPanel (조작반) ──X 쓰기──▶
```

- 설비 스크립트는 **X를 쓰고 Y만 읽습니다.** 판단은 하지 않습니다.
- 모든 판단은 `LadderLogic`이 합니다. 줄마다 대응하는 래더 명령어를 주석으로 달아 두었습니다.
- `LadderLogic`만 MC 프로토콜 통신으로 바꾸면 GX Simulator2나 실제 PLC가 같은 라인을 제어할 수 있습니다.
- Play 중에 Hierarchy에서 `PLC` 오브젝트를 선택하면 Inspector에서 X, Y, D 배열을 실시간으로 볼 수 있습니다. (GX Works2의 디바이스 모니터 역할)

## I/O 맵

| 디바이스 | 이름 | 담당 |
|---|---|---|
| X0 | 기동 버튼 | OperatorPanel (1키) |
| X1 | 정지 버튼 | OperatorPanel (2키) |
| X2 | 불량 판정 센서 | PhotoSensor (Sensor_defect, Defect Only) |
| X3 | 출구 센서 | PhotoSensor (Sensor_Exit) |
| X4 | 푸셔 후진단 | Pusher |
| X5 | 푸셔 전진단 | Pusher |
| Y0 | 컨베이어 구동 | Conveyor |
| Y1 | 푸셔 전진 솔레노이드 | Pusher |
| D0 | 양품 수 | LadderLogic |
| D1 | 불량 수 | LadderLogic |

## 제어 로직 (래더)

`LadderLogic.cs`가 실행하는 로직과 같은 래더 프로그램입니다. GX Works2에 그대로 입력할 수 있습니다.

```
; 운전 자기유지
LD   X0
OR   M0
ANI  X1
OUT  M0

; 불량 감지 → 푸셔 전진
LD   M0
AND  X2
SET  Y1

; 전진단 도달 → 후진
LD   X5
RST  Y1

; 컨베이어 운전 (푸셔 후진 상태일 때만)
LD   M0
ANI  Y1
AND  X4
OUT  Y0

; 양품 / 불량 카운트
LDP  X3
INC  D0
LDP  X5
INC  D1

END
```

## 스크립트 구성

| 스크립트 | 역할 |
|---|---|
| `PlcIo.cs` | I/O 이미지 (X, Y, D 배열). `PlcIo.Instance`로 어디서든 접근 |
| `LadderLogic.cs` | 제어 로직. 자기유지, SET/RST, 상승 펄스 카운트 |
| `OperatorPanel.cs` | 키보드 조작반. 누르는 동안만 ON 되는 기동/정지 버튼 |
| `Conveyor.cs` | 벨트 컨베이어. Y0이 ON이면 위의 물체를 마찰로 이동 |
| `PhotoSensor.cs` | 레이캐스트 광전 센서. 감지 결과를 X에 씀. Defect Only 옵션으로 불량만 감지 |
| `Pusher.cs` | 공압 실린더. Y1로 전진/후진, 전진단·후진단 리드 스위치를 X에 씀 |
| `BoxSpawner.cs` | 일정 간격으로 박스 투입, 일정 확률로 불량품 생성, 투입 위치가 막히면 대기 |
| `BoxItem.cs` | 박스의 불량 여부 데이터 |

## 동작 순서

1. **기동**(1키)을 누르면 M0이 자기유지되고, 푸셔가 후진단(X4)에 있으므로 컨베이어(Y0)가 돕니다.
2. 불량 박스가 불량 판정 센서(X2) 밑에 오면 푸셔 전진(Y1)이 SET 되고, 인터록으로 컨베이어가 멈춥니다.
3. 푸셔가 박스를 밀어내고 전진단(X5)에 닿으면 Y1이 RST 되어 후진합니다. 불량 수(D1) +1
4. 푸셔가 후진단(X4)으로 돌아오면 컨베이어가 다시 돕니다.
5. 양품은 출구 센서(X3)를 지나 배출됩니다. 양품 수(D0) +1

## 진행 기록

- [x] 1단계: 바닥과 컨베이어 배치
- [x] 2단계: 컨베이어 구동 (Rigidbody 마찰 이동)
- [x] 3단계: 박스 투입기 (프리팹, 타이머)
- [x] 4단계: 광전 센서 (레이캐스트, 태그)
- [x] 5단계: 불량품과 푸셔 (공압 실린더, 리드 스위치)
- [x] 6단계: PLC 구조로 분리 (I/O 이미지, 래더 로직)
- [ ] 7단계: 대시보드 UI (TextMeshPro, 한글 폰트, 모멘터리 버튼)
- [ ] 8단계: 알람 (타이머, 실린더 이상, 정체 감지)
- [ ] 9단계: 타워 램프와 설비 꾸미기
- [ ] 10단계: MC 프로토콜 통신 (GX Simulator2 / 실제 PLC 연동)

- 시운전 영상:
https://drive.google.com/drive/folders/1kEUlSuxZBdFdOE0UtyCbzy0uETyVeDGh
