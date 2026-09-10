

arg1 = int(input("첫번째 숫자 입력"))
arg2 = int(input("두번째 숫자 입력"))
num = input("사칙 연산자 입력")

def plus(a, b):
    print(f"{arg1}+{arg2}={arg1+arg2}")

def minus(a, b):
    print(f"{arg1}-{arg2}={arg1-arg2}")

def multiple(a, b):
   print(f"{arg1}*{arg2}={arg1*arg2}")

def divide(a, b):
   print(f"{arg1}/{arg2}={arg1/arg2}")
match num:
    case '+':
        plus(arg1, arg2)
    case '-':
        minus(arg1, arg2)
    case '*':
        multiple(arg1, arg2)
    case '/':
        divide(arg1, arg2)
        

