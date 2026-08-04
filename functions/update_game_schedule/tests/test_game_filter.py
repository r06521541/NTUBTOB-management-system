import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


FUNCTION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FUNCTION_DIR))

from game_filter import filter_games


@dataclass(frozen=True)
class FakeGame:
    name: str
    home_team: str
    away_team: str
    start_datetime: datetime


class FilterGamesTest(unittest.TestCase):
    def setUp(self):
        self.team_name = "Example Alumni"
        self.start_time = datetime(2026, 8, 1, tzinfo=timezone.utc)
        self.end_time = datetime(2026, 8, 31, tzinfo=timezone.utc)

    def make_game(self, name, home_team, away_team, start_datetime):
        return FakeGame(name, home_team, away_team, start_datetime)

    def test_keeps_home_and_away_games_in_input_order(self):
        games = [
            self.make_game(
                "away",
                "Example Opponent A",
                self.team_name,
                datetime(2026, 8, 10, tzinfo=timezone.utc),
            ),
            self.make_game(
                "home",
                self.team_name,
                "Example Opponent B",
                datetime(2026, 8, 20, tzinfo=timezone.utc),
            ),
        ]

        self.assertEqual(
            filter_games(games, self.team_name, self.start_time, self.end_time),
            games,
        )

    def test_excludes_other_teams_even_when_game_is_in_date_range(self):
        other_game = self.make_game(
            "other",
            "Example Team A",
            "Example Team B",
            datetime(2026, 8, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(
            filter_games(
                [other_game], self.team_name, self.start_time, self.end_time
            ),
            [],
        )

    def test_excludes_team_games_outside_date_range(self):
        games = [
            self.make_game(
                "before",
                self.team_name,
                "Example Opponent A",
                datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc),
            ),
            self.make_game(
                "after",
                "Example Opponent B",
                self.team_name,
                datetime(2026, 9, 1, tzinfo=timezone.utc),
            ),
        ]

        self.assertEqual(
            filter_games(games, self.team_name, self.start_time, self.end_time),
            [],
        )

    def test_includes_both_date_boundaries(self):
        games = [
            self.make_game(
                "start",
                self.team_name,
                "Example Opponent A",
                self.start_time,
            ),
            self.make_game(
                "end",
                "Example Opponent B",
                self.team_name,
                self.end_time,
            ),
        ]

        self.assertEqual(
            filter_games(games, self.team_name, self.start_time, self.end_time),
            games,
        )

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(
            filter_games([], self.team_name, self.start_time, self.end_time),
            [],
        )


if __name__ == "__main__":
    unittest.main()
