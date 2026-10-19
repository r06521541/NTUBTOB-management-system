"""Independent real transactions, fictional provider only; no live credentials."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.erasure_provider_execution import (
    PreparedProviderEffect,
    ProviderErasureExecutor,
)
from tests.portal_data import test_erasure_concurrency as concurrency
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data.test_erasure_verification import NOW


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class ProviderExecutionPostgresTests(unittest.TestCase):
    cleanup_fixture = concurrency.ErasureConcurrencyPostgresTests.cleanup_fixture

    def setUp(self):
        concurrency.ErasureConcurrencyPostgresTests.setUp(self)
        with self.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0017_erasure_work_items")
        with Session(self.engine) as session, session.begin():
            self.coordinator.verify(session, job_id=self.job_id, assertion="fictional")
        self.item_id = str(uuid4())
        with self.engine.begin() as connection:
            self.job = dict(
                connection.execute(
                    text("SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                    {"id": self.job_id},
                )
                .mappings()
                .one()
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) "
                    "VALUES (:id,:job,'provider_revocation',:hash,:generation,:now)"
                ),
                dict(
                    id=self.item_id,
                    job=self.job_id,
                    hash="b" * 64,
                    generation=self.job["expected_generation"],
                    now=NOW,
                ),
            )
        self.calls = 0
        self.effect = lambda: "succeeded"
        self.executor = ProviderErasureExecutor(
            self.engine, self.prepare, clock=lambda: NOW + timedelta(seconds=1)
        )

    def prepare(self, connection, job, item):
        return PreparedProviderEffect(
            item["binding_hash"],
            job["scope_hash"],
            str(job["expected_generation"]),
            self.invoke,
        )

    def invoke(self):
        self.calls += 1
        # Another independent connection must see durable start before dispatch.
        with self.engine.connect() as observer:
            row = observer.execute(
                text(
                    "SELECT status,irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job_id},
            ).one()
            self.assertEqual(row.status, "processing")
            self.assertIsNotNone(row.irreversible_started_at)
            self.assertEqual(
                observer.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.item_id},
                ),
                1,
            )
        return self.effect()

    def execute(self):
        return self.executor.execute(job_id=self.job_id, item_id=self.item_id)

    def test_outer_transaction_cannot_be_used_as_commit_boundary(self):
        with self.engine.connect() as connection, connection.begin():
            with self.assertRaises(ValueError):
                ProviderErasureExecutor(connection, self.prepare)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.calls, 0)

    def events(self):
        with self.engine.connect() as connection:
            return [
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT event_sequence,event_kind,result_code FROM ntubtob.account_erasure_item_events WHERE item_id=:id ORDER BY event_sequence"
                    ),
                    {"id": self.item_id},
                ).all()
            ]

    def test_committed_fence_and_result_are_visible_and_repeat_does_not_dispatch(self):
        result = self.execute()
        self.assertEqual(result.classification, "confirmed")
        self.assertEqual(
            self.events(),
            [(1, "started", "in_progress"), (2, "confirmed", "succeeded")],
        )
        self.assertEqual(self.execute().reason, "item_already_started")
        self.assertEqual(self.calls, 1)
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',cancelled_at=:now,updated_at=:now,person_id=NULL,auth_identity_id=NULL WHERE id=:id"
                ),
                dict(id=self.job_id, now=NOW + timedelta(seconds=2)),
            )

    def test_provider_exception_persists_unknown_and_not_missing_credential(self):
        def fail():
            raise RuntimeError("private provider sentinel")

        self.effect = fail
        result = self.execute()
        self.assertEqual(result.classification, "outcome_unknown")
        self.assertEqual(
            self.events(),
            [(1, "started", "in_progress"), (2, "unknown", "response_unknown")],
        )
        self.assertEqual(self.execute().reason, "item_already_started")
        self.assertEqual(self.calls, 1)

    def test_two_executors_only_one_can_start(self):
        started, release = Event(), Event()

        def wait():
            started.set()
            if not release.wait(10):
                raise AssertionError("fictional provider release timed out")
            return "succeeded"

        self.effect = wait
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.execute)
            try:
                self.assertTrue(started.wait(5))
                second = pool.submit(self.execute)
                self.assertEqual(
                    second.result(timeout=5).reason, "item_already_started"
                )
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5).classification, "confirmed")
        self.assertEqual(self.calls, 1)

    def test_cancelled_job_and_changed_plan_do_not_call_provider(self):
        self.executor.prepare_effect = (
            lambda connection, job, item: PreparedProviderEffect(
                "c" * 64,
                job["scope_hash"],
                str(job["expected_generation"]),
                self.invoke,
            )
        )
        self.assertEqual(self.execute().reason, "prepared_scope_changed")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',cancelled_at=:now,updated_at=:now,person_id=NULL,auth_identity_id=NULL WHERE id=:id"
                ),
                dict(id=self.job_id, now=NOW + timedelta(seconds=1)),
            )
        self.assertEqual(self.execute().reason, "verified_job_required")
        self.assertEqual(self.events(), [])
        self.assertEqual(self.calls, 0)

    def test_schema_rejects_unfenced_start_and_mutating_item(self):
        for sql in (
            "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,1,'started','in_progress',:now)",
            "UPDATE ntubtob.account_erasure_items SET binding_hash='"
            + "c" * 64
            + "' WHERE id=:id",
            "DELETE FROM ntubtob.account_erasure_items WHERE id=:id",
        ):
            with (
                self.subTest(sql=sql.split()[0]),
                self.assertRaises(DBAPIError),
                self.engine.begin() as connection,
            ):
                connection.execute(text(sql), dict(id=self.item_id, now=NOW))
        self.assertEqual(self.events(), [])

    def test_unknown_reconciliation_once_and_evidence_immutable(self):
        self.effect = lambda: None
        self.assertEqual(self.execute().classification, "outcome_unknown")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,3,'confirmed','succeeded',:now)"
                ),
                dict(id=self.item_id, now=NOW + timedelta(seconds=2)),
            )
        for sql in (
            "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,4,'started','in_progress',:now)",
            "DELETE FROM ntubtob.account_erasure_item_events WHERE item_id=:id",
        ):
            with self.assertRaises(DBAPIError), self.engine.begin() as connection:
                connection.execute(
                    text(sql), dict(id=self.item_id, now=NOW + timedelta(seconds=3))
                )
        self.assertEqual(len(self.events()), 3)
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
