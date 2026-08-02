from flask import Flask, request
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError,
)
from shared_module.notify.discord_notify import DiscordNotifyHelper

from envs import (
    channel_access_token,
    channel_secret
)
import webhook


app = Flask(__name__)

handler = WebhookHandler(channel_secret)

line_user_info_api = 'https://api.line.me/v2/bot/profile/'


discord_notify_helper = DiscordNotifyHelper()

def notify_alarm_log(message: str):
    discord_notify_helper.notify_alarm_log(message)

@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)

    # handle webhook body
    try:
        webhook.handle_event(body, signature)
    except InvalidSignatureError:
        notify_alarm_log("Invalid signature. Please check your channel access token/channel secret.")

    return 'OK'


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)