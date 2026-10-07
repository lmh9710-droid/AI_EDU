# 대시보드 데이터 API (프론트엔드 연동용)

`GET http://<서버PC IP>:8050/api/data?minutes=30`

- 읽기 전용이고 인증이 없습니다. 사내망에서만 사용하세요.
- `minutes` 범위는 5~720입니다 (표시 기간).
- 2초 간격 폴링을 권장합니다. 서버는 2초보다 자주 갱신할 데이터가 없습니다.
- 다른 출처의 브라우저에서 직접 호출하려면 서버를 `SF_DASH_CORS=<프론트 출처>` 로 실행해야 합니다.

## 시각 표기 (중요)
모든 시각은 **KST 벽시계 시각을 그대로 epoch ms 로 담은 값**입니다.
- JS에서는 `new Date(ms)` 후 **`getUTCHours()` 같은 UTC 게터로 읽으면 KST** 가 나옵니다.
- 로컬 게터(`getHours`)를 쓰면 브라우저 시간대만큼 어긋납니다.
- 문자열 필드(`ts`, `pred_ts`, `target_ts`)는 `YYYY-MM-DD HH:MM:SS.mmm` (KST) 형식입니다.

## 응답 구조
```jsonc
{
  "empty": false,                 // true 면 DB 에 데이터 없음 (이때 db 필드만 있음)
  "now": 1790850270871,           // 최신 실측 시각 (ms)
  "window_min": 30,
  "horizon_ms": 300000,           // 예측 선행 시간 (5분)
  "hub": {                        // 4호기 라인 상태. 허브 연결 안 되면 null
    "line_state": "RUNNING",      // RUNNING | STOPPING | EJECTING | STOPPED | UNKNOWN
    "warn_lamp": false, "eject_count": 1, "ok": true, "result": "STATUS"
  },
  "targets": [                    // AI 예측 대상 4개: 1호기 RMS·압력, 2호기 변위, 3호기 온도
    {
      "eq_id": "EQ_FORGING_01", "eq_label": "1호기 압조",
      "target": "pressure", "label": "압력", "unit": "ton",
      "lo": 48.0, "hi": 52.0, "hi_inclusive": false, "warn": null,   // 기준표 한계 (없으면 null)
      "sigma_w": 0.06, "k_sigma": 3.0,      // AI 정지 판단: P50 ± k_sigma*sigma_w 가 한계를 넘으면 정지
      "actual": [[ms, value], ...],         // 실측 개별값 (최대 900점으로 축소)
      "mean10": [[ms, value], ...],         // 실측 10초 평균 (= AI 가 예측하는 값)
      "pred":   [[target_ms, p10, p50, p90], ...],   // 유효 예측. x 는 '목표 시각' (예측 시각 + 5분)
      "latest": {                           // 최신 예측 1건 (없으면 null)
        "pred_ts": "...", "target_ts": "...", "current": 49.91, "current_mean": 49.9,
        "p10": 49.46, "p50": 49.79, "p90": 50.18,
        "status": "VALID",                  // VALID 만 신뢰. 그 외는 reason 참고
        "reason": ""
      },
      "metrics": {                          // 목표 시각이 지난 예측을 실측과 대조
        "n": 416, "mae_model": 0.2397, "mae_persist": 0.2804,   // AI 오차 vs 현재값 유지 시 오차
        "coverage": 0.77,                   // 실측이 P10~P90 안에 든 비율 (목표 약 0.8)
        "valid_share": 0.62
      },
      "truth": {"scenario": "HYD_LEAK", "damage": 0.15}   // 시뮬레이션 정답 (실제 센서면 null)
    }
  ],
  "extras": [                     // 실측 전용 (AI 대상 아님)
    {"label": "2호기 초음파 AE", "unit": "dB", "lo": null, "hi": 40.0, "ref_only": false, "note": "...", "actual": [[ms, v], ...]},
    {"label": "3호기 탄소 농도", "unit": "", "lo": 0.40, "hi": 0.45, "ref_only": true, "note": "...", "actual": [...]}
  ],
  "events": [                     // 인터록 이력 최근 15건 (최신 먼저)
    {"ts": "...", "source": "AI_EQ_FORGING_01", "kind": "PRED_STOP", "code": "PRED_NG_PRESSURE_LOW",
     "value": 47.98, "command": "CMD_STOP", "result": "ACKED(STOPPING)"}
  ],
  "link": [{"eq_id": "...", "eq_label": "1호기 압조", "received": 1615627, "lost": 0, "corrupt": 0, "resyncs": 1}],
  "vision": {                     // 비전 테이블 없으면 null
    "ok": 1200, "ng": 3, "total": 1203, "avg_ms": 7.2,
    "recent_ng": [{"ts": "...", "part": 1234, "status": "NG_VISION_CRACK", "cls": "crack", "conf": 0.91, "hub": "ACKED(STOPPING)"}]
  }
}
```

## 표시 규칙 (현재 대시보드와 같게 하려면)
- 예측 P50은 `pred` 의 x(목표 시각)에 그려 `mean10` 과 겹칩니다. 겹치는 정도가 곧 정확도입니다.
- 이상 판단: `latest.status == "VALID"` 이고 `P50 ± k_sigma*sigma_w` 가 `lo`/`hi` 를 넘으면 경보입니다. `hi_inclusive` 가 true면 `>=` 로 비교합니다.
- 라인 상태: `hub.line_state` 가 RUNNING이 아니면 정지 상태입니다. `hub` 가 null이면 "허브 연결 안 됨" 입니다.
- 오류 응답: HTTP 503 + `{"error": "...", "db": "..."}` (DB 읽기 실패).
