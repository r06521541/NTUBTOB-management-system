"""Fictional sealed-plan schema/custody; database cases require local opt-in."""

import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from shared_lib.shared_module.erasure_restore_binding import RestoreBinding
from shared_lib.shared_module.portal_data import erasure_models  # metadata registration
from shared_lib.shared_module.portal_data import erasure_plan_store as stores
from shared_lib.shared_module.portal_data.erasure_fulfillment import (
    PendingIdentityFulfillment,
    PendingIdentitySnapshot,
    capture_pending_snapshot,
)
from shared_lib.shared_module.portal_data.erasure_plan_codec import ErasurePlanCodec
from shared_lib.shared_module.portal_data.models import PortalDataBase
from tests.portal_data import test_erasure_cancellation_schema as fixture
from tests.portal_data._erasure_ledger_test_harness import _privacy_migration
from tests.portal_data.test_erasure_person_fulfillment import (
    _PersonFulfillmentFixture,
    ledger,
)

NAMESPACE = "00000000-0000-4000-8000-000000000003"
JOB = "00000000-0000-4000-8000-000000000004"
GENERATION = "00000000-0000-4000-8000-000000000005"


def fictional_store(*, key_id="fictional", key=b"F" * 32, clock=lambda: fixture.NOW):
    return stores.ErasurePlanStore(
        active_key_id=key_id,
        codecs={key_id: ErasurePlanCodec(namespace=NAMESPACE, key=key)},
        clock=clock,
    )


class PlanStoreConfigurationTests(unittest.TestCase):
    def test_store_requires_explicit_known_active_codec_and_no_key_fallback(self):
        from shared_lib.shared_module.portal_data.erasure_plan_store import (
            ErasurePlanStore,
        )

        for values in (
            dict(active_key_id="x", codecs={}),
            dict(active_key_id="bad key", codecs={"bad key": object()}),
            dict(active_key_id="x", codecs={"x": object()}),
        ):
            with self.assertRaisesRegex(ValueError, "invalid_plan_store_configuration"):
                ErasurePlanStore(**values)


class PlanStoreTests(unittest.TestCase):
    def setUp(self):
        locks = patch.object(stores, "acquire_admin_event_locks")
        self.locks = locks.start()
        self.addCleanup(locks.stop)
        self.configure()

    def configure(self):
        self.connection = MagicMock(spec=Connection)
        self.connection.in_transaction.return_value = True
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.scalars.return_value = ("0018_erasure_privacy_mutation",)
        self.snapshot = PendingIdentitySnapshot(
            7, GENERATION, "a" * 64, (), RestoreBinding(1, "fictional", "b" * 64)
        )
        self.job = dict(
            id=JOB,
            status="requested",
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=7,
            expected_generation=GENERATION,
            scope_version=1,
            scope_hash=self.snapshot.scope_hash,
            requested_at=fixture.NOW,
            evidence_expires_at=fixture.NOW + timedelta(hours=3),
        )
        self.row = (
            "fictional",
            ErasurePlanCodec(namespace=NAMESPACE, key=b"F" * 32).encode(
                self.snapshot, job_id=JOB
            ),
        )
        self.connection.scalar.side_effect = lambda sql, *args: (
            False if "row_security_active" in str(sql) else GENERATION
        )
        self.connection.execute.side_effect = self.execute
        self.store = fictional_store()

    def execute(self, sql, *args):
        result = MagicMock()
        if "SELECT * FROM ntubtob.account_erasure_jobs" in str(sql):
            self.locks.assert_called()
            result.mappings.return_value.first.return_value = self.job
        elif "SELECT key_id,ciphertext" in str(sql):
            result.first.return_value = self.row
        return result

    def test_load_original_no_mutation_or_recapture(self):
        self.assertEqual(self.store.load(self.connection, JOB), self.snapshot)
        self.assertFalse(
            any(
                str(call.args[0]).startswith(("INSERT", "UPDATE", "DELETE"))
                for call in self.connection.execute.call_args_list
            )
        )
        self.assertNotIn(GENERATION, repr(self.snapshot))

    def test_connection_revision_and_each_rls_failure_are_closed_before_rows(self):
        for changes in ("transaction", "isolation", "autocommit", "revision"):
            with self.subTest(changes=changes):
                self.configure()
                if changes == "transaction":
                    self.connection.in_transaction.return_value = False
                if changes == "isolation":
                    self.connection.get_isolation_level.return_value = "REPEATABLE READ"
                if changes == "autocommit":
                    self.connection.connection.dbapi_connection.autocommit = True
                if changes == "revision":
                    self.connection.scalars.return_value = ("0017_erasure_work_items",)
                with self.assertRaises(stores.SealedPlanRejected):
                    self.store.load(self.connection, JOB)
                self.assertFalse(
                    any(
                        "SELECT * FROM" in str(c.args[0])
                        for c in self.connection.execute.call_args_list
                    )
                )
        for index in range(4):
            for filtered in (True, None):
                with self.subTest(index=index, filtered=filtered):
                    self.configure()
                    self.connection.scalar.side_effect = [False] * index + [filtered]
                    with self.assertRaisesRegex(
                        stores.SealedPlanRejected, "unfiltered_tables_required"
                    ):
                        self.store.load(self.connection, JOB)
                    self.assertFalse(
                        any(
                            "SELECT * FROM" in str(c.args[0])
                            for c in self.connection.execute.call_args_list
                        )
                    )

    def test_missing_wrong_key_ciphertext_and_binding_never_fall_back(self):
        for row, reason in (
            (None, "sealed_plan_missing"),
            (("unknown", self.row[1]), "sealed_plan_key_unavailable"),
            (("fictional", b"bad-secret"), "sealed_plan_unavailable"),
        ):
            with self.subTest(reason=reason):
                self.row = row
                with self.assertRaisesRegex(
                    (stores.SealedPlanRejected, stores.SealedPlanUnavailable),
                    "^" + reason + "$",
                ):
                    self.store.load(self.connection, JOB)
        self.row = (
            "fictional",
            ErasurePlanCodec(namespace=NAMESPACE, key=b"F" * 32).encode(
                self.snapshot, job_id=JOB
            ),
        )
        self.job["auth_identity_id"] = 8
        with self.assertRaisesRegex(
            stores.SealedPlanRejected, "sealed_plan_binding_changed"
        ):
            self.store.load(self.connection, JOB)

    def test_expiry_after_read_and_private_errors_are_fixed(self):
        readings = iter((fixture.NOW, fixture.NOW, fixture.NOW + timedelta(hours=3)))
        self.store = fictional_store(clock=lambda: next(readings))
        with self.assertRaisesRegex(stores.SealedPlanRejected, "sealed_plan_expired"):
            self.store.load(self.connection, JOB)
        self.store = fictional_store(
            clock=lambda: (_ for _ in ()).throw(RuntimeError("private-sentinel"))
        )
        with self.assertRaisesRegex(
            stores.SealedPlanUnavailable, "^sealed_plan_unavailable$"
        ) as caught:
            self.store.load(self.connection, JOB)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_terminal_job_cannot_load_for_execution(self):
        for status in ("cancelled", "online_completed", "completed"):
            self.job["status"] = status
            with self.assertRaisesRegex(
                stores.SealedPlanRejected, "receipt_read_required"
            ):
                self.store.load(self.connection, JOB)


class SealedPlanSchemaTests(unittest.TestCase):
    def test_core_only_exact_columns_and_restrict_job_binding(self):
        table = PortalDataBase.metadata.tables["ntubtob.account_erasure_sealed_plans"]
        self.assertEqual(list(table.c.keys()), ["job_id", "key_id", "ciphertext"])
        self.assertEqual(list(table.primary_key.columns.keys()), ["job_id"])
        self.assertFalse(any(c.nullable for c in table.c))
        self.assertEqual(next(iter(table.c.job_id.foreign_keys)).ondelete, "RESTRICT")
        self.assertFalse(
            any(m.local_table is table for m in PortalDataBase.registry.mappers)
        )

    def test_candidate_has_insert_immutable_parent_binding_and_private_rls(self):
        module = _privacy_migration()
        with patch.object(module.op, "execute") as execute:
            module.upgrade()
        sql = "\n".join(str(c.args[0]) for c in execute.call_args_list)
        self.assertIn("CREATE TABLE ntubtob.account_erasure_sealed_plans", sql)
        for name in (
            "guard_erasure_sealed_plan",
            "guard_erasure_sealed_plan_job_binding",
            "erasure_sealed_plan_insert_guard",
            "erasure_sealed_plan_immutable",
            "erasure_sealed_plan_job_binding",
        ):
            self.assertIn(name, sql)
        self.assertIn(
            "ALTER TABLE ntubtob.account_erasure_sealed_plans ENABLE ROW LEVEL SECURITY",
            sql,
        )
        self.assertIn("octet_length(ciphertext) BETWEEN 52 AND 4194355", sql)
        for field in (
            "scope_version",
            "scope_hash",
            "retention_policy_version",
            "fulfillment_due_at",
            "receipt_expires_at",
            "evidence_expires_at",
        ):
            self.assertIn(f"NEW.{field} IS DISTINCT FROM OLD.{field}", sql)
        with patch.object(module.op, "execute") as execute:
            module.downgrade()
        execute.assert_not_called()


@unittest.skipUnless(fixture.DATABASE_URL, "isolated erasure URL required")
class SealedPlanSchemaPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        fixture.ErasureCancellationPostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        fixture.ErasureCancellationPostgresTests.tearDownClass.__func__
    )
    job = fixture.ErasureCancellationPostgresTests.job
    rejected = fixture.ErasureCancellationPostgresTests.rejected

    def setUp(self):
        fixture.ErasureCancellationPostgresTests.setUp(self)
        config = Config(str(fixture.ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0018_erasure_privacy_mutation")

    def store(self, job, **changes):
        values = dict(job=job, key="fictional", blob=b"x" * 64)
        values.update(changes)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_sealed_plans (job_id,key_id,ciphertext) VALUES (:job,:key,:blob)"
            ),
            values,
        )

    def test_schema_rejects_orphan_duplicate_invalid_payload_and_all_mutations(self):
        job = self.job()
        for values in (
            dict(job=str(uuid4())),
            dict(key=""),
            dict(key="bad key"),
            dict(blob=b""),
            dict(blob=b"x" * 4194356),
        ):
            self.rejected(
                lambda values=values: self.store(**dict({"job": job}, **values))
            )
        self.store(job)
        self.rejected(lambda: self.store(job))
        for sql in (
            "UPDATE ntubtob.account_erasure_sealed_plans SET key_id=key_id",
            "DELETE FROM ntubtob.account_erasure_sealed_plans",
            "TRUNCATE ntubtob.account_erasure_sealed_plans",
        ):
            self.rejected(lambda sql=sql: self.connection.execute(text(sql)))

    def test_sealed_requested_scope_is_frozen_but_legal_cancel_detaches(self):
        job = self.job()
        self.store(job)
        for field, value in (
            ("scope_hash", "b" * 64),
            ("scope_version", 2),
            ("retention_policy_version", 2),
            ("fulfillment_due_at", fixture.NOW + timedelta(minutes=30)),
            ("receipt_expires_at", fixture.NOW + timedelta(hours=1)),
            ("evidence_expires_at", fixture.NOW + timedelta(days=2)),
        ):
            self.rejected(
                lambda field=field, value=value: self.connection.execute(
                    text(
                        f"UPDATE ntubtob.account_erasure_jobs SET {field}=:value WHERE id=:job"
                    ),
                    {"job": job, "value": value},
                )
            )
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',person_id=NULL,cancelled_at=:now,updated_at=:now WHERE id=:job"
            ),
            {"job": job, "now": fixture.NOW},
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:job"
                ),
                {"job": job},
            ),
            1,
        )

    def test_unsealed_requested_contract_and_nonrequested_insert_rejection(self):
        job = self.job()
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET scope_version=2 WHERE id=:job"
            ),
            {"job": job},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='verified',verified_at=:now WHERE id=:job"
            ),
            {"job": job, "now": fixture.NOW},
        )
        self.rejected(lambda: self.store(job))

    def test_schema_has_no_nonowner_acl_or_policies_and_exact_enabled_guards(self):
        row = self.connection.execute(
            text(
                """
            SELECT c.relrowsecurity,c.relforcerowsecurity,
              (SELECT count(*) FROM pg_catalog.pg_policy p WHERE p.polrelid=c.oid),
              (SELECT count(*) FROM pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a WHERE a.grantee<>c.relowner)
            FROM pg_catalog.pg_class c WHERE c.oid='ntubtob.account_erasure_sealed_plans'::regclass
        """
            )
        ).one()
        self.assertEqual(tuple(row), (True, False, 0, 0))
        rows = self.connection.execute(
            text(
                """
            SELECT t.tgname,t.tgenabled,t.tgtype FROM pg_catalog.pg_trigger t
            WHERE t.tgname IN ('erasure_sealed_plan_insert_guard','erasure_sealed_plan_immutable','erasure_sealed_plan_job_binding')
            ORDER BY t.tgname
        """
            )
        ).all()
        self.assertEqual(
            [tuple(r) for r in rows],
            [
                ("erasure_sealed_plan_immutable", "O", 58),
                ("erasure_sealed_plan_insert_guard", "O", 7),
                ("erasure_sealed_plan_job_binding", "O", 19),
            ],
        )


@unittest.skipUnless(fixture.DATABASE_URL, "isolated erasure URL required")
class PlanStorePostgresTests(unittest.TestCase):
    setUpClass = SealedPlanSchemaPostgresTests.__dict__["setUpClass"]
    tearDownClass = SealedPlanSchemaPostgresTests.__dict__["tearDownClass"]
    setUp = SealedPlanSchemaPostgresTests.setUp
    job = SealedPlanSchemaPostgresTests.job

    def capture(self, identity=None):
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            self.assertIs(session.connection(), self.connection)
            return capture_pending_snapshot(
                session,
                identity or self.identity,
                reviewed_audits=(),
                restore_binding=RestoreBinding(1, "fictional", "b" * 64),
            )

    def seed(self):
        snapshot = self.capture()
        job = self.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.identity,
            expected_generation=snapshot.generation,
            scope_hash=snapshot.scope_hash,
        )
        fictional_store().store_requested(self.connection, job, snapshot)
        return job, snapshot

    def test_original_plan_loads_with_fresh_registry_and_rotation_keeps_old_key(self):
        job, snapshot = self.seed()
        fresh = stores.ErasurePlanStore(
            active_key_id="new",
            codecs={
                "new": ErasurePlanCodec(namespace=NAMESPACE, key=b"N" * 32),
                "fictional": ErasurePlanCodec(namespace=NAMESPACE, key=b"F" * 32),
            },
            clock=lambda: fixture.NOW,
        )
        self.assertEqual(fresh.load(self.connection, job), snapshot)
        with self.assertRaisesRegex(
            stores.SealedPlanRejected, "sealed_plan_key_unavailable"
        ):
            fictional_store(key_id="new").load(self.connection, job)
        with self.assertRaisesRegex(
            stores.SealedPlanUnavailable, "sealed_plan_unavailable"
        ):
            fictional_store(key=b"X" * 32).load(self.connection, job)

    def test_missing_plan_or_generation_mapping_drift_cannot_recapture(self):
        snapshot = self.capture()
        job = self.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.identity,
            expected_generation=snapshot.generation,
            scope_hash=snapshot.scope_hash,
        )
        with self.assertRaisesRegex(stores.SealedPlanRejected, "sealed_plan_missing"):
            fictional_store().load(self.connection, job)
        fictional_store().store_requested(self.connection, job, snapshot)
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.person, "id": self.identity},
        )
        with self.assertRaisesRegex(
            stores.SealedPlanRejected, "sealed_plan_binding_changed"
        ):
            fictional_store().load(self.connection, job)

    def test_expired_or_cross_job_ciphertext_is_not_execution_authority(self):
        job, snapshot = self.seed()
        with self.assertRaisesRegex(stores.SealedPlanRejected, "sealed_plan_expired"):
            fictional_store(clock=lambda: fixture.NOW + timedelta(hours=4)).load(
                self.connection, job
            )
        other = self.capture(self.other_identity)
        other_job = self.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.other_identity,
            expected_generation=other.generation,
            scope_hash=other.scope_hash,
        )
        # Schema accepts opaque ciphertext; authenticated decoding must reject a
        # copied blob even when a DB writer supplies the other valid parent.
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_sealed_plans (job_id,key_id,ciphertext) SELECT :other,key_id,ciphertext FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:job"
            ),
            {"other": other_job, "job": job},
        )
        with self.assertRaisesRegex(
            stores.SealedPlanUnavailable, "sealed_plan_unavailable"
        ):
            fictional_store().load(self.connection, other_job)


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class RestartPlanExecutionPostgresTests(_PersonFulfillmentFixture, unittest.TestCase):
    def setUp(self):
        original = ledger.ErasureLedgerPostgresTests.job

        def job_and_plan(fixture_instance, **values):
            job = original(fixture_instance, **values)
            fictional_store().store_requested(
                fixture_instance.connection, job, self.snapshot
            )
            return job

        # The fixture's requested job and sealed plan commit together, then its
        # real verification coordinator revokes sessions in a separate TX.
        with patch.object(ledger.ErasureLedgerPostgresTests, "job", job_and_plan):
            super().setUp()

    def test_restart_loads_committed_plan_then_fixed_executor_without_recapture(self):
        original = self.snapshot
        self.snapshot = None
        fresh = fictional_store()
        pending = PendingIdentityFulfillment(
            self.engine, lambda *args: None, self.store, clock=lambda: fixture.NOW
        )
        result = fresh.execute_stored(
            self.engine,
            job_id=self.job_id,
            pending_executor=pending,
            person_executor=self.executor,
        )
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id",
                id=self.job_id,
            ),
            1,
        )
        self.assertEqual(sorted(self.calls), ["apple", "line"])
        self.assertEqual(
            self.scalar(
                "SELECT scope_hash FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            original.scope_hash,
        )
        with self.assertRaisesRegex(stores.SealedPlanRejected, "receipt_read_required"):
            fresh.execute_stored(
                self.engine,
                job_id=self.job_id,
                pending_executor=pending,
                person_executor=self.executor,
            )
