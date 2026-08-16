import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

for key, value in {
    "DSN_DATABASE": "fixture",
    "DSN_HOSTNAME": "127.0.0.1",
    "DSN_PORT": "5432",
    "DSN_UID": "fixture",
    "DSN_PASSWORD": "fixture",
}.items():
    os.environ.setdefault(key, value)

from game_command_center import attendance_projection  # noqa: E402
from game_command_center import (
    bounded_game_role,
    game_scope,
    insight_projection,
    load_bounded_games,
)

from shared_lib.shared_module.models.games import Game


class GameCommandCenterDomainTest(unittest.TestCase):
    def test_bounded_role_accepts_only_active_officer_or_allowlisted_admin(self):
        person = SimpleNamespace(status="active", access_level="officer", member_id=8)
        self.assertEqual(bounded_game_role(person, frozenset()), "officer")
        person.access_level = "basic"
        self.assertIsNone(bounded_game_role(person, frozenset()))
        self.assertEqual(bounded_game_role(person, frozenset({8})), "admin")
        person.access_level = "admin"
        self.assertIsNone(bounded_game_role(person, frozenset()))
        self.assertEqual(
            bounded_game_role(person, frozenset(), local_preview=True), "admin"
        )
        for status in ("pending", "inactive", "disabled", "blocked", "unknown"):
            with self.subTest(status=status):
                person.status = status
                self.assertIsNone(
                    bounded_game_role(person, frozenset({8}), local_preview=True)
                )

    def test_game_reader_uses_only_invited_read_queries_and_deduplicates(self):
        now = datetime(2026, 8, 10, tzinfo=timezone.utc)
        first = SimpleNamespace(id=1, start_datetime=now + timedelta(days=1))
        second = SimpleNamespace(id=2, start_datetime=now - timedelta(days=2))
        model = MagicMock()
        model.search_games.side_effect = ([first], [second], [second])

        rows = load_bounded_games(model, now)

        self.assertEqual([row.id for row in rows], [1, 2])
        self.assertEqual(model.search_games.call_count, 3)
        for call in model.search_games.call_args_list:
            self.assertTrue(call.kwargs["has_invited"])
        for mutation in ("add_game", "update_time_field"):
            getattr(model, mutation).assert_not_called()

    def test_scope_projection_and_honest_insights(self):
        now = datetime(2026, 8, 10, tzinfo=timezone.utc)
        future = SimpleNamespace(
            id=1, start_datetime=now + timedelta(days=3), cancellation_time=None
        )
        recent = SimpleNamespace(
            id=2, start_datetime=now - timedelta(days=3), cancellation_time=None
        )
        past = SimpleNamespace(
            id=3, start_datetime=now - timedelta(days=60), cancellation_time=None
        )
        cancelled = SimpleNamespace(
            id=4, start_datetime=now + timedelta(days=2), cancellation_time=now
        )
        self.assertEqual(game_scope(future, now), "future")
        self.assertEqual(game_scope(recent, now), "recent")
        self.assertEqual(game_scope(past, now), "past")
        self.assertEqual(game_scope(cancelled, now), "cancelled")
        snapshot = attendance_projection(
            SimpleNamespace(
                participants=(
                    {
                        "person_id": 10,
                        "member_id": 20,
                        "name": "虛構隊員",
                        "reply": 1,
                        "qualification": "team_player",
                    },
                    {
                        "person_id": 11,
                        "member_id": None,
                        "name": "虛構來賓",
                        "reply": 3,
                        "qualification": "guest_player",
                    },
                    {
                        "person_id": 12,
                        "member_id": 22,
                        "name": "陳建宏",
                        "reply": 2,
                        "qualification": "team_player",
                    },
                    {
                        "person_id": 13,
                        "member_id": 23,
                        "name": "Kevin Lin",
                        "reply": 5,
                        "qualification": "team_player",
                    },
                ),
                team_player_total=3,
                team_player_replied=1,
            )
        )
        self.assertEqual(snapshot["team_player_unresolved"], 2)
        self.assertEqual(len(snapshot["candidates"]), 4)
        self.assertIsNone(snapshot["candidates"][1]["member_id"])
        insight = insight_projection(
            (future, recent, past, cancelled), {1: snapshot}, now
        )
        self.assertEqual(insight["future_7"], 1)
        self.assertEqual(insight["future_30"], 1)
        self.assertEqual(insight["cancelled"], 1)
        self.assertEqual(insight["recorded"][0]["recorded_replies"], 4)

    def test_game_short_date_and_status_labels(self):
        start = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)
        game = Game(
            id=7,
            year=2026,
            season=1,
            start_datetime=start,
            duration=120,
            location="A場",
            home_team="北科",
            away_team="中山",
            invitation_time=None,
            cancellation_time=None,
            cancellation_announcement_time=None,
        )
        self.assertEqual(game.get_formatted_short_date(), "8/13")
        self.assertEqual(game.get_status_label(start - timedelta(hours=1)), "即將開打")
        self.assertEqual(game.get_status_label(start + timedelta(minutes=30)), "進行中")
        self.assertEqual(game.get_status_label(start + timedelta(hours=3)), "已結束")
        game.cancellation_time = start + timedelta(hours=1)
        self.assertEqual(game.get_status_label(start + timedelta(hours=2)), "已結束")

    def test_game_recognizes_legacy_and_portal_team_names(self):
        values = {
            "id": 8,
            "year": 2026,
            "season": 1,
            "start_datetime": datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
            "duration": 180,
            "location": "虛構球場",
            "invitation_time": None,
            "cancellation_time": None,
            "cancellation_announcement_time": None,
        }

        home = Game(
            **values, home_team="NTUBTOB", away_team="虛構校友聯隊"
        )
        away = Game(**values, home_team="虛構主隊", away_team="台大")

        self.assertTrue(home.get_is_home_team())
        self.assertEqual(home.get_opponent(), "虛構校友聯隊")
        self.assertFalse(away.get_is_home_team())
        self.assertEqual(away.get_opponent(), "虛構主隊")


class GameCommandCenterStaticContractTest(unittest.TestCase):
    def test_loading_and_insight_surfaces_are_local_and_read_only(self):
        base = (WEB_PORTAL_DIR / "templates" / "_portal_base.html").read_text(
            encoding="utf-8"
        )
        loading = (WEB_PORTAL_DIR / "static" / "portal_loading.js").read_text(
            encoding="utf-8"
        )
        weather = (WEB_PORTAL_DIR / "static" / "dashboard_weather.js").read_text(
            encoding="utf-8"
        )
        person = (WEB_PORTAL_DIR / "templates" / "person_detail.html").read_text(
            encoding="utf-8"
        )
        report = (
            WEB_PORTAL_DIR / "templates" / "game_attendance_report.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-portal-loading", base)
        self.assertIn("pageshow", loading)
        self.assertNotIn("fetch(", loading)
        self.assertIn("credentials: \"same-origin\"", weather)
        self.assertNotIn("localStorage", weather)
        for tab in ("基本資料", "校友會成員", "參與資格", "參賽紀錄"):
            self.assertIn(tab, person)
        self.assertIn('name="history"', report)
        self.assertIn('name="rate"', report)
        self.assertIn("report.minimum_rate", report)
        self.assertIn("range(10,101,10)", report)
        self.assertIn("portal-unanswered-report", report)
        self.assertIn("report.not_attending", report)
        self.assertIn("person.participation_rate", report)
        self.assertIn("person.nonparticipation_rate", report)
        self.assertNotIn('method="post"', report.lower())

        lifecycle = (
            WEB_PORTAL_DIR.parents[1]
            / "shared_lib"
            / "shared_module"
            / "portal_data"
            / "identity_lifecycle.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from sqlalchemy import Engine, and_,", lifecycle)

    def test_lineup_uses_session_storage_and_has_no_side_effect_callers(self):
        script = (WEB_PORTAL_DIR / "static" / "game_lineup.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("sessionStorage", script)
        self.assertNotIn("localStorage", script)
        for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "/api/"):
            self.assertNotIn(forbidden, script)
        self.assertNotIn("window.confirm", script)
        self.assertIn("remove-stale", script)
        self.assertIn("data-clear-lineup-storage", script)
        self.assertIn("尚未分組", script)
        self.assertIn("assignedBattingSlot", script)
        self.assertIn("unassignedBatters", script)
        self.assertIn("assignedBatters", script)
        self.assertIn("以下已排入打序", script)
        self.assertIn("separator.disabled = true", script)
        self.assertIn("assignedIds.delete(fine.positions.P)", script)
        self.assertIn("non-batting-pitcher", script)
        self.assertIn("assignFinePosition(targetPosition, candidate.id)", script)
        self.assertIn("portal-dropdown-separator", script)
        self.assertIn("activateFieldPosition", script)
        self.assertIn("fineEligible", script)
        self.assertIn("預備球員", script)

    def test_lineup_template_has_field_and_accessible_fallback(self):
        template = (WEB_PORTAL_DIR / "templates" / "lineup_lab.html").read_text(
            encoding="utf-8"
        )
        for position in ("P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"):
            self.assertIn(f"'{position}'", template)
        self.assertIn("('DH',515,439)", template)
        self.assertIn('data-field-position="{{ position }}"', template)
        self.assertIn("<svg", template)
        self.assertIn('role="img"', template)
        self.assertIn('aria-labelledby="field-title field-desc"', template)
        self.assertIn("data-fine-position", template)
        self.assertNotIn('method="post"', template.lower())
        self.assertNotIn("http://", template)
        self.assertNotIn("https://", template)

    def test_mobile_touch_focus_and_print_contracts_are_local(self):
        css = (WEB_PORTAL_DIR / "static" / "production_portal.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("@media (max-width: 700px)", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("@media print", css)


if __name__ == "__main__":
    unittest.main()
