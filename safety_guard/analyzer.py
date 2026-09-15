import cv2
from config import Config

class MotionAnalyzer:
    def __init__(self, mm_per_px=Config.MM_PER_PIXEL):
        self.mm_per_px = mm_per_px

    def analyze(self, frame_a, frame_b, frame_c, roi_box):
        diff1 = cv2.absdiff(frame_a, frame_b)
        diff2 = cv2.absdiff(frame_b, frame_c)
        gray1 = cv2.cvtColor(diff1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(diff2, cv2.COLOR_BGR2GRAY)
        diff = cv2.bitwise_and(gray1, gray2)

        _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
        thresh = cv2.blur(thresh, (5, 5))
        _, thresh = cv2.threshold(thresh, 30, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        rx1, ry1, rx2, ry2 = roi_box
        max_px = 0
        max_direction = None
        motion_boxes = []

        for contour in contours:
            if cv2.contourArea(contour) < 1000:
                continue

            x, y, bw, bh = cv2.boundingRect(contour)
            motion_boxes.append((x, y, bw, bh))

            if y < ry1 and (y + bh) > ry1:
                p = (y + bh) - ry1
                if p > max_px: max_px, max_direction = p, '상'

            if (y + bh) > ry2 and y < ry2:
                p = ry2 - y
                if p > max_px: max_px, max_direction = p, '하'

            if x < rx1 and (x + bw) > rx1:
                p = (x + bw) - rx1
                if p > max_px: max_px, max_direction = p, '좌'

            if (x + bw) > rx2 and x < rx2:
                p = rx2 - x
                if p > max_px: max_px, max_direction = p, '우'

        max_mm = round(max_px * self.mm_per_px, 1)
        return motion_boxes, max_mm, max_direction