import logging
from flask import Flask, abort, jsonify

from shared_module.games_crawler_client import CrawlerClient
from shared_module.models.games import Game
import shared_module.message_templates.linebot_game_message as linebot_game_message
from shared_module.notify.discord_notify import DiscordNotifyHelper
from shared_module.announcement.linebot import LineBotAnnouncementHelper
from shared_module.message_templates.line_notify_message import (
    generate_error_message,
    generate_schedule_message_for_team,
)
import shared_module.attendance_analyzer as attendance_analyzer
import shared_module.message_templates.linebot_attendance_message as linebot_attendance_message

from envs import (
    game_crawl_api
)
import message_templates

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

@app.route("/run-future-game-announcement", methods=['POST'])
def run_future_game_announcement():
    games_crawler_client = CrawlerClient(game_crawl_api)    
    games = games_crawler_client.get_games()

    try:
        game_list = [Game.from_dict(data) for data in games]
        message = generate_schedule_message_for_team(game_list)
        announce(message)        
        notify_successful_log(message_templates.run_future_game_announcement_successful)
    except Exception as e:
        message = generate_error_message()
        notify_alarm_log(message_templates.run_future_game_announcement.format(result=repr(e)))

    return ""

@app.route("/run-game-attendance-count", methods=['POST'])
def run_game_attendance_count():    
    try:
        games = Game.search_for_invited()
        for game in games:
            mapping = attendance_analyzer.get_attendance_of_game(game.id)
            message = linebot_attendance_message.produce_attendance_message_text(game, mapping)
            notify_management_message(message)
        notify_successful_log(message_templates.run_game_attendance_count_successful)

    except Exception as e:
        message = generate_error_message()
        notify_alarm_log(message_templates.run_game_attendance_count.format(result=repr(e)))

    return ""



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

