from dataclasses import dataclass

import requests
from gcloud import get_id_token


@dataclass
class CrawlerClient:
    crawler_api: str

    def _get_api_token(self):
        return get_id_token(self.crawler_api)

    def _request(self):
        headers = {"Authorization": "Bearer " + self._get_api_token()}
        return requests.get(self.crawler_api, headers=headers)

    def get_games(self):
        response = self._request()

        if response.status_code == 200:
            games_data = response.json()["games"]
            return games_data
        else:
            return None
