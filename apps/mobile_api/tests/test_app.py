import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from shared_module.mobile_api import MobilePrincipal, TokenPair

from apps.mobile_api.app import Dependencies, create_app


class MobileApiRouteTest(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
