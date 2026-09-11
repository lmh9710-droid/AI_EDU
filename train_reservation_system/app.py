import streamlit as st
from database import DatabaseConnection
from repositories import MemberRepository, TrainRepository, ReservationRepository
from services import TicketService

# 하위 패키지 폴더 명시적 참조
from views.dashboard import show_dashboard
from views.reservation import show_reservation
from views.train_crud import show_train_management

def main():
    # 1. 의존성 주입 (Dependency Injection) 레이어 구축
    db_conn = DatabaseConnection()
    member_repo = MemberRepository(db_conn)
    train_repo = TrainRepository(db_conn)
    res_repo = ReservationRepository(db_conn)
    
    # 하나의 서비스로 리포지토리 레이어 결합
    ticket_service = TicketService(member_repo, train_repo, res_repo)

    # 2. 사이드바 내비게이션 라우팅
    st.sidebar.title("🚄 KTX 예약 오케스트레이터")
    menu = st.sidebar.selectbox("📂 메뉴 선택", ["대시보드", "승차권 예매", "열차 운행 관리"])

    # 3. 각 뷰 컴포넌트로 결합된 서비스 인스턴스 위임 전달
    if menu == "대시보드":
        show_dashboard(ticket_service)
    elif menu == "승차권 예매":
        show_reservation(ticket_service)
    elif menu == "열차 운행 관리":
        show_train_management(ticket_service)

if __name__ == "__main__":
    main()
