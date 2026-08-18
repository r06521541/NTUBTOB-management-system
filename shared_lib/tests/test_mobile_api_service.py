import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from shared_module.mobile_api import (
    AuthenticationError,
    BasicApiService,
    Conflict,
    HmacAccessTokenCodec,
    MobileAuthService,
    MobilePrincipal,
    TokenPair,
    VerifiedAssertion,
    secret_hash,
)

NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


class FakeCipher:
    def seal(self, value):
        return b"fake-encrypted:" + value[::-1]

    def open(self, value):
        return value.removeprefix(b"fake-encrypted:")[::-1]


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


class BasicApiServiceTest(unittest.TestCase):
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

    def test_five_replies_and_exact_idempotent_readback(self):
        repository = FakeAuthRepository()
        data = SimpleNamespace(
            scoped_game=lambda *_: {"id": 44, "start_at": NOW + timedelta(hours=6)},
            scoped_games=lambda *_: (),
        )
        attendance = SimpleNamespace(
            reply=Mock(
                return_value=SimpleNamespace(
                    changed=True, notification_status=SimpleNamespace(value="failed")
                )
            )
        )
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
        data = SimpleNamespace(
            scoped_game=lambda *_: {"id": 44, "start_at": NOW + timedelta(hours=6)}
        )
        attendance = SimpleNamespace(
            reply=Mock(
                return_value=SimpleNamespace(
                    changed=False,
                    notification_status=SimpleNamespace(value="not_required"),
                )
            )
        )
        service = BasicApiService(data, attendance, repository, clock=lambda: NOW)
        service.attendance_reply(repository.device, 44, "attending", "same", Mock())
        with self.assertRaises(Conflict):
            service.attendance_reply(
                repository.device, 44, "not_attending", "same", Mock()
            )


if __name__ == "__main__":
    unittest.main()
