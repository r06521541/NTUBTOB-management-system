"""Receipt and cancellation compatibility on rollback-only candidate0019."""

import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from shared_lib.shared_module.portal_data.erasure_cancellation import (
    ErasureCancellationRejected,
)
from shared_lib.shared_module.portal_data.erasure_context import (
    load_erasure_verification_context,
)
from shared_lib.shared_module.portal_data.erasure_management_guard import (
    ManagementWritesSuspended,
    require_management_writes_available,
)
from shared_lib.shared_module.portal_data.erasure_receipt import load_erasure_receipt
from tests.portal_data import test_erasure_cancellation_integration as cancellation
from tests.portal_data import test_erasure_receipt_recovery as recovery


def upgrade_candidate(case):
    config = Config("alembic.ini")
    config.attributes["connection"] = case.connection
    command.upgrade(config, "0019_erasure_admin_recovery")


@unittest.skipUnless(cancellation.fixture.DATABASE_URL, "isolated ledger URL required")
class CandidateCancellationTests(cancellation.CancellationIntegrationTests):
    def upgrade(self):
        upgrade_candidate(self)

    def test_requested_context_and_suspended_cancel_preserve_management_fence(self):
        job, token = self.prepare()
        with self.session() as session, session.begin():
            context = load_erasure_verification_context(
                session,
                job_id=job,
                receipt_secret=cancellation.SECRET,
                identity_id=self.identity,
                clock=lambda: self.now,
            )
        self.assertEqual(context.job_id, job)
        # A sole fictional admin is an explicit scenario premise, inside rollback.
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level="
                "CASE WHEN id=:id THEN 'admin' ELSE 'basic' END"
            ),
            {"id": self.person},
        )
        self.connection.execute(
            text("UPDATE ntubtob.portal_authority_state SET mode='persistent',epoch=10")
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='verified',"
                "verified_at=:now,updated_at=:now WHERE id=:id"
            ),
            {"now": self.now, "id": job},
        )
        generation = self.connection.scalar(
            text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
            {"id": self.person},
        )
        operation = str(uuid4())
        self.connection.execute(
            text(
                "SELECT ntubtob.suspend_management_for_erasure("
                "CAST(:job AS uuid),CAST(:generation AS uuid),10,CAST(:operation AS uuid))"
            ),
            {"job": job, "generation": str(generation), "operation": operation},
        )
        with self.session() as session, session.begin():
            self.assertEqual(
                load_erasure_receipt(
                    session,
                    job_id=job,
                    receipt_secret=cancellation.SECRET,
                    clock=lambda: self.now,
                ).status,
                "verified",
            )
        with self.assertRaises(ErasureCancellationRejected):
            self.cancel(job, "fictional-invalid-proof")
        self.cancel(job, token)
        with self.session() as session, session.begin():
            self.assertEqual(
                load_erasure_receipt(
                    session,
                    job_id=job,
                    receipt_secret=cancellation.SECRET,
                    clock=lambda: self.now,
                ).status,
                "cancelled",
            )
        self.assertEqual(
            tuple(
                self.connection.execute(
                    text(
                        "SELECT epoch,management_suspension_operation_id::text "
                        "FROM ntubtob.portal_authority_state"
                    )
                ).one()
            ),
            (11, operation),
        )
        with self.assertRaises(ManagementWritesSuspended):
            require_management_writes_available(self.connection)


@unittest.skipUnless(recovery.fixture.DATABASE_URL, "isolated ledger URL required")
class CandidateRecoveryTests(recovery.RecoveryPostgresTests):
    def upgrade(self):
        upgrade_candidate(self)

    def test_fresh_recovery_remains_read_only_during_management_suspension(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level="
                "CASE WHEN id=:id THEN 'admin' ELSE 'basic' END"
            ),
            {"id": self.person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' "
                "WHERE id=:identity"
            ),
            {"person": self.person, "identity": self.other_identity},
        )
        self.connection.execute(
            text("UPDATE ntubtob.portal_authority_state SET mode='persistent',epoch=10")
        )
        generation = self.connection.scalar(
            text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
            {"id": self.person},
        )
        admin_job = self.job(expected_generation=str(generation))
        self.update(
            admin_job,
            status="verified",
            verified_at=recovery.EARLIER,
            updated_at=recovery.EARLIER,
        )
        operation = str(uuid4())
        self.connection.execute(
            text(
                "SELECT ntubtob.suspend_management_for_erasure("
                "CAST(:job AS uuid),CAST(:generation AS uuid),10,CAST(:operation AS uuid))"
            ),
            {"job": admin_job, "generation": str(generation), "operation": operation},
        )
        before = self.snapshot()
        result = self.repo.recover(recovery.ASSERTION)
        self.assertEqual(result.job_id, self.job_id)
        self.assertEqual(result.receipt_secret, recovery.original_secret(self.job_id))
        self.assertEqual(before, self.snapshot())
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT management_suspension_operation_id::text "
                    "FROM ntubtob.portal_authority_state"
                )
            ),
            operation,
        )
        with self.assertRaises(ManagementWritesSuspended):
            require_management_writes_available(self.connection)
