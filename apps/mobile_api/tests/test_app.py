import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from shared_module.mobile_api import (
    AuthenticationError,
    MobilePrincipal,
    NotFound,
    PermissionDenied,
    TokenPair,
)

from apps.mobile_api.app import Dependencies, create_app


class MobileApiRouteTest(unittest.TestCase):
    def setUp(self):
        fixture_root = Path(__file__).resolve().parent / "fixtures"
        self.officer_me_fixture = json.loads(
            (fixture_root / "officer_me.json").read_text(encoding="utf-8")
        )
        self.report_fixture = json.loads(
            (fixture_root / "attendance_report_empty.json").read_text(encoding="utf-8")
        )
        self.principal = MobilePrincipal("session", 23, 7, "basic", "測試球員", 1)
        self.auth = SimpleNamespace(
            authenticate=Mock(return_value=self.principal),
            exchange=Mock(return_value=TokenPair("access", "refresh", "session", 900)),
            refresh=Mock(
                return_value=TokenPair("access-2", "refresh-2", "session", 900)
            ),
            repository=SimpleNamespace(logout=Mock()),
            clock=Mock(),
        )
        self.basic = SimpleNamespace(
            games=Mock(return_value=()),
            games_page=Mock(return_value={"items": [], "next_cursor": None}),
            game=Mock(return_value={"id": 44, "home_team": "A", "away_team": "B"}),
            data=SimpleNamespace(own_attendance_reply=Mock(return_value=5)),
            attendance_view=Mock(
                return_value={"game_id": "44", "own_reply": "undecided", "replied": []}
            ),
            attendance_report=Mock(return_value=self.report_fixture),
            attendance_reply=Mock(
                return_value=(
                    200,
                    {
                        "game_id": "44",
                        "reply": "attending",
                        "changed": True,
                        "updated_at": "2026-08-18T12:00:00Z",
                        "notification": {"status": "failed"},
                    },
                    False,
                )
            ),
        )
        self.revision = Mock(return_value=True)
        self.client = create_app(
            Dependencies(self.auth, self.basic, self.revision)
        ).test_client()

    def test_revision_mismatch_fails_before_auth_or_data_read(self):
        self.revision.return_value = False
        response = self.client.get(
            "/api/v1/games", headers={"Authorization": "Bearer token"}
        )
        self.assertEqual(response.status_code, 503)
        self.auth.authenticate.assert_not_called()
        self.basic.games_page.assert_not_called()

    def test_malformed_transport_and_unexpected_failure_use_safe_error_envelope(self):
        response = self.client.post(
            "/api/v1/auth/refresh", data="not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "malformed_request")
        self.auth.authenticate.side_effect = RuntimeError("raw-secret-must-not-leak")
        response = self.client.get(
            "/api/v1/me", headers={"Authorization": "Bearer fake-access"}
        )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("raw-secret", response.get_data(as_text=True))

    def test_bearer_is_required_and_cookie_is_not_used(self):
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)
        self.auth.authenticate.assert_not_called()

    def test_basic_read_routes_and_own_attendance(self):
        headers = {"Authorization": "Bearer token"}
        self.assertEqual(
            self.client.get("/api/v1/me", headers=headers).status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/v1/games", headers=headers).status_code, 200
        )
        response = self.client.get("/api/v1/games/game_44/attendance", headers=headers)
        self.assertEqual(
            response.get_json(),
            {"game_id": "44", "own_reply": "undecided", "replied": []},
        )

    def test_attendance_requires_idempotency_key_and_reports_saved_notification_failure(
        self,
    ):
        headers = {
            "Authorization": "Bearer token",
            "Idempotency-Key": "request-one-12345",
        }
        response = self.client.put(
            "/api/v1/games/game_44/attendance-reply",
            headers=headers,
            json={"reply": "attending"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["changed"])
        self.assertEqual(response.get_json()["notification"]["status"], "failed")
        self.assertEqual(
            self.client.put(
                "/api/v1/games/game_44/attendance-reply",
                headers={"Authorization": "Bearer token"},
                json={"reply": "attending"},
            ).status_code,
            422,
        )

    def test_me_projects_officer_capability_and_report_route(self):
        self.principal = MobilePrincipal("session", 23, 7, "officer", "Officer", 1)
        self.auth.authenticate.return_value = self.principal
        headers = {"Authorization": "Bearer token"}
        me = self.client.get("/api/v1/me", headers=headers).get_json()
        self.assertEqual(me, self.officer_me_fixture)
        response = self.client.get(
            "/api/v1/games/game_44/attendance-report"
            "?history_limit=8&minimum_response_rate=70",
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.report_fixture)
        self.basic.attendance_report.assert_called_once_with(
            self.principal, 44, history_limit=8, minimum_rate=70
        )

    def test_report_query_bounds_fail_before_service_read(self):
        headers = {"Authorization": "Bearer token"}
        for query in (
            "history_limit=9",
            "history_limit=nope",
            "minimum_response_rate=65",
        ):
            with self.subTest(query=query):
                response = self.client.get(
                    f"/api/v1/games/game_44/attendance-report?{query}",
                    headers=headers,
                )
                self.assertEqual(response.status_code, 422)
        self.basic.attendance_report.assert_not_called()

    def test_report_denied_and_invisible_states_use_standard_nonleaking_errors(self):
        headers = {"Authorization": "Bearer token"}
        for error, status, code in (
            (PermissionDenied("capability required"), 403, "forbidden"),
            (NotFound("game not found"), 404, "resource_not_found"),
        ):
            with self.subTest(status=status):
                self.basic.attendance_report.side_effect = error
                response = self.client.get(
                    "/api/v1/games/game_44/attendance-report", headers=headers
                )
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.get_json()["error"]["code"], code)
                self.assertNotIn("44", response.get_data(as_text=True))

    def test_inactive_fresh_principal_is_rejected_before_report_read(self):
        self.auth.authenticate.side_effect = AuthenticationError("inactive session")
        response = self.client.get(
            "/api/v1/games/game_44/attendance-report",
            headers={"Authorization": "Bearer token"},
        )
        self.assertEqual(response.status_code, 401)
        self.basic.attendance_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
