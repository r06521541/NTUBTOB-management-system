"""Fictional first-login contracts; normal bootstrap stays disabled."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shared_module.mobile_api import (
    AccountUnavailable,
    AppleLifecycleAuthService,
    AuthenticationError,
    Conflict,
    IdentityPending,
    PendingReviewEnvelope,
    ProviderExchangeOutcomeUnknown,
)
from shared_module.portal_data.mobile_repository import MobileRepository
from shared_module.portal_data.models import (
    AccessAuditRecord,
    AppleProviderCredentialRecord,
    AuthIdentityRecord,
    MobileSessionRecord,
    PersonRecord,
)

from shared_lib.tests import test_mobile_api_service as fixtures

NOW = fixtures.NOW


class AppleFirstLoginTest(unittest.TestCase):
    def exchange(self, service):
        return service.exchange(
            assertion="fictional.assertion.signature",
            authorization_code="fictional-single-use-code",
            nonce="fictional-raw-nonce-123456",
            login_attempt_id="fictional-login-attempt",
            installation_id="fictional-installation",
            platform="ios",
        )

    def service(self, *, enabled=True, provider_error=None):
        base, repository = fixtures.AppleLifecycleAuthServiceTest().service(
            fixtures.FakeAppleCodeExchanger(error=provider_error)
        )
        service = AppleLifecycleAuthService(
            repository,
            base.verifier,
            base.cipher,
            base.provider_cipher,
            base.token_codec,
            base.exchanger,
            audience=base.audience,
            allow_first_login=enabled,
            clock=lambda: NOW,
        )
        repository.ensure_apple_link_candidate = Mock(
            return_value={"identity_id": 73, "status": "pending"}
        )
        repository.exchange = Mock(side_effect=IdentityPending("pending", 73))
        return service, repository

    def test_pending_exists_before_provider_exchange_and_gets_only_review(self):
        service, repository = self.service()
        original = service.exchanger.exchange

        def exchanged(*args, **kwargs):
            repository.ensure_apple_link_candidate.assert_called_once()
            self.assertEqual(len(repository.apple_reservations), 1)
            return original(*args, **kwargs)

        service.exchanger.exchange = exchanged
        result = self.exchange(service)
        self.assertIsInstance(result, PendingReviewEnvelope)
        call = repository.ensure_apple_link_candidate.call_args
        self.assertEqual(call.args[0], "fictional-apple-subject")
        self.assertEqual(call.kwargs, {"first_login": True})
        completion = repository.apple_pending_completions[0]
        self.assertEqual(completion["identity_id"], 73)
        self.assertNotIn("fictional-provider-refresh-token", completion.values())

    def test_default_and_disabled_do_not_create_candidate(self):
        base, _ = fixtures.AppleLifecycleAuthServiceTest().service(
            fixtures.FakeAppleCodeExchanger()
        )
        self.assertIs(base.allow_first_login, False)
        service, repository = self.service(enabled=False)
        repository.exchange.side_effect = AccountUnavailable("unavailable")
        with self.assertRaises(AccountUnavailable):
            self.exchange(service)
        repository.ensure_apple_link_candidate.assert_not_called()

    def test_unavailable_identity_never_exchanges_or_reopens(self):
        for state in ("disabled", "blocked", "rejected", "ignored"):
            service, repository = self.service()
            repository.ensure_apple_link_candidate.return_value["status"] = state
            with self.subTest(state=state), self.assertRaises(AccountUnavailable):
                self.exchange(service)
            self.assertEqual(service.exchanger.calls, [])
            self.assertEqual(repository.apple_reservations, [])

    def test_callback_before_completion_prevents_review_or_retry(self):
        service, repository = self.service()
        repository.complete_apple_code_for_pending = Mock(
            side_effect=Conflict("pending changed")
        )
        service.token_codec.issue_review = Mock()
        with self.assertRaises(Conflict):
            self.exchange(service)
        service.token_codec.issue_review.assert_not_called()
        self.assertEqual(len(service.exchanger.calls), 1)

    def test_provider_failure_leaves_pending_but_never_issues_review(self):
        for error in (
            AuthenticationError("rejected"),
            ProviderExchangeOutcomeUnknown("unknown"),
        ):
            service, repository = self.service(provider_error=error)
            service.token_codec.issue_review = Mock()
            with (
                self.subTest(error=type(error).__name__),
                self.assertRaises(type(error)),
            ):
                self.exchange(service)
            repository.ensure_apple_link_candidate.assert_called_once()
            repository.exchange.assert_not_called()
            self.assertEqual(repository.apple_pending_completions, [])
            service.token_codec.issue_review.assert_not_called()

    def test_invalid_assertion_never_creates_pending(self):
        service, repository = self.service()
        service.verifier.verify = Mock(side_effect=AuthenticationError("invalid"))
        with self.assertRaises(AuthenticationError):
            self.exchange(service)
        repository.ensure_apple_link_candidate.assert_not_called()
        self.assertEqual(service.exchanger.calls, [])

    def test_post_provider_storage_failure_is_safe_and_not_retryable(self):
        service, repository = self.service()
        repository.complete_apple_code_for_pending = Mock(
            side_effect=RuntimeError("fictional-private-database-detail")
        )
        service.token_codec.issue_review = Mock()
        with self.assertRaises(Exception) as raised:
            self.exchange(service)
        self.assertEqual(
            type(raised.exception).__name__, "AppleLoginCompletionUnavailable"
        )
        self.assertIs(raised.exception.retryable, False)
        self.assertIn("app_completion", str(raised.exception))
        self.assertIn("provider_exchange=completed", str(raised.exception))
        self.assertNotIn("fictional-private", str(raised.exception))
        service.token_codec.issue_review.assert_not_called()
        self.assertEqual(len(service.exchanger.calls), 1)


class FakeSession:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.added = []
        self.operations = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def begin(self):
        return self

    def scalar(self, statement):
        self.operations.append("row")
        return next(self.rows)

    def execute(self, statement, parameters):
        if str(statement) != "SELECT pg_advisory_xact_lock(:key)":
            raise AssertionError("unexpected statement")
        self.operations.append(parameters["key"])

    def add(self, row):
        self.added.append(row)

    def flush(self):
        for row in self.added:
            if isinstance(row, AuthIdentityRecord):
                row.id = 73


class FirstLoginRepositoryTest(unittest.TestCase):
    def candidate(self, session):
        repo = MobileRepository(object())
        repo.lifecycle._thread = Mock()
        with (
            patch(
                "shared_module.portal_data.mobile_repository.Session",
                return_value=session,
            ),
            patch(
                "shared_module.portal_data.mobile_repository.acquire_admin_event_locks"
            ) as locks,
        ):
            result = repo.ensure_apple_link_candidate(
                "fictional-subject", "fictional-request", NOW, first_login=True
            )
        locks.assert_called_once_with(session)
        return result

    def test_pending_has_no_person_session_or_provider_credential(self):
        session = FakeSession([None])
        result = self.candidate(session)
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["person_id"])
        self.assertFalse(
            any(
                isinstance(
                    row,
                    (PersonRecord, MobileSessionRecord, AppleProviderCredentialRecord),
                )
                for row in session.added
            )
        )
        audit = next(row for row in session.added if isinstance(row, AccessAuditRecord))
        self.assertIn("first login", audit.reason)

    def test_existing_identity_is_not_reset(self):
        for state in ("linked", "pending", "disabled", "blocked"):
            row = SimpleNamespace(
                id=73, provider="apple", person_id=4, status=state, updated_at=NOW
            )
            session = FakeSession([row])
            with self.subTest(state=state):
                self.assertEqual(self.candidate(session)["status"], state)
                self.assertEqual(session.added, [])

    def test_completion_rechecks_pending_after_callback(self):
        code = SimpleNamespace(state="pending")
        session = FakeSession([code, None])
        with patch(
            "shared_module.portal_data.mobile_repository.Session", return_value=session
        ):
            with self.assertRaises(Conflict):
                MobileRepository(object()).complete_apple_code_for_pending(
                    code_hash="a" * 64,
                    identity_id=73,
                    subject="fictional-subject",
                    encrypted_provider_refresh=b"fictional-ciphertext",
                    provider_refresh_hash="b" * 64,
                    now=NOW,
                )
        self.assertEqual(session.added, [])
        self.assertEqual(code.state, "pending")
        from shared_module.portal_data.runtime import (
            ADMIN_LOCK_KEY,
            EVENT_SNAPSHOT_LOCK_KEY,
        )

        self.assertEqual(
            session.operations,
            [ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY, "row", "row"],
        )


if __name__ == "__main__":
    unittest.main()
