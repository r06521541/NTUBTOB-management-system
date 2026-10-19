"""Cancellation fixtures never contact providers or restore account authority."""

import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from shared_lib.shared_module.erasure_cancellation_proof import FreshCancellationProof
from shared_lib.shared_module.portal_data import erasure_cancellation as cancellation

NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
JOB = "11111111-1111-4111-8111-111111111111"
GEN = "22222222-2222-4222-8222-222222222222"
SECRET = "fictional-cancellation-receipt-1234567890"


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.in_transaction.return_value = True
        self.session.new = self.session.dirty = self.session.deleted = ()
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.scalars.return_value.all.return_value = [
            "0016_erasure_cancellation"
        ]
        self.connection.scalar.return_value = False
        self.job = dict(
            id=JOB,
            target_kind="person",
            person_id=7,
            auth_identity_id=None,
            expected_generation=GEN,
            status="verified",
            irreversible_started_at=None,
            requested_at=NOW - timedelta(minutes=1),
            updated_at=NOW - timedelta(seconds=20),
            receipt_expires_at=NOW + timedelta(hours=1),
            receipt_secret_hash=hashlib.sha256(SECRET.encode()).hexdigest(),
        )
        self.identity = dict(
            id=11,
            person_id=7,
            provider="google",
            provider_subject="fictional-subject",
            status="linked",
            account_generation=GEN,
        )
        self.person = dict(id=7, account_generation=GEN)
        self.writes = []

        def execute(statement, parameters=None):
            sql = str(statement)
            result = MagicMock(rowcount=1)
            if sql.startswith(("UPDATE", "INSERT")):
                self.writes.append(sql)
            elif "FROM ntubtob.account_erasure_jobs" in sql:
                result.mappings.return_value.first.return_value = self.job
            elif "FROM ntubtob.auth_identities" in sql:
                result.mappings.return_value.first.return_value = self.identity
            elif "FROM ntubtob.people" in sql:
                result.mappings.return_value.first.return_value = self.person
            return result

        self.connection.execute.side_effect = execute
        self.proof = FreshCancellationProof(
            job_id=JOB,
            target_kind="person",
            target_generation=GEN,
            provider="google",
            provider_subject="fictional-subject",
            issued_at=NOW - timedelta(seconds=10),
            authenticated_at=NOW - timedelta(seconds=5),
            expires_at=NOW + timedelta(seconds=30),
            purpose="account_erasure_cancellation",
            audience="fictional-cancel",
        )
        self.coordinator = cancellation.ErasureCancellationCoordinator(
            verifier=lambda _: self.proof,
            audience="fictional-cancel",
            max_proof_age=timedelta(minutes=5),
            clock=lambda: NOW,
        )

    def test_cancel_detaches_and_records_without_restoring_authority(self):
        result = self.coordinator.cancel(
            self.session, job_id=JOB, assertion="fictional"
        )
        self.assertEqual(result.job_id, JOB)
        self.assertEqual(len(self.writes), 2)
        self.assertIn("person_id=NULL,auth_identity_id=NULL", self.writes[0])
        self.assertIn("'cancellation'", self.writes[1])
        self.assertNotIn("mobile_sessions", " ".join(self.writes))
        self.assertNotIn("UPDATE ntubtob.people", " ".join(self.writes))

    def test_fence_terminal_and_wrong_identity_reject_without_writes(self):
        for field, value in (
            ("status", "cancelled"),
            ("status", "completed"),
            ("irreversible_started_at", NOW),
        ):
            original = self.job[field]
            self.job[field] = value
            with self.assertRaises(cancellation.ErasureCancellationRejected):
                self.coordinator.cancel(self.session, job_id=JOB, assertion="fictional")
            self.job[field] = original
        self.identity["person_id"] = 8
        with self.assertRaises(cancellation.ErasureCancellationRejected):
            self.coordinator.cancel(self.session, job_id=JOB, assertion="fictional")
        self.assertEqual(self.writes, [])

    def test_receipt_only_context_does_not_mutate_or_select_identity(self):
        context = cancellation.load_cancellation_context(
            self.session, job_id=JOB, receipt_secret=SECRET, clock=lambda: NOW
        )
        self.assertEqual(context.target_generation, GEN)
        self.assertEqual(self.writes, [])
        self.assertFalse(
            any(
                "FROM ntubtob.auth_identities" in str(c.args[0])
                for c in self.connection.execute.call_args_list
            )
        )
        with self.assertRaises(cancellation.ErasureCancellationRejected):
            cancellation.load_cancellation_context(
                self.session, job_id=JOB, receipt_secret="x" * 40, clock=lambda: NOW
            )

    def test_expired_receipt_blocks_even_fresh_provider_proof(self):
        self.job["receipt_expires_at"] = NOW
        with self.assertRaises(cancellation.ErasureCancellationRejected):
            self.coordinator.cancel(self.session, job_id=JOB, assertion="fictional")
        self.assertEqual(self.writes, [])

    def test_clock_failures_are_fixed_and_never_mutate(self):
        for clock in (
            MagicMock(side_effect=RuntimeError("fictional-private-clock")),
            lambda: None,
        ):
            self.coordinator.clock = clock
            for action in (
                lambda: self.coordinator.cancel(
                    self.session, job_id=JOB, assertion="fictional"
                ),
                lambda: cancellation.load_cancellation_context(
                    self.session, job_id=JOB, receipt_secret=SECRET, clock=clock
                ),
            ):
                with self.assertRaises(
                    cancellation.ErasureCancellationUnavailable
                ) as caught:
                    action()
                self.assertEqual(str(caught.exception), "invalid_cancellation_clock")
        self.assertEqual(self.writes, [])
