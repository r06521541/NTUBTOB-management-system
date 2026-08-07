from dataclasses import dataclass

from .portal_data.runtime import get_identity_lifecycle_repository, is_phase_c_enabled


@dataclass(frozen=True)
class AttendancePerson:
    name: str
    person_id: int
    member_id: int | None
    qualification: str


def get_attendance_of_game(game_id: int) -> dict[int, list[object]]:
    if is_phase_c_enabled():
        summary = get_identity_lifecycle_repository().attendance_summary(game_id)
        attendance = {}
        for participant in summary.participants:
            attendance.setdefault(participant["reply"], []).append(
                AttendancePerson(
                    name=participant["name"],
                    person_id=participant["person_id"],
                    member_id=participant["member_id"],
                    qualification=participant["qualification"],
                )
            )
        return attendance

    return _legacy_attendance(game_id)


def _legacy_attendance(game_id: int) -> dict[int, list[object]]:
    from .models.game_attendance_replies import GameAttendanceReply
    from .models.members import Member

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
