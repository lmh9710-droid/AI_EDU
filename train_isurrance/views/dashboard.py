import streamlit as st

def show_dashboard(services):
    st.header("📊 발권 및 시스템 대시보드")
    df_res = services.res_repo.fetch_all()
    df_mem = services.member_repo.fetch_all()
    df_trn = services.train_repo.fetch_all()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 발권 수", f"{len(df_res)}건")
    c2.metric("총 매출액", f"{df_res['total_fare'].sum():,}원" if not df_res.empty else "0원")
    c3.metric("총 회원 수", f"{len(df_mem)}명")
    c4.metric("운영 노선 수", f"{len(df_trn)}개")
    
    st.markdown("---")
    st.subheader("📋 실시간 전체 발권 내역")
    st.dataframe(df_res, use_container_width=True)
