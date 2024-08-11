
from .models.game_attendance_replies import GameAttendanceReply
from .models.members import Member

def get_attendance_of_game(game_id: int) -> dict[int, list[Member]]:
    replies = GameAttendanceReply.search_by_game_id(game_id)
    replies.sort(key=lambda x: x.updated_at, reverse=True)
    attendance = {}
    member_ids = set()
    for reply in replies:
        reply_type = reply.reply
        member_id = reply.member_id
        if member_id in member_ids:
            continue
        if reply_type not in attendance:
            attendance[reply_type] = []
        member_ids.add(member_id)
        member = Member.search_by_id(member_id)
        attendance[reply_type].append(member)
    return attendance