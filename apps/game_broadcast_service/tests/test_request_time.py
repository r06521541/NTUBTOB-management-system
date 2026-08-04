import ast
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from request_time import get_request_time_window


class FakeClock:
    def __init__(self, *values):
        self.values = iter(values)
        self.timezones = []

    def __call__(self, local_timezone):
        self.timezones.append(local_timezone)
        return next(self.values)


class RequestTimeWindowTest(unittest.TestCase):
    def test_each_call_uses_a_fresh_clock_value(self):
        local_timezone = timezone(timedelta(hours=8))
        first_now = datetime(2026, 8, 4, 23, 59, tzinfo=local_timezone)
        second_now = datetime(2026, 8, 5, 0, 1, tzinfo=local_timezone)
        clock = FakeClock(first_now, second_now)

        first = get_request_time_window(local_timezone, clock)
        second = get_request_time_window(local_timezone, clock)

        self.assertEqual(first.now, first_now)
        self.assertEqual(second.now, second_now)
        self.assertEqual(
            first.today_begin,
            datetime(2026, 8, 4, tzinfo=local_timezone),
        )
        self.assertEqual(
            second.today_begin,
            datetime(2026, 8, 5, tzinfo=local_timezone),
        )
        self.assertEqual(clock.timezones, [local_timezone, local_timezone])

    def test_window_starts_at_timezone_aware_midnight_and_spans_11_days(self):
        local_timezone = timezone(timedelta(hours=8))
        now = datetime(2026, 8, 4, 12, 34, 56, 789, tzinfo=local_timezone)

        window = get_request_time_window(local_timezone, FakeClock(now))

        self.assertEqual(
            window.today_begin,
            datetime(2026, 8, 4, tzinfo=local_timezone),
        )
        self.assertIs(window.today_begin.tzinfo, local_timezone)
        self.assertEqual(
            window.end_time,
            window.today_begin + timedelta(days=11),
        )


class RequestTimeWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app_path = SERVICE_DIR / "app.py"
        cls.tree = ast.parse(app_path.read_text(encoding="utf-8"))

    def find_function(self, name):
        return next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )

    def call_names(self, function):
        return [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]

    def find_call(self, function, name):
        return next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id == name
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == name
            )
        )

    def test_routes_each_create_one_request_time_window(self):
        for function_name in ("invite", "announce_cancellation"):
            with self.subTest(function_name=function_name):
                function = self.find_function(function_name)
                self.assertEqual(
                    self.call_names(function).count("get_request_time_window"),
                    1,
                )

    def test_mark_helpers_require_explicit_timestamp(self):
        invited = self.find_function("mark_games_as_invited")
        cancelled = self.find_function("mark_games_as_cancellation_announced")

        self.assertEqual(
            [argument.arg for argument in invited.args.args],
            ["games", "invited_at"],
        )
        self.assertEqual(
            [argument.arg for argument in cancelled.args.args],
            ["games", "announced_at"],
        )

    def test_routes_reuse_snapshot_for_query_and_update(self):
        cases = (
            (
                "invite",
                "search_for_invitation",
                "mark_games_as_invited",
            ),
            (
                "announce_cancellation",
                "search_cancelled_to_announce",
                "mark_games_as_cancellation_announced",
            ),
        )

        for function_name, search_name, mark_name in cases:
            with self.subTest(function_name=function_name):
                function = self.find_function(function_name)
                search_call = self.find_call(function, search_name)
                mark_call = self.find_call(function, mark_name)

                self.assertEqual(
                    [ast.unparse(argument) for argument in search_call.args],
                    ["request_time.now", "request_time.end_time"],
                )
                self.assertEqual(
                    ast.unparse(mark_call.args[1]),
                    "request_time.now",
                )

    def test_module_does_not_assign_import_time_window_globals(self):
        assigned_names = {
            target.id
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }

        self.assertTrue(
            {"now", "today_begin", "ten_days_later"}.isdisjoint(
                assigned_names
            )
        )

    def test_notify_cron_has_no_import_time_window_globals(self):
        notify_app_path = (
            SERVICE_DIR.parent / "notify_cronjob_service" / "app.py"
        )
        notify_tree = ast.parse(notify_app_path.read_text(encoding="utf-8"))
        assigned_names = {
            target.id
            for node in notify_tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }

        self.assertTrue(
            {"now", "today_begin", "ten_days_later"}.isdisjoint(
                assigned_names
            )
        )


if __name__ == "__main__":
    unittest.main()
