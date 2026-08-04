import logging
from flask import Flask, abort, jsonify
from time import sleep
from datetime import datetime

from linebot.v3.messaging import (
    FlexMessage,
    TextMessage
)

from shared_module.models.games import Game
from shared_module.message_templates.linebot_game_message import (
    produce_invitation_messages_by_games,
    produce_cancellation_message_by_games,
)
from shared_module.notify.discord_notify import DiscordNotifyHelper
from shared_module.announcement.linebot import LineBotAnnouncementHelper
import shared_module.linebot_config as linebot_config
from shared_module.settings import (
    local_timezone
)
import shared_module.line_messaging_api as line_messaging_api

import message_templates_notify_user
import message_templates_user
import message_templates_management
import game_reminder
from request_time import get_request_time_window

# 設置日誌記錄器
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

discord_notify_helper = DiscordNotifyHelper()

def notify_successful_log(message: str):
    discord_notify_helper.notify_successful_log(message)
def notify_alarm_log(message: str):
    discord_notify_helper.notify_alarm_log(message)
def notify_management_message(message: str):
    discord_notify_helper.notify_management_message(message)
    

linebot_announcement_helper = LineBotAnnouncementHelper()
def announce(message: str):
    linebot_announcement_helper.announce(message)

@app.route("/invitation-announcement/trigger", methods=['POST'])
def invite():
    request_time = get_request_time_window(local_timezone)
    is_successful = False
    games = Game.search_for_invitation(request_time.now, request_time.end_time)
    old_games = Game.search_for_invited()
    if games:
        messages = produce_new_invitation_messages(games)
        is_successful = False
        try:
            if line_messaging_api.broadcast(messages):
                mark_games_as_invited(games, request_time.now)
                notify_successful_log(message_templates_management.invited.format(count=len(games)))
                is_successful = True
        except Exception as e:
            logging.error("Error during invite broadcast: %s", e, exc_info=True)
            notify_alarm_log(f"{message_templates_management.invite_failed}: {e}")
            return jsonify({"error": "Failed to broadcast invite"}), 500
        
        if is_successful:
            announce(message_templates_notify_user.new_and_old_invitation_notification if old_games else message_templates_notify_user.invitation_notification)
            #announce(linebot_config.add_friend_link)
    else:
        if old_games:
            pass

    if is_successful:
        notify_successful_log(message_templates_management.invite_finish)
    return 'OK'

def produce_new_invitation_messages(games: list[Game]) -> list[FlexMessage]:
    if games:
        messages = [TextMessage(text=message_templates_user.invitation_intro)]
        messages.extend(produce_invitation_messages_by_games(games))
        return messages
    return []

def mark_games_as_invited(games: list[Game], invited_at: datetime):
    for game in games:
        Game.update_invitation_time(game.id, invited_at)

@app.route("/cancellation-announcement/trigger", methods=['POST'])
def announce_cancellation():
    request_time = get_request_time_window(local_timezone)
    games = Game.search_cancelled_to_announce(
        request_time.now, request_time.end_time
    )
    if games:
        messages = [produce_cancellation_message_by_games(games)]
        try:
            line_messaging_api.broadcast(messages)
            mark_games_as_cancellation_announced(games, request_time.now)
            notify_successful_log(message_templates_management.cancellation_announced.format(count=len(games)))
        except Exception as e:
            logging.error("Error during cancellation announcement broadcast: %s", e, exc_info=True)
            notify_alarm_log(f"{message_templates_management.cancellation_announce_failed}: {e}")
            return jsonify({"error": "Failed to broadcast cancellation announcement"}), 500
    notify_successful_log(message_templates_management.announce_cancellation_finish)
    return 'OK'


def mark_games_as_cancellation_announced(
    games: list[Game], announced_at: datetime
):
    for game in games:
        Game.update_cancellation_announcement_time(game.id, announced_at)

@app.route("/game-reminder/trigger", methods=['POST'])
def announce_game_reminder():
    text = game_reminder.get_game_reminder_string(1)
    if text:
        messages = [TextMessage(text=text)]
        try:
            line_messaging_api.broadcast(messages)
        except Exception as e:
            logging.error("Error during game reminder broadcast: %s", e, exc_info=True)
            notify_alarm_log(f"{message_templates_management.game_reminder_failed}: {e}")
            return jsonify({"error": "Failed to broadcast game reminder"}), 500
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

