import logging
from flask import Flask, abort, jsonify
from datetime import datetime, timedelta, time
import uuid

from linebot.v3.messaging.models.message import Message
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    BroadcastRequest,
    FlexMessage,
    TextMessage
)

from shared_module.games_crawler_client import CrawlerClient
from shared_module.models.games import Game
from shared_module.linebot_game_message import (
    produce_invitation_messages_by_games,
    produce_cancellation_messages_by_games,
)
import shared_module.line_notify as line_notify
from shared_module.settings import (
    local_timezone
)
from shared_module.line_notify_message import (
    generate_error_message,
    generate_schedule_message_for_team,
)
import shared_module.attendance_analyzer as attendance_analyzer
import shared_module.linebot_attendance_message as linebot_attendance_message

from envs import (
    channel_access_token,
    channel_secret,
    game_crawl_api
)
import message_templates

# 設置日誌記錄器
logging.basicConfig(level=logging.INFO)

now = datetime.now(local_timezone)
today_begin = datetime.combine(now, time.min, tzinfo=local_timezone)
ten_days_later = today_begin + timedelta(days=11)

app = Flask(__name__)

configuration = Configuration(access_token=channel_access_token)


@app.route("/run-future-game-announcement", methods=['GET'])
def run_future_game_announcement():
    games_crawler_client = CrawlerClient(game_crawl_api)    
    games = games_crawler_client.get_games()

    try:
        game_list = [Game.from_dict(data) for data in games]
        message = generate_schedule_message_for_team(game_list)
        line_notify.notify_announcement(message)        
        line_notify.notify_successful_log(message_templates.run_future_game_announcement_successful)
    except Exception as e:
        message = generate_error_message()
        line_notify.notify_alarm_log(message_templates.run_future_game_announcement.format(result=repr(e)))

    return ""


@app.route("/run-game-attendance-count", methods=['GET'])
def run_game_attendance_count():
    now = datetime.now(local_timezone)
    today_begin = datetime.combine(now, time.min, tzinfo=local_timezone)
    seven_days_later = today_begin + timedelta(days=8)
    
    try:
        games = Game.search_for_invited(now, seven_days_later)
        for game in games:
            mapping = attendance_analyzer.get_attendance_of_game(game.id)
            message = linebot_attendance_message.produce_attendance_message_text(game, mapping)
            line_notify.notify_management_message(message)
        line_notify.notify_successful_log(message_templates.run_game_attendance_count_successful)

    except Exception as e:
        message = generate_error_message()
        line_notify.notify_alarm_log(message_templates.run_game_attendance_count.format(result=repr(e)))

    return ""



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

