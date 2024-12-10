from datetime import datetime, timedelta

from .models.games import Game
from .models.members import Member
from .general_message import (
    cancellation_announcement_opening,
    weekday_mapping,
    offseason_game_sign,
    normal_game_sign,
    reply_text_mapping,
    offseason_game_reminder,
    game_reminder,
    attendance_opening,
    no_attendance
)


def generate_no_game_message() -> str:
    message = "\n一週一度的通知又來囉！不過近一個月尚未有聯盟賽呢～\n"
    message = message + "\n請密切注意幹部的通知，或上官網確認詳細資訊！\n"
    message = message + "\n期待下一場比賽！\U0001F4AA"
    return message


def generate_error_message() -> str:
    message = "\n一週一度的通知又來囉！\n"
    message = (
        message + "不過可能由於聯盟官網改版，或爬蟲機器人異常，撈不到應有的比賽訊息\n"
    )
    message = message + "請密切注意幹部的通知，或上官網確認詳細資訊\n"
    message = message + "希望管理員能夠盡快修復！\n"
    message = message + "\n期待下一場比賽！\U0001F4AA"
    return message


def generate_schedule_message_for_team(games: list[Game]) -> str:
    message = "\n一週一度的通知又來囉！\n"

    this_week_games, this_month_games = Game.get_games_in_this_week_and_month(games)

    if len(this_week_games) == 0 and len(this_month_games) == 0:
        return generate_no_game_message()

    has_offseason = False
    if len(this_week_games) > 0:
        message = message + "\n本週的比賽如下：\n"
    for game in this_week_games:
        message = message + game.generate_summary_for_team() + "\n"
        if game.season == 3:
            has_offseason = True

    if len(this_month_games) > 0:
        if len(this_week_games) > 0:
            message = message + "\n近一個月其餘的比賽如下：\n"
        else:
            message = message + "\n近一個月的比賽如下：\n"
    for game in this_month_games:
        message = message + game.generate_summary_for_team() + "\n"
        if game.season == 3:
            has_offseason = True

    if has_offseason:
        message = message + f"\n{offseason_game_sign} 黃球為季後賽\n"
    message = message + "\n期待你到場助陣！\U0001F4AA"
    return message


