"""Rollback-only minimal retention cleanup, never real erasure/provider evidence."""

import unittest
from datetime import timedelta
from uuid import uuid4

from alembic import command
from sqlalchemy import text

from shared_lib.shared_module.portal_data.erasure_management_guard import (
    ManagementGuardUnavailable,
    ManagementWritesSuspended,
    read_applied_admin_suspension,
    require_management_writes_available,
)
from tests.portal_data import test_erasure_retention as retention

REVISION = "0023_erasure_minimal_retention"


@unittest.skipUnless(retention.ledger.DATABASE_URL, "isolated ledger URL required")
class MinimalRetentionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retention.RetentionPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = retention.RetentionPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.request_age_days = 181
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.connection = self.fixture.connection
        self.job = self.fixture.job
        self.generation = self.fixture.generation
        self.now = self.fixture.now
        command.upgrade(self.fixture.config, REVISION)

    def ready(self, **options):
        self.fixture.complete_with_plan(**options)
        self.fixture.purge_plan()
        self.backup = str(uuid4())
        self.fixture.observe(
            operation=self.backup,
            horizon=self.now - timedelta(days=2),
            suppression=self.now - timedelta(days=1),
        )

    def call(self, function, *, generation=None, backup=None):
        return self.connection.scalar(
            text(
                f"SELECT ntubtob.{function}(CAST(:job AS uuid),CAST(:generation AS uuid),CAST(:backup AS uuid))"
            ),
            dict(
                job=self.job,
                generation=generation or self.generation,
                backup=backup or self.backup,
            ),
        )

    def complete(self):
        return self.call("complete_erasure_retention")

    def purge(self, **values):
        return self.call("purge_erasure_minimal_evidence", **values)

    def test_online_only_is_not_terminal_and_completion_needs_verified_backup(self):
        self.ready()
        self.fixture.reject(self.purge, "minimal_retention_not_terminal")
        self.assertEqual(self.complete(), "retention_completed")
        self.assertEqual(self.complete(), "retention_already_completed")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            ),
            "completed",
        )

    def test_exact_expired_terminal_cleanup_leaves_no_per_job_tombstone(self):
        self.ready()
        self.complete()
        self.assertEqual(self.purge(), "minimal_evidence_removed")
        for table, column in (
            ("account_erasure_jobs", "id"),
            ("account_erasure_items", "job_id"),
            ("account_erasure_steps", "job_id"),
            ("account_erasure_plan_purges", "job_id"),
            ("account_erasure_backup_checks", "request_id"),
            ("account_erasure_continuity_events", "request_id"),
        ):
            self.assertEqual(
                self.connection.scalar(
                    text(f"SELECT count(*) FROM ntubtob.{table} WHERE {column}=:id"),
                    {"id": self.job},
                ),
                0,
            )
        self.fixture.reject(self.purge, "minimal_retention_root_absent_unverified")

    def test_latest_unknown_or_different_observation_never_reuses_old_approval(self):
        self.ready()
        self.complete()
        self.fixture.observe(
            operation=str(uuid4()), complete=False, horizon=None, suppression=None
        )
        self.fixture.reject(self.purge, "minimal_retention_backup_unverified")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            ),
            1,
        )

    def test_wrong_generation_never_deletes_another_root(self):
        self.ready()
        self.complete()
        self.fixture.reject(
            lambda: self.purge(generation=str(uuid4())),
            "minimal_retention_binding_rejected",
        )

    def test_real_last_admin_suspension_survives_linkage_minimization(self):
        person = self.fixture.fixture.person
        self.fixture.capture_plan()
        self.connection.execute(
            text("UPDATE ntubtob.portal_authority_state SET mode='persistent',epoch=10")
        )
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"),
            {"id": person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": person, "id": self.fixture.fixture.identity},
        )
        self.fixture.fixture.update(
            self.job,
            status="verified",
            verified_at=self.fixture.requested + timedelta(seconds=1),
            updated_at=self.now - timedelta(days=31),
        )
        operation = str(uuid4())
        self.connection.execute(
            text(
                "SELECT ntubtob.suspend_management_for_erasure(CAST(:job AS uuid),"
                "CAST(:generation AS uuid),10,CAST(:operation AS uuid))"
            ),
            dict(job=self.job, generation=self.generation, operation=operation),
        )
        approval = read_applied_admin_suspension(
            self.connection,
            job_id=self.job,
            generation=self.generation,
            scope_hash="a" * 64,
        )
        self.assertEqual(approval.operation_id, operation)
        before = self.connection.scalar(
            text(
                "SELECT to_jsonb(r) FROM ntubtob.account_erasure_admin_recovery_operations r "
                "WHERE operation_id=:id"
            ),
            {"id": operation},
        )
        self.ready(capture_plan=False)
        self.complete()
        self.purge()
        after = self.connection.scalar(
            text(
                "SELECT to_jsonb(r) FROM ntubtob.account_erasure_admin_recovery_operations r "
                "WHERE operation_id=:id"
            ),
            {"id": operation},
        )
        for field in ("job_id", "expected_generation", "scope_hash"):
            self.assertIsNone(after.pop(field))
            before.pop(field)
        self.assertIsNotNone(after.pop("minimized_at"))
        self.assertIsNone(before.pop("minimized_at"))
        self.assertEqual(after, before)
        self.assertEqual(
            self.connection.execute(
                text(
                    "SELECT epoch,management_suspension_operation_id::text "
                    "FROM ntubtob.portal_authority_state"
                )
            ).one(),
            (11, operation),
        )
        with self.assertRaises(ManagementWritesSuspended):
            require_management_writes_available(self.connection)
        with self.assertRaises(ManagementGuardUnavailable):
            read_applied_admin_suspension(
                self.connection,
                job_id=self.job,
                generation=self.generation,
                scope_hash="a" * 64,
            )

    def test_effective_continuity_window_prevents_day180_cleanup(self):
        self.ready()
        self.complete()
        root = (
            self.connection.execute(
                text("SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            )
            .mappings()
            .one()
        )
        # Fictional historical extension event, inserted by fixture owner only.
        # This tests chain resolution, not permission to backdate an operator call.
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_continuity_events(operation_id,request_id,target_kind,expected_generation,original_requested_at,original_receipt_hash,sequence,previous_receipt_until,previous_evidence_until,receipt_until,evidence_until,occurred_at,operator_name) VALUES(:operation,:id,:kind,:generation,:requested,:hash,1,:old_receipt,:old_evidence,:until,:until,:occurred,SESSION_USER)"
            ),
            dict(
                operation=str(uuid4()),
                id=self.job,
                kind=root["target_kind"],
                generation=self.generation,
                requested=root["requested_at"],
                hash=root["receipt_secret_hash"],
                old_receipt=root["receipt_expires_at"],
                old_evidence=root["evidence_expires_at"],
                until=root["requested_at"] + timedelta(days=210),
                occurred=root["requested_at"] + timedelta(days=179),
            ),
        )
        self.fixture.reject(self.purge, "minimal_retention_window_active")

    def test_cleanup_rollback_restores_children_and_no_permit_leaks(self):
        self.ready()
        self.complete()
        with self.connection.begin_nested() as nested:
            self.purge()
            nested.rollback()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            ),
            1,
        )
        self.assertGreater(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_backup_checks WHERE request_id=:id"
                ),
                {"id": self.job},
            ),
            0,
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.erasure_evidence_delete_permits")
            ),
            0,
        )

    def test_raw_delete_and_runtime_capabilities_cannot_mint_cleanup(self):
        self.ready()
        self.complete()
        self.fixture.reject(
            lambda: self.connection.execute(
                text("DELETE FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            ),
            "erasure evidence mutation rejected",
        )
        for function in (
            "complete_erasure_retention",
            "purge_erasure_minimal_evidence",
        ):
            self.assertFalse(
                self.connection.scalar(
                    text("SELECT has_function_privilege(:role,:signature,'EXECUTE')"),
                    dict(
                        role=self.fixture.runtime,
                        signature=f"ntubtob.{function}(uuid,uuid,uuid)",
                    ),
                )
            )
        self.assertFalse(
            self.connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,'ntubtob.erasure_evidence_delete_permits','INSERT,UPDATE,DELETE,TRUNCATE')"
                ),
                {"role": self.fixture.runtime},
            )
        )

    def test_irreversible_cleanup_blocks_downgrade_without_target_tombstone(self):
        self.ready()
        self.complete()
        self.purge()
        self.fixture.reject(
            lambda: command.downgrade(self.fixture.config, "0022_erasure_retention"),
            "minimal_retention_irreversible",
        )

    def late_trigger(self, table, event, body):
        # Fixture-owned, rollback-only interference after the production guard.
        self.connection.execute(
            text(
                f"CREATE FUNCTION ntubtob.fake_late_retention() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {body} END $$"
            )
        )
        self.connection.execute(
            text(
                f"CREATE TRIGGER z_fake_late_retention BEFORE {event} ON ntubtob.{table} FOR EACH ROW EXECUTE FUNCTION ntubtob.fake_late_retention()"
            )
        )

    def test_completion_rejects_swallowed_or_rewritten_step_and_job(self):
        self.ready()
        for table, event, body in (
            ("account_erasure_steps", "INSERT", "RETURN NULL;"),
            (
                "account_erasure_steps",
                "INSERT",
                "NEW.result_code:='not_applicable'; RETURN NEW;",
            ),
            ("account_erasure_jobs", "UPDATE", "RETURN NULL;"),
            (
                "account_erasure_jobs",
                "UPDATE",
                "NEW.updated_at:=NEW.updated_at+interval '1 second'; RETURN NEW;",
            ),
        ):
            with self.subTest(table=table, body=body):
                with self.connection.begin_nested() as nested:
                    self.late_trigger(table, event, body)
                    self.fixture.reject(
                        self.complete, "minimal_retention_completion_unverified"
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"
                            ),
                            {"id": self.job},
                        ),
                        "online_completed",
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id AND stage='completion'"
                            ),
                            {"id": self.job},
                        ),
                        0,
                    )
                    nested.rollback()

    def test_cleanup_rejects_swallowed_or_rewritten_irreversible_flag(self):
        self.ready()
        self.complete()
        for body in ("RETURN NULL;", "NEW.cleanup_performed:=false; RETURN NEW;"):
            with self.subTest(body=body):
                with self.connection.begin_nested() as nested:
                    self.late_trigger("erasure_retention_state", "UPDATE", body)
                    self.fixture.reject(
                        self.purge, "minimal_retention_state_unverified"
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.account_erasure_jobs WHERE id=:id"
                            ),
                            {"id": self.job},
                        ),
                        1,
                    )
                    self.assertFalse(
                        self.connection.scalar(
                            text(
                                "SELECT cleanup_performed FROM ntubtob.erasure_retention_state"
                            )
                        )
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.erasure_evidence_delete_permits"
                            )
                        ),
                        0,
                    )
                    nested.rollback()

    def test_cleanup_rejects_rewritten_recovery_postimage(self):
        self.ready()
        self.complete()
        operation = str(uuid4())
        # Fixture owner supplies historical evidence, not a live approval claim.
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_admin_recovery_operations(operation_id,job_id,expected_generation,scope_hash,expected_epoch,applied_epoch,operator_session_user,applied_at) VALUES(:op,:job,:generation,:scope,1,2,'fictional-operator',:now)"
            ),
            dict(
                op=operation,
                job=self.job,
                generation=self.generation,
                scope="a" * 64,
                now=self.now,
            ),
        )
        self.late_trigger(
            "account_erasure_admin_recovery_operations",
            "UPDATE",
            "NEW.operator_session_user:='fictional-rewritten'; RETURN NEW;",
        )
        self.fixture.reject(self.purge, "minimal_retention_delete_unverified")
        self.assertEqual(
            self.connection.execute(
                text(
                    "SELECT job_id::text,operator_session_user,minimized_at FROM ntubtob.account_erasure_admin_recovery_operations WHERE operation_id=:id"
                ),
                {"id": operation},
            ).one(),
            (self.job, "fictional-operator", None),
        )

    def test_cleanup_rejects_missing_expected_foreign_key(self):
        self.ready()
        self.complete()
        self.connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        self.connection.execute(
            text(
                "ALTER TABLE ntubtob.account_erasure_admin_recovery_operations DROP CONSTRAINT fk_erasure_admin_recovery_job"
            )
        )
        self.fixture.reject(self.purge, "minimal_retention_dependency_changed")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job},
            ),
            1,
        )

    def test_cancelled_never_dispatched_plan_uses_terminal_backup_gate(self):
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_sealed_plans(job_id,key_id,ciphertext) VALUES(:id,'fictional-cancelled-key',:blob)"
            ),
            dict(id=self.job, blob=b"x" * 60),
        )
        self.fixture.fixture.update(
            self.job,
            status="cancelled",
            cancelled_at=self.now,
            updated_at=self.now,
            person_id=None,
            auth_identity_id=None,
        )
        self.backup = str(uuid4())
        self.fixture.observe(
            operation=self.backup,
            horizon=self.now + timedelta(days=1),
            suppression=None,
        )
        self.fixture.reject(self.purge, "minimal_retention_backup_unverified")
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id"
                ),
                {"id": self.job},
            ),
            1,
        )
        self.backup = str(uuid4())
        self.fixture.observe(
            operation=self.backup,
            horizon=self.now - timedelta(days=2),
            suppression=self.now - timedelta(days=1),
        )
        self.assertEqual(self.purge(), "minimal_evidence_removed")
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
        self.fixture.reject(self.purge, "minimal_retention_root_absent_unverified")


if __name__ == "__main__":
    unittest.main()
