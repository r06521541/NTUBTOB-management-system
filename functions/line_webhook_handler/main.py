
import functions_framework

from linebot.v3.exceptions import (
    InvalidSignatureError,
)
from shared_module.notify.discord_notify import DiscordNotifyHelper

import webhook

discord_notify_helper = DiscordNotifyHelper()

@functions_framework.http
def main(request):
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)

    # handle webhook body
    try:
        webhook.handle_event(body, signature)
    except InvalidSignatureError:
        discord_notify_helper.notify_alarm_log("Invalid signature. Please check your channel access token/channel secret.")

    return 'OK'