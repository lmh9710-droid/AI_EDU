import pygame

class Ball:
    def __init__ (self, ball_x, ball_y, ball_size, x_speed, y_speed):
        self.ball_x = ball_x
        self.ball_y = ball_y
        self.ball_size = ball_size
        self.x_speed = x_speed
        self.y_speed = y_speed
        

    def move(self):
        self.ball_x += self.x_speed
        self.ball_y += self.y_speed

        if (self.ball_x +self.ball_size) > 800 or (self.ball_x - self.ball_size) < 0:
                     self.x_speed *= -1
        if(self.ball_y+self.ball_size) > 600 or (self.ball_y - self.ball_size) < 0:
                     self.y_speed *= -1
    
    def draw(self, screen=None, Color=None):

        target_screen = screen if screen else self.screen
        if target_screen:
            pygame.draw.circle(target_screen, Color,[self.ball_x, self.ball_y], self.ball_size, 0)
            


        