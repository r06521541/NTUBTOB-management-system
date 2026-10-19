"""Real disposable PostgreSQL composition, fictional provider assertions only."""

import hashlib
import unittest
from datetime import timedelta
from unittest.mock import Mock

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared_lib.shared_module.erasure_cancellation_proof import CancellationProofService
from shared_lib.shared_module.mobile_api import VerifiedAssertion
from shared_lib.shared_module.portal_data.erasure_cancellation import (
    ErasureCancellationCoordinator,
    ErasureCancellationRejected,
    load_cancellation_context,
)
from shared_lib.shared_module.portal_data.erasure_receipt import load_erasure_receipt
from tests.portal_data import test_erasure_cancellation_schema as fixture

SECRET = "fictional-only-cancellation-receipt-1234567890"


@unittest.skipUnless(fixture.DATABASE_URL, "isolated ledger URL not configured")
class CancellationIntegrationTests(unittest.TestCase):
    job = fixture.ErasureCancellationPostgresTests.job
    upgrade = fixture.ErasureCancellationPostgresTests.upgrade

    @classmethod
    def setUpClass(cls):
        fixture.ErasureCancellationPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        fixture.ErasureCancellationPostgresTests.setUp(self)
        self.upgrade()
        self.now = fixture.NOW + timedelta(minutes=2)
        self.verifier = Mock()
        self.proofs = CancellationProofService(
            b"f" * 32,
            audience="fictional-cancel",
            lifetime=timedelta(minutes=2),
            providers={"apple": (self.verifier, "fake-client")},
            clock=lambda: self.now,
        )
        self.coordinator = ErasureCancellationCoordinator(
            verifier=self.proofs,
            audience=self.proofs.audience,
            max_proof_age=self.proofs.lifetime,
            clock=lambda: self.now,
        )

    def session(self):
        return Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def prepare(self, pending=False):
        if not pending:
            self.connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                ),
                dict(person=self.person, id=self.identity),
            )
        table = "auth_identities" if pending else "people"
        target = self.identity if pending else self.person
        generation = str(
            self.connection.scalar(
                text(f"SELECT account_generation FROM ntubtob.{table} WHERE id=:id"),
                dict(id=target),
            )
        )
        job = self.job(
            target_kind="pending_identity" if pending else "person",
            person_id=None if pending else self.person,
            auth_identity_id=self.identity if pending else None,
            expected_generation=generation,
            receipt_secret_hash=hashlib.sha256(SECRET.encode()).hexdigest(),
        )
        with self.session() as session, session.begin():
            context = load_cancellation_context(
                session, job_id=job, receipt_secret=SECRET, clock=lambda: self.now
            )
        challenge = self.proofs.begin(context, "apple")
        subject = self.connection.scalar(
            text("SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"),
            dict(id=self.identity),
        )
        self.verifier.verify.return_value = VerifiedAssertion(
            "apple",
            subject,
            "fake-client",
            challenge["nonce"],
            self.now + timedelta(minutes=3),
        )
        token = self.proofs.authenticate(
            challenge["challenge_credential"], "fictional-assertion"
        )
        return job, token

    def cancel(self, job, token):
        with self.session() as session, session.begin():
            return self.coordinator.cancel(session, job_id=job, assertion=token)

    def test_requested_person_and_pending_cancel_and_old_receipt_stays_readable(self):
        for pending in (False, True):
            with self.subTest(pending=pending), self.connection.begin_nested() as case:
                job, token = self.prepare(pending)
                self.assertEqual(self.cancel(job, token).job_id, job)
                with self.session() as session, session.begin():
                    receipt = load_erasure_receipt(
                        session,
                        job_id=job,
                        receipt_secret=SECRET,
                        clock=lambda: self.now,
                    )
                self.assertEqual(receipt.status, "cancelled")
                row = self.connection.execute(
                    text(
                        "SELECT person_id,auth_identity_id,verified_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    dict(id=job),
                ).one()
                self.assertEqual(tuple(row), (None, None, None))
                with self.assertRaises(ErasureCancellationRejected):
                    self.cancel(job, token)
                self.assertEqual(
                    self.connection.scalar(
                        text(
                            "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id AND stage='cancellation'"
                        ),
                        dict(id=job),
                    ),
                    1,
                )
                case.rollback()

    def test_dispatch_fence_after_provider_proof_prevents_cancellation(self):
        job, token = self.prepare()
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='verified',verified_at=:now,updated_at=:now WHERE id=:id"
            ),
            dict(id=job, now=self.now),
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET irreversible_started_at=:now WHERE id=:id"
            ),
            dict(id=job, now=self.now),
        )
        with self.assertRaises(ErasureCancellationRejected):
            self.cancel(job, token)
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                dict(id=job),
            ),
            0,
        )

    def test_remapped_identity_after_provider_proof_cannot_cancel_other_person(self):
        job, token = self.prepare()
        self.connection.execute(
            text("UPDATE ntubtob.auth_identities SET person_id=:person WHERE id=:id"),
            dict(person=self.other_person, id=self.identity),
        )
        with self.assertRaises(ErasureCancellationRejected):
            self.cancel(job, token)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                dict(id=job),
            ),
            "requested",
        )
