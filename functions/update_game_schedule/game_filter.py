from datetime import datetime
from typing import Iterable


def filter_games(
    games: Iterable[object],
    team_name: str,
    start_time: datetime,
    end_time: datetime,
) -> list[object]:
    return [
        game
        for game in games
        if (game.home_team == team_name or game.away_team == team_name)
        and start_time <= game.start_datetime <= end_time
    ]
