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
        self.identity_link = SimpleNamespace(
            confirm_mobile=Mock(
                return_value=SimpleNamespace(
                    web_principal=SimpleNamespace(person_id=999, identity_id=888),
                    mobile_public=lambda: {
                        "status": "linked",
                        "session": {"session_id": "one"},
                    },
                )
            ),
            begin_candidate=Mock(),
            issue_fresh_proof=Mock(),
        )
        self.apple_auth = SimpleNamespace(
            exchange=Mock(
                return_value=TokenPair(
                    "apple-access", "apple-refresh", "apple-session", 900
                )
            ),
            verifier=SimpleNamespace(
                verify=Mock(
                    return_value=SimpleNamespace(
                        provider="apple", subject="fictional-apple-stable-subject"
                    )
                )
            ),
            audience="fictional.ios.client",
            clock=Mock(),
        )
        self.basic = SimpleNamespace(
            update_profile=Mock(
                return_value=(
                    200,
                    {
                        "person": {
                            "id": "person_23",
                            "display_name": "新名稱",
                            "access_level": "basic",
                            "capabilities": [
                                "games:read",
                                "events:read",
                                "attendance:reply:self",
                                "notifications:read",
                            ],
                        },
                        "changed": True,
                    },
                    False,
                )
            ),
            games=Mock(return_value=()),
            games_page=Mock(return_value={"items": [], "next_cursor": None}),
            game=Mock(return_value={"id": 44, "home_team": "A", "away_team": "B"}),
            events_page=Mock(return_value={"items": [], "next_cursor": None}),
            event=Mock(
                return_value={
                    "id": "event_7",
                    "title": "虛構週末活動",
                    "type": "trip",
                    "status": "published",
                    "start_at": "2026-09-01T00:00:00Z",
                    "end_at": None,
                    "activities": [],
                }
            ),
            event_attendance_reply=Mock(
                return_value=(
                    200,
                    {"event": {"id": "event_7"}, "changed": True},
                    False,
                )
            ),
            activity_attendance_reply=Mock(
                return_value=(
                    200,
                    {
                        "event": {"id": "event_7"},
                        "activity_id": "activity_9",
                        "changed": True,
                    },
                    False,
                )
            ),
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
            notifications_page=Mock(return_value={"items": [], "next_cursor": None}),
            notification=Mock(
                return_value={
                    "id": "notification_41",
                    "type": "game_change",
                    "title": "場地異動",
                    "body": "比賽改到第二球場。",
                    "created_at": "2026-08-22T12:00:00Z",
                    "visible_until": "2026-11-20T12:00:00Z",
                    "read_at": None,
                }
            ),
            notification_unread_count=Mock(return_value=2),
            mark_notification_read=Mock(
                return_value={
                    "notification_id": "notification_41",
                    "read_at": "2026-08-22T12:01:00Z",
                    "changed": True,
                }
            ),
            mark_all_notifications_read=Mock(
                return_value={"changed_count": 2, "unread_count": 0}
            ),
        )
        self.publishing = SimpleNamespace(
            preview=Mock(
                return_value={
                    "recipient_count": 2,
                    "revision": "a" * 64,
                    "confirmation_text": "PUBLISH 2",
                }
            ),
            confirm=Mock(
                return_value={
                    "notification_id": "notification_81",
                    "recipient_count": 2,
                    "deliveries": [],
                    "idempotent_replay": False,
                }
            ),
            register_device=Mock(
                return_value={"registration_id": "device_5", "status": "active"}
            ),
            revoke_device=Mock(return_value={"status": "revoked", "changed": True}),
        )
        self.review = SimpleNamespace(
            authenticate=Mock(return_value=7),
            status=Mock(return_value={"status": "pending", "messages": []}),
            append=Mock(return_value={"status": "pending", "messages": []}),
        )
        self.revision = Mock(return_value=True)
        self.client = create_app(
            Dependencies(
                self.auth,
                self.basic,
                self.publishing,
                self.revision,
                self.review,
                self.auth,
                self.identity_link,
                self.apple_auth,
            )
        ).test_client()

    def test_recovery_confirm_requires_explicit_confirmation_and_forwards_platform(
        self,
    ):
        body = {
            "candidate_credential": "candidate",
            "proof_credential": "proof",
            "installation_id": "installation-1234",
            "platform": "android",
            "outcome": "recovery_link",
        }
        rejected = self.client.post("/api/v1/auth/identity-link/confirm", json=body)
        self.assertEqual(rejected.status_code, 422)
        self.identity_link.confirm_mobile.assert_not_called()
        response = self.client.post(
            "/api/v1/auth/identity-link/confirm", json={**body, "confirmed": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("999", response.get_data(as_text=True))
        self.assertNotIn("888", response.get_data(as_text=True))
        self.identity_link.confirm_mobile.assert_called_once_with(
            candidate_credential="candidate",
            proof_credential="proof",
            binding="installation-1234",
            outcome="recovery_link",
            current_person_id=None,
            platform="android",
        )

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

    def test_google_exchange_uses_only_id_token_and_never_accepts_profile_fields(self):
        response = self.client.post(
            "/api/v1/auth/google/exchange",
            json={
                "id_token": "obvious-fake-google-id-token",
                "login_attempt_id": "attempt-123456789",
                "installation_id": "installation-1234",
                "platform": "android",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.auth.exchange.assert_called_once_with(
            assertion="obvious-fake-google-id-token",
            nonce=None,
            login_attempt_id="attempt-123456789",
            installation_id="installation-1234",
            platform="android",
        )
        rejected = self.client.post(
            "/api/v1/auth/google/exchange",
            json={
                "id_token": "obvious-fake-google-id-token",
                "login_attempt_id": "attempt-123456789",
                "installation_id": "installation-1234",
                "platform": "android",
                "email": "spoof@example.test",
            },
        )
        self.assertEqual(rejected.status_code, 422)

    def test_apple_exchange_is_nonce_bound_ios_only_and_rejects_profile_fields(self):
        body = {
            "id_token": "obvious-fake-apple-id-token",
            "nonce": "fictional-raw-nonce-123456",
            "login_attempt_id": "attempt-123456789",
            "installation_id": "installation-1234",
            "platform": "ios",
        }
        response = self.client.post("/api/v1/auth/apple/exchange", json=body)

        self.assertEqual(response.status_code, 201)
        self.apple_auth.exchange.assert_called_once_with(
            assertion="obvious-fake-apple-id-token",
            nonce="fictional-raw-nonce-123456",
            login_attempt_id="attempt-123456789",
            installation_id="installation-1234",
            platform="ios",
        )
        for field in ("email", "name", "user", "real_user_status"):
            with self.subTest(field=field):
                rejected = self.client.post(
                    "/api/v1/auth/apple/exchange",
                    json={**body, field: "untrusted-profile-hint"},
                )
                self.assertEqual(rejected.status_code, 422)
        wrong_platform = self.client.post(
            "/api/v1/auth/apple/exchange", json={**body, "platform": "android"}
        )
        self.assertEqual(wrong_platform.status_code, 422)

    def test_missing_apple_runtime_config_disables_only_apple_auth(self):
        client = create_app(
            Dependencies(
                self.auth,
                self.basic,
                self.publishing,
                self.revision,
                self.review,
                self.auth,
                self.identity_link,
                None,
            )
        ).test_client()
        body = {
            "id_token": "obvious-fake-id-token",
            "nonce": "fictional-raw-nonce-123456",
            "login_attempt_id": "attempt-123456789",
            "installation_id": "installation-1234",
            "platform": "ios",
        }

        apple = client.post("/api/v1/auth/apple/exchange", json=body)
        line = client.post("/api/v1/auth/line/exchange", json=body)

        self.assertEqual(apple.status_code, 503)
        self.assertTrue(apple.get_json()["error"]["retryable"])
        self.assertEqual(line.status_code, 201)

    def test_apple_link_candidate_and_proof_use_only_verified_subject(self):
        candidate_body = {
            "id_token": "obvious-fake-apple-id-token",
            "nonce": "fictional-raw-nonce-123456",
            "login_attempt_id": "attempt-123456789",
            "installation_id": "installation-1234",
        }
        self.identity_link.begin_candidate.return_value = {"status": "candidate_ready"}
        candidate = self.client.post(
            "/api/v1/auth/identity-link/candidates/apple", json=candidate_body
        )
        self.assertEqual(candidate.status_code, 201)
        self.apple_auth.verifier.verify.assert_called_with(
            "obvious-fake-apple-id-token",
            "fictional.ios.client",
            "fictional-raw-nonce-123456",
            self.apple_auth.clock.return_value,
        )
        self.identity_link.begin_candidate.assert_called_once_with(
            provider="apple",
            subject="fictional-apple-stable-subject",
            raw_assertion="obvious-fake-apple-id-token",
            attempt_id="attempt-123456789",
            binding="installation-1234",
        )

        self.identity_link.issue_fresh_proof.return_value = {"status": "proof_ready"}
        proof = self.client.post(
            "/api/v1/auth/identity-link/proofs/apple",
            json={**candidate_body, "candidate_credential": "candidate-proof"},
        )
        self.assertEqual(proof.status_code, 201)
        self.identity_link.issue_fresh_proof.assert_called_once_with(
            candidate_credential="candidate-proof",
            provider="apple",
            subject="fictional-apple-stable-subject",
            attempt_id="attempt-123456789",
            binding="installation-1234",
        )
        for route in (
            "/api/v1/auth/identity-link/candidates/apple",
            "/api/v1/auth/identity-link/proofs/apple",
        ):
            for field in ("email", "name", "user", "real_user_status"):
                with self.subTest(route=route, field=field):
                    rejected = self.client.post(
                        route, json={**candidate_body, field: "untrusted-profile-hint"}
                    )
                    self.assertEqual(rejected.status_code, 422)

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

    def test_opaque_fixture_game_id_round_trips_to_read_routes(self):
        headers = {"Authorization": "Bearer token"}

        detail = self.client.get("/api/v1/games/game_-112001", headers=headers)
        attendance = self.client.get(
            "/api/v1/games/game_-112001/attendance", headers=headers
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(attendance.status_code, 200)
        self.basic.game.assert_called_once_with(self.principal, -112001)
        self.basic.attendance_view.assert_called_once_with(self.principal, -112001)

    def test_event_list_and_detail_are_authenticated_and_opaque(self):
        headers = {"Authorization": "Bearer token"}
        listed = self.client.get(
            "/api/v1/events?limit=10&cursor=opaque", headers=headers
        )
        detail = self.client.get("/api/v1/events/event_7", headers=headers)

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["id"], "event_7")
        self.basic.events_page.assert_called_once_with(self.principal, "opaque", 10)
        self.basic.event.assert_called_once_with(self.principal, 7)

    def test_event_transport_rejects_malformed_ids_and_limits_before_read(self):
        headers = {"Authorization": "Bearer token"}
        responses = [
            self.client.get(f"/api/v1/events/{value}", headers=headers)
            for value in (
                "event_0",
                "event_07",
                "event_nope",
                "event_-1",
                "event_9223372036854775808",
                "activity_1",
            )
        ]
        responses.extend(
            (self.client.get("/api/v1/events?limit=nope", headers=headers),)
        )
        self.assertTrue(
            all(response.status_code in {400, 422} for response in responses)
        )
        self.basic.event.assert_not_called()

    def test_event_attendance_mutations_are_canonical_and_idempotent(self):
        headers = {
            "Authorization": "Bearer token",
            "Idempotency-Key": "event-command-0001",
        }
        event = self.client.put(
            "/api/v1/events/event_7/attendance-reply",
            headers=headers,
            json={"reply": "maybe", "apply_to_activities": True},
        )
        activity = self.client.put(
            "/api/v1/events/event_7/activities/activity_9/attendance-reply",
            headers=headers,
            json={"reply": "not_attending"},
        )
        malformed = self.client.put(
            "/api/v1/events/event_7/activities/activity_09/attendance-reply",
            headers=headers,
            json={"reply": "attending"},
        )

        self.assertEqual(event.status_code, 200)
        self.assertEqual(activity.status_code, 200)
        self.assertEqual(malformed.status_code, 400)
        self.basic.event_attendance_reply.assert_called_once_with(
            self.principal, 7, "maybe", True, "event-command-0001"
        )
        self.basic.activity_attendance_reply.assert_called_once_with(
            self.principal, 7, 9, "not_attending", "event-command-0001"
        )

    def test_zero_and_malformed_game_ids_remain_rejected(self):
        headers = {"Authorization": "Bearer token"}
        for game_key in ("game_0", "game_nope", "fixture_-112001"):
            with self.subTest(game_key=game_key):
                response = self.client.get(f"/api/v1/games/{game_key}", headers=headers)
                self.assertEqual(response.status_code, 400)

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
                public_error = response.get_json()["error"]
                self.assertEqual(public_error["code"], code)
                self.assertNotIn("44", public_error["code"])
                self.assertNotIn("44", public_error["message"])

    def test_inactive_fresh_principal_is_rejected_before_report_read(self):
        self.auth.authenticate.side_effect = AuthenticationError("inactive session")
        response = self.client.get(
            "/api/v1/games/game_44/attendance-report",
            headers={"Authorization": "Bearer token"},
        )
        self.assertEqual(response.status_code, 401)
        self.basic.attendance_report.assert_not_called()

    def test_notification_routes_are_principal_scoped_and_mutations_are_empty_puts(
        self,
    ):
        headers = {"Authorization": "Bearer token"}
        listed = self.client.get(
            "/api/v1/notifications?limit=10&unread_only=true", headers=headers
        )
        detail = self.client.get(
            "/api/v1/notifications/notification_41", headers=headers
        )
        count = self.client.get("/api/v1/notifications/unread-count", headers=headers)
        read = self.client.put(
            "/api/v1/notifications/notification_41/read", headers=headers, json={}
        )
        read_all = self.client.put(
            "/api/v1/notifications/read-all", headers=headers, json={}
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(count.get_json(), {"unread_count": 2})
        self.assertTrue(read.get_json()["changed"])
        self.assertEqual(read_all.get_json()["changed_count"], 2)
        self.basic.notifications_page.assert_called_once_with(
            self.principal, None, 10, True
        )
        self.basic.notification.assert_called_once_with(self.principal, 41)
        self.basic.mark_notification_read.assert_called_once_with(self.principal, 41)

    def test_notification_transport_rejects_malformed_ids_queries_and_bodies(self):
        headers = {"Authorization": "Bearer token"}
        responses = (
            self.client.get("/api/v1/notifications?unread_only=maybe", headers=headers),
            self.client.get(
                "/api/v1/notifications/not-a-notification", headers=headers
            ),
            self.client.get(
                "/api/v1/notifications/notification_9223372036854775808",
                headers=headers,
            ),
            self.client.get(
                "/api/v1/notifications/notification_1111111111111111111111111111111111111111",
                headers=headers,
            ),
            self.client.put(
                "/api/v1/notifications/read-all",
                headers=headers,
                json={"unexpected": True},
            ),
        )
        self.assertTrue(
            all(response.status_code in {400, 422} for response in responses)
        )
        self.basic.notifications_page.assert_not_called()
        self.basic.notification.assert_not_called()
        self.basic.mark_all_notifications_read.assert_not_called()

    def test_officer_preview_confirm_and_fake_device_routes_are_typed(self):
        self.principal = MobilePrincipal("session", 23, 7, "officer", "Officer", 1)
        self.auth.authenticate.return_value = self.principal
        headers = {"Authorization": "Bearer token"}
        draft = {
            "type": "officer_team_broadcast",
            "title": "集合提醒",
            "body": "請準時抵達。",
            "audience": {"type": "team"},
            "destination": {"type": "notification"},
        }
        preview = self.client.post(
            "/api/v1/officer/notifications/preview", headers=headers, json=draft
        )
        confirm = self.client.post(
            "/api/v1/officer/notifications/confirm",
            headers={**headers, "Idempotency-Key": "publish-command-0001"},
            json={
                "draft": draft,
                "preview_revision": "a" * 64,
                "typed_confirmation": "PUBLISH 2",
            },
        )
        registered = self.client.put(
            "/api/v1/devices/current",
            headers=headers,
            json={
                "installation_id": "fictional-installation-001",
                "platform": "android",
                "provider": "fake",
                "token": "fake-device-token-obvious-test-only-0001",
            },
        )
        revoked = self.client.delete(
            "/api/v1/devices/current",
            headers=headers,
            json={"installation_id": "fictional-installation-001"},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(confirm.status_code, 201)
        self.assertEqual(registered.get_json()["status"], "active")
        self.assertTrue(revoked.get_json()["changed"])
        self.publishing.preview.assert_called_once_with(self.principal, draft)
        self.publishing.confirm.assert_called_once_with(
            self.principal,
            draft,
            preview_revision="a" * 64,
            typed_confirmation="PUBLISH 2",
            idempotency_key="publish-command-0001",
        )

    def test_publish_transport_rejects_unknown_fields_before_service(self):
        response = self.client.post(
            "/api/v1/officer/notifications/preview",
            headers={"Authorization": "Bearer token"},
            json={"title": "x", "unexpected": "private"},
        )
        self.assertEqual(response.status_code, 422)
        self.publishing.preview.assert_not_called()

    def test_profile_update_returns_replay_truth(self):
        response = self.client.patch(
            "/api/v1/me",
            headers={
                "Authorization": "Bearer token",
                "Idempotency-Key": "profile-change-0001",
            },
            json={"display_name": "新名稱"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["idempotent_replay"])

    def test_review_credential_cannot_be_used_as_normal_session(self):
        self.auth.authenticate.side_effect = AuthenticationError("invalid access token")
        response = self.client.get(
            "/api/v1/me", headers={"Authorization": "Bearer review-token"}
        )
        self.assertEqual(response.status_code, 401)
        self.review.authenticate.assert_not_called()

    def test_review_routes_are_credential_scoped(self):
        read = self.client.get(
            "/api/v1/auth/line/review",
            headers={"Authorization": "Bearer review-token"},
        )
        sent = self.client.post(
            "/api/v1/auth/line/review/messages",
            headers={
                "Authorization": "Bearer review-token",
                "Idempotency-Key": "review-message-0001",
            },
            json={"body": "請協助確認"},
        )
        self.assertEqual(read.status_code, 200)
        self.assertEqual(sent.status_code, 200)
        self.review.status.assert_called_once_with(7)
        self.review.append.assert_called_once_with(
            7, "請協助確認", "review-message-0001"
        )


if __name__ == "__main__":
    unittest.main()
