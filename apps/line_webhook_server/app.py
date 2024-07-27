from flask import Flask, request, abort, g
from datetime import datetime, timedelta, timezone
import threading

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    PushMessageRequest,
    ApiException
)
from linebot.v3.webhooks import (
    Event,
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)

from shared_module.games import Game
from shared_module.linebot_message import (
    produce_invite_messages,
)

from envs import (
    channel_access_token,
    channel_secret
)
import general_message


app = Flask(__name__)

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        threading.Thread(target=handle_event, args=(body, signature)).start()
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

def handle_event(body: str, signature: str):
    with app.app_context():
        # 這裡是新執行緒，在這裡初始化下兩者，就能確保他們都是獨立的
        api_client = ApiClient(configuration)
        line_bot_api = MessagingApi(api_client)
        
        g.line_bot_api = line_bot_api
        try:
            handler.handle(body, signature)
        except ApiException as e:
            app.logger.error(f"Exception: {e.status_code} - {e.message}")

@handler.default()
def handle_event_default(event: Event):
    print('handle_event_default')
    if hasattr(event, 'reply_token'):
        g.reply_token = event.reply_token
        print(g.reply_token)
    g.user_id = event.source.user_id

    if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
        # 相當於@handler.add(MessageEvent, message=TextMessageContent)
        handle_message(event)
    elif isinstance(event, PostbackEvent):
        # 相當於@handler.add(PostbackEvent)
        handle_postback(event)
    # 還可以在這添加對其他事件類型的處理


def handle_message(event: MessageEvent):
    message_text = event.message.text
    if message_text == '邀請':
        reply_invitation()
    elif message_text == '加入':
        reply_text(general_message.welcome_message)
    else:
        reply_text(message_text)

def reply_text(text):
    try:
        g.line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=g.reply_token,
                messages=[TextMessage(text=text)]
            )
        )
    except ApiException as e:
        print(f"Exception when calling MessagingApi->reply_message: {e}\n")

def reply_invitation():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=10)
    games = Game.search_for_invitation(now, end)
    messages = produce_invite_messages(games)
    try:
        g.line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=g.reply_token,
                messages=messages
            )
        )
    except ApiException as e:
        print(f"Exception when calling MessagingApi->reply_message: {e}\n")

def handle_postback(event: PostbackEvent):
    postback_data = event.postback.data

    print(event.postback)
    print(event.source.user_id)
    reply_text_msg = f"Received postback data: {postback_data}"
    reply_text(reply_text_msg)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

