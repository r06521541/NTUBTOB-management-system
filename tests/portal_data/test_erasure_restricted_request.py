"""Fictional restricted intent transactions, no provider/network or deletion."""

import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared_lib.shared_module.erasure_restricted_proof import (
    RESTRICTED_ERASURE_PROOF_PURPOSE,
    FreshRestrictedErasureProof,
)
from shared_lib.shared_module.portal_data import (
    erasure_restricted_request as restricted,
)
from tests.portal_data import test_erasure_cancellation_schema as fixture
from tests.portal_data.test_erasure_request import KEY, NOW, plan


@unittest.skipUnless(
    fixture.DATABASE_URL, "dedicated isolated erasure URL not configured"
)
class RestrictedRequestPostgresTests(unittest.TestCase):
    def test_approved_restricted_receipt_keeps_180_days_after_due(self):
        from shared_lib.shared_module.portal_data.erasure_composition import (
            ErasurePlanPolicy,
        )
        from shared_lib.shared_module.portal_data.erasure_receipt import (
            ErasureReceiptRejected,
            load_erasure_receipt,
        )

        policy = ErasurePlanPolicy.initial_request(NOW)
        self.repo.plan_builder = lambda **kw: replace(plan(), **vars(policy))
        receipt = self.repo.request_restricted("fictional-proof")
        due, expires = self.connection.execute(
            text(
                "SELECT fulfillment_due_at,receipt_expires_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
            ),
            {"id": receipt.job_id},
        ).one()
        self.assertEqual(due, NOW + timedelta(days=30))
        self.assertEqual(expires, NOW + timedelta(days=180))
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
                clock=lambda: NOW + timedelta(days=31),
            )
            self.assertEqual(status.status, "requested")
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            with self.assertRaises(ErasureReceiptRejected):
                load_erasure_receipt(
                    session,
                    job_id=receipt.job_id,
                    receipt_secret=receipt.receipt_secret,
                    clock=lambda: expires,
                )

    setUpClass = classmethod(
        fixture.ErasureCancellationPostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        fixture.ErasureCancellationPostgresTests.tearDownClass.__func__
    )
    upgrade = fixture.ErasureCancellationPostgresTests.upgrade

    def setUp(self):
        fixture.ErasureCancellationPostgresTests.setUp(self)
        self.upgrade()
        provider, subject = self.connection.execute(
            text(
                "SELECT provider,provider_subject FROM ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.identity},
        ).one()
        self.proof = FreshRestrictedErasureProof(
            str(uuid4()),
            provider,
            subject,
            NOW,
            NOW + timedelta(minutes=5),
            RESTRICTED_ERASURE_PROOF_PURPOSE,
            "fictional-erasure",
        )
        self.repo = restricted.RestrictedErasureRequestRepository(
            self.engine,
            KEY,
            plan,
            verifier=lambda assertion: self.proof,
            audience="fictional-erasure",
            clock=lambda: NOW,
        )
        replacement = patch.object(
            restricted,
            "Session",
            side_effect=lambda engine: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        )
        replacement.start()
        self.addCleanup(replacement.stop)

    def count(self, table):
        return self.connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))

    def test_pending_request_is_intent_only_and_attempt_replays_stably(self):
        result = self.repo.request_restricted("fictional-proof")
        self.assertEqual(result, self.repo.request_restricted("fictional-proof"))
        row = self.connection.execute(
            text(
                "SELECT status,target_kind,auth_identity_id,person_id FROM ntubtob.account_erasure_jobs WHERE id=:id"
            ),
            {"id": result.job_id},
        ).one()
        self.assertEqual(
            tuple(row), ("requested", "pending_identity", self.identity, None)
        )
        self.assertEqual(self.count("account_erasure_request_attempts"), 1)

    def test_cancelled_attempt_cannot_create_new_job_but_fresh_attempt_can(self):
        first = self.repo.request_restricted("fictional-proof")
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',auth_identity_id=NULL,"
                "cancelled_at=:now,updated_at=:now WHERE id=:id"
            ),
            {"id": first.job_id, "now": NOW},
        )
        with self.assertRaises(restricted.ErasureRequestRejected):
            self.repo.request_restricted("fictional-proof")
        self.proof = replace(self.proof, attempt_id=str(uuid4()))
        second = self.repo.request_restricted("fictional-proof")
        self.assertNotEqual(first.job_id, second.job_id)
        self.assertEqual(self.count("account_erasure_request_attempts"), 2)

    def test_new_attempt_coalesces_and_both_remain_bound(self):
        first = self.repo.request_restricted("fictional-proof")
        self.proof = replace(self.proof, attempt_id=str(uuid4()))
        self.assertEqual(first, self.repo.request_restricted("fictional-proof"))
        self.assertEqual(self.count("account_erasure_request_attempts"), 2)
        self.assertEqual(self.count("account_erasure_jobs"), 1)

    def test_blocked_linked_account_does_not_need_application_session(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET status='blocked',person_id=:person WHERE id=:id"
            ),
            {"person": self.person, "id": self.identity},
        )
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_status='blocked' WHERE id=:id"),
            {"id": self.person},
        )
        result = self.repo.request_restricted("fictional-proof")
        row = self.connection.execute(
            text(
                "SELECT target_kind,person_id,auth_identity_id FROM ntubtob.account_erasure_jobs WHERE id=:id"
            ),
            {"id": result.job_id},
        ).one()
        self.assertEqual(tuple(row), ("person", self.person, None))

    def test_unknown_provider_subject_and_expired_proof_create_nothing(self):
        original = self.proof
        for changes in (
            {"provider_subject": "unknown-fictional"},
            {"expires_at": NOW},
            {"audience": "wrong"},
        ):
            self.proof = replace(original, **changes)
            with self.assertRaises(restricted.ErasureRequestRejected):
                self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.count("account_erasure_jobs"), 0)
        self.assertEqual(self.count("account_erasure_request_attempts"), 0)

    def test_same_attempt_cannot_change_subject_or_expiry(self):
        first = self.repo.request_restricted("fictional-proof")
        original = self.proof
        for changes in (
            {"provider_subject": "different-subject"},
            {"expires_at": NOW + timedelta(minutes=4)},
        ):
            self.proof = replace(original, **changes)
            with self.assertRaises(restricted.ErasureRequestRejected):
                self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.count("account_erasure_jobs"), 1)
        self.assertEqual(self.count("account_erasure_request_attempts"), 1)
        self.proof = original
        self.assertEqual(first, self.repo.request_restricted("fictional-proof"))

    def test_pending_to_person_remap_rejects_old_attempt(self):
        self.repo.request_restricted("fictional-proof")
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET status='linked',person_id=:person WHERE id=:id"
            ),
            {"person": self.person, "id": self.identity},
        )
        with self.assertRaisesRegex(
            restricted.ErasureRequestRejected, "request_scope_changed"
        ):
            self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.count("account_erasure_jobs"), 1)

    def test_expiry_during_plan_rolls_back_everything(self):
        def slow_plan(**kwargs):
            self.repo.clock = lambda: NOW + timedelta(minutes=5)
            return plan(**kwargs)

        self.repo.plan_builder = slow_plan
        with self.assertRaises(restricted.ErasureRequestRejected):
            self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.count("account_erasure_jobs"), 0)
        self.assertEqual(self.count("account_erasure_request_attempts"), 0)

    def test_changed_key_does_not_issue_receipt_or_new_attempt(self):
        self.repo.request_restricted("fictional-proof")
        self.repo._key = b"another-fictional-key" * 2
        with self.assertRaises(restricted.ErasureRequestRejected):
            self.repo.request_restricted("fictional-proof")
        self.proof = replace(self.proof, attempt_id=str(uuid4()))
        with self.assertRaisesRegex(
            restricted.ErasureRequestRejected, "receipt_key_mismatch"
        ):
            self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.count("account_erasure_request_attempts"), 1)

    def test_unexpected_plan_failure_is_fixed_and_rolls_back(self):
        def broken_plan(**kwargs):
            raise RuntimeError("private-sentinel")

        self.repo.plan_builder = broken_plan
        with self.assertRaises(restricted.ErasureRequestUnavailable) as raised:
            self.repo.request_restricted("fictional-proof")
        self.assertNotIn("private-sentinel", str(raised.exception))
        self.assertEqual(self.count("account_erasure_jobs"), 0)

    def test_receipt_expiring_during_job_insert_rolls_back_both_rows(self):
        self.assert_expiry_after_insert("account_erasure_jobs")

    def test_receipt_expiring_during_attempt_insert_rolls_back_both_rows(self):
        self.assert_expiry_after_insert("account_erasure_request_attempts")

    def assert_expiry_after_insert(self, table):
        self.repo.plan_builder = lambda **kwargs: replace(
            plan(), receipt_expires_at=NOW + timedelta(seconds=1)
        )
        original = self.connection.execute

        def execute(statement, *args, **kwargs):
            result = original(statement, *args, **kwargs)
            if str(statement).startswith("INSERT INTO ntubtob." + table + " "):
                self.repo.clock = lambda: NOW + timedelta(seconds=2)
            return result

        with patch.object(self.connection, "execute", side_effect=execute):
            with self.assertRaisesRegex(
                restricted.ErasureRequestRejected, "request_expired"
            ):
                self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.count("account_erasure_jobs"), 0)
        self.assertEqual(self.count("account_erasure_request_attempts"), 0)


@unittest.skipUnless(fixture.DATABASE_URL, "isolated erasure URL required")
class RestrictedCustodyPostgresTests(unittest.TestCase):
    setUpClass = RestrictedRequestPostgresTests.__dict__["setUpClass"]
    tearDownClass = RestrictedRequestPostgresTests.__dict__["tearDownClass"]
    upgrade = RestrictedRequestPostgresTests.upgrade
    count = RestrictedRequestPostgresTests.count

    def setUp(self):
        from alembic import command
        from alembic.config import Config

        from tests.portal_data.test_erasure_plan_store import fictional_store

        RestrictedRequestPostgresTests.setUp(self)
        config = Config(str(fixture.ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0018_erasure_privacy_mutation")
        self.captures = []
        self.store = fictional_store()
        self.repo.plan_builder = self.capture
        self.repo.sealed_plan_store = self.store

    def capture(self, *, connection, job_id, identity_id, **values):
        from shared_lib.shared_module.erasure_restore_binding import RestoreBindingCodec
        from shared_lib.shared_module.portal_data.erasure_fulfillment import (
            capture_pending_snapshot,
        )
        from shared_lib.shared_module.portal_data.erasure_request import (
            CapturedErasureRequestPlan,
        )

        self.assertIs(connection, self.connection)
        self.assertIsNone(
            connection.scalar(
                text("SELECT id FROM ntubtob.account_erasure_jobs WHERE id=:job"),
                {"job": job_id},
            )
        )
        codec = RestoreBindingCodec(
            namespace="00000000-0000-4000-8000-000000000003",
            active_key="fictional",
            keys={"fictional": b"F" * 32},
        )
        with (
            Session(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            self.assertIs(session.connection(), connection)
            snapshot = capture_pending_snapshot(
                session,
                identity_id,
                reviewed_audits=(),
                restore_binding=codec.bind(
                    provider=self.proof.provider,
                    audience=self.proof.audience,
                    subject=self.proof.provider_subject,
                    generation=values["target_generation"],
                ),
            )
        self.captures.append(snapshot)
        return CapturedErasureRequestPlan(
            replace(plan(), scope_hash=snapshot.scope_hash), snapshot
        )

    def test_pending_capture_and_attempt_custody_are_atomic_coalesced_and_reloadable(
        self,
    ):
        from tests.portal_data.test_erasure_plan_store import fictional_store

        receipt = self.repo.request_restricted("fictional-proof")
        self.assertEqual(self.repo.request_restricted("fictional-proof"), receipt)
        self.proof = replace(self.proof, attempt_id=str(uuid4()))
        self.assertEqual(self.repo.request_restricted("fictional-proof"), receipt)
        self.assertEqual(len(self.captures), 1)
        self.assertEqual(
            fictional_store().load(self.connection, receipt.job_id), self.captures[0]
        )
        self.assertEqual(
            [
                self.count(t)
                for t in (
                    "account_erasure_jobs",
                    "account_erasure_sealed_plans",
                    "account_erasure_request_attempts",
                )
            ],
            [1, 1, 2],
        )

    def test_after_storage_or_attempt_expiry_rolls_back_all_three_rows(self):
        original = self.connection.execute
        for target in (
            "account_erasure_sealed_plans",
            "account_erasure_request_attempts",
        ):
            self.repo.clock = lambda: NOW

            def execute(statement, *args, **kwargs):
                result = original(statement, *args, **kwargs)
                if str(statement).startswith("INSERT INTO ntubtob." + target + " "):
                    self.repo.clock = lambda: NOW + timedelta(minutes=5)
                return result

            with patch.object(self.connection, "execute", side_effect=execute):
                with self.assertRaises(restricted.ErasureRequestRejected):
                    self.repo.request_restricted("fictional-proof")
            self.assertEqual(
                [
                    self.count(t)
                    for t in (
                        "account_erasure_jobs",
                        "account_erasure_sealed_plans",
                        "account_erasure_request_attempts",
                    )
                ],
                [0, 0, 0],
            )

    def test_failed_readback_rolls_back_job_plan_and_attempt(self):
        with patch.object(
            self.store, "load", side_effect=RuntimeError("private-sentinel")
        ):
            with self.assertRaises(restricted.ErasureRequestUnavailable) as raised:
                self.repo.request_restricted("fictional-proof")
        self.assertNotIn("private-sentinel", str(raised.exception))
        self.assertEqual(
            [
                self.count(t)
                for t in (
                    "account_erasure_jobs",
                    "account_erasure_sealed_plans",
                    "account_erasure_request_attempts",
                )
            ],
            [0, 0, 0],
        )

    def test_cancelled_attempt_never_reuses_plan_but_new_intent_gets_new_binding(self):
        first = self.repo.request_restricted("fictional-proof")
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',auth_identity_id=NULL,cancelled_at=:now,updated_at=:now WHERE id=:id"
            ),
            {"id": first.job_id, "now": NOW},
        )
        with self.assertRaisesRegex(
            restricted.ErasureRequestRejected, "attempt_already_consumed"
        ):
            self.repo.request_restricted("fictional-proof")
        self.assertEqual(len(self.captures), 1)
        self.proof = replace(self.proof, attempt_id=str(uuid4()))
        second = self.repo.request_restricted("fictional-proof")
        self.assertNotEqual(first.job_id, second.job_id)
        self.assertEqual(
            [
                self.count(t)
                for t in (
                    "account_erasure_jobs",
                    "account_erasure_sealed_plans",
                    "account_erasure_request_attempts",
                )
            ],
            [2, 2, 2],
        )
