import cv2
import numpy as np
from config import Config
from renderer import TextRenderer

class GalleryManager:
    def __init__(self, gallery_w=Config.GALLERY_W, total_h=Config.TOTAL_H):
        self.gallery_w = gallery_w
        self.total_h = total_h
        self.captured_images = []
        self.gallery_idx = 0
        self.file_counter = 1
        
        self.is_dragging = False
        self.drag_start_y = 0

    def handle_mouse(self, event, x, y):
        if x >= Config.LIVE_W:
            if event == cv2.EVENT_LBUTTONDOWN:
                self.is_dragging = True
                self.drag_start_y = y

            elif event == cv2.EVENT_MOUSEMOVE and self.is_dragging:
                diff_y = y - self.drag_start_y
                if diff_y < -40:
                    if self.gallery_idx < len(self.captured_images) - 1:
                        self.gallery_idx += 1
                    self.drag_start_y = y
                elif diff_y > 40:
                    if self.gallery_idx > 0:
                        self.gallery_idx -= 1
                    self.drag_start_y = y

            elif event == cv2.EVENT_LBUTTONUP:
                self.is_dragging = False

    def add_image(self, image):
        resized = cv2.resize(image, (self.gallery_w, self.total_h))
        self.captured_images.append(resized)
        self.gallery_idx = len(self.captured_images) - 1
        self.file_counter += 1

    def render_panel(self):
        panel = np.zeros((self.total_h, self.gallery_w, 3), dtype=np.uint8)
        if len(self.captured_images) > 0:
            panel = self.captured_images[self.gallery_idx].copy()
            nav_text = f"갤러리 [{self.gallery_idx + 1}/{len(self.captured_images)}] (상하 드래그)"
            panel = TextRenderer.put_korean_text(
                panel, nav_text, (10, 10), font_size=14, 
                font_color=(255, 255, 255), bg_color=(0, 0, 0)
            )
        else:
            panel = TextRenderer.put_korean_text(
                panel, "20mm 이상 침투 시 자동 촬영", (40, 220), 
                font_size=15, font_color=(150, 150, 150)
            )
            panel = TextRenderer.put_korean_text(
                panel, "(오른쪽 영역 상하 드래그 가능)", (40, 250), 
                font_size=13, font_color=(100, 100, 100)
            )
        return panel