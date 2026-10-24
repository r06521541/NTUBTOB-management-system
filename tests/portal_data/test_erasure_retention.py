"""Rollback-only real PG retention guard; no real provider or custody effects."""

import unittest
from datetime import timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.portal_data import test_erasure_ledger as ledger

REVISION = "0022_erasure_retention"
FUNCTION = "ntubtob.record_erasure_backup_check(uuid,uuid,uuid,text,boolean,timestamptz,timestamptz,boolean,boolean)"


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL required")
class RetentionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ledger.ErasureLedgerPostgresTests.setUpClass.__func__(cls)

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
        self.runtime = "fake_retention_" + uuid4().hex
        self.connection.execute(text(f'CREATE ROLE "{self.runtime}" NOLOGIN'))
        for privileges, kind in (("ALL", "TABLES"), ("EXECUTE", "FUNCTIONS")):
            self.connection.execute(
                text(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT {privileges} ON {kind} TO "{self.runtime}"'
                )
            )
        command.upgrade(self.config, REVISION)
        self.now = self.connection.scalar(text("SELECT clock_timestamp()"))
        self.requested = self.now - timedelta(
            days=getattr(self, "request_age_days", 179)
        )
        self.generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.person},
            )
        )
        self.job = self.make_job(self.fixture.person, self.generation, self.requested)
        self.args = dict(
            operation=str(uuid4()),
            request=self.job,
            generation=self.generation,
            inventory="d" * 64,
            complete=True,
            horizon=self.now + timedelta(days=10),
            suppression=None,
            binding=True,
            key=True,
        )

    def make_job(self, person, generation, requested):
        return self.fixture.job(
            person_id=person,
            expected_generation=generation,
            requested_at=requested,
            updated_at=requested,
            fulfillment_due_at=requested + timedelta(days=30),
            receipt_expires_at=requested + timedelta(days=180),
            evidence_expires_at=requested + timedelta(days=180),
        )

    def observe(self, **changes):
        return self.connection.scalar(
            text(
                "SELECT ntubtob.record_erasure_backup_check(CAST(:operation AS uuid),CAST(:request AS uuid),CAST(:generation AS uuid),:inventory,:complete,:horizon,:suppression,:binding,:key)"
            ),
            {**self.args, **changes},
        )

    def item(self, *, job=None, generation=None, stage="online_erasure"):
        job, generation = job or self.job, generation or self.generation
        self.fixture.update(
            job, status="verified", verified_at=self.now, updated_at=self.now
        )
        self.fixture.update(
            job,
            status="processing",
            irreversible_started_at=self.now,
            updated_at=self.now,
        )
        identifier = str(uuid4())
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_items(id,job_id,stage,binding_hash,expected_generation,created_at) VALUES(:id,:job,:stage,:hash,:generation,:now)"
            ),
            dict(
                id=identifier,
                job=job,
                stage=stage,
                hash="b" * 64,
                generation=generation,
                now=self.now,
            ),
        )
        return identifier

    def event(self, item, *, sequence=1, kind="started", result="in_progress"):
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_item_events(item_id,event_sequence,event_kind,result_code,occurred_at) VALUES(:item,:sequence,:kind,:result,:now)"
            ),
            dict(item=item, sequence=sequence, kind=kind, result=result, now=self.now),
        )

    def reject(self, action, reason):
        with self.connection.begin_nested() as nested:
            try:
                action()
            except DBAPIError as error:
                self.assertIn(reason, str(error.orig))
                nested.rollback()
                return
            self.fail("expected fixed database rejection")

    def test_unknown_old_request_blocks_every_new_irreversible_stage(self):
        item = self.item()
        self.reject(lambda: self.event(item), "retention_backup_horizon_unresolved")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_item_events")
            ),
            0,
        )

    def test_known_future_horizon_allows_start_without_claiming_backup_absence(self):
        operation = self.observe()
        self.assertEqual(str(operation), self.args["operation"])
        item = self.item()
        self.event(item)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_item_events")
            ),
            1,
        )

    def test_existing_outcome_can_finish_after_a_new_unknown_check(self):
        self.observe()
        item = self.item()
        self.event(item)
        self.observe(operation=str(uuid4()), complete=False, horizon=None)
        self.event(item, sequence=2, kind="confirmed", result="succeeded")
        # Another new effect of this already-processing job is still fenced.
        second = str(uuid4())
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_items(id,job_id,stage,binding_hash,expected_generation,created_at) VALUES(:id,:job,'provider_revocation',:hash,:generation,:now)"
            ),
            dict(
                id=second,
                job=self.job,
                hash="e" * 64,
                generation=self.generation,
                now=self.now,
            ),
        )
        self.reject(lambda: self.event(second), "retention_backup_horizon_unresolved")

    def test_restore_custody_append_is_not_an_erase_exemption(self):
        item = self.item(stage="restore_suppression")
        self.event(item)
        self.event(item, sequence=2, kind="confirmed", result="succeeded")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            ),
            "processing",
        )

    def test_unknown_old_job_blocks_unrelated_new_job(self):
        generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.other_person},
            )
        )
        new = self.make_job(
            self.fixture.other_person, generation, self.now - timedelta(seconds=1)
        )
        item = self.item(job=new, generation=generation)
        self.reject(lambda: self.event(item), "retention_backup_horizon_unresolved")

    def test_latest_unknown_cannot_fall_back_to_earlier_known_inventory(self):
        self.observe()
        self.observe(operation=str(uuid4()), complete=False, horizon=None)
        item = self.item()
        self.reject(lambda: self.event(item), "retention_backup_horizon_unresolved")

    def test_exact_replay_keeps_clock_sequence_and_rejects_changed_args(self):
        original = self.observe()
        before = self.connection.execute(
            text("SELECT * FROM ntubtob.account_erasure_backup_checks")
        ).one()
        self.assertEqual(self.observe(), original)
        self.assertEqual(
            self.connection.execute(
                text("SELECT * FROM ntubtob.account_erasure_backup_checks")
            ).one(),
            before,
        )
        self.reject(
            lambda: self.observe(inventory="e" * 64), "backup_check_operation_replay"
        )
        self.reject(
            lambda: self.observe(operation=str(uuid4()), generation=str(uuid4())),
            "backup_check_root_rejected",
        )

    def test_runtime_default_grants_guc_and_raw_mutation_cannot_forge_observation(self):
        self.assertFalse(
            self.connection.scalar(
                text("SELECT has_function_privilege(:role,:signature,'EXECUTE')"),
                dict(role=self.runtime, signature=FUNCTION),
            )
        )
        self.assertFalse(
            self.connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,'ntubtob.account_erasure_backup_checks','INSERT')"
                ),
                {"role": self.runtime},
            )
        )
        self.connection.execute(text("SET LOCAL ntubtob.retention_ready='true'"))
        item = self.item()
        self.reject(lambda: self.event(item), "retention_backup_horizon_unresolved")
        self.observe()
        self.reject(
            lambda: self.connection.execute(
                text("DELETE FROM ntubtob.account_erasure_backup_checks")
            ),
            "erasure evidence mutation rejected",
        )

    def test_acknowledged_backup_check_prevents_native_downgrade(self):
        self.observe()
        self.reject(
            lambda: command.downgrade(self.config, "0021_erasure_continuity"),
            "retention_evidence_retained",
        )

    def test_empty_native_downgrade_and_reupgrade_preserve_old_guards(self):
        command.downgrade(self.config, "0021_erasure_continuity")
        self.assertIsNone(
            self.connection.scalar(
                text("SELECT to_regclass('ntubtob.account_erasure_backup_checks')")
            )
        )
        command.upgrade(self.config, REVISION)
        self.observe()

    def test_22_continuity_function_and_reader_preserve_original_deadlines(self):
        from shared_lib.shared_module.portal_data.erasure_continuity import (
            effective_deadlines,
        )

        original = (
            self.connection.execute(
                text(
                    "SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE"
                ),
                {"id": self.job},
            )
            .mappings()
            .one()
        )
        until = self.now + timedelta(days=60)
        self.connection.execute(
            text(
                "SELECT ntubtob.extend_erasure_continuity(CAST(:id AS uuid),CAST(:generation AS uuid),0,CAST(:operation AS uuid),:until,:until)"
            ),
            dict(
                id=self.job,
                generation=self.generation,
                operation=str(uuid4()),
                until=until,
            ),
        )
        result = effective_deadlines(self.connection, original, revisions=(REVISION,))
        self.assertEqual(result.receipt_until, until)
        self.assertEqual(result.evidence_until, until)
        self.assertEqual(
            original["receipt_expires_at"], self.requested + timedelta(days=180)
        )

    def test_force_rls_function_owner_cannot_silently_accept_partial_inventory(self):
        owner = "fake_retention_owner_" + uuid4().hex
        self.connection.execute(text(f'CREATE ROLE "{owner}" NOLOGIN'))
        self.connection.execute(text(f'GRANT USAGE ON SCHEMA ntubtob TO "{owner}"'))
        self.connection.execute(
            text(f'GRANT SELECT ON ntubtob.alembic_version TO "{owner}"')
        )
        self.connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        for table in (
            "account_erasure_jobs",
            "account_erasure_intakes",
            "account_erasure_backup_checks",
        ):
            self.connection.execute(
                text(f'ALTER TABLE ntubtob.{table} OWNER TO "{owner}"')
            )
        self.connection.execute(text(f'ALTER FUNCTION {FUNCTION} OWNER TO "{owner}"'))
        self.connection.execute(
            text(
                "ALTER TABLE ntubtob.account_erasure_backup_checks FORCE ROW LEVEL SECURITY"
            )
        )
        self.reject(self.observe, "backup_check_unfiltered_state_required")

    def test_explicit_operator_capability_does_not_grant_runtime_insert(self):
        operator = "fake_retention_operator_" + uuid4().hex
        self.connection.execute(text(f'CREATE ROLE "{operator}" NOLOGIN'))
        self.connection.execute(
            text(f'GRANT USAGE ON SCHEMA ntubtob TO "{operator}","{self.runtime}"')
        )
        self.connection.execute(
            text(f'GRANT EXECUTE ON FUNCTION {FUNCTION} TO "{operator}"')
        )
        self.connection.execute(text(f'SET LOCAL ROLE "{self.runtime}"'))
        self.reject(self.observe, "permission denied")
        self.connection.execute(text(f'SET LOCAL ROLE "{operator}"'))
        self.assertEqual(str(self.observe()), self.args["operation"])
        self.connection.execute(text("SET LOCAL ROLE NONE"))
        self.assertFalse(
            self.connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,'ntubtob.account_erasure_backup_checks','INSERT')"
                ),
                {"role": operator},
            )
        )

    def capture_plan(self):
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_sealed_plans(job_id,key_id,ciphertext) VALUES(:id,'fictional-shared-key',:blob)"
            ),
            dict(id=self.job, blob=b"x" * 60),
        )

    def complete_with_plan(
        self,
        *,
        online_days_ago=31,
        record_custody=True,
        unfinished=False,
        capture_plan=True,
        provider_result=None,
    ):
        if capture_plan:
            self.capture_plan()
        online = self.now - timedelta(days=online_days_ago)
        self.fixture.update(
            self.job,
            status="verified",
            verified_at=self.requested + timedelta(seconds=1),
            updated_at=online,
        )
        self.fixture.update(
            self.job,
            status="processing",
            irreversible_started_at=online,
            updated_at=online,
        )
        item = str(uuid4())
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_items(id,job_id,stage,binding_hash,expected_generation,created_at) VALUES(:id,:job,'restore_suppression',:hash,:generation,:now)"
            ),
            dict(
                id=item,
                job=self.job,
                hash="c" * 64,
                generation=self.generation,
                now=online,
            ),
        )
        for sequence, kind, result in (
            (1, "started", "in_progress"),
            (2, "confirmed", "succeeded"),
        ):
            self.connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_item_events(item_id,event_sequence,event_kind,result_code,occurred_at) VALUES(:item,:seq,:kind,:result,:now)"
                ),
                dict(item=item, seq=sequence, kind=kind, result=result, now=online),
            )
        if unfinished or provider_result is not None:
            provider_item = str(uuid4())
            self.connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items(id,job_id,stage,binding_hash,expected_generation,created_at) VALUES(:id,:job,'provider_revocation',:hash,:generation,:now)"
                ),
                dict(
                    id=provider_item,
                    job=self.job,
                    hash="e" * 64,
                    generation=self.generation,
                    now=online,
                ),
            )
            if provider_result is not None:
                for sequence, kind, result in (
                    (1, "started", "in_progress"),
                    (
                        2,
                        (
                            "unknown"
                            if provider_result == "response_unknown"
                            else "confirmed"
                        ),
                        provider_result,
                    ),
                ):
                    self.connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_erasure_item_events(item_id,event_sequence,event_kind,result_code,occurred_at) VALUES(:item,:seq,:kind,:result,:now)"
                        ),
                        dict(
                            item=provider_item,
                            seq=sequence,
                            kind=kind,
                            result=result,
                            now=online,
                        ),
                    )
        self.fixture.update(
            self.job,
            status="online_completed",
            online_completed_at=online,
            updated_at=online,
            person_id=None,
            auth_identity_id=None,
        )
        if record_custody:
            self.observe()

    def purge_plan(self, *, operation=None, generation=None):
        return self.connection.scalar(
            text(
                "SELECT ntubtob.purge_erasure_sealed_plan(CAST(:job AS uuid),CAST(:generation AS uuid),:scope,CAST(:operation AS uuid))"
            ),
            dict(
                job=self.job,
                generation=generation or self.generation,
                scope="a" * 64,
                operation=operation or str(uuid4()),
            ),
        )

    def test_online_plus_thirty_private_plan_exact_purge_is_atomic_and_replayable(self):
        self.complete_with_plan()
        original = self.connection.execute(
            text(
                "SELECT status,online_completed_at,completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
            ),
            {"id": self.job},
        ).one()
        operation = str(uuid4())
        self.assertEqual(str(self.purge_plan(operation=operation)), operation)
        self.assertEqual(str(self.purge_plan(operation=operation)), operation)
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id"
                ),
                {"id": self.job},
            ),
            0,
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.erasure_plan_delete_permits")
            ),
            0,
        )
        self.assertEqual(
            self.connection.execute(
                text(
                    "SELECT status,online_completed_at,completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job},
            ).one(),
            original,
        )
        self.reject(self.purge_plan, "plan_purge_already_recorded")

    def test_private_plan_not_due_or_unverified_custody_does_not_delete(self):
        self.complete_with_plan(online_days_ago=29, record_custody=False)
        self.reject(self.purge_plan, "plan_purge_not_due")
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id"
                ),
                {"id": self.job},
            ),
            1,
        )

    def test_private_plan_requires_readable_independent_custody_and_same_generation(
        self,
    ):
        self.complete_with_plan(record_custody=False)
        self.reject(self.purge_plan, "plan_purge_custody_unverified")
        self.observe(binding=False)
        self.reject(self.purge_plan, "plan_purge_custody_unverified")
        self.reject(
            lambda: self.purge_plan(generation=str(uuid4())),
            "plan_purge_binding_rejected",
        )

    def test_private_plan_raw_delete_guc_and_runtime_permissions_cannot_mint_permit(
        self,
    ):
        self.complete_with_plan()
        self.connection.execute(
            text("SET LOCAL ntubtob.erasure_plan_delete='approved'")
        )
        self.reject(
            lambda: self.connection.execute(
                text(
                    "DELETE FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id"
                ),
                {"id": self.job},
            ),
            "erasure evidence mutation rejected",
        )
        for table in ("erasure_plan_delete_permits", "account_erasure_plan_purges"):
            self.assertFalse(
                self.connection.scalar(
                    text(
                        "SELECT has_table_privilege(:role,:table,'INSERT,UPDATE,DELETE,TRUNCATE')"
                    ),
                    dict(role=self.runtime, table="ntubtob." + table),
                )
            )
        self.assertFalse(
            self.connection.scalar(
                text(
                    "SELECT has_function_privilege(:role,'ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid)','EXECUTE')"
                ),
                {"role": self.runtime},
            )
        )

    def test_private_plan_exact_day_thirty_and_rollback_keep_shared_key_other_job(self):
        self.complete_with_plan(online_days_ago=30)
        generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.other_person},
            )
        )
        other = self.make_job(self.fixture.other_person, generation, self.requested)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_sealed_plans(job_id,key_id,ciphertext) VALUES(:id,'fictional-shared-key',:blob)"
            ),
            dict(id=other, blob=b"y" * 60),
        )
        with self.connection.begin_nested() as nested:
            self.purge_plan()
            self.assertEqual(
                self.connection.scalar(
                    text("SELECT count(*) FROM ntubtob.account_erasure_plan_purges")
                ),
                1,
            )
            nested.rollback()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_sealed_plans")
            ),
            2,
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_plan_purges")
            ),
            0,
        )
        self.purge_plan()
        other_plan = self.connection.execute(
            text(
                "SELECT key_id,ciphertext FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id"
            ),
            {"id": other},
        ).one()
        self.assertEqual(
            (other_plan[0], bytes(other_plan[1])), ("fictional-shared-key", b"y" * 60)
        )

    def test_private_plan_unknown_unstarted_item_prevents_cleanup_even_if_online_marked(
        self,
    ):
        self.complete_with_plan(unfinished=True)
        self.reject(self.purge_plan, "plan_purge_work_unfinished")
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id"
                ),
                {"id": self.job},
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
