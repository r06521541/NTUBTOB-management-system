from dataclasses import dataclass

import requests
from gcloud import get_id_token


@dataclass
class NotifyClient:
    token_id: str
    notify_api: str
    notify_api_token: str

    def _get_api_token(self):
        return get_id_token(self.notify_api)

    def _request(self, message: str):
        json_payload = {"message": message, "token_id": self.token_id}
        headers = {"Authorization": "Bearer " + self._get_api_token()}
        requests.post(self.notify_api, json=json_payload, headers=headers)

    def send(self, message: str):
        self._request(message)

    def send_alarm(self, message: str):
        self._request("weekly-game-notify: " + message)
