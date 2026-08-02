from flask import g
from datetime import datetime, timedelta, timezone
import requests
from urllib.parse import urlparse, parse_qs

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.messaging.models.message import Message
from linebot.v3.messaging import (
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
    StickerMessageContent,
    PostbackEvent
)

from shared_module.models.line_users import LineUser
from shared_module.models.games import Game
from shared_module.models.line_groups import LineGroup
from shared_module.models.game_attendance_replies import GameAttendanceReply
from shared_module.message_templates.linebot_game_message import (
    produce_invitation_messages_by_games,
    produce_message_of_game_query_attendance
)
from shared_module.notify.discord_notify import DiscordNotifyHelper
from shared_module.message_templates.general_message import (
    reply_text_mapping
)
import shared_module.attendance_analyzer as attendance_analyzer
import shared_module.message_templates.linebot_attendance_message as linebot_attendance_message
import shared_module.web_cache as web_cache
import shared_module.line_messaging_api as line_messaging_api

from envs import (
    channel_access_token,
    channel_secret
)
import message_templates_user
import message_templates_group
import message_templates_management



handler = WebhookHandler(channel_secret)

line_user_info_api = 'https://api.line.me/v2/bot/profile/'


discord_notify_helper = DiscordNotifyHelper()

def notify_successful_log(message: str):
    discord_notify_helper.notify_successful_log(message)
def notify_alarm_log(message: str):
    discord_notify_helper.notify_alarm_log(message)
def notify_management_message(message: str):
    discord_notify_helper.notify_management_message(message)

def handle_event(body: str, signature: str):
    g.messages_to_reply = [] # list[Message]
    try:
        handler.handle(body, signature)
    except ApiException as e:
        notify_alarm_log(f"Exception: {e.status_code} - {e.message}")

@handler.default()
def handle_event_default(event: Event):
    if hasattr(event, 'reply_token'):
        reply_token = event.reply_token

    g.group_id = None
    if hasattr(event.source, 'group_id'):
        g.group_id = event.source.group_id
    if hasattr(event.source, 'user_id'):
        g.user_id = event.source.user_id
        g.user = LineUser.search_by_id(g.user_id)
        if not g.user and not isinstance(event, FollowEvent):
            welcome()

    if isinstance(event, MessageEvent):
        # 相當於@handler.add(MessageEvent, message=TextMessageContent)
        if isinstance(event.message, TextMessageContent):
            handle_text_message(event)
        elif isinstance(event.message, StickerMessageContent):
            handle_sticker_message(event)

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

    if reply_token and len(g.messages_to_reply) > 0:
        line_messaging_api.reply(reply_token, g.messages_to_reply)

def get_user_nickname(user_id: str) -> str:
    headers = {"Authorization": "Bearer " + channel_access_token}
    user_info = requests.get(line_user_info_api + user_id, headers=headers).json()
    return user_info['displayName']

def get_user_name(user: LineUser) -> str:
    return user.member.name if user.member else None

def get_user_note(real_name: str, nickname: str) -> str:
    return '身分尚不明' if not real_name else '此為本名' if nickname == real_name else f'本名為{real_name}'

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
        notify_management_message(message_templates_management.member_come_back.format(nickname=nickname, note=get_user_note(real_name, nickname)))
        
        invitation_messages = produce_invitation_messages()
        if (invitation_messages):
            add_messages_to_reply(invitation_messages)
    else:
        add_text_message_to_reply(message_templates_user.welcome)
        nickname = get_user_nickname(g.user_id)
        g.user = LineUser(nickname, g.user_id)
        LineUser.add(g.user)
        notify_management_message(message_templates_management.new_user.format(nickname=nickname))

def handle_unfollow(event: UnfollowEvent):
    for i in range(3):
        try:
            user = g.user
            nickname = user.nickname if user else None
            real_name = get_user_name(user)
            notify_management_message(message_templates_management.user_left.format(nickname=nickname, note=get_user_note(real_name, nickname)))
            return
        except Exception as e:
            notify_alarm_log(f"Exception when handling unfollow event: {e}\n")

def handle_sticker_message(event: MessageEvent):
    user = g.user
    
    if not g.group_id:
        if not user.has_replied:
            user.mark_as_first_replied()
            welcome_after_first_message()

def handle_text_message(event: MessageEvent):
    user = g.user
    message_text = event.message.text

    if g.group_id:
        if message_text == '機器人啟動':
            LineGroup.enable_broadcast_for_group(g.group_id)
            add_text_message_to_reply(message_templates_group.group_added)
    else:        
        if not user.has_replied:
            user.mark_as_first_replied()
            welcome_after_first_message()
        elif message_text == '邀請':
            invitation_messages = produce_invitation_messages()
            if (invitation_messages):
                add_messages_to_reply(invitation_messages)

        elif message_text == '回來':
            name = get_user_name(user)
            name = name if name else user.nickname
            add_text_message_to_reply(message_templates_user.welcome_back.format(name=name))
            
        elif message_text == '加入':
            add_text_message_to_reply(message_templates_user.welcome)
        elif message_text == '網址':
            add_text_message_to_reply(message_templates_management.web_portal_url)

def welcome_after_first_message():
    add_text_message_to_reply(message_templates_user.welcome_after_first_message)
    invitation_messages = produce_invitation_messages()
    if (invitation_messages):
        add_messages_to_reply(invitation_messages)
        add_text_message_to_reply(message_templates_user.welcome_inviting_game)
    else:
        add_text_message_to_reply(message_templates_user.welcome_no_inviting_game)

def produce_invitation_messages() -> list[FlexMessage]:
    games = Game.search_for_invited()
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
        web_cache.clear_cache_of_attendance_page()
        if datetime.now(timezone.utc) > game.start_datetime - timedelta(0, 0, 0, 0, 0, 12):
            notify_management_message(message_templates_management.member_rush_reply_attendance.format(game_short_summary=game_verbal_summary, member=get_user_name(g.user), reply=reply_text_mapping[reply]))
    else:
        add_text_message_to_reply(message_templates_user.game_same_reply.format(game_verbal_summary=game_verbal_summary))

    if is_new_member:
        add_text_message_to_reply(message_templates_user.first_game_reply_hint)

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



