import datetime
from config import GRADE_RATES

class TicketService:
    def __init__(self, member_repo, train_repo, res_repo):
        self.member_repo = member_repo
        self.train_repo = train_repo
        self.res_repo = res_repo

    def verify_member(self, member_id):
        return self.member_repo.find_by_id(member_id)

    def join_member(self, member_id, name):
        if not self.member_repo.find_by_id(member_id):
            self.member_repo.save(member_id, name)
            return True
        return False

    def calculate_price(self, base_fare, room_type, count, grade):
        multiplier = 1.4 if room_type == "특실" else 1.0
        total_fare = int((base_fare * multiplier) * count)
        reward_points = int(total_fare * GRADE_RATES.get(grade, 0.0))
        return total_fare, reward_points

    def execute_booking(self, name, grade, count, dest, dep, arr, room, fare, points, member_id=None):
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = (name, grade, count, dest, dep, arr, room, fare, points, now_str)
        self.res_repo.save_reservation(data)
        if member_id:
            self.member_repo.update_points(member_id, points)
        return now_str
