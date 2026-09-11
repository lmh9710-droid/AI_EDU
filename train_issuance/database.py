import sqlite3
from config import SAMPLE_TRAINS, SAMPLE_MEMBERS

class DatabaseConnection:
    def __init__(self, db_name="ktx_system.db"):
        self.db_name = db_name
        self.setup_tables()

    def get_conn(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def setup_tables(self):
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    member_id TEXT PRIMARY KEY, name TEXT, grade TEXT, points INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trains (
                    train_id INTEGER PRIMARY KEY AUTOINCREMENT, destination TEXT, dep_time TEXT, arr_time TEXT, base_fare INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    res_id INTEGER PRIMARY KEY AUTOINCREMENT, passenger_name TEXT, member_grade TEXT, 
                    passenger_count INTEGER, destination TEXT, dep_time TEXT, arr_time TEXT, 
                    room_type TEXT, total_fare INTEGER, reward_points INTEGER, res_date TEXT
                )
            """)
            
            # 초기 샘플 데이터 벌크 인서트
            cursor.execute("SELECT COUNT(*) FROM trains")
            if cursor.fetchone()[0] == 0:
                cursor.executemany("INSERT INTO trains (destination, dep_time, arr_time, base_fare) VALUES (?, ?, ?, ?)", SAMPLE_TRAINS)
            cursor.execute("SELECT COUNT(*) FROM members")
            if cursor.fetchone()[0] == 0:
                cursor.executemany("INSERT INTO members (member_id, name, grade, points) VALUES (?, ?, ?, ?)", SAMPLE_MEMBERS)
            conn.commit()
