import cv2
import numpy as np
import datetime
import time
from config import Config
from database import DatabaseManager
from renderer import TextRenderer
from zoom_roi_manager import ZoomAndROIManager
from analyzer import MotionAnalyzer
from gallery import GalleryManager

class SafetyGuardApp:
    def __init__(self):
        self.zoom_roi_mgr = ZoomAndROIManager()
        self.analyzer = MotionAnalyzer()
        self.gallery_mgr = GalleryManager()
        self.db_mgr = DatabaseManager()
        
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

        if not ret or frame_a is None or frame_b is None:
            print("[오류] 초기 프레임을 읽어오지 못했습니다.")
            cap.release()
            return

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