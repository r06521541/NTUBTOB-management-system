"""Exact continuity SQL on rollback-only fictional PostgreSQL fixtures."""

import hashlib
import unittest
from datetime import timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.erasure_cancellation import (
    load_cancellation_context,
)
from shared_lib.shared_module.portal_data.erasure_continuity import effective_deadlines
from shared_lib.shared_module.portal_data.erasure_receipt import (
    ErasureReceiptRejected,
    load_erasure_receipt,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)

FUNCTION = (
    "ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz)"
)
TABLE = "ntubtob.account_erasure_continuity_events"
REVISION = "0021_erasure_continuity"


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL required")
class ContinuityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(ledger.DATABASE_URL))
        remove_retained_erasure_ledger_from_isolated_test_database(cls.engine)
        with cls.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0014_account_erasure_ledger")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.connection = self.fixture.connection
        self.config = Config(str(ledger.ROOT / "alembic.ini"))
        self.config.attributes["connection"] = self.connection
        self.runtime = "fake_cont_runtime_" + uuid4().hex
        self.owner = "fake_cont_owner_" + uuid4().hex
        for role in (self.runtime, self.owner):
            self.connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        self.connection.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT ALL ON TABLES TO "{self.runtime}"'
            )
        )
        self.connection.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT EXECUTE ON FUNCTIONS TO "{self.runtime}"'
            )
        )
        command.upgrade(self.config, REVISION)
        self.now = self.connection.scalar(text("SELECT clock_timestamp()"))
        self.requested = self.now - timedelta(days=179)
        self.generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.person},
            )
        )
        self.job = self.fixture.job(
            expected_generation=self.generation,
            requested_at=self.requested,
            updated_at=self.requested,
            fulfillment_due_at=self.requested + timedelta(days=30),
            receipt_expires_at=self.requested + timedelta(days=180),
            evidence_expires_at=self.requested + timedelta(days=180),
            receipt_secret_hash=hashlib.sha256(
                b"fictional-continuity-receipt-secret-12345"
            ).hexdigest(),
        )
        self.args = dict(
            request=self.job,
            generation=self.generation,
            sequence=0,
            operation=str(uuid4()),
            receipt=self.requested + timedelta(days=210),
            evidence=self.requested + timedelta(days=240),
        )

    def apply(self, **changes):
        return self.connection.scalar(
            text(
                "SELECT ntubtob.extend_erasure_continuity(CAST(:request AS uuid),"
                "CAST(:generation AS uuid),:sequence,CAST(:operation AS uuid),:receipt,:evidence)"
            ),
            {**self.args, **changes},
        )

    def root(self):
        return (
            self.connection.execute(
                text(
                    "SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE"
                ),
                {"id": self.job},
            )
            .mappings()
            .one()
        )

    def rejected(self, action, reason=None):
        with self.connection.begin_nested() as nested:
            try:
                action()
            except DBAPIError as error:
                if reason is not None:
                    self.assertIn(reason, str(error.orig))
                nested.rollback()
                return
            self.fail("expected database rejection")

    def test_extension_preserves_originals_and_exact_replay(self):
        original = dict(self.root())
        self.assertEqual(str(self.apply()), self.args["operation"])
        self.assertEqual(str(self.apply()), self.args["operation"])
        self.assertEqual(dict(self.root()), original)
        deadlines = effective_deadlines(
            self.connection, self.root(), revisions=(REVISION,)
        )
        self.assertEqual(deadlines.receipt_until, self.args["receipt"])
        self.assertEqual(deadlines.evidence_until, self.args["evidence"])
        self.rejected(
            lambda: self.apply(receipt=self.args["receipt"] + timedelta(days=1))
        )
        self.rejected(lambda: self.apply(operation=str(uuid4()), sequence=0))
        self.rejected(lambda: self.connection.execute(text(f"DELETE FROM {TABLE}")))
        self.rejected(lambda: command.downgrade(self.config, "0020_erasure_intake"))

    def test_receipt_and_cancellation_context_use_same_extended_window(self):
        clock = lambda: self.requested + timedelta(days=181)
        with Session(bind=self.connection) as session, session.begin():
            with self.assertRaises(ErasureReceiptRejected):
                load_erasure_receipt(
                    session,
                    job_id=self.job,
                    receipt_secret="fictional-continuity-receipt-secret-12345",
                    clock=clock,
                )
            self.apply()
            self.assertEqual(
                load_erasure_receipt(
                    session,
                    job_id=self.job,
                    receipt_secret="fictional-continuity-receipt-secret-12345",
                    clock=clock,
                ).status,
                "requested",
            )
            self.assertEqual(
                load_cancellation_context(
                    session,
                    job_id=self.job,
                    receipt_secret="fictional-continuity-receipt-secret-12345",
                    clock=clock,
                ).job_id,
                self.job,
            )
            with self.assertRaises(ErasureReceiptRejected):
                load_erasure_receipt(
                    session,
                    job_id=self.job,
                    receipt_secret="fictional-continuity-receipt-secret-12345",
                    clock=lambda: self.args["receipt"],
                )
        self.assertEqual(
            self.root()["receipt_expires_at"], self.requested + timedelta(days=180)
        )

    def test_new_fresh_attempt_after_original_expiry_requires_extension(self):
        def insert_attempt(identifier, *, intake=False):
            table = (
                "account_erasure_intake_attempts"
                if intake
                else "account_erasure_request_attempts"
            )
            column = "intake_id" if intake else "job_id"
            self.connection.execute(
                text(
                    f"INSERT INTO ntubtob.{table} "
                    f"(attempt_id,{column},assertion_binding,created_at,proof_expires_at) "
                    "VALUES (:attempt,:id,:binding,:now,:expiry)"
                ),
                dict(
                    attempt=str(uuid4()),
                    id=identifier,
                    binding="f" * 64,
                    now=self.requested + timedelta(days=181),
                    expiry=self.requested + timedelta(days=181, minutes=2),
                ),
            )

        self.rejected(lambda: insert_attempt(self.job))
        self.apply()
        insert_attempt(self.job)
        intake_id = str(uuid4())
        generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.other_person},
            )
        )
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_intakes "
                "(id,target_kind,person_id,expected_generation,status,receipt_secret_hash,retention_policy_version,"
                "requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) "
                "SELECT :id,target_kind,:person,:generation,'requested',receipt_secret_hash,retention_policy_version,"
                "requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at "
                "FROM ntubtob.account_erasure_jobs WHERE id=:job"
            ),
            dict(
                id=intake_id,
                person=self.fixture.other_person,
                generation=generation,
                job=self.job,
            ),
        )
        self.rejected(lambda: insert_attempt(intake_id, intake=True))
        self.apply(request=intake_id, generation=generation, operation=str(uuid4()))
        insert_attempt(intake_id, intake=True)
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_intake_attempts WHERE intake_id=:id"
                ),
                {"id": intake_id},
            ),
            1,
        )

    def test_wrong_generation_missing_root_and_invalid_windows_reject(self):
        for change in (
            dict(generation=str(uuid4())),
            dict(request=str(uuid4())),
            dict(sequence=1),
            dict(receipt=self.requested + timedelta(days=180)),
            dict(evidence=self.requested + timedelta(days=200)),
        ):
            with self.subTest(field=tuple(change)):
                self.rejected(lambda: self.apply(**change))

    def test_named_default_grants_and_public_cannot_extend_or_write(self):
        for privilege, target in (
            ("INSERT", TABLE),
            ("UPDATE", TABLE),
            ("DELETE", TABLE),
        ):
            self.assertFalse(
                self.connection.scalar(
                    text("SELECT has_table_privilege(:role,:target,:privilege)"),
                    dict(role=self.runtime, target=target, privilege=privilege),
                )
            )
        self.assertFalse(
            self.connection.scalar(
                text("SELECT has_function_privilege(:role,:target,'EXECUTE')"),
                dict(role=self.runtime, target=FUNCTION),
            )
        )

    def test_clock_before_current_root_cannot_append(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET updated_at=:future WHERE id=:id"
            ),
            dict(future=self.now + timedelta(hours=1), id=self.job),
        )
        self.rejected(self.apply)

    def test_clock_before_previous_event_cannot_append(self):
        # Simulate an earlier forward wall-clock followed by a regression; no
        # system-clock mutation and no UPDATE of append-only event evidence.
        self.connection.execute(
            text(
                f"""INSERT INTO {TABLE}
              (operation_id,request_id,target_kind,expected_generation,original_requested_at,
               original_receipt_hash,sequence,previous_receipt_until,previous_evidence_until,
               receipt_until,evidence_until,occurred_at,operator_name)
              SELECT :operation,id,target_kind,expected_generation,requested_at,receipt_secret_hash,
               1,receipt_expires_at,evidence_expires_at,:receipt,:evidence,:future,SESSION_USER
              FROM ntubtob.account_erasure_jobs WHERE id=:request"""
            ),
            {**self.args, "future": self.now + timedelta(hours=1)},
        )
        self.rejected(
            lambda: self.apply(
                sequence=1,
                operation=str(uuid4()),
                receipt=self.args["receipt"] + timedelta(days=30),
                evidence=self.args["evidence"] + timedelta(days=30),
            ),
            "continuity_window_rejected",
        )

    def test_empty_downgrade_restores_previous_marker(self):
        command.downgrade(self.config, "0020_erasure_intake")
        self.assertIsNone(
            self.connection.scalar(text(f"SELECT to_regclass('{TABLE}')"))
        )

    def test_force_rls_hidden_evidence_cannot_be_downgraded(self):
        self.apply()
        self.connection.execute(
            text(f'GRANT USAGE ON SCHEMA ntubtob TO "{self.owner}"')
        )
        self.connection.execute(
            text(f'GRANT SELECT ON ntubtob.alembic_version TO "{self.owner}"')
        )
        self.connection.execute(text(f'ALTER TABLE {TABLE} OWNER TO "{self.owner}"'))
        self.connection.execute(text(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"))
        self.connection.execute(text(f'SET LOCAL ROLE "{self.owner}"'))
        try:
            self.rejected(
                lambda: command.downgrade(self.config, "0020_erasure_intake"),
                "continuity_unfiltered_state_required",
            )
        finally:
            self.connection.execute(text("RESET ROLE"))
        self.assertEqual(
            self.connection.scalar(text(f"SELECT count(*) FROM {TABLE}")), 1
        )


if __name__ == "__main__":
    unittest.main()
