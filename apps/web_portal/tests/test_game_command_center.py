import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from game_command_center import attendance_projection  # noqa: E402
from game_command_center import (
    bounded_game_role,
    game_scope,
    insight_projection,
    load_bounded_games,
)


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
                ),
                team_player_total=3,
                team_player_replied=1,
            )
        )
        self.assertEqual(snapshot["team_player_unresolved"], 2)
        self.assertEqual(len(snapshot["candidates"]), 2)
        self.assertIsNone(snapshot["candidates"][1]["member_id"])
        insight = insight_projection(
            (future, recent, past, cancelled), {1: snapshot}, now
        )
        self.assertEqual(insight["future_7"], 1)
        self.assertEqual(insight["future_30"], 1)
        self.assertEqual(insight["cancelled"], 1)
        self.assertEqual(insight["recorded"][0]["recorded_replies"], 2)


class GameCommandCenterStaticContractTest(unittest.TestCase):
    def test_lineup_uses_session_storage_and_has_no_side_effect_callers(self):
        script = (WEB_PORTAL_DIR / "static" / "game_lineup.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("sessionStorage", script)
        self.assertNotIn("localStorage", script)
        for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "/api/"):
            self.assertNotIn(forbidden, script)
        self.assertIn("window.confirm", script)
        self.assertIn("remove-stale", script)
        self.assertIn("data-clear-lineup-storage", script)

    def test_lineup_template_has_field_and_accessible_fallback(self):
        template = (WEB_PORTAL_DIR / "templates" / "lineup_lab.html").read_text(
            encoding="utf-8"
        )
        for position in ("P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"):
            self.assertIn(f"'{position}'", template)
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
