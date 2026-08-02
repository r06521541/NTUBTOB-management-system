import threading
import requests
from ..models.discord_webhooks import DiscordWebhook
from ..notify.notify_helper import NotifyHelper

notify_api = 'https://discord.com/api/webhooks'

_notify_announcement_webhook_id = 2
_notify_management_webhook_id = 5
_notify_alarm_log_webhook_id = 3
_notify_success_log_webhook_id = 4

failure_message = 'Discord Webhook傳送失敗 - webhook ID: {webhook_id}, 內容: {content}'


class DiscordNotifyHelper(NotifyHelper):
    def _notify(self, webhook_id: int, content: str):
        identifier = DiscordWebhook.search_by_id(webhook_id)

        if not identifier or len(identifier) == 0:
            self.notify_alarm_log(failure_message.format(webhook_id=webhook_id, content=content))
        else:
            data = {
                "content" : content
            }
            request = requests.post(notify_api + '/' + identifier, data = data)
            request.close()

    def notify_alarm_log(self, message: str):
        self._notify(_notify_alarm_log_webhook_id, message)

    def notify_successful_log(self, message: str):
        self._notify(_notify_success_log_webhook_id, message)

    def notify_announcement(self, message: str):
        self._notify(_notify_announcement_webhook_id, message)

    def notify_management_message(self, message: str):
        self._notify(_notify_management_webhook_id, message)