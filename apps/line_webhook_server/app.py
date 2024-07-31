from flask import Flask, request, abort, g
from datetime import datetime, timedelta, timezone
import threading
import requests

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError,
)
from linebot.v3.messaging.models.message import Message
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    PushMessageRequest,
    ApiException
)
from linebot.v3.webhooks import (
    Event,
    FollowEvent,
    UnfollowEvent,
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)

from shared_module.line_users import LineUser
from shared_module.games import Game
from shared_module.linebot_message import (
    produce_invitation_messages_by_games,
)

from envs import (
    channel_access_token,
    channel_secret
)
import general_message


app = Flask(__name__)

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

line_user_info_api = 'https://api.line.me/v2/bot/profile/'

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
        g.messages_to_reply = [] # list[Message]
        try:
            handler.handle(body, signature)
        except ApiException as e:
            app.logger.error(f"Exception: {e.status_code} - {e.message}")

@handler.default()
def handle_event_default(event: Event):
    if hasattr(event, 'reply_token'):
        g.reply_token = event.reply_token
    g.user_id = event.source.user_id

    if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
        # 相當於@handler.add(MessageEvent, message=TextMessageContent)
        handle_message(event)
    elif isinstance(event, PostbackEvent):
        # 相當於@handler.add(PostbackEvent)
        handle_postback(event)
    elif isinstance(event, FollowEvent):
        # 相當於@handler.add(FollowEvent)
        handle_follow(event)
    elif isinstance(event, UnfollowEvent):
        # 相當於@handler.add(UnfollowEvent)
        handle_unfollow(event)
    # 還可以在這添加對其他事件類型的處理

    reply_messages()

def get_user_nickname(user_id: str):
    headers = {"Authorization": "Bearer " + channel_access_token}
    user_info = requests.get(line_user_info_api + user_id, headers=headers).json()
    return user_info['displayName']

def reply_messages():
    if len(g.messages_to_reply) > 0:
        try:
            g.line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=g.reply_token,
                    messages=g.messages_to_reply
                )
            )
        except ApiException as e:
            print(f"Exception when calling MessagingApi->reply_message: {e}\n")

def add_message_to_reply(message: Message):
    g.messages_to_reply.append(message)

def add_messages_to_reply(messages: list[Message]):
    g.messages_to_reply.extend(messages)
    
def add_text_message_to_reply(text):
    g.messages_to_reply.append(TextMessage(text=text))

def handle_follow(event: FollowEvent):
    user = LineUser.search_by_id(g.user_id)
    if user:
        add_text_message_to_reply(general_message.welcome_back_message.format(name=user.nickname))
    else:
        add_text_message_to_reply(general_message.welcome_message)
        LineUser.add_user(LineUser(get_user_nickname(g.user_id), g.user_id))

    invitation_messages = produce_invitation_messages()
    if (invitation_messages):
        add_text_message_to_reply(general_message.welcome_inviting_game_message)
        add_messages_to_reply(invitation_messages)
    else:
        add_text_message_to_reply(general_message.welcome_no_inviting_game_message)

def handle_unfollow(event: UnfollowEvent):
    user = LineUser.search_by_id(event.source.user_id)
    print(f'Line user {user.nickname} unfollowed.')

def handle_message(event: MessageEvent):
    message_text = event.message.text
    if message_text == '邀請':
        add_messages_to_reply(produce_invitation_messages())
    elif message_text == '加入':
        add_text_message_to_reply(general_message.welcome_message)
    else:
        add_text_message_to_reply(message_text)

def produce_invitation_messages() -> list[FlexMessage]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=10)
    games = Game.search_for_invited(now, end)
    if games:
        messages = produce_invitation_messages_by_games(games)
        return messages
    return []

def handle_postback(event: PostbackEvent):
    postback_data = event.postback.data

    print(event.postback)
    print(event.source.user_id)
    reply_text_msg = f"Received postback data: {postback_data}"
    add_text_message_to_reply(reply_text_msg)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

