import pandas as pd

class BaseRepository:
    def __init__(self, db_connection):
        self.db = db_connection

class MemberRepository(BaseRepository):
    def find_by_id(self, member_id):
        with self.db.get_conn() as conn:
            df = pd.read_sql_query("SELECT name, grade, points FROM members WHERE member_id = ?", conn, params=(member_id,))
            return df.iloc[0].to_dict() if not df.empty else None

    def save(self, member_id, name):
        with self.db.get_conn() as conn:
            conn.cursor().execute("INSERT INTO members (member_id, name, grade, points) VALUES (?, ?, ?, 0)", (member_id, name, "일반회원"))
            conn.commit()

    def update_points(self, member_id, points):
        with self.db.get_conn() as conn:
            conn.cursor().execute("UPDATE members SET points = points + ? WHERE member_id = ?", (points, member_id))
            conn.commit()

    def fetch_all(self):
        with self.db.get_conn() as conn:
            return pd.read_sql_query("SELECT * FROM members", conn)


class TrainRepository(BaseRepository):
    def fetch_all(self):
        with self.db.get_conn() as conn:
            return pd.read_sql_query("SELECT * FROM trains", conn)

    def add(self, dest, dep, arr, fare):
        with self.db.get_conn() as conn:
            conn.cursor().execute("INSERT INTO trains (destination, dep_time, arr_time, base_fare) VALUES (?, ?, ?, ?)", (dest, dep, arr, fare))
            conn.commit()

    def update(self, train_id, dest, dep, arr, fare):
        with self.db.get_conn() as conn:
            conn.cursor().execute("UPDATE trains SET destination=?, dep_time=?, arr_time=?, base_fare=? WHERE train_id=?", (dest, dep, arr, fare, train_id))
            conn.commit()

    def delete(self, train_id):
        with self.db.get_conn() as conn:
            conn.cursor().execute("DELETE FROM trains WHERE train_id=?", (train_id,))
            conn.commit()


class ReservationRepository(BaseRepository):
    def fetch_all(self):
        with self.db.get_conn() as conn:
            return pd.read_sql_query("SELECT * FROM reservations", conn)

    def save_reservation(self, data_tuple):
        with self.db.get_conn() as conn:
            conn.cursor().execute("""
                INSERT INTO reservations (passenger_name, member_grade, passenger_count, destination, dep_time, arr_time, room_type, total_fare, reward_points, res_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data_tuple)
            conn.commit()
