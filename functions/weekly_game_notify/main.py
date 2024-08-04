import functions_framework
from shared_module.games_crawler_client import CrawlerClient
from shared_module.line_notify_message import (
    generate_error_message,
    generate_schedule_message_for_team,
)
from shared_module.notify_client import NotifyClient
from shared_module.models.games import Game

import envs


@functions_framework.http
def main(request):
    games_crawler_client = CrawlerClient(envs.game_crawl_api)
    games = games_crawler_client.get_games()

    try:
        game_list = [Game.from_dict(data) for data in games]
        message = generate_schedule_message_for_team(game_list)
        NotifyClient(envs.notify_token_id, envs.notify_api).send(message)
    except Exception as e:
        message = generate_error_message()
        NotifyClient(envs.notify_alarm_token_id, envs.notify_api).send(
            "weekly-game-notify: " + repr(e)
        )

    return ""
