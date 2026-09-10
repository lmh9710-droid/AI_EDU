mdic = {}
num = int(input("회원등록할 사람 수"))
nowNo = 0

while(num >= nowNo):
    member = input("등록할 회원:")
    grade = input("회원의 등급: ")
    point = input("적립 포인트: ")
    phoneNo = input("연락처: ")  
    mdic[member] = [grade, point, phoneNo]
    nowNo +=1
# for member in mdic.keys():
    
    

print("===========================================")
print("         쇼핑몰 데이터 분석 리포트           ")
print("===========================================")

