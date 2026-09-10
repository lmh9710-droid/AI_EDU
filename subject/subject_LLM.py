mdic = {}
num = int(input("회원등록할 사람 수: "))
nowNumber = 0

print("===================================")

while num > nowNumber:
    member = input("등록할 회원: ")
    grade = input("회원의 등급: ")
    point = int(input("적립 포인트: "))
    phoneNo = input("연락처 (예: 010-1234-5678): ")  
    mdic[member] = [grade, point, phoneNo]
    nowNumber += 1
    print("===================================")

print("==================================================================================================")
print("                                쇼핑몰 데이터 분석 리포트                                          ")
print("==================================================================================================")

total_point = 0
list_members = list(mdic.keys())

for member in list_members:
    grade = mdic[member][0]
    point = mdic[member][1]
    phoneNo = mdic[member][2]
    
    # 1. 천 단위 콤마 포맷팅 (1000원 미만도 안전하게 처리)
    formatted_point = f"{point:,}"
    
    # 2. 전화번호 뒷자리 4자리 마스킹 처리
    anony_phoneNo = phoneNo[:-4] + "****" if len(phoneNo) >= 4 else phoneNo
    
    print(f"{member} | 등급: {grade} | 적립포인트: {formatted_point}원 | 연락처: {anony_phoneNo}")
    total_point += point

print("==================================================================================================")

# 0명 등록 시 ZeroDivisionError(0으로 나누기 오류) 방지
if len(list_members) > 0:
    total_rev = total_point * (100 / 5)  # 적립포인트는 구매액의 5%
    mean_rev = total_rev / len(list_members)
    
    print(f"총 회원수: {len(list_members)}명")
    print(f"총 매출액: {int(total_rev):,}원")
    print(f"평균 구매액: {int(mean_rev):,}원")
else:
    print("등록된 회원이 없습니다.")
