# 나라별 수도 맞추기 
countries = ["한국", "미국", "일본", "중국", "러시아"]
diccon = {}
correct = 0

for country in countries:
    print(f"{country}수도 정보를 입력해주세요:")
    capital = input("수도 입력: ")
    diccon[country] = capital

if diccon["한국"] == '서울':
    correct +=1

if diccon["미국"] == '워싱턴':
    correct +=1

if diccon["일본"] == '도쿄':
    correct +=1

if diccon["중국"] == '베이징':
    correct +=1

if diccon["러시아"] == '모스크바':
    correct +=1


print(f"맞은 개수: {correct}")
