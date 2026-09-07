import pygame 
from ball import Ball


WINDOW_WIDTH, WINDOW_HEIGHT = 800, 600

WHITE, BLACK, GREEN, BLUE, GRAY = (255, 255, 255), (0, 0, 0),\
    (255, 0, 0), (0, 0, 255), (200, 200, 200)

# 초기화
pygame.init()

pygame.display.set_caption("BALL")
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))

ball1 = Ball(WINDOW_WIDTH/1.2, WINDOW_HEIGHT/1.2, 20, 3, 10)
ball2 = Ball(WINDOW_WIDTH/1.3, WINDOW_HEIGHT/1.3, 10, 3, 13)
ball3 = Ball(WINDOW_WIDTH/1.4, WINDOW_HEIGHT/1.4, 15, 2, 12)
ball4 = Ball(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, 15, 5, 11)
ball5 = Ball(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, 15, 1, 15)
ball6 = Ball(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, 15, 2, 11)
ball7 = Ball(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, 15, 4, 12)
ball8 = Ball(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, 15, 1, 10)



#ball_x1, ball_y1, ball_size1 = int(WINDOW_WIDTH/2), int(WINDOW_HEIGHT/2), 20
#dx1, dy1 = 3, 5

clock = pygame.time.Clock()

done = False
while not done:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done =True

    screen.fill(WHITE)
    #ball move 
    ball1.move()
    ball2.move()
    ball3.move()
    ball4.move()
    ball5.move()
    ball6.move()
    ball7.move()
    ball8.move()
   

    #ball draw
    ball1.draw(screen, Color =BLUE)
    ball2.draw(screen, Color =GRAY)
    ball3.draw(screen, Color =GREEN)
    ball4.draw(screen, Color =BLACK)
    ball5.draw(screen, Color =GRAY)
    ball6.draw(screen, Color =GREEN)
    ball7.draw(screen, Color =BLUE)
    ball8.draw(screen, Color =GRAY)
 
    #ball_x1 += dx1; ball_y1 += dy1
    #if (ball_x1 +ball_size1) > WINDOW_WIDTH or (ball_x1 - ball_size1) < 0:
     #   dx1 *= -1
    #if(ball_y1+ball_size1) > WINDOW_HEIGHT or (ball_y1 - ball_size1) < 0:
     #   dy1 *= -1
    # 그리기 로직
    #pygame.draw.circle(screen, BLUE, [ball_x1, ball_y1], ball_size1, 0)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()