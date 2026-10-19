"""Committed fictional fixtures and independent PostgreSQL connections only."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    require_account_not_erasing,
)
from shared_lib.shared_module.portal_data.erasure_verification import (
    ErasureVerificationCoordinator,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)
from tests.portal_data.test_erasure_verification import AUDIENCE, NOW, proof


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class ErasureConcurrencyPostgresTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            require_local_database_url(ledger.DATABASE_URL),
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=5000 -c lock_timeout=5000",
            },
            pool_timeout=5,
        )
        self.addCleanup(self.engine.dispose)
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0015_account_generations")
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.addCleanup(self.cleanup_fixture)
        self.fixture.setUp()
        connection = self.fixture.connection
        connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person, "
                "status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.person, "id": self.fixture.identity},
        )
        identity = connection.execute(
            text(
                "SELECT provider_subject, account_generation FROM "
                "ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        ).one()
        generation = str(
            connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.person},
            )
        )
        self.job_id = self.fixture.job(expected_generation=generation)
        fresh = proof(
            job_id=self.job_id,
            identity_id=self.fixture.identity,
            provider_subject=identity.provider_subject,
            identity_generation=str(identity.account_generation),
            person_id=self.fixture.person,
            target_generation=generation,
        )
        self.coordinator = ErasureVerificationCoordinator(
            verifier=lambda assertion: fresh,
            audience=AUDIENCE,
            max_proof_age=timedelta(minutes=1),
            clock=lambda: NOW,
        )
        self.fixture.transaction.commit()
        connection.close()

    def cleanup_fixture(self):
        transaction = getattr(self.fixture, "transaction", None)
        connection = getattr(self.fixture, "connection", None)
        try:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
        finally:
            if connection is not None:
                connection.close()
        # Immutable evidence needs the existing exact disposable-database helper.
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            for table, names in (
                ("auth_identities", ("identity", "other_identity")),
                ("people", ("person", "other_person")),
            ):
                for name in names:
                    identifier = getattr(self.fixture, name, None)
                    if type(identifier) is int and identifier > 0:
                        connection.execute(
                            text(f"DELETE FROM ntubtob.{table} WHERE id=:id"),
                            {"id": identifier},
                        )

    def race(self, *, commit):
        verified = Event()
        release = Event()
        waiting = Event()
        state = {}

        def verify():
            with Session(self.engine) as session:
                transaction = session.begin()
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                self.coordinator.verify(
                    session, job_id=self.job_id, assertion="fictional-proof"
                )
                verified.set()
                if not release.wait(10):
                    raise AssertionError("verification release deadline exceeded")
                transaction.commit() if commit else transaction.rollback()

        def access():
            with Session(self.engine) as session, session.begin():
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                state["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
                waiting.set()
                try:
                    require_account_not_erasing(session, person_id=self.fixture.person)
                except ErasureAccessBlocked:
                    return "blocked"
                return "allowed"

        with ThreadPoolExecutor(max_workers=2) as workers:
            verification = workers.submit(verify)
            try:
                self.assertTrue(verified.wait(5), "verification did not reach fence")
                access_result = workers.submit(access)
                self.assertTrue(waiting.wait(2), "guard did not open connection")
                deadline = monotonic() + 2
                lock_wait = False
                with self.engine.connect() as observer:
                    while monotonic() < deadline:
                        lock_wait = observer.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE "
                                "pid=:pid AND locktype='advisory' AND NOT granted)"
                            ),
                            {"pid": state["pid"]},
                        )
                        if lock_wait or access_result.done():
                            break
                        release.wait(0.01)
                self.assertTrue(lock_wait, "guard did not wait on canonical fence")
                self.assertFalse(access_result.done())
            finally:
                release.set()
            verification.result(timeout=7)
            self.assertEqual(
                access_result.result(timeout=7), "blocked" if commit else "allowed"
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    {"id": self.job_id},
                ),
                "verified" if commit else "requested",
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                    ),
                    {"id": self.job_id},
                ),
                1 if commit else 0,
            )

    def test_commit_blocks_waiting_access_after_real_commit(self):
        self.race(commit=True)

    def test_rollback_allows_waiting_access_without_partial_evidence(self):
        self.race(commit=False)


class ErasureConcurrencyCleanupTests(unittest.TestCase):
    def test_partial_fixture_setup_rolls_back_closes_and_disposes(self):
        case = ErasureConcurrencyPostgresTests("runTest")
        engine, connection, transaction = MagicMock(), MagicMock(), MagicMock()

        def partial_setup(fixture):
            fixture.connection, fixture.transaction = connection, transaction
            fixture.person = 123
            raise RuntimeError("fictional setup failure")

        with (
            patch(__name__ + ".create_engine", return_value=engine) as factory,
            patch(
                __name__ + ".require_local_database_url", return_value="fictional-local"
            ),
            patch(
                __name__ + ".remove_retained_erasure_ledger_from_isolated_test_database"
            ),
            patch.object(command, "upgrade"),
            patch.object(ledger.ErasureLedgerPostgresTests, "setUp", partial_setup),
        ):
            with self.assertRaisesRegex(RuntimeError, "fictional setup failure"):
                case.setUp()
            self.assertTrue(case.doCleanups())
        transaction.rollback.assert_called_once()
        connection.close.assert_called_once()
        engine.dispose.assert_called_once()
        self.assertEqual(factory.call_args.kwargs["connect_args"]["connect_timeout"], 5)
        self.assertIn(
            "statement_timeout=5000",
            factory.call_args.kwargs["connect_args"]["options"],
        )
        self.assertEqual(factory.call_args.kwargs["pool_timeout"], 5)
        writes = engine.begin.return_value.__enter__.return_value.execute.call_args_list
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[1], {"id": 123})
        self.assertIn("DELETE FROM ntubtob.people", str(writes[0].args[0]))

    def test_rollback_failure_still_closes_connection(self):
        case = ErasureConcurrencyPostgresTests("runTest")
        case.fixture = MagicMock()
        case.fixture.transaction.rollback.side_effect = RuntimeError(
            "fictional rollback failure"
        )
        with self.assertRaisesRegex(RuntimeError, "fictional rollback failure"):
            case.cleanup_fixture()
        case.fixture.connection.close.assert_called_once()
