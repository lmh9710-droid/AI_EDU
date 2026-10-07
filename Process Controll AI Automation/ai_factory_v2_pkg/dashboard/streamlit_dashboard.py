"""
스마트팩토리 대시보드를 Streamlit 으로 그리기 (기존 대시보드 서버의 /api/data 사용)

  준비: pip install streamlit plotly
  실행: SF_DASH_URL=http://localhost:8050 streamlit run streamlit_dashboard.py
  ※ 대시보드 서버(./scripts/run_dashboard.sh)가 먼저 실행 중이어야 합니다.
     Streamlit 서버가 다른 PC 라면 대시보드를 SF_DASH_HOST=0.0.0.0 으로 열고 그 PC 의 IP 를 넣으세요.
"""
import json
import os
import urllib.request

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DASH_URL = os.environ.get("SF_DASH_URL", "http://localhost:8050").rstrip("/")
LINE_COLOR = {"RUNNING": "🟢", "STOPPING": "🔴", "EJECTING": "🔴", "STOPPED": "🔴", "UNKNOWN": "⚪"}


def fetch(minutes: int) -> dict:
    with urllib.request.urlopen(f"{DASH_URL}/api/data?minutes={minutes}", timeout=5) as r:
        return json.load(r)


def ts(ms_list):
    # 서버가 KST 시각을 그대로 ms 로 보내므로 UTC 로 해석하면 KST 숫자가 그대로 나옴
    return pd.to_datetime(ms_list, unit="ms")


def target_figure(t: dict, now_ms: int) -> go.Figure:
    fig = go.Figure()
    if t.get("pred"):
        x = ts([p[0] for p in t["pred"]])
        fig.add_trace(go.Scatter(x=x, y=[p[3] for p in t["pred"]], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=[p[1] for p in t["pred"]], fill="tonexty", line=dict(width=0),
                                 fillcolor="rgba(46,100,166,0.18)", name="예측 P10~P90"))
        fig.add_trace(go.Scatter(x=x, y=[p[2] for p in t["pred"]], line=dict(color="#2E64A6", dash="dash"), name="5분 전 예측 P50"))
    if t.get("actual"):
        fig.add_trace(go.Scatter(x=ts([a[0] for a in t["actual"]]), y=[a[1] for a in t["actual"]],
                                 line=dict(color="#1E2730", width=1.5), name="실측"))
    for lim in (t.get("lo"), t.get("hi")):
        if lim is not None:
            fig.add_hline(y=lim, line=dict(color="#C0182B", width=1.5))
    if t.get("warn") is not None:
        fig.add_hline(y=t["warn"], line=dict(color="#B4410E", dash="dot"))
    fig.add_vline(x=ts([now_ms])[0], line=dict(color="#7C8792", dash="dot"))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.2),
                      yaxis_title=t.get("unit", ""))
    return fig


st.set_page_config(page_title="스마트팩토리 PdM", layout="wide")
minutes = st.sidebar.selectbox("표시 구간", [10, 30, 60, 180], index=1, format_func=lambda m: f"{m}분")


@st.fragment(run_every=2)          # 2초마다 이 부분만 새로 그림 (Streamlit 1.37 이상)
def live():
    try:
        d = fetch(minutes)
    except Exception as e:  # noqa: BLE001
        st.error(f"대시보드 서버에 연결할 수 없습니다 ({DASH_URL}): {e}")
        return
    if d.get("empty"):
        st.info("아직 DB 에 데이터가 없습니다.")
        return
    hub = d.get("hub") or {}
    state = hub.get("line_state", "UNKNOWN")
    banner = f"{LINE_COLOR.get(state, '⚪')} 라인 {state} · 경고등 {'켜짐' if hub.get('warn_lamp') else '꺼짐'} · 누적 퇴출 {hub.get('eject_count', '-')}개"
    (st.error if state != "RUNNING" else st.success)(banner if hub else "허브 연결 안 됨")

    cols = st.columns(2)
    for i, t in enumerate(d.get("targets", [])):
        with cols[i % 2]:
            latest = t.get("latest") or {}
            m = t.get("metrics") or {}
            st.subheader(f"{t['eq_label']} · {t['label']}")
            c1, c2, c3 = st.columns(3)
            unit = f" ({t['unit']})" if t.get("unit") else ""
            c1.metric(f"현재 10초 평균{unit}", f"{latest['current_mean']:.3f}" if latest.get("current_mean") is not None else "-")
            c2.metric(f"5분 뒤 P50{unit}", f"{latest['p50']:.3f}" if latest.get("p50") is not None else latest.get("status", "-"))
            c3.metric("적중률 P10~P90", f"{m.get('coverage', 0) * 100:.0f}%" if m.get("n") else "-")
            st.plotly_chart(target_figure(t, d["now"]), use_container_width=True, key=f"fig-{i}")

    st.subheader("인터록 이력 (최근 15건)")
    if d.get("events"):
        st.dataframe(pd.DataFrame(d["events"]), use_container_width=True, hide_index=True)


live()
