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

from shared_module.models.line_users import LineUser
from shared_module.models.games import Game
from shared_module.models.members import Member
from shared_module.linebot_message import (
    produce_invitation_messages_by_games,
)
import shared_module.line_notify as line_notify

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

def get_user_nickname(user_id: str) -> str:
    headers = {"Authorization": "Bearer " + channel_access_token}
    user_info = requests.get(line_user_info_api + user_id, headers=headers).json()
    return user_info['displayName']

def get_user_name(user: LineUser) -> str:
    return get_member_name(user.member_id) if user else None

def get_member_name(member_id: int) -> str:
    member = Member.search_by_id(member_id)
    return '' if member == None else member.name

def get_user_note(real_name: str, nickname: str) -> str:
    return '身分尚不明' if not real_name else '此為本名' if nickname == real_name else f'本名為{real_name}'

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
        nickname = get_user_nickname(event.source.user_id)
        real_name = get_user_name(user)
        add_text_message_to_reply(general_message.welcome_back_message.format(name=get_user_name(user)))
        line_notify.notify_management_message(f'{nickname}（{get_user_note(real_name, nickname)}）已重返追蹤')
    else:
        add_text_message_to_reply(general_message.welcome_message)
        nickname = get_user_nickname(g.user_id)
        LineUser.add(LineUser(nickname, g.user_id))
        line_notify.notify_management_message(f'{nickname}已加入！')

    invitation_messages = produce_invitation_messages()
    if (invitation_messages):
        add_text_message_to_reply(general_message.welcome_inviting_game_message)
        add_messages_to_reply(invitation_messages)
    else:
        add_text_message_to_reply(general_message.welcome_no_inviting_game_message)

def handle_unfollow(event: UnfollowEvent):
    user = LineUser.search_by_id(event.source.user_id)
    nickname = user.nickname if user else None
    real_name = get_user_name(user)
    line_notify.notify_management_message(f'{nickname}（{get_user_note(real_name, nickname)}）已退追蹤')

def handle_message(event: MessageEvent):
    message_text = event.message.text
    if message_text == '邀請':
        add_messages_to_reply(produce_invitation_messages())
    elif message_text == '回來':
        user = LineUser.search_by_id(g.user_id)
        name = get_member_name(user.member_id) if user.member_id else None
        name = name if name else user.nickname
        add_text_message_to_reply(general_message.welcome_back_message.format(name=name))
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

