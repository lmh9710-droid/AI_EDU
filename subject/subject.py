mdic = {}
num = int(input("회원등록할 사람 수: "))
nowNumber = 0

print("===================================")

while(num > nowNumber):
    member = input("등록할 회원: ")
    grade = input("회원의 등급: ")
    point = int(input("적립 포인트: "))
    phoneNo = input("연락처: ")  
    mdic[member] = [grade, point, phoneNo]
    nowNumber +=1
    print("===================================")

print("==================================================================================================")
print("                                쇼핑몰 데이터 분석 리포트                                          ")
print("==================================================================================================")
total_point = 0
list_members = [member for member in mdic.keys()]
for member in list_members:

  str_point = str(mdic[member][1]) #적립포인트 문자열 처리 
  anony_phoneNo= mdic[member][2][:9]+"****" #전화번호 뒷자리 ****처리
  print(f"{member}|등급: {mdic[member][0]}| 적립포인트: {str_point[0:-3]},{str_point[-3:]}원 | 연락처 : {anony_phoneNo} ")
  total_point +=mdic[member][1]
print("==================================================================================================")

total_rev = total_point*(100/5) #적립포인트는 구매액에 5%
mean_rev = total_rev/len(list_members)
print(f"총회원수: {len(list_members)}명")
print(f"총 매출액: {int(total_rev)}원")
print(f"평균 구매액: {int(mean_rev)}원")
