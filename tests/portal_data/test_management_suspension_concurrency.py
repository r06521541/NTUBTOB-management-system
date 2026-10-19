"""One-shot committed fixture on a NEW disposable PostgreSQL database only.

Set MANAGEMENT_SUSPENSION_RACE_TEST_DATABASE_URL explicitly; ordinary ledger or
portal URLs are never a fallback. Existing ntubtob schemas are rejected before
DDL. The fixture leaves committed immutable evidence intact: cleanup only closes
connections/disposes engines. Main must destroy the dedicated container afterward.
This proves the native suspension / real create_person race, not runtime rollout,
all management callers, deployment ACLs, or any account-erasure executor.
"""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest.mock import MagicMock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text

from shared_lib.shared_module.portal_data.domain import AuthorizationError
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.repository import PostgresTeamPortalRepository
from shared_lib.shared_module.portal_data.runtime import ADMIN_LOCK_KEY
from tests.portal_data import test_erasure_admin_recovery_schema as native
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

DATABASE_URL = os.environ.get("MANAGEMENT_SUSPENSION_RACE_TEST_DATABASE_URL")


def _new_engine(url):
    return create_engine(
        require_local_database_url(url),
        isolation_level="READ COMMITTED",
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=10000 "
            "-c idle_in_transaction_session_timeout=20000",
        },
        pool_timeout=5,
    )


def _prepare_fresh_schema(engine):
    with engine.begin() as connection:
        if connection.scalar(text("SELECT to_regnamespace('ntubtob')")) is not None:
            raise RuntimeError("fresh disposable database required")
        connection.execute(text(LEGACY_FIXTURE_SQL))
        config = Config(str(native.ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "0018_erasure_privacy_mutation")


def _close_fixture_connection(fixture):
    # close rolls back only an unfinished setup transaction. Never call the old
    # schema/historical cleanup helpers or downgrade committed 0019 evidence.
    connection = getattr(getattr(fixture, "fixture", None), "connection", None)
    if connection is not None:
        connection.close()


@unittest.skipUnless(DATABASE_URL, "fresh suspension-race database URL not configured")
class ManagementSuspensionConcurrencyPostgresTests(unittest.TestCase):
    def setUp(self):
        self.engine = _new_engine(DATABASE_URL)
        self.addCleanup(self.engine.dispose)
        _prepare_fresh_schema(self.engine)

        # Reuse only reviewed native DDL/roles/fictional rows, not its test cases
        # or rollback-only test runner. This fixture is intentionally committed.
        fixture = native.AdminRecoveryPostgresTests("runTest")
        fixture.engine = self.engine
        try:
            fixture.setUp()
            self.operator = fixture.operator
            self.job_id = fixture.job_id
            self.generation = fixture.generation
            fixture.fixture.transaction.commit()
        finally:
            _close_fixture_connection(fixture)

        self.writer_engine = _new_engine(DATABASE_URL)
        self.addCleanup(self.writer_engine.dispose)
        self.repo = PostgresTeamPortalRepository(self.writer_engine)

    def _assert_durable_state(self, *, operation, epoch, people, name, name_count):
        with self.engine.connect() as observer:
            self.assertEqual(
                tuple(
                    observer.execute(
                        text(
                            "SELECT mode,epoch,management_suspension_operation_id::text "
                            "FROM ntubtob.portal_authority_state"
                        )
                    ).one()
                ),
                ("persistent", epoch, operation),
            )
            operations = observer.execute(
                text(
                    "SELECT operation_id::text,job_id::text,expected_generation::text,"
                    "expected_epoch,applied_epoch FROM "
                    "ntubtob.account_erasure_admin_recovery_operations"
                )
            ).all()
            self.assertEqual(
                [tuple(row) for row in operations],
                (
                    []
                    if operation is None
                    else [(operation, self.job_id, self.generation, 10, 11)]
                ),
            )
            self.assertEqual(
                observer.scalar(text("SELECT count(*) FROM ntubtob.people")), people
            )
            self.assertEqual(
                observer.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.people WHERE display_name=:name"
                    ),
                    {"name": name},
                ),
                name_count,
            )
            self.assertEqual(
                observer.scalar(
                    text(
                        "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    {"id": self.job_id},
                ),
                "verified",
            )

    def _race(self, *, commit, name):
        checked_out = Event()
        state = {}
        operation = str(uuid4())

        def observe_checkout(dbapi_connection, connection_record, connection_proxy):
            # Observe only: no Session/gate patch and no SQL before the real gate.
            state["writer_pid"] = dbapi_connection.get_backend_pid()
            checked_out.set()

        event.listen(self.writer_engine, "checkout", observe_checkout)
        try:
            with self.engine.connect() as suspender:
                transaction = suspender.begin()
                try:
                    suspension_pid = suspender.scalar(text("SELECT pg_backend_pid()"))
                    suspender.execute(text(f'SET LOCAL ROLE "{self.operator}"'))
                    applied = suspender.scalar(
                        text(
                            "SELECT ntubtob.suspend_management_for_erasure("
                            "CAST(:job AS uuid),CAST(:generation AS uuid),10,"
                            "CAST(:operation AS uuid))"
                        ),
                        {
                            "job": self.job_id,
                            "generation": self.generation,
                            "operation": operation,
                        },
                    )
                    self.assertEqual(str(applied), operation)
                    with ThreadPoolExecutor(max_workers=1) as workers:
                        writer = workers.submit(self.repo.create_person, name)
                        try:
                            self.assertTrue(
                                checked_out.wait(5), "management connection not opened"
                            )
                            self.assertNotEqual(state["writer_pid"], suspension_pid)
                            deadline = monotonic() + 5
                            observed_wait = False
                            with self.engine.connect() as observer:
                                observer_pid = observer.scalar(
                                    text("SELECT pg_backend_pid()")
                                )
                                self.assertNotIn(
                                    observer_pid, (state["writer_pid"], suspension_pid)
                                )
                                while monotonic() < deadline:
                                    observed_wait = observer.scalar(
                                        text(
                                            "SELECT EXISTS(SELECT 1 FROM pg_locks "
                                            "WHERE pid=:writer AND locktype='advisory' "
                                            "AND classid=0 AND objid=:key AND objsubid=1 "
                                            "AND NOT granted) AND :holder = ANY("
                                            "pg_blocking_pids(:writer))"
                                        ),
                                        {
                                            "writer": state["writer_pid"],
                                            "holder": suspension_pid,
                                            "key": ADMIN_LOCK_KEY,
                                        },
                                    )
                                    if observed_wait or writer.done():
                                        break
                                    # Poll pacing only; success requires real pg_locks
                                    # evidence plus the exact blocking backend PID.
                                    Event().wait(0.01)
                            self.assertTrue(
                                observed_wait, "management did not wait on suspension"
                            )
                            self.assertFalse(writer.done())
                            if commit:
                                transaction.commit()
                            else:
                                transaction.rollback()
                        finally:
                            # Release even on failed assertions before waiting for
                            # the worker; SQL/connect timeouts bound secondary waits.
                            if transaction.is_active:
                                transaction.rollback()
                        if commit:
                            with self.assertRaisesRegex(
                                AuthorizationError, "^management writes unavailable$"
                            ):
                                writer.result(timeout=15)
                        else:
                            created = writer.result(timeout=15)
                            self.assertEqual(created.display_name, name)
                finally:
                    if transaction.is_active:
                        transaction.rollback()
        finally:
            event.remove(self.writer_engine, "checkout", observe_checkout)
        return operation

    def test_rollback_admits_then_committed_suspension_fences_waiting_writer(self):
        with self.engine.connect() as observer:
            people = observer.scalar(text("SELECT count(*) FROM ntubtob.people"))
        allowed = "Fictional suspension rollback person"
        blocked = "Fictional suspension commit person"
        self._race(commit=False, name=allowed)
        self._assert_durable_state(
            operation=None, epoch=10, people=people + 1, name=allowed, name_count=1
        )
        operation = self._race(commit=True, name=blocked)
        self._assert_durable_state(
            operation=operation,
            epoch=11,
            people=people + 1,
            name=blocked,
            name_count=0,
        )


class ManagementSuspensionRaceFixtureTests(unittest.TestCase):
    def test_existing_schema_rejects_before_any_ddl_or_migration(self):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        connection.scalar.return_value = "ntubtob"
        with patch.object(command, "upgrade") as upgrade:
            with self.assertRaisesRegex(
                RuntimeError, "^fresh disposable database required$"
            ):
                _prepare_fresh_schema(engine)
        connection.execute.assert_not_called()
        upgrade.assert_not_called()

    def test_local_validation_precedes_engine_creation_and_waits_are_bounded(self):
        with patch(__name__ + ".create_engine") as factory:
            with self.assertRaises(RuntimeError):
                _new_engine(
                    "postgresql://fictional@example.invalid/ntubtob_portal_local"
                )
            factory.assert_not_called()
            _new_engine("postgresql://fictional@127.0.0.1/ntubtob_portal_local")
        options = factory.call_args.kwargs
        self.assertEqual(options["isolation_level"], "READ COMMITTED")
        self.assertEqual(options["pool_timeout"], 5)
        self.assertEqual(options["connect_args"]["connect_timeout"], 5)
        self.assertIn("statement_timeout=15000", options["connect_args"]["options"])
        self.assertIn("lock_timeout=10000", options["connect_args"]["options"])

    def test_partial_fixture_cleanup_only_closes_connection_without_erasing_history(
        self,
    ):
        fixture = MagicMock()
        _close_fixture_connection(fixture)
        fixture.fixture.connection.close.assert_called_once_with()
        fixture.fixture.connection.execute.assert_not_called()
        fixture.doCleanups.assert_not_called()
        fixture.tearDown.assert_not_called()
        _close_fixture_connection(object())


if __name__ == "__main__":
    unittest.main()
