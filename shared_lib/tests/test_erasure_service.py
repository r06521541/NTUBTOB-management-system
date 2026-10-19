"""Composition order and uncertain commit safety, without real provider or DB."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from shared_module.mobile_api import (
    AuthenticationError,
    InvalidArgument,
    MobilePrincipal,
)
from shared_module.portal_data import erasure_service as module
from shared_module.portal_data.erasure_receipt_recovery import (
    ReceiptRecoveryRejected,
    ReceiptRecoveryUnavailable,
    RecoveredErasureReceipt,
)
from shared_module.portal_data.erasure_request import (
    ErasureRequestRejected,
    ErasureRequestUnavailable,
)
from shared_module.portal_data.erasure_verification import ErasureVerificationRejected
from sqlalchemy.exc import SQLAlchemyError


class ErasureServiceTests(unittest.TestCase):
    def recovery_service(self):
        self.recovery_proofs = Mock()
        self.recovery_repository = Mock()
        return module.AccountErasureService(
            self.repository,
            self.proofs,
            recovery_proofs=self.recovery_proofs,
            recovery_repository=self.recovery_repository,
        )

    def test_recovery_pair_is_default_off_and_must_be_configured_together(self):
        for values in ({"recovery_proofs": Mock()}, {"recovery_repository": Mock()}):
            with self.assertRaises(ValueError):
                module.AccountErasureService(self.repository, self.proofs, **values)
        with self.assertRaises(module.AccountErasureUnavailable):
            self.service.recovery_challenge("apple")
        with self.assertRaises(module.AccountErasureUnavailable):
            self.service.recover_receipt("fake", "fake", True)
        self.assertEqual(self.repository.mock_calls, [])

    def test_recovery_confirmation_rejects_before_proof_or_read(self):
        service = self.recovery_service()
        for confirmed in (None, False, 1, "true"):
            with self.assertRaises(InvalidArgument):
                service.recover_receipt("fake", "fake", confirmed)
        self.recovery_proofs.authenticate.assert_not_called()
        self.recovery_repository.recover.assert_not_called()

    def test_recovery_challenge_is_provider_only_and_never_looks_up_account(self):
        service = self.recovery_service()
        response = {
            "challenge_credential": "fake",
            "nonce": "fake",
            "provider": "apple",
            "expires_in": 300,
        }
        self.recovery_proofs.begin.return_value = response
        with patch.object(module, "Session") as session:
            self.assertEqual(service.recovery_challenge("apple"), response)
        session.assert_not_called()
        self.recovery_proofs.begin.assert_called_once_with("apple")
        self.assertEqual(self.recovery_repository.mock_calls, [])

    def test_recovery_provider_precedes_read_and_returns_actual_six_fields(self):
        service = self.recovery_service()
        events = []
        self.recovery_proofs.authenticate.side_effect = (
            lambda *args: events.append("provider") or "sealed"
        )

        def read(credential):
            events.append("read")
            return RecoveredErasureReceipt(
                "fake-job",
                "fake-receipt",
                "needs_attention",
                self.now,
                self.now + timedelta(seconds=1),
                self.now + timedelta(hours=1),
            )

        self.recovery_repository.recover.side_effect = read
        with patch.object(module, "Session") as session:
            result = service.recover_receipt("challenge", "assertion", True)
        self.assertEqual(events, ["provider", "read"])
        self.assertEqual(
            result,
            dict(
                id="fake-job",
                receipt_secret="fake-receipt",
                status="needs_attention",
                requested_at=self.now.isoformat(),
                updated_at=(self.now + timedelta(seconds=1)).isoformat(),
                receipt_expires_at=(self.now + timedelta(hours=1)).isoformat(),
            ),
        )
        session.assert_not_called()
        self.recovery_proofs.authenticate.assert_called_once_with(
            "challenge", "assertion"
        )
        self.recovery_repository.recover.assert_called_once_with("sealed")
        self.repository.request.assert_not_called()
        self.assertIsNone(service.restricted_repository)

    def test_recovery_invalid_proof_prevents_read_and_error_is_generic(self):
        service = self.recovery_service()
        self.recovery_proofs.authenticate.side_effect = (
            module.RestrictedErasureProofRejected("private-sentinel")
        )
        with self.assertRaisesRegex(
            AuthenticationError, "^account erasure recovery rejected$"
        ) as raised:
            service.recover_receipt("challenge", "assertion", True)
        self.assertIsNone(raised.exception.__cause__)
        self.recovery_repository.recover.assert_not_called()

    def test_recovery_reader_rejection_and_unavailability_never_retry_or_leak(self):
        service = self.recovery_service()
        for error, expected in (
            (ReceiptRecoveryRejected("private-sentinel"), AuthenticationError),
            (
                ReceiptRecoveryUnavailable("private-sentinel"),
                module.AccountErasureUnavailable,
            ),
            (SQLAlchemyError("private-sentinel"), module.AccountErasureUnavailable),
            (RuntimeError("private-sentinel"), module.AccountErasureUnavailable),
        ):
            self.recovery_proofs.reset_mock()
            self.recovery_repository.reset_mock()
            self.recovery_repository.recover.side_effect = error
            with self.assertRaises(expected) as raised:
                service.recover_receipt("challenge", "assertion", True)
            self.assertNotIn("private-sentinel", str(raised.exception))
            self.assertIsNone(raised.exception.__cause__)
            self.recovery_proofs.authenticate.assert_called_once()
            self.recovery_repository.recover.assert_called_once()
            if expected is module.AccountErasureUnavailable:
                self.assertFalse(raised.exception.retryable)

    def test_recovery_challenge_failures_are_redacted(self):
        service = self.recovery_service()
        for error, expected in (
            (
                module.RestrictedErasureProofRejected("private-sentinel"),
                AuthenticationError,
            ),
            (RuntimeError("private-sentinel"), module.AccountErasureUnavailable),
        ):
            self.recovery_proofs.begin.side_effect = error
            with self.assertRaises(expected) as raised:
                service.recovery_challenge("apple")
            self.assertNotIn("private-sentinel", str(raised.exception))
            self.assertIsNone(raised.exception.__cause__)

    def test_recovery_invalid_reader_result_is_not_coerced_to_requested(self):
        service = self.recovery_service()
        for result in (
            SimpleNamespace(status="requested"),
            RecoveredErasureReceipt(
                "fake-job",
                "private-sentinel",
                "completed",
                self.now,
                self.now,
                self.now,
            ),
            RecoveredErasureReceipt(
                "fake-job",
                "private-sentinel",
                "requested",
                "private-date",
                self.now,
                self.now,
            ),
        ):
            self.recovery_repository.recover.return_value = result
            with self.assertRaises(module.AccountErasureUnavailable) as raised:
                service.recover_receipt("challenge", "assertion", True)
            self.assertNotIn("private-sentinel", str(raised.exception))
            self.assertNotIn("private-date", str(raised.exception))

    def test_restricted_request_provider_precedes_repository_without_app_session(self):
        events = []
        self.service.restricted_proofs = self.proofs
        self.service.restricted_repository = Mock()
        self.proofs.authenticate.side_effect = (
            lambda *args: events.append("provider") or "sealed"
        )
        self.service.restricted_repository.request_restricted.side_effect = (
            lambda credential: (
                events.append("repository")
                or SimpleNamespace(
                    job_id="fake-job",
                    receipt_secret="fake-secret",
                    requested_at=self.now,
                )
            )
        )
        result = self.service.request_restricted("challenge", "assertion", True)
        self.assertEqual(events, ["provider", "repository"])
        self.service.restricted_repository.request_restricted.assert_called_once_with(
            "sealed"
        )
        self.assertEqual(result["status"], "requested")
        self.assertEqual(result["receipt_secret"], "fake-secret")
        self.service.coordinator.verify.assert_not_called()

    def test_restricted_default_off_confirmation_and_rejection_never_mutate(self):
        with self.assertRaises(module.AccountErasureUnavailable):
            self.service.restricted_challenge("google")
        with self.assertRaises(module.AccountErasureUnavailable):
            self.service.request_restricted("challenge", "assertion", True)
        self.service.restricted_proofs = self.proofs
        self.service.restricted_repository = Mock()
        for confirmed in (False, None, 1, "true"):
            with self.assertRaises(InvalidArgument):
                self.service.request_restricted("challenge", "assertion", confirmed)
        self.proofs.authenticate.side_effect = module.RestrictedErasureProofRejected(
            "fixed"
        )
        with self.assertRaises(AuthenticationError):
            self.service.request_restricted("challenge", "assertion", True)
        self.service.restricted_repository.request_restricted.assert_not_called()

    def test_restricted_uncertainty_is_nonretryable_without_success(self):
        self.service.restricted_proofs = self.proofs
        self.service.restricted_repository = Mock()
        self.service.restricted_repository.request_restricted.side_effect = (
            ErasureRequestUnavailable("fixed")
        )
        with self.assertRaises(module.AccountErasureUnavailable) as raised:
            self.service.request_restricted("challenge", "assertion", True)
        self.assertFalse(raised.exception.retryable)
        self.proofs.authenticate.assert_called_once()
        self.service.restricted_repository.request_restricted.assert_called_once()

    def test_cancel_uncertain_commit_never_returns_success_or_retries(self):
        self.service.cancellation_proofs = self.proofs
        self.service.cancellation_coordinator = Mock()
        self.service.cancellation_coordinator.cancel.return_value = SimpleNamespace(
            job_id="fake-job"
        )
        session = MagicMock()
        session.__enter__.return_value = session
        session.begin.return_value.__exit__.side_effect = SQLAlchemyError(
            "fictional-private-driver"
        )
        with patch.object(module, "Session", return_value=session):
            with self.assertRaises(module.AccountErasureUnavailable) as caught:
                self.service.cancel("challenge", "assertion", True)
        self.assertFalse(caught.exception.retryable)
        self.assertNotIn("fictional-private-driver", str(caught.exception))
        self.proofs.authenticate.assert_called_once()
        self.service.cancellation_coordinator.cancel.assert_called_once()

    def test_cancellation_context_commit_failure_does_not_issue_challenge(self):
        self.service.cancellation_proofs = self.proofs
        session = MagicMock()
        session.__enter__.return_value = session
        session.begin.return_value.__exit__.side_effect = SQLAlchemyError(
            "fictional-private-driver"
        )
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(module, "load_cancellation_context"),
        ):
            with self.assertRaises(module.AccountErasureUnavailable):
                self.service.cancellation_challenge("fake-job", "fake-secret", "google")
        self.proofs.begin.assert_not_called()

    def test_cancel_requires_explicit_confirmation_and_optional_configuration(self):
        with self.assertRaises(module.AccountErasureUnavailable):
            self.service.cancel("challenge", "assertion", True)
        self.service.cancellation_proofs = self.proofs
        for confirmed in (False, None, 1, "true"):
            with self.assertRaises(InvalidArgument):
                self.service.cancel("challenge", "assertion", confirmed)
        self.proofs.authenticate.assert_not_called()

    def test_cancel_provider_outside_transaction_and_response_after_commit(self):
        events = []
        self.service.cancellation_proofs = self.proofs
        self.service.cancellation_coordinator = Mock()
        self.service.cancellation_coordinator.cancel.return_value = SimpleNamespace(
            job_id="fake-job"
        )
        self.proofs.authenticate.side_effect = (
            lambda *args: events.append("provider") or "sealed"
        )
        session = MagicMock()
        session.__enter__.side_effect = lambda: events.append("session") or session
        session.begin.return_value.__exit__.side_effect = (
            lambda *args: events.append("commit") or False
        )
        with patch.object(module, "Session", return_value=session):
            result = self.service.cancel("challenge", "assertion", True)
        self.assertEqual(events, ["provider", "session", "commit"])
        self.assertEqual(result, {"id": "fake-job", "status": "cancelled"})

    def test_status_is_minimal_and_does_not_call_provider_or_mutation(self):
        session = MagicMock()
        session.__enter__.return_value = session
        receipt = SimpleNamespace(
            job_id="fake-job",
            status="verified",
            requested_at=self.now,
            updated_at=self.now,
        )
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(
                module, "load_erasure_receipt", return_value=receipt
            ) as reader,
        ):
            result = self.service.status("fake-job", "fake-secret")
        self.assertEqual(set(result), {"id", "status", "requested_at", "updated_at"})
        reader.assert_called_once_with(
            session,
            job_id="fake-job",
            receipt_secret="fake-secret",
            clock=self.proofs.clock,
        )
        self.proofs.authenticate.assert_not_called()
        self.service.coordinator.verify.assert_not_called()

    def test_status_rejection_and_storage_failure_are_redacted(self):
        for error, expected in (
            (module.ErasureReceiptRejected("sentinel"), AuthenticationError),
            (
                module.ErasureReceiptUnavailable("sentinel"),
                module.AccountErasureUnavailable,
            ),
            (SQLAlchemyError("sentinel"), module.AccountErasureUnavailable),
        ):
            with (
                patch.object(module, "Session", return_value=MagicMock()),
                patch.object(module, "load_erasure_receipt", side_effect=error),
            ):
                with self.assertRaises(expected) as caught:
                    self.service.status("fake-job", "fake-secret")
            self.assertNotIn("sentinel", str(caught.exception))

    def setUp(self):
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.repository = Mock()
        self.proofs = Mock(
            audience="fictional", lifetime=timedelta(minutes=2), clock=lambda: self.now
        )
        self.proofs.return_value = SimpleNamespace(job_id="fake-job")
        self.service = module.AccountErasureService(self.repository, self.proofs)
        self.service.coordinator = Mock()
        self.service.coordinator.verify.return_value = SimpleNamespace(
            job_id="fake-job"
        )
        self.principal = MobilePrincipal("fake-session", 1, 2, "basic", "Fake", 1)

    def test_request_confirmation_and_safe_receipt(self):
        for value in (False, 1, "true", None):
            with self.assertRaises(InvalidArgument):
                self.service.request(self.principal, value)
        self.repository.request.assert_not_called()
        self.repository.request.return_value = SimpleNamespace(
            job_id="fake-job", receipt_secret="fake-receipt", requested_at=self.now
        )
        self.assertEqual(
            self.service.request(self.principal, True)["status"], "requested"
        )
        for error, expected in (
            (ErasureRequestRejected("sentinel"), AuthenticationError),
            (ErasureRequestUnavailable("sentinel"), module.AccountErasureUnavailable),
        ):
            self.repository.request.side_effect = error
            with self.assertRaises(expected) as caught:
                self.service.request(self.principal, True)
            self.assertNotIn("sentinel", str(caught.exception))

    def test_provider_finishes_before_session_opens_and_commit_before_return(self):
        events = []
        session = MagicMock()
        session.__enter__.return_value = session
        session.begin.return_value.__exit__.side_effect = (
            lambda *args: events.append("commit") or False
        )
        self.proofs.authenticate.side_effect = (
            lambda *args: events.append("provider") or "fake-proof"
        )
        with patch.object(
            module,
            "Session",
            side_effect=lambda *args: events.append("session") or session,
        ):
            result = self.service.verify("fake-challenge", "fake-token")
        self.assertEqual(events, ["provider", "session", "commit"])
        self.assertEqual(result, {"id": "fake-job", "status": "verified"})
        self.proofs.authenticate.assert_called_once()
        self.service.coordinator.verify.assert_called_once_with(
            session, job_id="fake-job", assertion="fake-proof"
        )

    def test_rejected_provider_never_opens_transaction(self):
        self.proofs.authenticate.side_effect = ErasureVerificationRejected("sentinel")
        with patch.object(module, "Session") as session:
            with self.assertRaises(AuthenticationError):
                self.service.verify("fake-challenge", "fake-token")
        session.assert_not_called()

    def test_uncertain_commit_is_nonretryable_and_no_success(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.begin.return_value.__exit__.side_effect = SQLAlchemyError("sentinel")
        with patch.object(module, "Session", return_value=session):
            with self.assertRaises(module.AccountErasureUnavailable) as caught:
                self.service.verify("fake-challenge", "fake-token")
        self.assertFalse(caught.exception.retryable)
        self.assertNotIn("sentinel", str(caught.exception))
        self.service.coordinator.verify.assert_called_once()

    def test_challenge_issued_after_transaction_and_person_binding_checked(self):
        events = []
        session = MagicMock()
        session.__enter__.return_value = session
        session.begin.return_value.__exit__.side_effect = (
            lambda *args: events.append("commit") or False
        )
        context = SimpleNamespace(person_id=1)
        self.proofs.begin.side_effect = lambda *args: events.append("issue") or {
            "nonce": "fake"
        }
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(
                module, "load_erasure_verification_context", return_value=context
            ),
        ):
            self.service.challenge(self.principal, "fake-job", "fake-secret")
            self.assertEqual(events, ["commit", "issue"])
            context.person_id = 99
            with self.assertRaises(AuthenticationError):
                self.service.challenge(self.principal, "fake-job", "fake-secret")
        self.proofs.begin.assert_called_once()
