import streamlit as st

def show_reservation(services):
    st.header("🎫 추석 KTX 승차권 실시간 예매")
    df_trains = services.train_repo.fetch_all()
    if df_trains.empty:
        st.warning("등록된 KTX 열차가 없습니다.")
        return

    count = st.number_input("인원 선택", min_value=1, max_value=10, value=1)
    df_trains["label"] = df_trains["destination"] + "행 (" + df_trains["dep_time"] + ")"
    selected_str = st.selectbox("KTX 여정 선택", df_trains["label"].tolist())
    selected_row = df_trains[df_trains["label"] == selected_str].iloc[0]

    m_type = st.radio("회원 인증", ["기존회원", "신규가입", "비회원"], horizontal=True)
    p_name, p_grade, m_id = "", "비회원", None

    if m_type == "기존회원":
        input_id = st.text_input("회원번호 입력")
        if input_id:
            user = services.verify_member(input_id)
            if user:
                p_name, p_grade, m_id = user["name"], user["grade"], input_id
                st.success(f"✅ {p_name}님 확인 완료")
    elif m_type == "신규가입":
        n_name = st.text_input("이름")
        n_id = st.text_input("새 번호")
        if n_name and n_id and st.button("회원 등록"):
            if services.join_member(n_id, n_name): st.success("가입 성공")
            p_name, p_grade, m_id = n_name, "일반회원", n_id
    elif m_type == "비회원":
        p_name = st.text_input("탑승자 이름")

    room = st.selectbox("객실", ["일반실", "특실"])
    fare, points = services.calculate_price(int(selected_row["base_fare"]), room, count, p_grade)

    if st.button("🎫 최종 발권하기", type="primary") and p_name:
        now = services.execute_booking(p_name, p_grade, count, selected_row["destination"], selected_row["dep_time"], selected_row["arr_time"], room, fare, points, m_id)
        st.success(f"발권 성공! 시간: {now} / 금액: {fare:,}원")
