"""Restricted-intent replay binding; no provider credentials or live database."""

import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import CheckConstraint, text

from shared_lib.shared_module.portal_data import erasure_models
from tests.portal_data import test_erasure_cancellation_schema as cancellation


class ErasureAttemptSchemaTests(unittest.TestCase):
    def test_model_and_candidate_migration_match(self):
        model = erasure_models.AccountErasureRequestAttemptRecord
        table = model.__table__
        self.assertEqual(
            set(table.c.keys()),
            {
                "attempt_id",
                "job_id",
                "assertion_binding",
                "created_at",
                "proof_expires_at",
            },
        )
        sql = " ".join(cancellation.ErasureCancellationSchemaTests().sql().split())
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                self.assertIn(constraint.name, sql)
                self.assertIn(" ".join(str(constraint.sqltext).split()), sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("BEFORE UPDATE OR DELETE OR TRUNCATE", sql)
        self.assertIn("erasure_request_attempt_immutable", sql)
        self.assertEqual(len(table.foreign_keys), 1)
        self.assertEqual(next(iter(table.foreign_keys)).ondelete, "RESTRICT")


@unittest.skipUnless(
    cancellation.DATABASE_URL, "dedicated isolated erasure URL not configured"
)
class ErasureAttemptPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        cancellation.ErasureCancellationPostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        cancellation.ErasureCancellationPostgresTests.tearDownClass.__func__
    )
    setUp = cancellation.ErasureCancellationPostgresTests.setUp
    upgrade = cancellation.ErasureCancellationPostgresTests.upgrade
    job = cancellation.ErasureCancellationPostgresTests.job
    rejected = cancellation.ErasureCancellationPostgresTests.rejected
    update = cancellation.ErasureCancellationPostgresTests.update

    def insert(self, target_job, **changes):
        values = dict(
            attempt_id=str(uuid4()),
            job_id=target_job,
            assertion_binding="a" * 64,
            created_at=cancellation.NOW,
            proof_expires_at=cancellation.NOW + timedelta(minutes=5),
        )
        values.update(changes)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_request_attempts "
                "(attempt_id,job_id,assertion_binding,created_at,proof_expires_at) "
                "VALUES (:attempt_id,:job_id,:assertion_binding,:created_at,:proof_expires_at)"
            ),
            values,
        )
        return values["attempt_id"]

    def test_insert_is_immutable_and_cancel_preserves_attempt(self):
        self.upgrade()
        job = self.job()
        attempt = self.insert(job)
        for sql in (
            "UPDATE ntubtob.account_erasure_request_attempts SET assertion_binding=repeat('b',64)",
            "DELETE FROM ntubtob.account_erasure_request_attempts",
            "TRUNCATE ntubtob.account_erasure_request_attempts",
        ):
            self.rejected(lambda: self.connection.execute(text(sql)))
        self.update(
            job,
            status="cancelled",
            person_id=None,
            auth_identity_id=None,
            cancelled_at=cancellation.LATER,
            updated_at=cancellation.LATER,
        )
        self.assertEqual(
            str(
                self.connection.scalar(
                    text(
                        "SELECT job_id FROM ntubtob.account_erasure_request_attempts WHERE attempt_id=:id"
                    ),
                    {"id": attempt},
                )
            ),
            job,
        )
        self.rejected(lambda: self.insert(job))

    def test_binding_format_expiry_and_duplicate_are_rejected(self):
        self.upgrade()
        job = self.job()
        attempt = self.insert(job)
        for changes in (
            {"assertion_binding": "raw-provider-subject"},
            {"proof_expires_at": cancellation.NOW},
            {"proof_expires_at": cancellation.NOW + timedelta(seconds=301)},
            {"created_at": cancellation.NOW - timedelta(seconds=1)},
            {"attempt_id": attempt},
            {"job_id": str(uuid4())},
        ):
            with self.subTest(fields=tuple(changes)):
                self.rejected(lambda: self.insert(job, **changes))


if __name__ == "__main__":
    unittest.main()
