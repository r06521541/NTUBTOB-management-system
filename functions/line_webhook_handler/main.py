
import functions_framework
from flask import g
from datetime import datetime, timedelta, timezone
import threading
import requests
from urllib.parse import urlparse, parse_qs
import time

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
from shared_module.models.game_attendance_replies import GameAttendanceReply
from shared_module.linebot_game_message import (
    produce_invitation_messages_by_games,
    produce_message_of_game_query_attendance
)
import shared_module.line_notify as line_notify
from shared_module.general_message import (
    reply_text_mapping
)
import shared_module.attendance_analyzer as attendance_analyzer
import shared_module.linebot_attendance_message as linebot_attendance_message

from envs import (
    channel_access_token,
    channel_secret
)
import message_templates_user
import message_templates_management



configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

line_user_info_api = 'https://api.line.me/v2/bot/profile/'



@functions_framework.http
def main(request):
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)

    # handle webhook body
    try:
        handle_event(body, signature)
    except InvalidSignatureError:
        line_notify.notify_alarm_log("Invalid signature. Please check your channel access token/channel secret.")

    return 'OK'

def handle_event(body: str, signature: str):
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)
    
    g.line_bot_api = line_bot_api
    g.messages_to_reply = [] # list[Message]
    try:
        handler.handle(body, signature)
    except ApiException as e:
        line_notify.notify_alarm_log(f"Exception: {e.status_code} - {e.message}")

@handler.default()
def handle_event_default(event: Event):
    if hasattr(event, 'reply_token'):
        g.reply_token = event.reply_token

    g.user_id = event.source.user_id
    g.user = LineUser.search_by_id(g.user_id)
    if not g.user and not isinstance(event, FollowEvent):
        welcome()

    if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
        # 相當於@handler.add(MessageEvent, message=TextMessageContent)
        handle_text_message(event)
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
    return user.member.name if user.member else None

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
            app.logger.info(f"Exception when calling MessagingApi->reply_message: {e}\n")

def add_message_to_reply(message: Message):
    g.messages_to_reply.append(message)

def add_messages_to_reply(messages: list[Message]):
    g.messages_to_reply.extend(messages)
    
def add_text_message_to_reply(text):
    g.messages_to_reply.append(TextMessage(text=text))

def handle_follow(event: FollowEvent):
    welcome()

def welcome():
    if g.user:
        nickname = get_user_nickname(g.user_id)
        real_name = get_user_name(g.user)
        add_text_message_to_reply(message_templates_user.welcome_back.format(name=real_name))
        line_notify.notify_management_message(message_templates_management.member_come_back.format(nickname=nickname, note=get_user_note(real_name, nickname)))
        
        invitation_messages = produce_invitation_messages()
        if (invitation_messages):
            add_messages_to_reply(invitation_messages)
    else:
        add_text_message_to_reply(message_templates_user.welcome)
        nickname = get_user_nickname(g.user_id)
        g.user = LineUser(nickname, g.user_id)
        LineUser.add(g.user)
        line_notify.notify_management_message(message_templates_management.new_user.format(nickname=nickname))

def handle_unfollow(event: UnfollowEvent):
    for i in range(3):
        try:
            user = g.user
            nickname = user.nickname if user else None
            real_name = get_user_name(user)
            line_notify.notify_management_message(message_templates_management.user_left.format(nickname=nickname, note=get_user_note(real_name, nickname)))
            return
        except Exception as e:
            app.logger.info(f"Exception when handling unfollow event: {e}\n")

def handle_text_message(event: MessageEvent):
    user = g.user
    message_text = event.message.text
    if not user.has_replied:
        user.mark_as_first_replied()
        welcome_after_first_message()
    elif message_text == '邀請':
        invitation_messages = produce_invitation_messages()
        if (invitation_messages):
            add_text_message_to_reply(message_templates_user.welcome_inviting_game)
            add_messages_to_reply(invitation_messages)
        else:
            add_text_message_to_reply(message_templates_user.welcome_no_inviting_game)
    elif message_text == '回來':
        name = get_user_name(user)
        name = name if name else user.nickname
        add_text_message_to_reply(message_templates_user.welcome_back.format(name=name))
    elif message_text == '加入':
        add_text_message_to_reply(message_templates_user.welcome)

def welcome_after_first_message():
    add_text_message_to_reply(message_templates_user.welcome_after_first_message)
    invitation_messages = produce_invitation_messages()
    if (invitation_messages):
        add_messages_to_reply(invitation_messages)
        add_text_message_to_reply(message_templates_user.welcome_inviting_game)
    else:
        add_text_message_to_reply(message_templates_user.welcome_no_inviting_game)

def produce_invitation_messages() -> list[FlexMessage]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=10)
    games = Game.search_for_invited(now, end)
    if games:
        messages = produce_invitation_messages_by_games(games)
        return messages
    return []

def handle_postback(event: PostbackEvent):
    parsed_url = urlparse(event.postback.data)
    path = parsed_url.path
    if path == 'reply-game-attendance' or path == 'reply_game_attendance':
        handle_postback_reply_game_attendance(parsed_url.query)

    if path == 'query-attendance-of-game' or path == 'query_attendance_of_game':
        handle_postback_query_attendance_of_game(parsed_url.query)

def handle_postback_reply_game_attendance(query: str):
    member_id = g.user.member_id

    if not g.user.has_replied:
        add_text_message_to_reply(message_templates_user.has_not_replied_yet)
        return
    if not member_id:
        add_text_message_to_reply(message_templates_user.not_authenticated)
        return

    query_params = parse_qs(query)
    game_id = int(query_params.get('id', [-1])[0])
    reply = int(query_params.get('reply', [-1])[0])
    
    game = Game.search_by_id(game_id)
    game_verbal_summary = game.generate_verbal_summary_for_team()

    if game.start_datetime < datetime.now(timezone.utc):
        add_text_message_to_reply(message_templates_user.game_already_past.format(game_verbal_summary=game_verbal_summary))
        return
    if game.cancellation_time:
        add_text_message_to_reply(message_templates_user.game_already_cancelled.format(game_verbal_summary=game_verbal_summary))
        return
    
    is_new_member = len(GameAttendanceReply.search_by_member_id(member_id)) == 0

    is_different_reply = True
    old_replies = GameAttendanceReply.search_single_game_reply_of_member(game_id, member_id)
    if old_replies:
        if old_replies[-1].reply == reply:
            is_different_reply = False
    
    if is_different_reply:
        GameAttendanceReply.add(GameAttendanceReply(game_id, g.user.id, member_id, reply))
        add_text_message_to_reply(message_templates_user.game_reply.format(game_verbal_summary=game_verbal_summary, reply=reply_text_mapping[reply]))
    else:
        add_text_message_to_reply(message_templates_user.game_same_reply.format(game_verbal_summary=game_verbal_summary))

    if is_new_member:
        add_text_message_to_reply(message_templates_user.first_game_reply_hint)
    if not old_replies:
        add_message_to_reply(produce_message_of_game_query_attendance(game))

def handle_postback_query_attendance_of_game(query: str):    
    query_params = parse_qs(query)
    game_id = int(query_params.get('id', [-1])[0])
    game = Game.search_by_id(game_id)
    game_verbal_summary = game.generate_verbal_summary_for_team()

    if game.start_datetime < datetime.now(timezone.utc):
        add_text_message_to_reply(message_templates_user.game_already_past.format(game_verbal_summary=game_verbal_summary))
        return
    if game.cancellation_time:
        add_text_message_to_reply(message_templates_user.game_already_cancelled.format(game_verbal_summary=game_verbal_summary))
        return
    
    mapping = attendance_analyzer.get_attendance_of_game(game_id)
    message = linebot_attendance_message.produce_attendance_message(game, mapping)
    add_message_to_reply(message)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

