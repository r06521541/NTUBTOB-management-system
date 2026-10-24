"""Private suspension primitive; isolated PG DDL/roles/history roll back together.

No old harness is taught to discard 0019 evidence. Tests upgrade an existing 0018
fixture only inside their outer transaction, then roll the entire candidate back.
The fictional owner/operator/runtime roles are not deployment role definitions.
"""

import importlib.util
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from shared_lib.shared_module.portal_data.erasure_management_guard import (
    ManagementGuardUnavailable,
    ManagementWritesSuspended,
    read_applied_admin_suspension,
    require_management_writes_available,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)

ROOT = Path(__file__).resolve().parents[2]
TABLE = "ntubtob.account_erasure_admin_recovery_operations"
FUNCTION = "ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)"
REVISION = "0019_erasure_admin_recovery"


def migration():
    spec = importlib.util.spec_from_file_location(
        "erasure_admin_recovery",
        ROOT / "migrations/versions/0019_erasure_admin_recovery.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AdminRecoverySchemaTests(unittest.TestCase):
    def sql(self, action="upgrade"):
        module = migration()
        with patch.object(module.op, "execute") as execute:
            getattr(module, action)()
        return "\n".join(str(call.args[0]) for call in execute.call_args_list)

    def test_private_capability_exact_revision_and_native_lock_order(self):
        self.assertEqual(migration().revision, REVISION)
        self.assertEqual(migration().down_revision, "0018_erasure_privacy_mutation")
        sql = self.sql()
        self.assertIn("SECURITY DEFINER SET search_path=pg_catalog", sql)
        self.assertIn("SECURITY INVOKER SET search_path=pg_catalog", sql)
        self.assertLess(
            sql.index("pg_advisory_xact_lock(70070)"),
            sql.index("pg_advisory_xact_lock(1315198274)"),
        )
        self.assertIn(REVISION, sql)
        self.assertIn("session_user", sql)
        self.assertIn("aclexplode", sql)
        executable = re.sub(r"--[^\n]*", "", sql)
        self.assertNotRegex(executable.upper(), r"\b(GRANT|CREATE ROLE|SET_CONFIG)\b")

    def test_evidence_is_immutable_and_has_no_person_fk_or_resume(self):
        sql = self.sql()
        self.assertIn(
            "REFERENCES ntubtob.account_erasure_jobs(id) ON DELETE RESTRICT", sql
        )
        self.assertNotIn("REFERENCES ntubtob.people", sql)
        self.assertIn("BEFORE UPDATE OR DELETE OR TRUNCATE", sql)
        self.assertIn("management_suspension_operation_id", sql)
        self.assertIn("REVOKE ALL", sql)
        self.assertNotIn("CREATE FUNCTION ntubtob.resume", sql)

    def test_downgrade_refuses_history_or_suspension_before_removal(self):
        sql = self.sql("downgrade")
        self.assertIn("recovery_history_retained", sql)
        self.assertLess(sql.index("recovery_history_retained"), sql.index("DROP TABLE"))
        self.assertIn("management_suspension_operation_id IS NOT NULL", sql)
        self.assertNotRegex(sql, r"(?i)\b(DELETE FROM|TRUNCATE|CASCADE)\b")


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class AdminRecoveryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(ledger.DATABASE_URL))
        remove_retained_erasure_ledger_from_isolated_test_database(cls.engine)
        with cls.engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_erasure_privacy_mutation")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.connection = self.fixture.connection
        self.addCleanup(self.fixture.tearDown)
        self.owner = "fictional_recovery_owner_" + uuid4().hex[:12]
        self.operator = "fictional_recovery_operator_" + uuid4().hex[:12]
        self.runtime = "fictional_recovery_runtime_" + uuid4().hex[:12]
        for role, extra in (
            (self.owner, "BYPASSRLS"),
            (self.operator, "NOBYPASSRLS"),
            (self.runtime, "NOBYPASSRLS"),
        ):
            self.connection.execute(
                text(
                    f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT {extra}'
                )
            )
            self.connection.execute(text(f'GRANT USAGE ON SCHEMA ntubtob TO "{role}"'))
        self.connection.execute(
            text(f'GRANT CREATE ON SCHEMA ntubtob TO "{self.owner}"')
        )
        self.connection.execute(
            text(f'ALTER TABLE ntubtob.portal_authority_state OWNER TO "{self.owner}"')
        )
        self.connection.execute(
            text(
                f'GRANT SELECT, UPDATE, REFERENCES ON ntubtob.account_erasure_jobs, ntubtob.people, ntubtob.auth_identities TO "{self.owner}"'
            )
        )
        self.connection.execute(
            text(f'GRANT SELECT ON ntubtob.alembic_version TO "{self.owner}"')
        )
        self.connection.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{self.owner}" IN SCHEMA ntubtob GRANT ALL ON TABLES TO "{self.runtime}"'
            )
        )
        self.connection.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{self.owner}" IN SCHEMA ntubtob GRANT EXECUTE ON FUNCTIONS TO "{self.runtime}"'
            )
        )
        # Execute exactly the candidate DDL as its distinct, non-superuser owner.
        self.connection.execute(text(f'SET LOCAL ROLE "{self.owner}"'))
        try:
            with patch.object(
                migration().op,
                "execute",
                lambda sql: self.connection.execute(text(sql)),
            ):
                migration().upgrade()
        finally:
            self.connection.execute(text("RESET ROLE"))
        self.connection.execute(
            text("UPDATE ntubtob.alembic_version SET version_num=:version"),
            {"version": REVISION},
        )
        self.connection.execute(
            text(f'GRANT EXECUTE ON FUNCTION {FUNCTION} TO "{self.operator}"')
        )
        # Deliberately broad ordinary-table rights must NOT bypass the pointer.
        self.connection.execute(
            text(
                f'GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE ON ntubtob.portal_authority_state TO "{self.runtime}"'
            )
        )
        self.connection.execute(
            text(
                f'CREATE POLICY fictional_recovery_runtime ON ntubtob.portal_authority_state TO "{self.runtime}" USING (true) WITH CHECK (true)'
            )
        )
        self.connection.execute(
            text("UPDATE ntubtob.portal_authority_state SET mode='persistent',epoch=10")
        )
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"),
            {"id": self.fixture.person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.person, "id": self.fixture.identity},
        )
        self.generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.person},
            )
        )
        self.job_id = self.fixture.job(expected_generation=self.generation)
        self.fixture.update(
            self.job_id,
            status="verified",
            verified_at=ledger.NOW,
            updated_at=ledger.NOW,
        )
        self.operation = str(uuid4())

    def apply(self, *, role=None, **changes):
        args = dict(
            job=self.job_id,
            generation=self.generation,
            epoch=10,
            operation=self.operation,
        )
        args.update(changes)
        self.connection.execute(text(f'SET LOCAL ROLE "{role or self.operator}"'))
        # On failure rejected() rolls back the aborted savepoint before RESET.
        return self.connection.scalar(
            text(
                "SELECT ntubtob.suspend_management_for_erasure(CAST(:job AS uuid),CAST(:generation AS uuid),:epoch,CAST(:operation AS uuid))"
            ),
            args,
        )

    def rejected(self, action):
        transaction = self.connection.begin_nested()
        try:
            with self.assertRaises(DBAPIError):
                action()
        finally:
            transaction.rollback()
            self.connection.execute(text("RESET ROLE"))

    def state(self):
        self.connection.execute(text("RESET ROLE"))
        return tuple(
            self.connection.execute(
                text(
                    "SELECT mode,epoch,management_suspension_operation_id FROM ntubtob.portal_authority_state"
                )
            ).one()
        )

    def test_acl_three_roles_and_named_default_grants_are_removed(self):
        for role, expected in (
            (self.owner, True),
            (self.operator, True),
            (self.runtime, False),
        ):
            self.assertEqual(
                self.connection.scalar(
                    text("SELECT has_function_privilege(:role,:function,'EXECUTE')"),
                    {"role": role, "function": FUNCTION},
                ),
                expected,
            )
        self.assertFalse(
            self.connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a WHERE p.oid=CAST(:fn AS regprocedure) AND a.grantee=0 AND a.privilege_type='EXECUTE')"
                ),
                {"fn": FUNCTION},
            )
        )
        for role in (self.operator, self.runtime):
            self.assertFalse(
                self.connection.scalar(
                    text(
                        "SELECT has_table_privilege(:role,:table,'INSERT,UPDATE,DELETE,TRUNCATE')"
                    ),
                    {"role": role, "table": TABLE},
                )
            )
        self.rejected(lambda: self.apply(role=self.runtime))
        self.assertEqual(self.state()[1:], (10, None))

    def test_current_metadata_has_no_pending_migration(self):
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0022_erasure_retention")
        command.check(config)

    def test_exact_operation_pointer_epoch_and_session_user_are_atomic(self):
        expected_user = self.connection.scalar(text("SELECT session_user"))
        self.assertEqual(str(self.apply()), self.operation)
        self.assertEqual(self.state(), ("persistent", 11, UUID(self.operation)))
        row = self.connection.execute(text(f"SELECT * FROM {TABLE}")).mappings().one()
        self.assertEqual(str(row["job_id"]), self.job_id)
        self.assertEqual(str(row["expected_generation"]), self.generation)
        self.assertEqual(row["scope_hash"], "a" * 64)
        self.assertEqual((row["expected_epoch"], row["applied_epoch"]), (10, 11))
        self.assertEqual(row["operator_session_user"], expected_user)
        self.assertIsNotNone(row["applied_at"].tzinfo)
        self.connection.execute(text("SET LOCAL ROLE NONE"))
        self.assertEqual(
            self.state()[1], 11
        )  # No session/GUC reset resumes management.

    def test_wrong_status_generation_epoch_target_and_replay_reject(self):
        for changes in (
            dict(generation=str(uuid4())),
            dict(epoch=9),
            dict(epoch=0),
            dict(job=str(uuid4())),
            dict(operation=None),
        ):
            self.rejected(lambda changes=changes: self.apply(**changes))
        # Create a separate requested intent without changing an immutable job.
        requested = self.fixture.job(
            person_id=self.fixture.other_person, expected_generation=str(uuid4())
        )
        self.rejected(lambda: self.apply(job=requested))
        self.assertEqual(str(self.apply()), self.operation)
        self.connection.execute(text("RESET ROLE"))
        self.rejected(lambda: self.apply())
        self.rejected(lambda: self.apply(operation=str(uuid4()), epoch=11))
        self.rejected(lambda: self.apply(job=requested, operation=self.operation))
        self.assertEqual(self.state()[1], 11)
        self.assertEqual(
            self.connection.scalar(text(f"SELECT count(*) FROM {TABLE}")), 1
        )

    def test_another_reachable_admin_rejects_without_any_suspension(self):
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"),
            {"id": self.fixture.other_person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.other_person, "id": self.fixture.other_identity},
        )
        self.rejected(lambda: self.apply())
        self.assertEqual(self.state()[1:], (10, None))
        self.assertEqual(
            self.connection.scalar(text(f"SELECT count(*) FROM {TABLE}")), 0
        )

    def test_runtime_table_update_cannot_set_clear_or_replace_pointer(self):
        def runtime_sql(sql):
            self.connection.execute(text(f'SET LOCAL ROLE "{self.runtime}"'))
            self.connection.execute(text(sql))

        self.rejected(
            lambda: runtime_sql(
                f"UPDATE ntubtob.portal_authority_state SET management_suspension_operation_id='{self.operation}'"
            )
        )
        # Ordinary unsuspended authority updates are intentionally still possible.
        runtime_sql("UPDATE ntubtob.portal_authority_state SET epoch=12")
        self.connection.execute(text("RESET ROLE"))
        self.assertEqual(str(self.apply(epoch=12)), self.operation)
        self.connection.execute(text("RESET ROLE"))
        for sql in (
            "UPDATE ntubtob.portal_authority_state SET management_suspension_operation_id=NULL",
            "UPDATE ntubtob.portal_authority_state SET epoch=1",
            "UPDATE ntubtob.portal_authority_state SET mode='legacy_allowlist'",
            "DELETE FROM ntubtob.portal_authority_state",
            "TRUNCATE ntubtob.portal_authority_state",
        ):
            self.rejected(lambda sql=sql: runtime_sql(sql))
        self.assertEqual(self.state()[1], 13)

    def test_immutable_history_and_failed_downgrade_leave_suspension(self):
        self.apply()
        self.connection.execute(text("RESET ROLE"))
        for sql in (
            f"UPDATE {TABLE} SET scope_hash=scope_hash",
            f"DELETE FROM {TABLE}",
            f"TRUNCATE {TABLE}",
        ):
            self.rejected(lambda sql=sql: self.connection.execute(text(sql)))

        def downgrade():
            with patch.object(
                migration().op,
                "execute",
                lambda sql: self.connection.execute(text(sql)),
            ):
                migration().downgrade()

        self.rejected(downgrade)
        self.assertEqual(self.state()[1], 11)
        self.assertEqual(
            self.connection.scalar(text(f"SELECT count(*) FROM {TABLE}")), 1
        )

    def test_rollback_after_success_removes_operation_and_pointer_together(self):
        transaction = self.connection.begin_nested()
        self.apply()
        self.assertEqual(self.state()[1], 11)
        transaction.rollback()
        self.assertEqual(self.state()[1:], (10, None))
        self.assertEqual(
            self.connection.scalar(text(f"SELECT count(*) FROM {TABLE}")), 0
        )

    def test_empty_downgrade_removes_only_candidate_schema(self):
        with patch.object(
            migration().op,
            "execute",
            lambda sql: self.connection.execute(text(sql)),
        ):
            migration().downgrade()
        self.assertIsNone(
            self.connection.scalar(text("SELECT to_regclass(:table)"), {"table": TABLE})
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT epoch FROM ntubtob.portal_authority_state")
            ),
            10,
        )

    def test_real_management_guard_and_exact_bound_reader(self):
        require_management_writes_available(self.connection)
        with self.assertRaises(ManagementGuardUnavailable):
            read_applied_admin_suspension(
                self.connection,
                job_id=self.job_id,
                generation=self.generation,
                scope_hash="a" * 64,
            )
        self.apply()
        self.connection.execute(text("RESET ROLE"))
        with self.assertRaises(ManagementWritesSuspended):
            require_management_writes_available(self.connection)
        result = read_applied_admin_suspension(
            self.connection,
            job_id=self.job_id,
            generation=self.generation,
            scope_hash="a" * 64,
        )
        self.assertEqual(
            (
                result.operation_id,
                result.job_id,
                result.generation,
                result.scope_hash,
                result.authority_epoch,
            ),
            (self.operation, self.job_id, self.generation, "a" * 64, 11),
        )
        for changes in (
            dict(job_id=str(uuid4())),
            dict(generation=str(uuid4())),
            dict(scope_hash="b" * 64),
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(ManagementGuardUnavailable),
            ):
                read_applied_admin_suspension(
                    self.connection,
                    **{
                        **dict(
                            job_id=self.job_id,
                            generation=self.generation,
                            scope_hash="a" * 64,
                        ),
                        **changes,
                    },
                )
        # An attempted epoch mismatch is blocked by the native trigger itself.
        self.rejected(
            lambda: self.connection.execute(
                text("UPDATE ntubtob.portal_authority_state SET epoch=12")
            )
        )
        self.assertEqual(self.state()[1], 11)


if __name__ == "__main__":
    unittest.main()
