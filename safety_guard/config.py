import cv2
import numpy as np
import datetime
import time
import sqlite3
from PIL import Image, ImageDraw, ImageFont

# =========================================================
# 1. 시스템 환경설정 및 상수 관리 모듈
# =========================================================
class Config:
    MM_PER_PIXEL = 0.264  # 픽셀 -> mm 환산 상수
    
    TOTAL_W, TOTAL_H = 960, 480
    LIVE_W = 600
    GALLERY_W = 360
    
    DEFAULT_ROI_MARGIN = 80
    COOLDOWN_SEC = 2.0
    DB_FILE = "safety_guard.db"  # SQLite DB 파일명

    RISK_MAP = {
        '상': '상: 낙상사고 위험',
        '하': '하: 미끄러짐 위험',
        '좌': '좌: 충돌사고 위험',
        '우': '우: 끼임사고 위험'
    }

# =========================================================
# 2. SQLite 데이터베이스 관리 모듈 (신규 추가)
# =========================================================
class DatabaseManager:
    def __init__(self, db_path=Config.DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """테이블이 없을 경우 자동 생성"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intrusion_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_no INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT,
                    penetration_mm REAL NOT NULL,
                    risk_level TEXT,
                    zoom_level REAL,
                    roi_margin INTEGER
                )
            """)
            conn.commit()

    def log_event(self, image_no, filename, timestamp, direction, penetration_mm, risk_level, zoom_level, roi_margin):
        """감지된 경보 이벤트를 SQLite DB에 저장"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO intrusion_logs (
                    image_no, filename, timestamp, direction, 
                    penetration_mm, risk_level, zoom_level, roi_margin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (image_no, filename, timestamp, direction, penetration_mm, risk_level, zoom_level, roi_margin))
            conn.commit()

# =========================================================
# 3. 한글 출력 및 고가독성 자막 렌더링 모듈
# =========================================================
class TextRenderer:
    @staticmethod
    def put_korean_text(img, text, position, font_size=18, font_color=(255, 255, 255), 
                        bg_color=None, stroke_color=(0, 0, 0), stroke_width=2):
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)

        try:
            font = ImageFont.truetype("malgun.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        x, y = position

        if bg_color is not None:
            bbox = draw.textbbox((x, y), text, font=font)
            padding = 4
            bg_rect = [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding]
            draw.rectangle(bg_rect, fill=bg_color)

        draw.text((x, y), text, font=font, fill=font_color, 
                  stroke_width=stroke_width, stroke_fill=stroke_color)

        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    @classmethod
    def apply_high_readability_banner(cls, img, text, banner_height=55):
        """이미지 하단에 어두운 배경 바를 생성하고 고대비 텍스트 각인"""
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, h - banner_height), (w, h), (15, 15, 15), -1)

        return cls.put_korean_text(
            img,
            text,
            position=(12, h - banner_height + 12),
            font_size=18,
            font_color=(255, 30, 30),
            stroke_color=(255, 255, 255),
            stroke_width=2
        )

# =========================================================
# 4. 줌(Zoom) 및 ROI(경계선) 좌표 관리 모듈
# =========================================================
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

# =========================================================
# 5. 모션 탐지 및 침투 분석 모듈
# =========================================================
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

# =========================================================
# 6. 갤러리 관리 및 마우스 드래그 이벤트 모듈
# =========================================================
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

# =========================================================
# 7. 메인 애플리케이션 컨트롤러
# =========================================================
class SafetyGuardApp:
    def __init__(self):
        self.zoom_roi_mgr = ZoomAndROIManager()
        self.analyzer = MotionAnalyzer()
        self.gallery_mgr = GalleryManager()
        self.db_mgr = DatabaseManager()  # DB 매니저 추가
        
        self.window_name = "Safety Motion Guard"
        self.last_capture_time = 0
        self.is_fullscreen = False

    def _init_window(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, Config.TOTAL_W, Config.TOTAL_H)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        cv2.createTrackbar("Zoom (x10)", self.window_name, 10, 30, lambda x: None)
        cv2.createTrackbar("ROI Size", self.window_name, Config.DEFAULT_ROI_MARGIN, 180, lambda x: None)

    def _mouse_callback(self, event, x, y, flags, param):
        self.gallery_mgr.handle_mouse(event, x, y)

    def run(self):
        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print("[오류] 카메라인식 실패")
            return

        self._init_window()

        ret, frame_a = cap.read()
        ret, frame_b = cap.read()

        frame_a = cv2.resize(frame_a, (Config.LIVE_W, Config.TOTAL_H))
        frame_b = cv2.resize(frame_b, (Config.LIVE_W, Config.TOTAL_H))

        while cap.isOpened():
            ret, frame_c = cap.read()
            if not ret:
                break

            frame_c = cv2.resize(frame_c, (Config.LIVE_W, Config.TOTAL_H))

            zoom_val = max(10, cv2.getTrackbarPos("Zoom (x10)", self.window_name)) / 10.0
            roi_margin = cv2.getTrackbarPos("ROI Size", self.window_name)

            zoomed_c = self.zoom_roi_mgr.process_zoom(frame_c, zoom_val)
            zoomed_b = self.zoom_roi_mgr.process_zoom(frame_b, zoom_val)
            zoomed_a = self.zoom_roi_mgr.process_zoom(frame_a, zoom_val)

            roi_box = self.zoom_roi_mgr.calculate_roi_box(roi_margin)
            live_frame = zoomed_c.copy()

            motion_boxes, max_mm, max_direction = self.analyzer.analyze(
                zoomed_a, zoomed_b, zoomed_c, roi_box
            )

            for (bx, by, bw, bh) in motion_boxes:
                cv2.rectangle(live_frame, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)

            border_color = (0, 255, 0)
            is_red_alert = False

            if max_mm >= 20.0:
                border_color = (0, 0, 255)
                is_red_alert = True
            elif max_mm >= 10.0:
                border_color = (0, 165, 255)
            elif max_mm >= 5.0:
                border_color = (0, 255, 255)

            rx1, ry1, rx2, ry2 = roi_box
            cv2.rectangle(live_frame, (rx1, ry1), (rx2, ry2), border_color, 3)

            current_time = time.time()
            if is_red_alert and (current_time - self.last_capture_time > Config.COOLDOWN_SEC):
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                risk_msg = Config.RISK_MAP.get(max_direction, "경계 침투 위험")
                img_no = self.gallery_mgr.file_counter

                save_img = live_frame.copy()
                info_text = f"[{risk_msg}] 침투: {max_mm}mm | 일시: {now_str}"
                save_img = TextRenderer.apply_high_readability_banner(save_img, info_text)

                filename = f"{img_no:03d}.jpg"
                cv2.imwrite(filename, save_img)

                # SQLite DB 기록 추가
                self.db_mgr.log_event(
                    image_no=img_no,
                    filename=filename,
                    timestamp=now_str,
                    direction=max_direction,
                    penetration_mm=max_mm,
                    risk_level=risk_msg,
                    zoom_level=zoom_val,
                    roi_margin=roi_margin
                )

                print(f"[경보 촬영 및 DB 저장] No.{img_no:03d} | 파일: {filename} | {risk_msg} ({max_mm}mm)")

                self.gallery_mgr.add_image(save_img)
                self.last_capture_time = current_time

            status_str = f"침투: {max_mm}mm"
            if max_direction:
                status_str += f" ({max_direction}측)"

            live_frame = TextRenderer.put_korean_text(
                live_frame, f"[LIVE] {status_str} | Zoom: {zoom_val:.1f}x | [F]:전체화면 [Q]:종료", 
                (10, 10), font_size=14, font_color=border_color, bg_color=(0, 0, 0)
            )

            gallery_panel = self.gallery_mgr.render_panel()
            combined_display = np.hstack((live_frame, gallery_panel))

            cv2.imshow(self.window_name, combined_display)

            frame_a = frame_b
            frame_b = frame_c

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key in (ord('f'), ord('F')):
                self.is_fullscreen = not self.is_fullscreen
                if self.is_fullscreen:
                    cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(self.window_name, Config.TOTAL_W, Config.TOTAL_H)

        cap.release()
        cv2.destroyAllWindows()

# =========================================================
# 프로그램 실행 엔트리 포인트
# =========================================================
if __name__ == "__main__":
    app = SafetyGuardApp()
    app.run()