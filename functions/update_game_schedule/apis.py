from shared_module.games_crawler_client import CrawlerClient
from shared_module.notify_client import NotifyClient
from shared_module.games import Game

import envs


def game_crawl(team_name, start_time, end_time):
    games_crawler_client = CrawlerClient(envs.game_crawl_api)
    games = games_crawler_client.get_games()
    game_list = [Game.from_dict(data) for data in games]
    try:
        games = [game for game in game_list if game.home_team == team_name or game.away_team == team_name]
        games = [game for game in game_list if game.start_datetime >= start_time and game.start_datetime <= end_time]
        return games
    
    except Exception as e:
        notify_alarm(repr(e))

    return ""


def notify_successful(message):
    NotifyClient(envs.notify_success_token_id, envs.notify_api).send(message)

def notify_alarm(message):
    NotifyClient(envs.notify_alarm_token_id, envs.notify_api).send(
        "update-game-schedule: " + message
    )