import functions_framework
from shared_module.games_crawler_client import CrawlerClient
from shared_module.line_notify_message import (
    generate_error_message,
    generate_schedule_message_for_team,
)
import shared_module.line_notify as line_notify
import shared_module.settings as settings
import shared_module.models.games as Game

import envs


@functions_framework.http
def main(request):
    games_crawler_client = CrawlerClient(envs.game_crawl_api)
    games = games_crawler_client.get_games()

    try:
        game_list = [Game.from_dict(data) for data in games]
        message = generate_schedule_message_for_team(game_list, settings.current_team)
        line_notify.notify_announcement(message)
    except Exception as e:
        message = generate_error_message()
        line_notify.notify_alarm_log("weekly-game-notify: " + repr(e))

    return ""
