import envs
import functions_framework
from message import generate_error_message, generate_schedule_message_for_team

from shared.orm.games import Game
from shared.utils.games_crawler_client import CrawlerClient
from shared.utils.notify_client import NotifyClient


@functions_framework.http
def main(request):
    games_crawler_client = CrawlerClient(envs.game_crawl_api)
    games = games_crawler_client.get_games()

    try:
        game_list = [Game.from_dict(data) for data in games]
        message = generate_schedule_message_for_team(game_list, envs.team_name)
        NotifyClient(envs.notify_token_id, envs.notify_api).send(message)
    except Exception as e:
        message = generate_error_message()
        NotifyClient(envs.notify_alarm_token_id, envs.notify_api).send(
            "weekly-game-notify: " + repr(e)
        )

    return ""
