import cv2
from config import Config

class ZoomAndROIManager:
    def __init__(self, base_w=Config.LIVE_W, base_h=Config.TOTAL_H):
        self.base_w = base_w
        self.base_h = base_h

    def calculate_roi_box(self, margin_val):
        rx1 = max(10, margin_val)
        ry1 = max(10, margin_val)
        rx2 = min(self.base_w - 10, self.base_w - margin_val)
        ry2 = min(self.base_h - 10, self.base_h - margin_val)
        return (rx1, ry1, rx2, ry2)

    def process_zoom(self, frame, zoom_factor):
        if zoom_factor <= 1.0:
            return frame.copy()

        h, w = frame.shape[:2]
        crop_w = int(w / zoom_factor)
        crop_h = int(h / zoom_factor)

        x1 = (w - crop_w) // 2
        y1 = (h - crop_h) // 2

        cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
        return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)