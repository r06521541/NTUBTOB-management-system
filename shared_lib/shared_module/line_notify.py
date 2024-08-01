import requests
from .models.line_notify_tokens import LineNotifyToken

notify_api = 'https://notify-api.line.me/api/notify'

notify_announcement_token_id = 2
notify_management_token_id = 5
notify_alarm_log_token_id = 3
notify_success_log_token_id = 4

failure_message = 'LINE Notify傳送失敗 - token ID: {token_id}, 內容: {content}'


def _notify(token_id: int, message: str):
    notify_token = LineNotifyToken.search_by_id(token_id)

    if not notify_token or len(notify_token) == 0:
        notify_alarm_log(failure_message.format(token_id=token_id, content=message))
    else:
        data = {
            "message" : message
        }
        headers = {
            "Authorization" : "Bearer " + notify_token
        }
        requests.post(notify_api, data = data, headers = headers)

def notify_alarm_log(message: str):
    _notify(notify_alarm_log_token_id, message)

def notify_successful_log(message: str):
    _notify(notify_success_log_token_id, message)

def notify_announcement(message: str):
    _notify(notify_announcement_token_id, message)

def notify_management_message(message: str):
    _notify(notify_management_token_id, message)