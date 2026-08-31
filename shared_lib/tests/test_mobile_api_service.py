import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from shared_module.mobile_api import (
    MAX_POSTGRESQL_BIGINT,
    AppleLifecycleAuthService,
    AppleNotificationService,
    AuthenticationError,
    BasicApiService,
    Conflict,
    HmacAccessTokenCodec,
    IdentityPending,
    InvalidArgument,
    MobileAuthService,
    MobilePrincipal,
    NotFound,
    PendingReviewEnvelope,
    PendingReviewService,
    PermissionDenied,
    ProviderExchangeOutcomeUnknown,
    TokenPair,
    VerifiedAssertion,
    mobile_capabilities,
    secret_hash,
)

NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


class FakeCipher:
    def __init__(self, prefix=b"fake-encrypted:"):
        self.prefix = prefix

    def seal(self, value):
        return self.prefix + value[::-1]

    def open(self, value):
        return value.removeprefix(self.prefix)[::-1]


class FakeVerifier:
    def __init__(self, assertion=None):
        self.assertion = assertion or VerifiedAssertion(
            "line",
            "line-subject",
            "fake-audience",
            "fake-nonce-123456",
            NOW + timedelta(minutes=5),
        )

    def verify(self, assertion, audience, nonce, now):
        return self.assertion


class FakeAuthRepository:
    def __init__(self):
        self.device = MobilePrincipal("session", 23, 7, "basic", "測試球員", 1)
        self.exchanges = []
        self.rotations = []
        self.records = {}
        self.apple_reservations = []
        self.apple_marks = []
        self.apple_pending_completions = []
        self.apple_notifications = []

    def exchange(self, **values):
        self.exchanges.append(values)
        return self.device

    def rotate(self, **values):
        self.rotations.append(values)
        access, expires = values["token_codec"].issue(self.device, values["now"])
        return (
            TokenPair(access, values["successor"], self.device.session_id, expires),
            False,
        )

    def principal(self, session_id, person_id, identity_id, access_epoch, now):
        return (
            self.device
            if (session_id, person_id, identity_id, access_epoch)
            == ("session", 23, 7, 1)
            else None
        )

    def idempotent(self, **values):
        scope = (values["session_id"], values["route"], values["key_hash"])
        existing = self.records.get(scope)
        if existing:
            if existing[0] != values["request_hash"]:
                raise Conflict("idempotency key body mismatch")
            return existing[1], existing[2], True
        status, body = values["mutation"]()
        self.records[scope] = (values["request_hash"], status, body)
        return status, body, False

    def reserve_apple_code(self, **values):
        self.apple_reservations.append(values)

    def mark_apple_code(self, **values):
        self.apple_marks.append(values)

    def complete_apple_code_for_pending(self, **values):
        self.apple_pending_completions.append(values)

    def apply_apple_notification(self, **values):
        self.apple_notifications.append(values)
        return True


class FakeAppleCodeExchanger:
    def __init__(self, *, error=None, subject="fictional-apple-subject"):
        self.error = error
        self.subject = subject
        self.calls = []

    def exchange(self, authorization_code, **values):
        self.calls.append((authorization_code, values))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            refresh_token="fictional-provider-refresh-token", subject=self.subject
        )


class MobileAuthServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = FakeAuthRepository()
        self.tokens = iter(("refresh-one", "refresh-two"))
        self.service = MobileAuthService(
            self.repository,
            FakeVerifier(),
            FakeCipher(),
            HmacAccessTokenCodec(b"x" * 32),
            audience="fake-audience",
            clock=lambda: NOW,
            token_factory=lambda: next(self.tokens),
        )

    def test_exchange_persists_hashes_only_and_issues_access_pair(self):
        result = self.service.exchange(
            assertion="raw-line-token",
            nonce="fake-nonce-123456",
            login_attempt_id="attempt-123456789",
            installation_id="installation-1234",
            platform="ios",
        )
        values = self.repository.exchanges[0]
        self.assertEqual(result.refresh_token, "refresh-one")
        self.assertNotIn("raw-line-token", values.values())
        self.assertNotIn("attempt", values.values())
        self.assertEqual(self.service.authenticate(result.access_token).person_id, 23)

    def test_wrong_audience_nonce_and_expiry_fail_closed(self):
        for assertion in (
            VerifiedAssertion(
                "line", "s", "wrong", "fake-nonce-123456", NOW + timedelta(minutes=1)
            ),
            VerifiedAssertion(
                "line", "s", "fake-audience", "wrong", NOW + timedelta(minutes=1)
            ),
            VerifiedAssertion("line", "s", "fake-audience", "fake-nonce-123456", NOW),
        ):
            service = MobileAuthService(
                self.repository,
                FakeVerifier(assertion),
                FakeCipher(),
                HmacAccessTokenCodec(b"x" * 32),
                audience="fake-audience",
                clock=lambda: NOW,
            )
            with self.assertRaises(AuthenticationError):
                service.exchange(
                    assertion="token",
                    nonce="fake-nonce-123456",
                    login_attempt_id="attempt-123456789",
                    installation_id="device-1234567890",
                    platform="ios",
                )

    def test_pending_exchange_issues_review_only_without_refresh_or_session(self):
        from shared_module.mobile_api import IdentityPending

        self.repository.exchange = Mock(side_effect=IdentityPending("pending", 77))
        result = self.service.exchange(
            assertion="raw-line-token",
            nonce="fake-nonce-123456",
            login_attempt_id="attempt-123456789",
            installation_id="installation-1234",
            platform="ios",
        )
        self.assertIsInstance(result, PendingReviewEnvelope)
        self.assertEqual(result.status, "pending")
        self.assertFalse(hasattr(result, "refresh_token"))
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(result.review_credential)

    def test_refresh_passes_only_hash_and_encrypted_successor(self):
        result = self.service.refresh(
            refresh_token="raw-refresh-token-12345678901234567890",
            refresh_attempt_id="raw-attempt-123456",
            installation_id="device-1234567890",
        )
        values = self.repository.rotations[0]
        self.assertEqual(result.refresh_token, "refresh-one")
        self.assertEqual(values["successor_hash"], secret_hash("refresh-one"))
        self.assertNotIn("raw-refresh", values.values())

    def test_authenticate_rejects_inactive_or_unlinked_fresh_principal(self):
        access, _expires = self.service.token_codec.issue(self.repository.device, NOW)
        self.repository.device = None
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(access)

    def test_authenticate_projects_request_time_access_downgrade(self):
        access, _expires = self.service.token_codec.issue(self.repository.device, NOW)
        self.repository.device = MobilePrincipal(
            "session", 23, 7, "basic", "Fresh Basic", 1
        )
        principal = self.service.authenticate(access)
        self.assertEqual(principal.access_level, "basic")
        self.assertNotIn("attendance:report:read", mobile_capabilities(principal))


class AppleLifecycleAuthServiceTest(unittest.TestCase):
    def service(self, exchanger):
        repository = FakeAuthRepository()
        verifier = FakeVerifier(
            VerifiedAssertion(
                "apple",
                "fictional-apple-subject",
                "fictional.ios.client",
                "fictional-raw-nonce-123456",
                NOW + timedelta(minutes=5),
            )
        )
        session_cipher = FakeCipher(b"session-encrypted:")
        provider_cipher = FakeCipher(b"provider-encrypted:")
        service = AppleLifecycleAuthService(
            repository,
            verifier,
            session_cipher,
            provider_cipher,
            HmacAccessTokenCodec(b"x" * 32),
            exchanger,
            audience="fictional.ios.client",
            clock=lambda: NOW,
            token_factory=lambda: "fictional-app-refresh-token",
        )
        return service, repository

    def test_reserves_before_exchange_and_persists_only_encrypted_credential(self):
        exchanger = FakeAppleCodeExchanger()
        service, repository = self.service(exchanger)
        result = service.exchange(
            assertion="header.payload.signature",
            authorization_code="fictional-single-use-code",
            nonce="fictional-raw-nonce-123456",
            login_attempt_id="fictional-login-attempt",
            installation_id="fictional-installation",
            platform="ios",
        )

        self.assertEqual(result.refresh_token, "fictional-app-refresh-token")
        self.assertEqual(len(repository.apple_reservations), 1)
        values = repository.exchanges[0]
        self.assertEqual(
            values["encrypted_provider_refresh"],
            b"provider-encrypted:" + b"fictional-provider-refresh-token"[::-1],
        )
        self.assertNotIn("fictional-provider-refresh-token", values.values())
        self.assertNotIn("fictional-single-use-code", values.values())
        self.assertNotIn("header.payload.signature", values.values())

    def test_unknown_exchange_marks_terminal_and_never_calls_repository_exchange(self):
        exchanger = FakeAppleCodeExchanger(
            error=ProviderExchangeOutcomeUnknown("safe unknown")
        )
        service, repository = self.service(exchanger)
        with self.assertRaises(ProviderExchangeOutcomeUnknown):
            service.exchange(
                assertion="header.payload.signature",
                authorization_code="fictional-single-use-code",
                nonce="fictional-raw-nonce-123456",
                login_attempt_id="fictional-login-attempt",
                installation_id="fictional-installation",
                platform="ios",
            )
        self.assertEqual(repository.apple_marks[0]["state"], "unknown")
        self.assertEqual(repository.exchanges, [])

    def test_pending_identity_persists_consumed_provider_credential(self):
        exchanger = FakeAppleCodeExchanger()
        service, repository = self.service(exchanger)

        def pending(**values):
            repository.exchanges.append(values)
            raise IdentityPending("pending", 73)

        repository.exchange = pending
        result = service.exchange(
            assertion="header.payload.signature",
            authorization_code="fictional-single-use-code",
            nonce="fictional-raw-nonce-123456",
            login_attempt_id="fictional-login-attempt",
            installation_id="fictional-installation",
            platform="ios",
        )

        self.assertIsInstance(result, PendingReviewEnvelope)
        completion = repository.apple_pending_completions[0]
        self.assertEqual(completion["identity_id"], 73)
        self.assertEqual(
            completion["encrypted_provider_refresh"],
            b"provider-encrypted:" + b"fictional-provider-refresh-token"[::-1],
        )
        self.assertNotIn("fictional-provider-refresh-token", completion.values())

    def test_wrong_platform_fails_before_verifier_or_provider_mutation(self):
        exchanger = FakeAppleCodeExchanger()
        service, repository = self.service(exchanger)
        with self.assertRaises(InvalidArgument):
            service.exchange(
                assertion="header.payload.signature",
                authorization_code="fictional-single-use-code",
                nonce="fictional-raw-nonce-123456",
                login_attempt_id="fictional-login-attempt",
                installation_id="fictional-installation",
                platform="android",
            )
        self.assertEqual(repository.apple_reservations, [])
        self.assertEqual(exchanger.calls, [])

    def test_inherited_refresh_rotation_keeps_session_cipher(self):
        service, repository = self.service(FakeAppleCodeExchanger())

        result = service.refresh(
            refresh_token="fictional-existing-refresh-token-123456",
            refresh_attempt_id="fictional-refresh-attempt",
            installation_id="fictional-installation",
        )

        self.assertEqual(result.refresh_token, "fictional-app-refresh-token")
        self.assertIs(repository.rotations[0]["cipher"], service.cipher)
        self.assertEqual(service.cipher.prefix, b"session-encrypted:")
        self.assertEqual(service.provider_cipher.prefix, b"provider-encrypted:")


class AppleNotificationServiceTest(unittest.TestCase):
    def test_verified_event_is_reduced_to_hash_and_bounded_repository_values(self):
        repository = FakeAuthRepository()
        verifier = SimpleNamespace(
            verify=Mock(
                return_value=SimpleNamespace(
                    event_type="account-deleted",
                    subject="fictional-apple-subject",
                    jti="fictional-notification-jti-0001",
                    event_at=NOW,
                )
            )
        )
        service = AppleNotificationService(
            repository,
            verifier,
            audience="fictional.notification.audience",
            clock=lambda: NOW,
        )

        self.assertTrue(service.receive("fictional.signed.payload"))

        verifier.verify.assert_called_once_with(
            "fictional.signed.payload", "fictional.notification.audience", NOW
        )
        values = repository.apple_notifications[0]
        self.assertEqual(
            values["jti_hash"], secret_hash("fictional-notification-jti-0001")
        )
        self.assertNotIn("fictional-notification-jti-0001", values.values())
        self.assertNotIn("fictional.signed.payload", values.values())


class PendingReviewServiceTest(unittest.TestCase):
    def test_credential_is_self_scoped_and_terminal_state_fails_closed(self):
        codec = HmacAccessTokenCodec(b"x" * 32)
        token, _ = codec.issue_review(77, NOW)
        lifecycle = SimpleNamespace(
            identity_status_for_id=Mock(return_value="pending"),
            review_messages=Mock(return_value=[]),
        )
        service = PendingReviewService(lifecycle, codec, clock=lambda: NOW)
        self.assertEqual(service.authenticate(token), 77)
        lifecycle.identity_status_for_id.return_value = "linked"
        with self.assertRaises(AuthenticationError):
            service.authenticate(token)


class BasicApiServiceTest(unittest.TestCase):
    def test_profile_update_hashes_key_and_replays_exactly(self):
        repository = FakeAuthRepository()
        data = SimpleNamespace(
            update_profile=Mock(
                return_value=SimpleNamespace(
                    id=23,
                    display_name="新名稱",
                    access_level="basic",
                    status="active",
                )
            )
        )
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        first = service.update_profile(
            repository.device, " 新名稱 ", "raw-key-123456789"
        )
        replay = service.update_profile(
            repository.device, " 新名稱 ", "raw-key-123456789"
        )
        self.assertFalse(first[2])
        self.assertTrue(replay[2])
        self.assertNotIn("raw-key-123456789", str(repository.records))
        data.update_profile.assert_called_once()

    def test_profile_same_key_different_payload_conflicts(self):
        repository = FakeAuthRepository()
        data = SimpleNamespace(
            update_profile=Mock(
                return_value=SimpleNamespace(
                    id=23, display_name="一", access_level="basic", status="active"
                )
            )
        )
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        service.update_profile(repository.device, "一", "same-key-1234567")
        with self.assertRaises(Conflict):
            service.update_profile(repository.device, "二", "same-key-1234567")

    def test_capabilities_are_projected_from_fresh_access_level(self):
        basic = MobilePrincipal("s", 1, 2, "basic", "Basic", 1)
        officer = MobilePrincipal("s", 1, 2, "officer", "Officer", 1)
        admin = MobilePrincipal("s", 1, 2, "admin", "Admin", 1)
        self.assertEqual(
            mobile_capabilities(basic),
            (
                "games:read",
                "events:read",
                "attendance:reply:self",
                "notifications:read",
            ),
        )
        for principal in (officer, admin):
            self.assertIn("attendance:report:read", mobile_capabilities(principal))

    def test_attendance_report_is_scoped_private_and_stably_ordered(self):
        repository = FakeAuthRepository()
        repository.device = MobilePrincipal("session", 23, 7, "officer", "Officer", 1)
        report = {
            "game_id": 44,
            "generated_at": NOW,
            "history_games": 8,
            "history_limit": 12,
            "minimum_rate": 60,
            "attending": (
                {
                    "person_id": 3,
                    "name": "Zulu",
                    "reply": 1,
                    "member_id": 99,
                    "member_number": 18,
                },
                {
                    "person_id": 6,
                    "name": "Too High",
                    "reply": 1,
                    "member_number": 1000,
                },
                {
                    "person_id": 7,
                    "name": "Negative",
                    "reply": 1,
                    "member_number": -1,
                },
                {
                    "person_id": 8,
                    "name": "Boundary",
                    "reply": 1,
                    "member_number": 27,
                },
                {
                    "person_id": 9,
                    "name": "Boolean",
                    "reply": 1,
                    "member_number": True,
                },
                {
                    "person_id": 10,
                    "name": "String",
                    "reply": 1,
                    "member_number": "27",
                },
                {"person_id": 2, "name": "Alpha", "reply": 3, "admin_note": "x"},
            ),
            "not_attending": ({"person_id": 4, "name": "Beta", "reply": 2},),
            "unanswered": (
                {
                    "person_id": 5,
                    "name": "Gamma",
                    "reply": None,
                    "replied": 7,
                    "total": 8,
                    "rate": 88,
                    "participation_rate": 63,
                    "nonparticipation_rate": 25,
                    "provider_subject": "private",
                },
            ),
        }
        data = SimpleNamespace(
            scoped_game=Mock(return_value={"id": 44, "start_at": NOW}),
            game_attendance_report=Mock(return_value=report),
        )
        attendance = Mock()
        service = BasicApiService(data, attendance, repository, clock=lambda: NOW)
        result = service.attendance_report(repository.device, 44)
        self.assertEqual(
            [item["display_name"] for item in result["attending"]],
            [
                "Alpha",
                "Boolean",
                "Boundary",
                "Negative",
                "String",
                "Too High",
                "Zulu",
            ],
        )
        self.assertEqual(result["observation"]["history_games"], 8)
        self.assertIsNone(result["attending"][0]["member_number"])
        self.assertIsNone(result["attending"][1]["member_number"])
        self.assertEqual(result["attending"][2]["member_number"], 27)
        self.assertIsNone(result["attending"][3]["member_number"])
        self.assertIsNone(result["attending"][4]["member_number"])
        self.assertIsNone(result["attending"][5]["member_number"])
        self.assertEqual(result["attending"][6]["member_number"], 18)
        self.assertNotIn("member_id", str(result))
        self.assertNotIn("admin_note", str(result))
        self.assertNotIn("provider_subject", str(result))
        data.scoped_game.assert_called_once()
        data.game_attendance_report.assert_called_once_with(
            44, at=NOW, history_limit=12, minimum_rate=60
        )
        attendance.assert_not_called()

    def test_basic_is_denied_before_game_or_report_lookup(self):
        repository = FakeAuthRepository()
        data = SimpleNamespace(scoped_game=Mock(), game_attendance_report=Mock())
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        with self.assertRaises(PermissionDenied):
            service.attendance_report(repository.device, 44)
        data.scoped_game.assert_not_called()
        data.game_attendance_report.assert_not_called()

    def test_invisible_game_is_not_found_before_report_lookup(self):
        repository = FakeAuthRepository()
        repository.device = MobilePrincipal("session", 23, 7, "officer", "Officer", 1)
        data = SimpleNamespace(
            scoped_game=Mock(return_value=None), game_attendance_report=Mock()
        )
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        with self.assertRaises(NotFound):
            service.attendance_report(repository.device, 44)
        data.game_attendance_report.assert_not_called()

    def test_games_pagination_and_basic_attendance_projection_are_bounded(self):
        repository = FakeAuthRepository()
        games = tuple(
            {
                "id": value,
                "start_at": NOW + timedelta(days=value),
                "duration_minutes": 120,
                "location": "Field",
                "home_team": "A",
                "away_team": "B",
            }
            for value in range(1, 4)
        )
        summary = SimpleNamespace(
            participants=(
                {
                    "person_id": 24,
                    "name": "Visible Reply",
                    "reply": 1,
                    "qualification": "team_player",
                    "member_id": 7001,
                    "member_number": 9,
                    "admin_note": "must not leak",
                },
            )
        )
        data = SimpleNamespace(
            scoped_games=lambda *_: games,
            scoped_game=lambda *_: games[0],
            own_attendance_reply=lambda *_: 5,
            attendance_summaries=lambda *_args, **_kwargs: {1: summary},
        )
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        first = service.games_page(repository.device, None, 2)
        second = service.games_page(repository.device, first["next_cursor"], 2)
        self.assertEqual([item["id"] for item in first["items"]], ["game_1", "game_2"])
        self.assertEqual([item["id"] for item in second["items"]], ["game_3"])
        attendance = service.attendance_view(repository.device, 1)
        self.assertEqual(attendance["own_reply"], "undecided")
        self.assertEqual(
            attendance["replied"],
            [
                {
                    "person_id": "person_24",
                    "display_name": "Visible Reply",
                    "reply": "attending",
                    "qualification": "team_player",
                }
            ],
        )

    def test_events_are_paginated_redacted_and_linked_game_is_already_scoped(self):
        repository = FakeAuthRepository()
        events = tuple(
            {
                "id": value,
                "title": f"Event {value}",
                "type": "trip",
                "status": "cancelled" if value == 2 else "published",
                "start_at": NOW + timedelta(days=value),
                "end_at": None,
                "activities": (
                    {
                        "id": value,
                        "title": "Game activity",
                        "type": "game",
                        "position": 1,
                        "start_at": NOW + timedelta(days=value),
                        "end_at": None,
                        "linked_game_id": 44 if value == 1 else None,
                        "manager": "must not leak",
                    },
                ),
                "invitees": "must not leak",
            }
            for value in range(1, 4)
        )
        data = SimpleNamespace(
            scoped_events=Mock(return_value=events),
            scoped_event=Mock(return_value=events[0]),
        )
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)

        first = service.events_page(repository.device, None, 2)
        second = service.events_page(repository.device, first["next_cursor"], 2)
        self.assertEqual(
            [event["id"] for event in first["items"]], ["event_1", "event_2"]
        )
        self.assertEqual([event["id"] for event in second["items"]], ["event_3"])
        self.assertEqual(first["items"][0]["activities"][0]["id"], "activity_1")
        self.assertEqual(
            first["items"][0]["activities"][0]["linked_game_id"], "game_44"
        )
        self.assertEqual(first["items"][1]["status"], "cancelled")
        self.assertNotIn("invitees", str(first))
        self.assertNotIn("manager", str(first))
        self.assertEqual(service.event(repository.device, 1), first["items"][0])

        data.scoped_event.return_value = None
        with self.assertRaises(NotFound):
            service.event(repository.device, 999)

    def test_event_projection_rejects_unbounded_or_malformed_stored_values(self):
        repository = FakeAuthRepository()
        data = SimpleNamespace(scoped_events=Mock(return_value=()))
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        with self.assertRaises(InvalidArgument):
            service.events_page(repository.device, "not-base64", 20)
        with self.assertRaises(InvalidArgument):
            service.events_page(repository.device, None, 101)
        malformed = {
            "id": 0,
            "title": "Malformed",
            "type": "other",
            "status": "published",
            "start_at": NOW,
            "end_at": None,
            "activities": (),
        }
        with self.assertRaises(InvalidArgument):
            service._public_event(malformed)

    def test_event_mutations_reuse_durable_idempotency_and_exclude_linked_game(self):
        repository = FakeAuthRepository()
        state = {
            "own_reply": None,
            "counts": {
                "attending": 0,
                "not_attending": 0,
                "maybe": 0,
                "unanswered": 1,
            },
            "activities": {
                11: {
                    "own_reply": None,
                    "counts": {
                        "attending": 0,
                        "not_attending": 0,
                        "maybe": 0,
                        "unanswered": 1,
                    },
                },
                12: None,
            },
        }

        def stored_event(*_):
            return {
                "id": 7,
                "title": "Event",
                "type": "trip",
                "status": "published",
                "start_at": NOW + timedelta(days=1),
                "end_at": None,
                "attendance": state,
                "activities": (
                    {
                        "id": 11,
                        "title": "Meet",
                        "type": "gathering",
                        "position": 1,
                        "start_at": NOW + timedelta(days=1),
                        "end_at": None,
                        "linked_game_id": None,
                    },
                    {
                        "id": 12,
                        "title": "Game",
                        "type": "game",
                        "position": 2,
                        "start_at": NOW + timedelta(days=1),
                        "end_at": None,
                        "linked_game_id": 44,
                    },
                ),
            }

        def save_event(_person, _event, reply, apply_all, _now):
            state["own_reply"] = reply
            if apply_all:
                state["activities"][11]["own_reply"] = reply
            return {"changed": True, "updated_at": NOW}

        data = SimpleNamespace(
            scoped_event=Mock(side_effect=stored_event),
            event_attendance=Mock(side_effect=lambda *_: state),
            reply_to_event_attendance=Mock(side_effect=save_event),
        )
        service = BasicApiService(data, Mock(), repository, clock=lambda: NOW)
        first = service.event_attendance_reply(
            repository.device, 7, "maybe", True, "event-key-123456"
        )
        data.scoped_event.side_effect = AssertionError(
            "a completed replay must not re-read an Event that may now be closed"
        )
        replay = service.event_attendance_reply(
            repository.device, 7, "maybe", True, "event-key-123456"
        )

        self.assertFalse(first[2])
        self.assertTrue(replay[2])
        self.assertEqual(first[1]["event"]["attendance"]["own_reply"], "maybe")
        self.assertIsNone(first[1]["event"]["activities"][1]["attendance"])
        data.reply_to_event_attendance.assert_called_once()
        self.assertNotIn("event-key-123456", repr(repository.records))

    def test_event_linked_game_uses_exact_signed_bigint_boundaries(self):
        repository = FakeAuthRepository()
        service = BasicApiService(
            SimpleNamespace(), Mock(), repository, clock=lambda: NOW
        )

        def event_with_linked_games(*values):
            return {
                "id": 1,
                "title": "Signed linked Games",
                "type": "other",
                "status": "published",
                "start_at": NOW,
                "end_at": None,
                "activities": tuple(
                    {
                        "id": index,
                        "title": f"Activity {index}",
                        "type": "game",
                        "position": index,
                        "start_at": NOW,
                        "end_at": None,
                        "linked_game_id": value,
                    }
                    for index, value in enumerate(values, start=1)
                ),
            }

        projected = service._public_event(
            event_with_linked_games(
                -MAX_POSTGRESQL_BIGINT - 1,
                MAX_POSTGRESQL_BIGINT,
            )
        )
        self.assertEqual(
            [activity["linked_game_id"] for activity in projected["activities"]],
            ["game_-9223372036854775808", "game_9223372036854775807"],
        )

        for malformed in (
            0,
            -MAX_POSTGRESQL_BIGINT - 2,
            MAX_POSTGRESQL_BIGINT + 1,
            True,
            1.0,
            "44",
        ):
            with self.subTest(malformed=malformed), self.assertRaises(InvalidArgument):
                service._public_event(event_with_linked_games(malformed))

        for malformed in (-1, MAX_POSTGRESQL_BIGINT + 1, True, 1.0):
            with (
                self.subTest(positive_id=malformed),
                self.assertRaises(InvalidArgument),
            ):
                event = event_with_linked_games(None)
                event["id"] = malformed
                service._public_event(event)
            with (
                self.subTest(positive_activity_id=malformed),
                self.assertRaises(InvalidArgument),
            ):
                event = event_with_linked_games(None)
                event["activities"][0]["id"] = malformed
                service._public_event(event)

    def test_five_replies_and_exact_idempotent_readback(self):
        repository = FakeAuthRepository()
        state = {"reply": None, "updated_at": NOW}
        data = SimpleNamespace(
            scoped_game=lambda *_: {"id": 44, "start_at": NOW + timedelta(hours=6)},
            scoped_games=lambda *_: (),
            own_attendance_reply_state=lambda *_: dict(state),
        )

        def save(command):
            state["reply"] = command.reply
            return SimpleNamespace(
                changed=True, notification_status=SimpleNamespace(value="failed")
            )

        attendance = SimpleNamespace(reply=Mock(side_effect=save))
        service = BasicApiService(data, attendance, repository, clock=lambda: NOW)
        for value in (
            "attending",
            "not_attending",
            "arriving_late",
            "leaving_early",
            "undecided",
        ):
            first = service.attendance_reply(
                repository.device, 44, value, f"key-{value}", Mock()
            )
            replay = service.attendance_reply(
                repository.device, 44, value, f"key-{value}", Mock()
            )
            self.assertFalse(first[2])
            self.assertTrue(replay[2])
            self.assertEqual(first[1]["notification"]["status"], "failed")
        self.assertEqual(attendance.reply.call_count, 5)

    def test_same_key_different_body_conflicts(self):
        repository = FakeAuthRepository()
        state = {"reply": None, "updated_at": NOW}
        data = SimpleNamespace(
            scoped_game=lambda *_: {"id": 44, "start_at": NOW + timedelta(hours=6)},
            own_attendance_reply_state=lambda *_: dict(state),
        )

        def save(command):
            state["reply"] = command.reply
            return SimpleNamespace(
                changed=False,
                notification_status=SimpleNamespace(value="not_required"),
            )

        attendance = SimpleNamespace(reply=Mock(side_effect=save))
        service = BasicApiService(data, attendance, repository, clock=lambda: NOW)
        service.attendance_reply(repository.device, 44, "attending", "same", Mock())
        with self.assertRaises(Conflict):
            service.attendance_reply(
                repository.device, 44, "not_attending", "same", Mock()
            )


if __name__ == "__main__":
    unittest.main()
