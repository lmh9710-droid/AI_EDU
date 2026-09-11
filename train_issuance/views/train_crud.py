import streamlit as st

def show_train_management(services):
    st.header("🛠️ KTX 운행 노선 관리 테이블 (CRUD)")
    t1, t2 = st.tabs(["➕ 노선 추가", "🔍 조회 및 삭제/수정"])
    
    with t1:
        with st.form("add_form"):
            dest = st.text_input("목적지")
            dep = st.text_input("출발")
            arr = st.text_input("도착")
            fare = st.number_input("요금", min_value=1000, value=30000)
            if st.form_submit_button("등록") and dest:
                services.train_repo.add(dest, dep, arr, fare)
                st.success("등록 완료")
                
    with t2:
        df = services.train_repo.fetch_all()
        st.dataframe(df, use_container_width=True)
        if not df.empty:
            t_id = st.selectbox("제어할 열차 ID 선택", df["train_id"].tolist())
            if st.button("❌ 선택 노선 완전히 삭제"):
                services.train_repo.delete(t_id)
                st.rerun()
