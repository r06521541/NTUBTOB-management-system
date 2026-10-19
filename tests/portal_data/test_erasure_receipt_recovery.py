"""Fictional local proofs; optional isolated PostgreSQL, never provider I/O."""

import hashlib
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ReleaseSavepointClause, SavepointClause

from shared_lib.shared_module.portal_data import erasure_receipt_recovery as recovery
from shared_lib.shared_module.portal_data.erasure_receipt import load_erasure_receipt
from shared_lib.shared_module.portal_data.erasure_request import (
    AccountErasureRequestRepository,
)
from shared_lib.shared_module.portal_data.runtime import (
    ADMIN_LOCK_KEY,
    EVENT_SNAPSHOT_LOCK_KEY,
)
from tests.portal_data import test_erasure_cancellation_schema as fixture

NOW = datetime(2035, 1, 1, 0, 2, tzinfo=timezone.utc)
EARLIER = NOW - timedelta(minutes=2)
ISSUED = NOW - timedelta(seconds=10)
KEY = b"fictional-recovery-receipt-key-only-12345"
AUDIENCE = "fictional-erasure-recovery"
SUBJECT = "fictional-recovery-subject"
ASSERTION = "fictional-recovery-envelope-" + "a" * 100
JOB = "a1111111-1111-4111-8111-111111111111"
GENERATION = "b1111111-1111-4111-8111-111111111111"


def proof(**changes):
    return replace(
        recovery.FreshReceiptRecoveryProof(
            "apple",
            SUBJECT,
            ISSUED,
            NOW,
            NOW + timedelta(minutes=1),
            recovery.RECEIPT_RECOVERY_PURPOSE,
            AUDIENCE,
        ),
        **changes,
    )


def original_secret(job_id=JOB):
    return AccountErasureRequestRepository(None, KEY, lambda: None)._secret(job_id)


def read_or_fixture_savepoint(statement):
    # The opt-in PG fixture joins an outer transaction via SQLAlchemy savepoints.
    # Allow only its typed begin/release clauses, never arbitrary control/DML SQL.
    return type(statement) in (SavepointClause, ReleaseSavepointClause) or str(
        statement
    ).startswith("SELECT")


class RecoveryTests(unittest.TestCase):
    def test_fixture_sql_allowlist_accepts_typed_savepoints_but_not_mutations(self):
        for statement in (
            text("SELECT 1"),
            SavepointClause("fixture"),
            ReleaseSavepointClause("fixture"),
        ):
            self.assertTrue(read_or_fixture_savepoint(statement))
        for sql in (
            "INSERT INTO fictional VALUES (1)",
            "UPDATE fictional SET id=1",
            "DELETE FROM fictional",
            "TRUNCATE fictional",
            "CREATE TABLE fictional (id int)",
            "SAVEPOINT arbitrary",
            "COMMIT",
            "ROLLBACK",
        ):
            self.assertFalse(read_or_fixture_savepoint(text(sql)))

    def setUp(self):
        self.engine = Mock(spec=Engine)
        self.engine.dialect = SimpleNamespace(name="postgresql")
        self.proof = proof()
        self.session = MagicMock()
        self.session.in_transaction.return_value = True
        self.session.new = self.session.dirty = self.session.deleted = set()
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.scalars.return_value.all.return_value = [
            "0018_erasure_privacy_mutation"
        ]
        self.connection.scalar.return_value = False
        self.identity = dict(
            id=2,
            person_id=1,
            status="blocked",
            account_generation=GENERATION,
            created_at=EARLIER,
            updated_at=EARLIER,
        )
        self.person = dict(
            id=1, account_generation=GENERATION, created_at=EARLIER, updated_at=EARLIER
        )
        self.job = dict(
            id=JOB,
            target_kind="person",
            person_id=1,
            auth_identity_id=None,
            expected_generation=GENERATION,
            status="requested",
            requested_at=EARLIER,
            updated_at=EARLIER,
            receipt_expires_at=NOW + timedelta(hours=1),
            receipt_secret_hash=hashlib.sha256(
                original_secret().encode("ascii")
            ).hexdigest(),
        )
        self.verifier = Mock(side_effect=lambda value: self.proof)
        self.repo = recovery.ReceiptRecoveryRepository(
            self.engine,
            KEY,
            verifier=self.verifier,
            audience=AUDIENCE,
            clock=lambda: NOW,
        )
        self.connection.execute.side_effect = self.execute
        patcher = patch.object(recovery, "Session")
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.factory.return_value.__enter__.return_value = self.session

    def execute(self, statement, parameters=None):
        sql = str(statement)
        if "FROM ntubtob.auth_identities" in sql:
            self.assertEqual(
                parameters,
                dict(provider=self.proof.provider, subject=self.proof.provider_subject),
            )
            row = self.identity
        elif "FROM ntubtob.people" in sql:
            row = self.person
        elif "FROM ntubtob.account_erasure_jobs" in sql:
            row = self.job
        else:
            self.assertIn("pg_advisory_xact_lock", sql)
            return Mock()
        result = Mock()
        result.mappings.return_value.one_or_none.return_value = row
        return result

    def recover(self):
        return self.repo.recover(ASSERTION)

    def test_live_states_recover_original_receipt_without_mutating_rows(self):
        for kind in ("person", "pending_identity"):
            for status in ("requested", "verified", "processing", "needs_attention"):
                with self.subTest(kind=kind, status=status):
                    self.identity["person_id"] = 1 if kind == "person" else None
                    self.job.update(
                        target_kind=kind,
                        person_id=self.identity["person_id"],
                        auth_identity_id=2 if kind == "pending_identity" else None,
                        status=status,
                    )
                    before = deepcopy((self.identity, self.person, self.job))
                    result = self.recover()
                    self.assertEqual(result.receipt_secret, original_secret())
                    self.assertEqual(result.status, status)
                    self.assertEqual(
                        result.receipt_expires_at, self.job["receipt_expires_at"]
                    )
                    self.assertEqual(before, (self.identity, self.person, self.job))

    def test_verifier_before_transaction_canonical_locks_and_select_only(self):
        def verify(value):
            self.factory.assert_not_called()
            return self.proof

        self.verifier.side_effect = verify
        self.recover()
        calls = self.connection.execute.call_args_list
        self.assertEqual(
            [call.args[1] for call in calls[:2]],
            [{"key": ADMIN_LOCK_KEY}, {"key": EVENT_SNAPSHOT_LOCK_KEY}],
        )
        self.assertTrue(all(str(call.args[0]).startswith("SELECT") for call in calls))
        self.assertTrue(all("FOR UPDATE" in str(call.args[0]) for call in calls[2:]))
        self.assertFalse(any("attempt" in str(call.args[0]) for call in calls))
        self.session.execute.assert_not_called()
        self.session.add.assert_not_called()
        self.session.flush.assert_not_called()

    def test_proof_and_result_are_frozen_secret_free_repr(self):
        result = self.recover()
        self.assertIs(type(result), recovery.RecoveredErasureReceipt)
        for value, attr, secret in (
            (result, "status", result.receipt_secret),
            (self.proof, "provider", SUBJECT),
        ):
            self.assertNotIn(secret, repr(value))
            with self.assertRaises(FrozenInstanceError):
                setattr(value, attr, "changed")

    def test_invalid_configuration_rejects_without_opening_session(self):
        values = dict(
            engine=self.engine,
            key=KEY,
            verifier=self.verifier,
            audience=AUDIENCE,
            clock=lambda: NOW,
        )
        for changes in (
            {"engine": None},
            {"engine": self.connection},
            {"key": b"short"},
            {"key": bytearray(KEY)},
            {"verifier": None},
            {"clock": None},
            {"audience": ""},
            {"audience": "a" * 201},
        ):
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                recovery.ReceiptRecoveryRepository(**dict(values, **changes))
        self.factory.assert_not_called()

    def test_wrong_proof_types_purposes_and_unbounded_input_reject_before_session(self):
        for invalid in (
            True,
            None,
            object(),
            SimpleNamespace(**vars(proof())),
            proof(purpose="account_erasure_restricted_intent"),
            proof(purpose="account_erasure_receipt_verification"),
            proof(purpose="account_erasure_cancellation"),
            proof(audience="wrong"),
            proof(provider="unknown"),
            proof(provider_subject=" "),
            proof(provider_subject="a" * 256),
            proof(issued_at=NOW.replace(tzinfo=None)),
            proof(issued_at=NOW + timedelta(seconds=1)),
            proof(expires_at=NOW),
            proof(issued_at=NOW - timedelta(minutes=5)),
        ):
            self.proof = invalid
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                self.recover()
        self.proof = proof()
        for value in (None, True, "", "x" * 79, "x" * 4097):
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                self.repo.recover(value)
        self.factory.assert_not_called()

    def test_issue_must_follow_job_and_current_rows_including_equal_timestamps(self):
        for row, field in (
            (self.identity, "created_at"),
            (self.identity, "updated_at"),
            (self.person, "created_at"),
            (self.person, "updated_at"),
            (self.job, "requested_at"),
        ):
            for value in (ISSUED, ISSUED + timedelta(microseconds=1)):
                old = row[field]
                row[field] = value
                with self.assertRaises(recovery.ReceiptRecoveryRejected):
                    self.recover()
                row[field] = old

    def test_same_subject_rebuilt_generation_or_remap_cannot_reuse_old_proof(self):
        new_generation = str(uuid4())
        self.identity.update(
            id=9,
            person_id=None,
            account_generation=new_generation,
            created_at=NOW,
            updated_at=NOW,
        )
        self.job.update(
            auth_identity_id=9,
            person_id=None,
            target_kind="pending_identity",
            expected_generation=new_generation,
            requested_at=NOW,
        )
        with self.assertRaises(recovery.ReceiptRecoveryRejected):
            self.recover()
        # Even a remap into an older job is rejected by current identity updated_at.
        self.identity.update(person_id=1, created_at=EARLIER)
        self.job.update(
            auth_identity_id=None,
            person_id=1,
            target_kind="person",
            expected_generation=GENERATION,
            requested_at=EARLIER,
        )
        with self.assertRaises(recovery.ReceiptRecoveryRejected):
            self.recover()

    def test_missing_detached_mismatched_and_terminal_targets_reject(self):
        original = deepcopy(self.job)
        for changes in (
            {"person_id": None},
            {"person_id": 7},
            {"auth_identity_id": 2},
            {"expected_generation": str(uuid4())},
            {"target_kind": "pending_identity"},
            *(
                {"status": status}
                for status in ("cancelled", "online_completed", "completed", "unknown")
            ),
        ):
            self.job = dict(original, **changes)
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                self.recover()
        self.job = original
        for attribute in ("identity", "person", "job"):
            old = getattr(self, attribute)
            setattr(self, attribute, None)
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                self.recover()
            setattr(self, attribute, old)

    def test_lock_wait_rechecks_proof_and_receipt_expiry(self):
        original = self.execute
        for expires in ("proof", "receipt"):
            self.repo.clock = lambda: NOW
            self.job["receipt_expires_at"] = NOW + timedelta(seconds=5)
            deadline = (
                self.proof.expires_at
                if expires == "proof"
                else self.job["receipt_expires_at"]
            )

            def execute(statement, parameters=None):
                result = original(statement, parameters)
                if "FROM ntubtob.account_erasure_jobs" in str(statement):
                    self.repo.clock = lambda: deadline
                return result

            self.connection.execute.side_effect = execute
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                self.recover()

    def test_known_revisions_each_work_but_ambiguous_rows_fail_closed(self):
        for revision in (
            "0015_account_generations",
            "0016_erasure_cancellation",
            "0017_erasure_work_items",
            "0018_erasure_privacy_mutation",
        ):
            self.connection.scalars.return_value.all.return_value = [revision]
            self.assertEqual(self.recover().job_id, JOB)
        from sqlalchemy.exc import MultipleResultsFound

        original = self.execute

        def execute(statement, parameters=None):
            if "FROM ntubtob.auth_identities" in str(statement):
                result = Mock()
                result.mappings.return_value.one_or_none.side_effect = (
                    MultipleResultsFound("private-sentinel")
                )
                return result
            return original(statement, parameters)

        self.connection.execute.side_effect = execute
        with self.assertRaisesRegex(
            recovery.ReceiptRecoveryUnavailable,
            "^receipt_recovery_storage_unavailable$",
        ):
            self.recover()

    def test_schema_rls_isolation_and_dirty_session_fail_closed(self):
        for revisions in (
            [],
            ["0014_account_erasure_ledger"],
            ["unknown"],
            ["0016_erasure_cancellation", "0018_erasure_privacy_mutation"],
        ):
            self.connection.scalars.return_value.all.return_value = revisions
            with self.assertRaises(recovery.ReceiptRecoveryUnavailable):
                self.recover()
        self.connection.scalars.return_value.all.return_value = [
            "0018_erasure_privacy_mutation"
        ]
        self.connection.scalar.return_value = True
        with self.assertRaises(recovery.ReceiptRecoveryUnavailable):
            self.recover()
        self.connection.scalar.return_value = False
        for autocommit in (True, None):
            self.connection.connection.dbapi_connection.autocommit = autocommit
            with self.assertRaises(recovery.ReceiptRecoveryUnavailable):
                self.recover()
        self.connection.connection.dbapi_connection.autocommit = False
        self.session.dirty = {object()}
        with self.assertRaises(recovery.ReceiptRecoveryUnavailable):
            self.recover()
        self.session.dirty = set()
        self.connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaises(recovery.ReceiptRecoveryUnavailable):
            self.recover()

    def test_key_mismatch_malformed_hash_and_expiry_do_not_rotate(self):
        for changes in (
            {"receipt_secret_hash": "b" * 64},
            {"receipt_secret_hash": "private-sentinel"},
            {"receipt_expires_at": NOW},
        ):
            old = deepcopy(self.job)
            self.job.update(changes)
            with self.assertRaisesRegex(
                recovery.ReceiptRecoveryRejected, "^receipt_recovery_unavailable$"
            ):
                self.recover()
            self.job = old

    def test_transaction_and_verifier_failures_do_not_expose_input_or_return_receipt(
        self,
    ):
        for boundary in ("verifier", "select", "commit"):
            with self.subTest(boundary=boundary):
                failure = SQLAlchemyError("private-sentinel " + SUBJECT + ASSERTION)
                if boundary == "verifier":
                    self.verifier.side_effect = failure
                elif boundary == "select":
                    self.connection.execute.side_effect = failure
                else:
                    self.session.begin.return_value.__exit__.side_effect = failure
                with self.assertRaises(
                    (
                        recovery.ReceiptRecoveryRejected,
                        recovery.ReceiptRecoveryUnavailable,
                    )
                ) as raised:
                    self.recover()
                self.assertNotIn("private-sentinel", str(raised.exception))
                self.assertNotIn(SUBJECT, str(raised.exception))
                self.assertIsNone(raised.exception.__cause__)
                self.verifier.side_effect = lambda value: self.proof
                self.connection.execute.side_effect = self.execute


@unittest.skipUnless(
    fixture.DATABASE_URL, "dedicated isolated erasure URL not configured"
)
class RecoveryPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        fixture.ErasureCancellationPostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        fixture.ErasureCancellationPostgresTests.tearDownClass.__func__
    )
    upgrade = fixture.ErasureCancellationPostgresTests.upgrade
    job = fixture.ErasureCancellationPostgresTests.job
    update = fixture.ErasureCancellationPostgresTests.update

    def setUp(self):
        fixture.ErasureCancellationPostgresTests.setUp(self)
        self.upgrade()
        subject, generation = self.connection.execute(
            text(
                "SELECT provider_subject,account_generation FROM ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.identity},
        ).one()
        self.proof = proof(provider_subject=subject)
        self.job_id = str(uuid4())
        self.job(
            id=self.job_id,
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.identity,
            expected_generation=str(generation),
            receipt_secret_hash=hashlib.sha256(
                original_secret(self.job_id).encode("ascii")
            ).hexdigest(),
        )
        self.repo = recovery.ReceiptRecoveryRepository(
            self.engine,
            KEY,
            verifier=lambda value: self.proof,
            audience=AUDIENCE,
            clock=lambda: NOW,
        )
        patcher = patch.object(
            recovery,
            "Session",
            side_effect=lambda engine: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def snapshot(self):
        return [
            self.connection.execute(
                text(f"SELECT * FROM ntubtob.{table} ORDER BY 1")
            ).all()
            for table in (
                "account_erasure_jobs",
                "account_erasure_request_attempts",
                "auth_identities",
                "people",
            )
        ]

    def test_pending_every_live_status_has_identical_receipt_and_no_dml(self):
        for status in ("requested", "verified", "processing", "needs_attention"):
            if status == "verified":
                self.update(
                    self.job_id, status=status, verified_at=EARLIER, updated_at=EARLIER
                )
            elif status != "requested":
                self.update(self.job_id, status=status)
            before = self.snapshot()
            with patch.object(
                self.connection, "execute", wraps=self.connection.execute
            ) as execute:
                result = self.repo.recover(ASSERTION)
            self.assertEqual(result.status, status)
            self.assertEqual(result.receipt_secret, original_secret(self.job_id))
            self.assertEqual(before, self.snapshot())
            self.assertTrue(
                all(
                    read_or_fixture_savepoint(call.args[0])
                    for call in execute.call_args_list
                )
            )

    def test_same_subject_delete_rebuild_and_new_job_reject_old_proof(self):
        self.update(
            self.job_id,
            status="cancelled",
            cancelled_at=NOW,
            updated_at=NOW,
            auth_identity_id=None,
        )
        self.connection.execute(
            text("DELETE FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.identity},
        )
        row = self.connection.execute(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at) "
                "VALUES ('apple',:subject,'pending',:now,:now) RETURNING id,account_generation"
            ),
            {"subject": self.proof.provider_subject, "now": NOW},
        ).one()
        new_job = str(uuid4())
        self.job(
            id=new_job,
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=row.id,
            expected_generation=str(row.account_generation),
            requested_at=NOW,
            updated_at=NOW,
            receipt_secret_hash=hashlib.sha256(
                original_secret(new_job).encode("ascii")
            ).hexdigest(),
        )
        before = self.snapshot()
        with self.assertRaises(recovery.ReceiptRecoveryRejected):
            self.repo.recover(ASSERTION)
        self.assertEqual(before, self.snapshot())

    def test_remap_after_proof_cannot_recover_an_older_person_job(self):
        self.update(
            self.job_id,
            status="cancelled",
            cancelled_at=NOW,
            updated_at=NOW,
            auth_identity_id=None,
        )
        generation = self.connection.scalar(
            text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
            {"id": self.person},
        )
        other_job = str(uuid4())
        self.job(
            id=other_job,
            expected_generation=str(generation),
            receipt_secret_hash=hashlib.sha256(
                original_secret(other_job).encode("ascii")
            ).hexdigest(),
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='blocked',updated_at=:now WHERE id=:id"
            ),
            {"person": self.person, "now": NOW, "id": self.identity},
        )
        before = self.snapshot()
        with self.assertRaises(recovery.ReceiptRecoveryRejected):
            self.repo.recover(ASSERTION)
        self.assertEqual(before, self.snapshot())
        self.proof = replace(
            self.proof,
            issued_at=NOW + timedelta(seconds=1),
            authenticated_at=NOW + timedelta(seconds=1),
        )
        self.repo.clock = lambda: NOW + timedelta(seconds=1)
        self.assertEqual(self.repo.recover(ASSERTION).job_id, other_job)

    def test_after_target_deletion_only_original_receipt_still_reads(self):
        receipt = self.repo.recover(ASSERTION)
        self.update(
            self.job_id, status="verified", verified_at=EARLIER, updated_at=EARLIER
        )
        self.update(self.job_id, status="processing", irreversible_started_at=EARLIER)
        self.update(
            self.job_id,
            status="online_completed",
            online_completed_at=NOW,
            updated_at=NOW,
            auth_identity_id=None,
        )
        self.connection.execute(
            text("DELETE FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.identity},
        )
        with self.assertRaises(recovery.ReceiptRecoveryRejected):
            self.repo.recover(ASSERTION)
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            status = load_erasure_receipt(
                session,
                job_id=receipt.job_id,
                receipt_secret=receipt.receipt_secret,
                clock=lambda: NOW,
            )
        self.assertEqual(status.status, "online_completed")

    def test_wrong_proof_equal_time_expiry_and_key_leave_every_row_unchanged(self):
        before = self.snapshot()
        original = self.proof
        for changes in (
            {"purpose": "account_erasure_restricted_intent"},
            {"issued_at": EARLIER},
            {"expires_at": NOW},
            {"provider_subject": "missing-fictional-subject"},
        ):
            self.proof = replace(original, **changes)
            with self.assertRaises(recovery.ReceiptRecoveryRejected):
                self.repo.recover(ASSERTION)
            self.assertEqual(before, self.snapshot())
        self.proof = original
        self.repo._key = b"different-fictional-receipt-key-12345"
        with self.assertRaises(recovery.ReceiptRecoveryRejected):
            self.repo.recover(ASSERTION)
        self.assertEqual(before, self.snapshot())

    def test_two_same_provider_identities_resolve_only_the_verified_subject(self):
        subject, generation = self.connection.execute(
            text(
                "SELECT provider_subject,account_generation FROM ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.other_identity},
        ).one()
        other_job = str(uuid4())
        self.job(
            id=other_job,
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.other_identity,
            expected_generation=str(generation),
            receipt_secret_hash=hashlib.sha256(
                original_secret(other_job).encode("ascii")
            ).hexdigest(),
        )
        before = self.snapshot()
        self.assertEqual(self.repo.recover(ASSERTION).job_id, self.job_id)
        self.proof = replace(self.proof, provider_subject=subject)
        self.assertEqual(self.repo.recover(ASSERTION).job_id, other_job)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
