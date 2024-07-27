import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Any


from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from .games import Game
from .settings import (
    current_team, local_timezone
)
from .general_message import (
    weekday_mapping,
    offseason_game_sign,
    normal_game_sign,
    reply_text_mapping
)

# announce cancellation
def produce_cancellation_messages(games: list[Game]):
    sorted_games = sorted(games, key=lambda x: x.start_datetime)
    
    message_text = '通知一下！這些比賽已經沒有出現在賽程表上，可能是賽程有調整。有任何疑問請跟幹部聯絡！\n'
    for game in sorted_games:
        message_text += '\n'
        message_text += game.generate_game_summary(current_team)

    return [{
            "type": "text",
            "text": message_text
        }]


# invite
def produce_invite_messages(games: list[Game], is_broadcasting=False) -> str:
    sorted_games = sorted(games, key=lambda x: x.start_datetime)
    games_in_days = defaultdict(list)
    for game in sorted_games:
        game_datetime = game.start_datetime.astimezone(local_timezone)
        game_date = game_datetime.date()
        games_in_days[game_date].append(game)

    messages = []
    if is_broadcasting:
        messages.append(_produce_intro_message())
    for date, games_in_a_day in games_in_days.items():
        messages.append(_produce_game_message(games_in_a_day))

    return messages

def _produce_intro_message() -> TextMessage:
    reply_text = "熱騰騰的比賽消息來啦！麻煩回覆一下出席狀況唷～"
    return TextMessage(text=reply_text)

def _produce_game_message(games_in_a_day: list[Game]) -> FlexMessage:
    first_game = games_in_a_day[0]
    first_game_datetime = first_game.start_datetime.astimezone(local_timezone)
    
    # 獲取星期的中文表示
    chinese_weekday = weekday_mapping[first_game_datetime.strftime('%A')]    
    # 格式化日期和時間
    date = first_game_datetime.strftime("%-m/%-d（%a）").replace(first_game_datetime.strftime('%a'), chinese_weekday)

    opponent = first_game.away_team if first_game.home_team == current_team else first_game.home_team
    location = first_game.location

    hint = f"{date}在{location}有對上{opponent}的比賽！點開訊息回覆出席狀況吧！"
    if len(games_in_a_day) > 1:
        hint = f"{date}在{location}有雙重賽！點開訊息回覆出席狀況吧！"
    
    bubbles = [_produce_game_bubble(game) for game in games_in_a_day]
    
    contents = {
      "type": "carousel",
      "contents": bubbles,
    }
    contents_string =str(contents).replace('\'', '"')
    return FlexMessage(alt_text=hint, contents=FlexContainer.from_json(contents_string))

def _produce_game_bubble(game: Game) -> dict[str, Any]:
    game_datetime = game.start_datetime.astimezone(local_timezone)
    
    # 獲取星期的中文表示
    chinese_weekday = weekday_mapping[game_datetime.strftime('%A')]    
    # 格式化日期和時間
    date = game_datetime.strftime("%-m/%-d")
    date_with_weekday = game_datetime.strftime("%-m/%-d（%a）").replace(game_datetime.strftime('%a'), chinese_weekday)
    
    opponent = game.away_team if game.home_team == current_team else game.home_team
    begin_time = game_datetime.strftime("%H%M")
    end_time = (game_datetime + timedelta(minutes=game.duration)).strftime("%H%M")
    location = game.location
    home_or_away = '先攻（一壘側）' if game.home_team == current_team else '先守（三壘側）'
    is_postseason = game.season == 3
    postseason_text = '季後賽 - ' if is_postseason else ''
    reminder = '身分證要記得帶！' if is_postseason else '無'

    fake_api = "https://linecorp.com"
    attend_api = fake_api
    not_attend_api = fake_api
    arrive_late_api = fake_api
    leave_early_api = fake_api
    undecided_api = fake_api

    header_text = f"{postseason_text}{date} vs {opponent}"
    time_text = f"{date_with_weekday} {begin_time} - {end_time}"

    # 將資訊轉換為目標格式的 JSON 物件
    bubble = {
      "type": "bubble",
      "body": {
        "type": "box",
        "layout": "vertical",
        "contents": [
          {
            "type": "text",
            "text": header_text,
            "weight": "bold",
            "size": "md",
            "margin": "sm",
            "align": "center"
          },
          {
            "type": "box",
            "layout": "vertical",
            "margin": "sm",
            "spacing": "none",
            "contents": [
              {
                "type": "box",
                "layout": "horizontal",
                "spacing": "none",
                "contents": [
                  {
                    "type": "text",
                    "text": "時間",
                    "color": "#aaaaaa",
                    "size": "sm",
                    "decoration": "underline",
                    "offsetBottom": "none",
                    "gravity": "center",
                    "flex": 1,
                    "margin": "sm"
                  },
                  {
                    "type": "text",
                    "text": time_text,
                    "color": "#666666",
                    "size": "sm",
                    "flex": 5,
                    "margin": "sm"
                  }
                ],
                "margin": "none"
              },
              {
                "type": "box",
                "layout": "horizontal",
                "spacing": "none",
                "contents": [
                  {
                    "type": "text",
                    "text": "球場",
                    "color": "#aaaaaa",
                    "size": "sm",
                    "decoration": "underline",
                    "offsetBottom": "none",
                    "gravity": "center",
                    "flex": 1,
                    "margin": "sm"
                  },
                  {
                    "type": "text",
                    "text": location,
                    "color": "#666666",
                    "size": "sm",
                    "flex": 5,
                    "margin": "sm"
                  }
                ],
                "margin": "xs"
              },
              {
                "type": "box",
                "layout": "horizontal",
                "spacing": "none",
                "contents": [
                  {
                    "type": "text",
                    "text": "攻守",
                    "color": "#aaaaaa",
                    "size": "sm",
                    "flex": 1,
                    "decoration": "underline",
                    "offsetBottom": "none",
                    "gravity": "center",
                    "margin": "sm"
                  },
                  {
                    "type": "text",
                    "text": home_or_away,
                    "color": "#666666",
                    "size": "sm",
                    "flex": 5,
                    "margin": "sm"
                  }
                ],
                "margin": "xs"
              },
              {
                "type": "box",
                "layout": "horizontal",
                "spacing": "none",
                "contents": [
                  {
                    "type": "text",
                    "text": "備註",
                    "color": "#aaaaaa",
                    "size": "sm",
                    "flex": 1,
                    "decoration": "underline",
                    "offsetBottom": "none",
                    "gravity": "top",
                    "margin": "sm"
                  },
                  {
                    "type": "text",
                    "text": reminder,
                    "color": "#666666",
                    "size": "sm",
                    "flex": 5,
                    "margin": "sm"
                  }
                ],
                "margin": "xs"
              }
            ]
          },
          {
            "type": "box",
            "layout": "vertical",
            "spacing": "none",
            "contents": [
              {
                "type": "text",
                "text": "如期來參賽嗎？",
                "color": "#666666",
                "size": "sm"
              },
              {
                "type": "box",
                "layout": "horizontal",
                "spacing": "none",
                "contents": [
                  {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "action": {
                      "type": "postback",
                      "label": reply_text_mapping[1],
                      "data": f"reply_game_attendance?id={game.id}&reply={1}",
                      "displayText": f"{time_text} {reply_text_mapping[1]}"
                    }
                  },
                  {
                    "type": "button",
                    "style": "secondary",
                    "action": {
                      "type": "postback",
                      "label": reply_text_mapping[2],
                      "data": f"reply_game_attendance?id={game.id}&reply={2}",
                      "displayText": f"{time_text} {reply_text_mapping[2]}"
                    },
                    "height": "sm",
                    "margin": "sm"
                  }
                ],
                "margin": "md"
              },
              {
                "type": "button",
                "action": {
                  "type": "postback",
                  "label": reply_text_mapping[5],
                  "data": f"reply_game_attendance?id={game.id}&reply={5}",
                  "displayText": f"{time_text} {reply_text_mapping[5]}"
                },
                "height": "sm",
                "style": "link"
              },
              {
                "type": "text",
                "text": "或是確定能參加，但...",
                "color": "#666666",
                "size": "sm",
                "margin": "lg"
              },
              {
                "type": "box",
                "layout": "horizontal",
                "spacing": "none",
                "contents": [
                  {
                    "type": "button",
                    "height": "sm",
                    "action": {
                      "type": "postback",
                      "label": reply_text_mapping[3],
                      "data": f"reply_game_attendance?id={game.id}&reply={3}",
                      "displayText": f"{time_text} {reply_text_mapping[3]}"
                    },
                    "style": "link"
                  },
                  {
                    "type": "button",
                    "height": "sm",
                    "action": {
                      "type": "postback",
                      "label": reply_text_mapping[4],
                      "data": f"reply_game_attendance?id={game.id}&reply={4}",
                      "displayText": f"{time_text} {reply_text_mapping[4]}"
                    },
                    "style": "link"
                  }
                ],
                "flex": 0,
              }
            ],
            "margin": "md"
          }
        ],
        "margin": "none",
        "spacing": "none"
      },
      "size": "deca"
    }

    return bubble
