

arg1 = int(input("더해질 숫자 입력"))
arg2 = int(input("더할 숫자 입력"))
num = input("사칙 연산자 입력")

def plus(a, b):
    return a+b

def minus(a, b):
    return a-b

def multiple(a, b):
    return a*b

def divide(a, b):
    return a/b

match num:
    case '+':
      print(plus(arg1, arg2))
    case '-':
      print(minus(arg1, arg2))
    case '*':
      print(multiple(arg1, arg2))
    case '/':
      print(divide(arg1, arg2))
        

