import datetime

# 가상의 회원 데이터베이스 (회12: [성명, 회원등급, 누적적립금])
MEMBER_DB = {
    "12345": ["홍길동", "우수회원", 1500],
    "67890": ["김철수", "VIP회원", 5000],
    "11111": ["이영희", "일반회원", 0]
}

GRADE_RATES = {
    "일반회원": 0.05,
    "우수회원": 0.07,
    "VIP회원": 0.10
}

def manage_member():
    """회원 인증 및 성명 등록 시스템"""
    print("\n[회원 확인 및 성명 등록 단계]")
    print(" 1. 기존 회원 로그인 (회원번호 입력)")
    print(" 2. 신규 회원 등록 (성명 및 회원번호 생성)")
    print(" 3. 비회원 예매 (성명 입력 필수)")
    
    while True:
        try:
            choice = int(input("   선택 (번호 입력): "))
            if choice == 1:
                # 기존 회원 조회
                mem_id = input("   회원번호를 입력하세요: ").strip()
                if mem_id in MEMBER_DB:
                    name, grade, point = MEMBER_DB[mem_id]
                    print(f"   => [인증 성공] {name}님({grade}) 환영합니다. (현재 보유 적립금: {point:,}원)")
                    return name, grade, mem_id
                else:
                    print("   [오류] 등록되지 않은 회원번호입니다. 다시 시도하거나 신규 등록해주세요.")
            
            elif choice == 2:
                # 신규 회원 등록 및 성명 입력
                print("\n   [신규 회원 등록]")
                new_name = input("   고객님의 성명을 입력하세요: ").strip()
                if not new_name:
                    print("   [오류] 성명은 공백일 수 없습니다.")
                    continue
                    
                new_id = input("   사용할 회원번호를 입력하세요 (예: 5자리 숫자): ").strip()
                if new_id in MEMBER_DB:
                    print("   [오류] 이미 존재하는 회원번호입니다.")
                    continue
                
                # 신규 등록 (기본 '일반회원', 적립금 0원)
                MEMBER_DB[new_id] = [new_name, "일반회원", 0]
                print(f"   => [등록 완료] {new_name}님의 회원 가입이 완료되었습니다! (등급: 일반회원)")
                return new_name, "일반회원", new_id
                
            elif choice == 3:
                # 비회원도 성명 등록
                guest_name = input("   발권 확인을 위한 성명을 입력하세요: ").strip()
                if not guest_name:
                    print("   [오류] 성명은 공백일 수 없습니다.")
                    continue
                print(f"   => 비회원({guest_name}님)으로 예매를 진행합니다. (적립금 미제공)")
                return guest_name, "비회원", None
            else:
                print("[오류] 1, 2, 3번 중에서 선택해주세요.")
        except ValueError:
            print("[오류] 숫자만 입력 가능합니다.")

def run_ktx_program():
    print("=" * 45)
    print("      추석 KTX 열차표 발행 프로그램 (성명 반영)     ")
    print("=" * 45)

    # 1. 인원수 입력
    while True:
        try:
            passenger_count = int(input("1. 인원수를 입력하세요 (숫자만): "))
            if passenger_count > 0:
                break
            print("[오류] 인원수는 1명 이상이어야 합니다.")
        except ValueError:
            print("[오류] 올바른 숫자를 입력해주세요.")

    # 2. 목적지 선택
    print("\n2. 목적지를 선택하세요 (기본 출발지: 서울)")
    print("   1. 부산  2. 대전  3. 대구  4. 광주")
    destinations = {1: ("부산", 59800), 2: ("대전", 23700), 3: ("대구", 43500), 4: ("광주", 46800)}
    
    while True:
        try:
            dest_choice = int(input("   선택 (번호 입력): "))
            if dest_choice in destinations:
                dest_name, base_fare = destinations[dest_choice]
                break
            print("[오류] 선택지 안의 번호를 입력해주세요.")
        except ValueError:
            print("[오류] 숫자만 입력 가능합니다.")

    # 3. 시간(출발, 도착) 선택
    print("\n3. 열차 시간대를 선택하세요")
    print("   1. 08:00 출발 -> 10:30 도착")
    print("   2. 13:00 출발 -> 15:45 도착")
    print("   3. 18:30 출발 -> 21:10 도착")
    times = {1: ("08:00", "10:30"), 2: ("13:00", "15:45"), 3: ("18:30", "21:10")}
    
    while True:
        try:
            time_choice = int(input("   선택 (번호 입력): "))
            if time_choice in times:
                dep_time, arr_time = times[time_choice]
                break
            print("[오류] 선택지 안의 번호를 입력해주세요.")
        except ValueError:
            print("[오류] 숫자만 입력 가능합니다.")

    # 4. 회원 관리 및 성명 가져오기 (수정 파트)
    passenger_name, member_grade, member_id = manage_member()
    mileage_rate = GRADE_RATES.get(member_grade, 0.0)

    # 5. 실(일반실, 특실) 선택
    print("\n5. 좌석 등급(실)을 선택하세요")
    print("   1. 일반실 (기본 요금)  2. 특실 (기본 요금의 40% 할증)")
    
    while True:
        try:
            room_choice = int(input("   선택 (번호 입력): "))
            if room_choice == 1:
                room_type = "일반실"
                room_multiplier = 1.0
                break
            elif room_choice == 2:
                room_type = "특실"
                room_multiplier = 1.4
                break
            print("[오류] 1번 또는 2번을 선택해주세요.")
        except ValueError:
            print("[오류] 숫자만 입력 가능합니다.")

    # 6 & 7. 요금 및 적립금 계산
    total_fare = int((base_fare * room_multiplier) * passenger_count)
    reward_points = int(total_fare * mileage_rate)

    # 회원 데이터베이스에 누적 적립금 저장 (회원일 경우만)
    if member_id:
        MEMBER_DB[member_id][2] += reward_points

    # 영수증(열차표) 발행 출력 (성명 출력 추가)
    print("\n" + "=" * 45)
    print("         ★ KTX 명절 승차권 발권 완료 ★         ")
    print("=" * 45)
    print(f" 발행 일시 : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 승 객 성 명 : {passenger_name} 님")  # <--- 성명 출력 부분 추가
    print(f" 1. 인 원 수 : {passenger_count}명")
    print(f" 2. 목 적 지 : 서울 → {dest_name}")
    print(f" 3. 열차시간 : 출발 {dep_time} ──> 도착 {arr_time}")
    print(f" 4. 회원등급 : {member_grade if member_id else '비회원'}")
    print(f" 5. 실 선 택 : {room_type}")
    print(f" 6. 금회적립 : {reward_points:,}원 (적립률: {int(mileage_rate*100)}%)")
    if member_id:
        print(f"    (누적 총 적립금: {MEMBER_DB[member_id][2]:,}원)")
    print(f" 7. 최 종 요 금 : {total_fare:,}원")
    print("=" * 45)
    print(" 즐거운 한가위 명절 되시길 바랍니다. 감사합니다. ")
    print("=" * 45)

if __name__ == "__main__":
    run_ktx_program()
