import sqlite3
from config import Config

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