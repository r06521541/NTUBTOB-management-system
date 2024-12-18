import logging
from flask import Flask, abort, jsonify
from time import sleep
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

from shared_module.models.games import Game
from shared_module.linebot_game_message import (
    produce_invitation_messages_by_games,
    produce_cancellation_message_by_games,
)
import shared_module.line_notify as line_notify
import shared_module.linebot_config as linebot_config
from shared_module.settings import (
    local_timezone
)

from envs import (
    channel_access_token,
    channel_secret
)
import message_templates_notify_user
import message_templates_user
import message_templates_management
import game_reminder

# 設置日誌記錄器
logging.basicConfig(level=logging.INFO)

now = datetime.now(local_timezone)
today_begin = datetime.combine(now, time.min, tzinfo=local_timezone)
ten_days_later = today_begin + timedelta(days=11)

app = Flask(__name__)

configuration = Configuration(access_token=channel_access_token)


@app.route("/invitation-announcement/trigger", methods=['POST'])
def invite():
    is_successful = False
    games = Game.search_for_invitation(now, ten_days_later)
    old_games = Game.search_for_invited()
    if games:
        messages = produce_new_invitation_messages(games)
        is_successful = False
        try:
            if broadcast(messages):
                mark_games_as_invited(games)
                line_notify.notify_successful_log(message_templates_management.invited.format(count=len(games)))
                is_successful = True
        except Exception as e:
            logging.error("Error during invite broadcast: %s", e, exc_info=True)
            line_notify.notify_alarm_log(f"{message_templates_management.invite_failed}: {e}")
            return jsonify({"error": "Failed to broadcast invite"}), 500
        
        if is_successful:
            line_notify.notify_announcement(message_templates_notify_user.new_and_old_invitation_notification if old_games else message_templates_notify_user.invitation_notification)
            line_notify.notify_announcement(linebot_config.add_friend_link)
    else:
        if old_games:
            pass
            # message = message_templates_notify_user.no_new_invitation_but_has_old_notification
            # messages = [TextMessage(text=message)]
            # broadcast(messages)
            # line_notify.notify_announcement(message)
            # line_notify.notify_announcement(linebot_config.add_friend_link)

    if is_successful:
        line_notify.notify_successful_log(message_templates_management.invite_finish)
    return 'OK'

def produce_new_invitation_messages(games: list[Game]) -> list[FlexMessage]:
    if games:
        messages = [TextMessage(text=message_templates_user.invitation_intro)]
        messages.extend(produce_invitation_messages_by_games(games))
        return messages
    return []

def broadcast(messages: list[Message]) -> bool:
    with ApiClient(configuration) as api_client:
        # Create an instance of the API class
        api_instance = MessagingApi(api_client)
        broadcast_request = BroadcastRequest(messages=messages) # BroadcastRequest | 
        x_line_retry_key = str(uuid.uuid4()) # str | Retry key. Specifies the UUID in hexadecimal format (e.g., `123e4567-e89b-12d3-a456-426614174000`) generated by any method. The retry key isn't generated by LINE. Each developer must generate their own retry key.  (optional)
        reason = ''
        for i in range(3):
            try:
                api_response = api_instance.broadcast_with_http_info(broadcast_request, x_line_retry_key=x_line_retry_key)
                status_code = api_response.status_code
                if status_code == 500:
                    print(api_response.raw_data)
                    line_notify.notify_alarm_log(f"broadcast failed - status_code={status_code}, reason=\n{api_response.raw_data}")
                else:
                    return True
            except Exception as e:
                reason = "Exception when calling MessagingApi->broadcast: %s\n" % e
            sleep(5)
        
        line_notify.notify_alarm_log(f"broadcast failed - reason=\n{reason}")
        return False

def mark_games_as_invited(games: list[Game]):
    for game in games:
        Game.update_invitation_time(game.id, now)

@app.route("/cancellation-announcement/trigger", methods=['POST'])
def announce_cancellation():
    games = Game.search_cancelled_to_announce(now, ten_days_later)
    if games:
        messages = [produce_cancellation_message_by_games(games)]
        try:
            broadcast(messages)
            mark_games_as_cancellation_announced(games)
            line_notify.notify_successful_log(message_templates_management.cancellation_announced.format(count=len(games)))
        except Exception as e:
            logging.error("Error during cancellation announcement broadcast: %s", e, exc_info=True)
            line_notify.notify_alarm_log(f"{message_templates_management.cancellation_announce_failed}: {e}")
            return jsonify({"error": "Failed to broadcast cancellation announcement"}), 500
    line_notify.notify_successful_log(message_templates_management.announce_cancellation_finish)
    return 'OK'


def mark_games_as_cancellation_announced(games: list[Game]):
    for game in games:
        Game.update_cancellation_announcement_time(game.id, now)

@app.route("/game-reminder/trigger", methods=['POST'])
def announce_game_reminder():
    text = game_reminder.get_game_reminder_string(1)
    if text:
        messages = [TextMessage(text=text)]
        try:
            broadcast(messages)
        except Exception as e:
            logging.error("Error during game reminder broadcast: %s", e, exc_info=True)
            line_notify.notify_alarm_log(f"{message_templates_management.game_reminder_failed}: {e}")
            return jsonify({"error": "Failed to broadcast game reminder"}), 500
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

