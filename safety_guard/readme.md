# 🛡️ 프로젝트명: 실시간 안전 경계 침투 감지 및 DB 저장 시스템 (Safety Motion Guard)

> OpenCV 기반의 3-Frame 차분 알고리즘을 활용하여 작업 공간 내 위험 구역 침투를 실시간 감지하고, 픽셀 단위 측정값을 mm 단위로 환산하여 SQLite DB 및 이미지 갤러리에 자동 저장하는 모듈형 안전 관리 시스템입니다.

---

## 🛠️ 1. 개발 환경 (Tech Stack)

| 구분 | 기술 스택 |
| :--- | :--- |
| **Operating System** | Ubuntu |
| **Language** | C++ |
| **Vision & Image** | OpenCV (`cv2`) |
| **Math & Data** | cmath |
| **Database** | SQLite3 |

---

## 🔄 2. Work Process

### 📌 2.1. 요구사양 협의
- **주제 선정**: 산업 현장 실시간 작업자/물체 경계선 침투 감지 시스템 개발 주제 확정
- **요소 도출**: 픽셀-mm 변환 연산(0.264 mm/px), ROI 경계 설정, 위험 단계별 색상 표시(5mm/10mm/20mm) 및 쿨다운 2초 제어 로직 정의

### 📐 2.2. 구조 설계
- **클래스 설계**: 객체지향(OOP) 기반 모듈화 
- **흐름도 작성**: 3-Frame 차분 및 경보 캡처 처리 Flowchart 작성
- **DB 모델링**: SQLite 기반 침투 이력 로그(`intrusion_logs`) 데이터베이스 테이블 모델링

### 💻 2.3. 로직 구현
- **클래스 구현**: 역할별 독립 클래스 파일 모듈화 분리
- **메인 로직**: Main 실행 

---

## 📊 3. 시스템 설계 (Diagrams)

### 3.1. Class Diagram
```mermaid
classDiagram
    direction TB

    class Config {
        <<struct>>
        +double PIXEL_TO_MM
        +int ALERT_LEVELS
        +int COOLDOWN_SEC
    }

    class DatabaseManager {
        -sqlite3* db
        +initDatabase() bool
        +insertLog(log) bool
    }

    class MotionAnalyzer {
        -Mat framePrev1, framePrev2
        -Rect roiArea
        +processFrame(frame) Mat
        -calcFrameDiff() Mat
        -convertPixelsToMm() double
    }

    class MainApp {
        +main() int
    }

    MotionAnalyzer ..> Config : 참조
    DatabaseManager ..> Config : 참조
    MainApp --> MotionAnalyzer : 제어
    MainApp --> DatabaseManager : 기록
```


### 3.2. Flow Chart
```mermaid
flowchart TD
    Start([시작]) --> Init[1. 시스템 및 DB 초기화]
    Init --> Capture[2. 실시간 프레임 캡처]
    
    Capture --> Diff[3. 3-Frame 차분 및 ROI 검출]
    Diff --> Calc[4. 픽셀-mm 환산 연산 *0.264mm/px*]
    
    Calc --> Cond1{5. 침투 감지?}
    Cond1 -- No --> Update[7. 프레임 버퍼 업데이트]
    
    Cond1 -- Yes --> Cond2{6. 2초 쿨다운 해제?}
    Cond2 -- No --> Update
    
    Cond2 -- Yes --> Action[8. 위험 단계별 시각화 & DB 저장]
    Action --> Update
    
    Update --> Loop{9. 종료 키 요청?}
    Loop -- No --> Capture
    Loop -- Yes --> End([종료])
```

### 3.3 DataBase Modeling
erDiagram
    intrusion_logs {
        INTEGER log_id PK "AUTOINCREMENT"
        TEXT timestamp "NOT NULL (DEFAULT: local_time)"
        REAL distance_mm "NOT NULL"
        INTEGER alert_level "NOT NULL"
        TEXT img_path
    }
```
---

## 🖥️ 4. 실습 

<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/e39665fd-9245-437c-91de-41d5185094b7" />

