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

from .models.games import Game
from .settings import (
    current_team, local_timezone
)
from .general_message import (
    cancellation_announcement_opening,
    weekday_mapping,
    offseason_game_sign,
    normal_game_sign,
    reply_text_mapping,
    offseason_game_reminder,
    game_reminder
)

# announce cancellation
def produce_cancellation_messages_by_games(games: list[Game]) -> TextMessage:
    if not games:
        return None
    sorted_games = sorted(games, key=lambda x: x.start_datetime)
    
    message_text = cancellation_announcement_opening
    for game in sorted_games:
        message_text += '\n'
        message_text += game.generate_game_summary(current_team)

    return TextMessage(text=message_text)

# invite
def produce_invitation_messages_by_games(games: list[Game]) -> list[FlexMessage]:
    if not games:
        return []
    
    sorted_games = sorted(games, key=lambda x: x.start_datetime)
    games_in_days = defaultdict(list)
    for game in sorted_games:
        game_datetime = game.start_datetime.astimezone(local_timezone)
        game_date = game_datetime.date()
        games_in_days[game_date].append(game)

    messages = []
    for date, games_in_a_day in games_in_days.items():
        messages.append(_produce_invitation_message_by_games_in_a_day(games_in_a_day))

    return messages

def _produce_invitation_message_by_games_in_a_day(games_in_a_day: list[Game]) -> FlexMessage:
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
    reminder = offseason_game_reminder if is_postseason else game_reminder

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

def produce_message_of_game_query_attendance(game: Game) -> FlexMessage:
    game_datetime = game.start_datetime.astimezone(local_timezone)
    
    # 獲取星期的中文表示
    chinese_weekday = weekday_mapping[game_datetime.strftime('%A')]    
    # 格式化日期和時間
    date = game_datetime.strftime("%-m/%-d（%a）").replace(game_datetime.strftime('%a'), chinese_weekday)

    opponent = game.away_team if game.home_team == current_team else game.home_team
    location = game.location

    hint = f"點開訊息，查看一下{date}在{location}打{opponent}的比賽有誰會到！"
    
    contents = {
      "type": "carousel",
      "contents": [_produce_bubble_of_game_query_attendance(game)],
    }
    contents_string = json.dumps(contents, indent=4)
    return FlexMessage(alt_text=hint, contents=FlexContainer.from_json(contents_string))


def _produce_bubble_of_game_query_attendance(game: Game) -> dict[str, Any]:
    return {
          "type": "bubble",
          "size": "giga",
          "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
              {
                "type": "text",
                "text": game.generate_short_summary_for_team(),
                "weight": "bold",
                "size": "sm"
              }
            ],
            "margin": "none",
            "spacing": "none"
          },
          "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "none",
            "contents": [
              {
                "type": "button",
                "action": {
                  "type": "postback",
                  "label": "這場有誰來❓",
                  "data": f"query_attendance_of_game?id={game.id}",
                  "displayText": f"{game.generate_verbal_summary_for_team()}這場有誰來？"
                },
                "height": "sm",
                "style": "primary"
              }
            ],
            "margin": "sm"
          }
        }