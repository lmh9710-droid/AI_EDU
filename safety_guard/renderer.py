import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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