from linebot.v3.messaging import (
    TextMessage
)

from .models.games import Game
from .models.members import Member
from .general_message import (
    reply_text_mapping,
    attendance_opening,
    no_attendance
)

def produce_attendance_message(game: Game, attendance: dict[int, list[Member]]) -> TextMessage:
    return TextMessage(text=produce_attendance_message_text(game, attendance))

def produce_attendance_message_text(game: Game, attendance: dict[int, list[Member]]) -> str:
    if not attendance:
        return no_attendance.format(game_short_summary=game.generate_verbal_summary_for_team())
    
    text = attendance_opening.format(game_short_summary=game.generate_verbal_summary_for_team())
    text += '\n'

    for reply in reply_text_mapping:
        if reply not in attendance:
            continue
        if not attendance[reply]:
            continue
        members = attendance[reply]
        text += f'{reply_text_mapping[reply]}：'
        for member in members:
            text += f'{member.name}、'

        text = text.rstrip('、')
        text += '\n'        
    text = text.rstrip('\n')

    return text