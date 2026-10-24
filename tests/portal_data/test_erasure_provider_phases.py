"""Fictional phase boundaries; PostgreSQL is opt-in and never a provider call."""

import importlib.util
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from shared_lib.shared_module.portal_data.erasure_plan_store import (
    ErasurePlanStore,
    SealedPlanRejected,
)
from shared_lib.shared_module.portal_data.erasure_provider_reconciliation import (
    ProviderErasureReconciler,
    ProviderOutcomeEvidence,
)
from tests.portal_data import test_erasure_fulfillment as pending
from tests.portal_data import test_erasure_person_fulfillment as person
from tests.portal_data import test_erasure_retention as retention
from tests.portal_data._fresh_erasure_database import FreshErasureDatabases
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

REVISION = "0024_erasure_provider_phases"
PREVIOUS = "0023_erasure_minimal_retention"


def upgrade(engine, revision=REVISION):
    with engine.begin() as connection:
        config = Config(str(retention.ledger.ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


class _PersonScenario(person._PersonFulfillmentFixture, unittest.TestCase):
    pass


def close_fixture_connection(fixture):
    """No row deletion or rewind of committed phase evidence."""
    ledger_fixture = getattr(fixture, "fixture", None)
    transaction = getattr(ledger_fixture, "transaction", None)
    connection = getattr(ledger_fixture, "connection", None)
    try:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
    finally:
        if connection is not None and not connection.closed:
            connection.close()


class _FreshPhaseDatabases:
    @classmethod
    def setUpClass(cls):
        cls.databases = FreshErasureDatabases(retention.ledger.DATABASE_URL)
        cls.addClassCleanup(cls.close_databases)

        def initialize(engine):
            with engine.begin() as connection:
                connection.execute(text(LEGACY_FIXTURE_SQL))
                config = Config(str(retention.ledger.ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "0018_erasure_privacy_mutation")

        cls.databases.create_template(initialize)

    @classmethod
    def close_databases(cls):
        errors = cls.databases.close()
        if errors:
            raise AssertionError("fresh_database_cleanup_incomplete", errors)

    def clone(self):
        engine = self.databases.clone()
        self.addCleanup(self.databases.release, engine)
        return engine


class ProviderPhaseOfflineTests(unittest.TestCase):
    def test_function_edits_are_exact_reversible_and_grant_no_capability(self):
        def load(name):
            spec = importlib.util.spec_from_file_location(
                "phase_migration",
                retention.ledger.ROOT / "migrations/versions" / (name + ".py"),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        phase = load(REVISION)
        sources = {}
        for name in ("0017_erasure_work_items", "0022_erasure_retention", PREVIOUS):
            module = load(name)
            with patch.object(module.op, "execute") as execute:
                module.upgrade()
            sources[name] = "\n".join(
                str(call.args[0]) for call in execute.call_args_list
            )
        for signature in (phase.EVENT, phase.PLAN, phase.CONTEXT):
            original = sources[
                (
                    "0017_erasure_work_items"
                    if signature == phase.EVENT
                    else (
                        "0022_erasure_retention"
                        if signature == phase.PLAN
                        else PREVIOUS
                    )
                )
            ]
            source = original
            changes = [
                (before, after)
                for name, before, after in phase.EDITS
                if name == signature
            ]
            for before, after in changes:
                self.assertEqual(source.count(before), 1)
                source = source.replace(before, after)
            for before, after in reversed(changes):
                self.assertEqual(source.count(after), 1)
                source = source.replace(after, before)
            self.assertEqual(source, original)
        with patch.object(phase.op, "execute") as execute:
            phase.upgrade()
        sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)
        self.assertNotRegex(
            sql.upper(), r"\b(GRANT|CREATE TABLE|CREATE POLICY|DISABLE TRIGGER)\b"
        )

    def test_online_stored_execution_rejects_before_loading_erased_plan(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        store = object.__new__(ErasurePlanStore)
        store._locked = Mock(return_value={"status": "online_completed"})
        store.load = Mock(side_effect=AssertionError("must not load"))
        pending_executor = object.__new__(pending.PendingIdentityFulfillment)
        person_executor = object.__new__(person.PersonFulfillment)
        pending_executor.engine = person_executor.engine = engine
        with patch("shared_lib.shared_module.portal_data.erasure_plan_store.Session"):
            with self.assertRaisesRegex(SealedPlanRejected, "^receipt_read_required$"):
                store.execute_stored(
                    engine,
                    job_id="fictional",
                    pending_executor=pending_executor,
                    person_executor=person_executor,
                )
        store.load.assert_not_called()


@unittest.skipUnless(retention.ledger.DATABASE_URL, "isolated ledger URL required")
class ProviderPhaseFulfillmentPostgresTests(_FreshPhaseDatabases, unittest.TestCase):
    def scenario(self, *, linked=False, revision=REVISION):
        fixture = (
            _PersonScenario("runTest")
            if linked
            else pending.PendingFulfillmentPostgresTests("runTest")
        )
        engine = self.clone()
        self.addCleanup(close_fixture_connection, fixture)
        self.addCleanup(fixture.doCleanups)
        fixture.cleanup_fixture = lambda: close_fixture_connection(fixture)
        if not linked:
            fixture.target_provider = "line"
        module = person if linked else pending

        def check_fresh(candidate):
            self.assertIs(candidate, engine)
            with engine.connect() as connection:
                self.assertEqual(
                    tuple(
                        connection.scalars(
                            text("SELECT version_num FROM ntubtob.alembic_version")
                        )
                    ),
                    ("0018_erasure_privacy_mutation",),
                )

        # Adapt old fixture construction only: all runtime queries/commits use
        # the actual bounded clone engine; no global database is modified.
        with (
            patch.object(module, "create_engine", return_value=engine),
            patch.object(
                module,
                "remove_retained_erasure_ledger_from_isolated_test_database",
                side_effect=check_fresh,
            ),
        ):
            fixture.setUp()
        upgrade(fixture.engine, revision)
        return fixture

    def test_pending_manual_outcome_deletes_local_target_without_provider_success(self):
        fixture = self.scenario()
        fixture.provider_result = "manual_action_needed"
        result = fixture.execute()
        self.assertEqual(result.reason, "online_completed", result)
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=fixture.fixture.identity,
            ),
            0,
        )
        self.assertEqual(
            fixture.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=fixture.job_id,
            ),
            "online_completed",
        )
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_item_events e JOIN ntubtob.account_erasure_items i ON i.id=e.item_id WHERE i.job_id=:id AND i.stage='provider_revocation' AND e.result_code='manual_action_needed'",
                id=fixture.job_id,
            ),
            1,
        )
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=fixture.fixture.other_identity,
            ),
            1,
        )
        self.assertEqual(fixture.execute().reason, "receipt_read_required")
        self.assertEqual(fixture.calls, 1)

    def test_person_unknown_provider_still_finishes_exact_local_work(self):
        fixture = self.scenario(linked=True)
        fixture.line_provider_result = None
        result = fixture.execute()
        self.assertEqual(result.reason, "online_completed", result)
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=fixture.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=fixture.fixture.other_person,
            ),
            1,
        )
        with fixture.engine.connect() as connection:
            item = str(
                connection.scalar(
                    text(
                        "SELECT i.id FROM ntubtob.account_erasure_items i JOIN ntubtob.account_erasure_item_events e ON e.item_id=i.id WHERE i.job_id=:id AND i.stage='provider_revocation' AND e.event_kind='unknown'"
                    ),
                    {"id": fixture.job_id},
                )
            )
        inspected = []

        def inspect(connection, job, item):
            inspected.append(True)
            return ProviderOutcomeEvidence(
                item["binding_hash"],
                job["scope_hash"],
                str(job["expected_generation"]),
                "succeeded",
            )

        reconciler = ProviderErasureReconciler(
            fixture.engine, inspect, clock=lambda: person.NOW + timedelta(seconds=2)
        )
        self.assertEqual(
            reconciler.reconcile(job_id=fixture.job_id, item_id=item).classification,
            "confirmed",
        )
        self.assertEqual(
            reconciler.reconcile(job_id=fixture.job_id, item_id=item).reason,
            "item_not_uncertain",
        )
        self.assertEqual(inspected, [True])
        self.assertEqual(
            fixture.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=fixture.job_id,
            ),
            "online_completed",
        )
        self.assertEqual(len(fixture.calls), 2)

    def test_previous_schema_keeps_guarded_local_finalization(self):
        fixture = self.scenario(revision=PREVIOUS)
        fixture.provider_result = "credential_missing"
        self.assertEqual(fixture.execute().classification, "needs_attention")
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=fixture.fixture.identity,
            ),
            1,
        )

    def test_manual_outcome_requires_exact_trusted_evidence_not_boolean(self):
        fixture = self.scenario()
        fixture.provider_result = "credential_missing"
        self.assertEqual(fixture.execute().reason, "online_completed")
        item_id = str(
            fixture.scalar(
                "SELECT id FROM ntubtob.account_erasure_items WHERE job_id=:id AND stage='provider_revocation'",
                id=fixture.job_id,
            )
        )
        for inspect in (
            lambda *args: True,
            lambda connection, job, item: ProviderOutcomeEvidence(
                "c" * 64,
                job["scope_hash"],
                str(job["expected_generation"]),
                "succeeded",
            ),
            lambda connection, job, item: ProviderOutcomeEvidence(
                item["binding_hash"],
                job["scope_hash"],
                str(job["expected_generation"]),
                "credential_missing",
            ),
        ):
            result = ProviderErasureReconciler(
                fixture.engine,
                inspect,
                clock=lambda: pending.NOW + timedelta(seconds=2),
            ).reconcile(job_id=fixture.job_id, item_id=item_id)
            self.assertEqual(result.reason, "evidence_not_verified", result)
        result = ProviderErasureReconciler(
            fixture.engine,
            lambda connection, job, item: ProviderOutcomeEvidence(
                item["binding_hash"],
                job["scope_hash"],
                str(job["expected_generation"]),
                "succeeded",
            ),
            clock=lambda: pending.NOW + timedelta(seconds=2),
        ).reconcile(job_id=fixture.job_id, item_id=item_id)
        self.assertEqual(result.classification, "confirmed", result)
        self.assertEqual(fixture.calls, 1)
        # Neither executor dispatch nor a newly inserted work item may reopen it.
        self.assertEqual(fixture.execute().reason, "receipt_read_required")
        with self.assertRaises(DBAPIError), fixture.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items(id,job_id,stage,binding_hash,expected_generation,created_at) SELECT gen_random_uuid(),id,'provider_revocation',scope_hash,expected_generation,updated_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": fixture.job_id},
            )

    def test_late_callback_unknown_does_not_downgrade_online_completion(self):
        fixture = self.scenario()
        calls = []

        def invoke():
            calls.append(True)
            self.assertEqual(
                fixture.executor._local(
                    fixture.job_id, fixture.snapshot
                ).classification,
                "confirmed",
            )
            self.assertEqual(
                fixture.executor._restore(
                    fixture.job_id, fixture.snapshot
                ).classification,
                "confirmed",
            )
            self.assertEqual(
                fixture.executor._finalize(fixture.job_id, fixture.snapshot).reason,
                "online_completed",
            )
            return None

        fixture.invoke = invoke
        fixture.execute()
        self.assertEqual(calls, [True])
        self.assertEqual(
            fixture.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=fixture.job_id,
            ),
            "online_completed",
        )
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_item_events e JOIN ntubtob.account_erasure_items i ON i.id=e.item_id WHERE i.job_id=:id AND i.stage='provider_revocation' AND e.event_sequence=2 AND e.event_kind='unknown'",
                id=fixture.job_id,
            ),
            1,
        )

    def test_unconfirmed_restore_still_preserves_target(self):
        fixture = self.scenario()
        fixture.provider_result = "manual_action_needed"
        fixture.store.read = lambda identifier: None
        result = fixture.execute()
        self.assertEqual(result.classification, "needs_attention", result)
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=fixture.fixture.identity,
            ),
            1,
        )

    def test_unknown_reconciliation_cannot_spend_final_sequence_on_manual_outcome(self):
        fixture = self.scenario()
        fixture.provider_result = None
        self.assertEqual(fixture.execute().reason, "online_completed")
        item_id = str(
            fixture.scalar(
                "SELECT id FROM ntubtob.account_erasure_items WHERE job_id=:id AND stage='provider_revocation'",
                id=fixture.job_id,
            )
        )
        reconciler = ProviderErasureReconciler(
            fixture.engine,
            lambda connection, job, item: ProviderOutcomeEvidence(
                item["binding_hash"],
                job["scope_hash"],
                str(job["expected_generation"]),
                "manual_action_needed",
            ),
            clock=lambda: pending.NOW + timedelta(seconds=2),
        )
        self.assertEqual(
            reconciler.reconcile(job_id=fixture.job_id, item_id=item_id).reason,
            "evidence_not_verified",
        )
        self.assertEqual(
            fixture.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id",
                id=item_id,
            ),
            2,
        )


@unittest.skipUnless(retention.ledger.DATABASE_URL, "isolated ledger URL required")
class ProviderPhaseRetentionPostgresTests(_FreshPhaseDatabases, unittest.TestCase):
    def setUp(self):
        self.engine = self.clone()
        self.fixture = retention.RetentionPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.request_age_days = 181
        self.addCleanup(close_fixture_connection, self.fixture)
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.connection = self.fixture.connection
        command.upgrade(self.fixture.config, PREVIOUS)

    def completion(self):
        backup = self.connection.scalar(
            text(
                "SELECT operation_id FROM ntubtob.account_erasure_backup_checks WHERE request_id=:id ORDER BY sequence DESC LIMIT 1"
            ),
            {"id": self.fixture.job},
        )
        return self.connection.scalar(
            text(
                "SELECT ntubtob.complete_erasure_retention(CAST(:job AS uuid),CAST(:generation AS uuid),CAST(:backup AS uuid))"
            ),
            dict(
                job=self.fixture.job,
                generation=self.fixture.generation,
                backup=str(backup),
            ),
        )

    def ready(self, result):
        # Request+181 deliberately exercises terminal retention. The global
        # day150 dispatch fence still needs current inventory BEFORE started.
        self.fixture.observe(
            operation=str(uuid4()),
            horizon=self.fixture.now - timedelta(days=2),
            suppression=self.fixture.now - timedelta(days=1),
        )
        self.fixture.complete_with_plan(provider_result=result, record_custody=False)

    def test_plan_purge_unknown_provider_does_not_authorize_completion(self):
        self.ready("response_unknown")
        command.upgrade(self.fixture.config, REVISION)
        self.fixture.purge_plan()
        self.fixture.reject(self.completion, "minimal_retention_work_unfinished")
        self.fixture.reject(
            lambda: command.downgrade(self.fixture.config, PREVIOUS),
            "provider_phases_downgrade_requires_review",
        )

    def test_upgrade_refuses_historical_false_completed(self):
        self.ready("credential_missing")
        self.fixture.purge_plan()
        self.assertEqual(self.completion(), "retention_completed")
        self.fixture.reject(
            lambda: command.upgrade(self.fixture.config, REVISION),
            "provider_phases_historical_completion_unproven",
        )

    def test_unused_upgrade_downgrade_restores_exact_bodies(self):
        signatures = (
            "ntubtob.guard_erasure_item_event()",
            "ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid)",
            "ntubtob.require_erasure_retention_context(uuid,uuid,uuid,boolean)",
        )

        def definitions():
            return [
                self.connection.scalar(
                    text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))"),
                    {"name": name},
                )
                for name in signatures
            ]

        before = definitions()
        command.upgrade(self.fixture.config, REVISION)
        command.downgrade(self.fixture.config, PREVIOUS)
        self.assertEqual(definitions(), before)

    def test_real_provider_evidence_after_plan_purge_allows_completion(self):
        self.ready("manual_action_needed")
        command.upgrade(self.fixture.config, REVISION)
        self.fixture.purge_plan()
        self.fixture.reject(self.completion, "minimal_retention_work_unfinished")
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_item_events(item_id,event_sequence,event_kind,result_code,occurred_at) SELECT id,3,'confirmed','succeeded',:now FROM ntubtob.account_erasure_items WHERE job_id=:job AND stage='provider_revocation'"
            ),
            dict(now=self.fixture.now, job=self.fixture.job),
        )
        self.assertEqual(self.completion(), "retention_completed")
        self.fixture.reject(
            lambda: command.downgrade(self.fixture.config, PREVIOUS),
            "provider_phases_downgrade_requires_review",
        )

    def test_online_nonprovider_event_new_start_and_unproven_completion_rejected(self):
        self.ready("not_applicable")
        command.upgrade(self.fixture.config, REVISION)
        for stage, sequence, kind, result in (
            ("provider_revocation", 3, "started", "in_progress"),
            ("restore_suppression", 3, "confirmed", "succeeded"),
        ):

            def write():
                self.connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events(item_id,event_sequence,event_kind,result_code,occurred_at) SELECT id,:sequence,:kind,:result,:now FROM ntubtob.account_erasure_items WHERE job_id=:job AND stage=:stage"
                    ),
                    dict(
                        sequence=sequence,
                        kind=kind,
                        result=result,
                        now=self.fixture.now,
                        job=self.fixture.job,
                        stage=stage,
                    ),
                )

            self.fixture.reject(write, "erasure online outcome rejected")
        self.fixture.purge_plan()
        self.fixture.reject(self.completion, "minimal_retention_work_unfinished")

    def test_upgrade_preserves_function_acl_owner_and_no_runtime_capability(self):
        def attributes():
            return self.connection.execute(
                text(
                    "SELECT oid::regprocedure::text,proowner,proacl::text,prosecdef,proconfig FROM pg_proc WHERE oid IN ('ntubtob.guard_erasure_item_event()'::regprocedure,'ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid)'::regprocedure,'ntubtob.require_erasure_retention_context(uuid,uuid,uuid,boolean)'::regprocedure) ORDER BY oid"
                )
            ).all()

        before = attributes()
        command.upgrade(self.fixture.config, REVISION)
        self.assertEqual(attributes(), before)

    def test_same_timestamp_late_outcome_cannot_hide_downgrade_history(self):
        self.ready("response_unknown")
        command.upgrade(self.fixture.config, REVISION)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_item_events(item_id,event_sequence,event_kind,result_code,occurred_at) SELECT i.id,3,'confirmed','succeeded',j.online_completed_at FROM ntubtob.account_erasure_items i JOIN ntubtob.account_erasure_jobs j ON j.id=i.job_id WHERE j.id=:job AND i.stage='provider_revocation'"
            ),
            {"job": self.fixture.job},
        )
        self.fixture.reject(
            lambda: command.downgrade(self.fixture.config, PREVIOUS),
            "provider_phases_downgrade_requires_review",
        )

    def test_unresolved_nonprovider_step_keeps_plan(self):
        self.ready("response_unknown")
        command.upgrade(self.fixture.config, REVISION)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_steps(job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at) VALUES(:job,'online_erasure',1,2,'unknown','response_unknown',:now)"
            ),
            dict(job=self.fixture.job, now=self.fixture.now),
        )
        self.fixture.reject(self.fixture.purge_plan, "plan_purge_work_unfinished")

    def test_filtered_retention_function_cannot_treat_hidden_evidence_as_complete(self):
        command.upgrade(self.fixture.config, REVISION)
        role = self.fixture.runtime
        self.connection.execute(text(f'GRANT USAGE ON SCHEMA ntubtob TO "{role}"'))
        self.connection.execute(
            text(f'GRANT SELECT ON ALL TABLES IN SCHEMA ntubtob TO "{role}"')
        )
        self.connection.execute(
            text(
                f'ALTER FUNCTION ntubtob.require_erasure_retention_context(uuid,uuid,uuid,boolean) OWNER TO "{role}"'
            )
        )

        def call():
            self.connection.execute(
                text(
                    "SELECT ntubtob.require_erasure_retention_context(CAST(:job AS uuid),CAST(:generation AS uuid),CAST(:backup AS uuid),false)"
                ),
                dict(
                    job=self.fixture.job,
                    generation=self.fixture.generation,
                    backup=str(uuid4()),
                ),
            )

        self.fixture.reject(call, "minimal_retention_unfiltered_state_required")
