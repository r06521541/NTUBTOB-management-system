from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data import local_database
from tests.portal_data import _event_guest_lifecycle_test_harness as cleanup_harness
from tests.portal_data._event_guest_lifecycle_test_harness import (
    reset_pre_0011_schema_for_isolated_test_database,
)
from tools import portal_data_event_management_rollout as rollout
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class EventManagementRolloutIsolationStaticTests(unittest.TestCase):
    def test_canonical_reset_rejects_unproven_database_before_ddl(self):
        invalid_urls = (
            SimpleNamespace(
                drivername="sqlite", host="localhost", database="ntubtob_portal_local"
            ),
            SimpleNamespace(
                drivername="postgresql",
                host="database.example.invalid",
                database="ntubtob_portal_local",
            ),
            SimpleNamespace(
                drivername="postgresql", host="localhost", database="production"
            ),
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                engine = MagicMock()
                engine.url = url
                upgrade = MagicMock()
                with self.assertRaisesRegex(RuntimeError, "isolated test database"):
                    reset_pre_0011_schema_for_isolated_test_database(engine, upgrade)
                engine.begin.assert_not_called()
                upgrade.assert_not_called()

        for has_version_table, revisions in (
            (False, ()),
            (True, ()),
            (True, ("0011_event_notification_guest_lifecycle",)),
            (True, ("0010_apple_provider_lifecycle", "branch")),
        ):
            with self.subTest(has_version_table=has_version_table, revisions=revisions):
                engine = MagicMock()
                engine.url = SimpleNamespace(
                    drivername="postgresql",
                    host="localhost",
                    database=cleanup_harness.LOCAL_DATABASE_NAME,
                )
                engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = (
                    revisions
                )
                inspector = MagicMock()
                inspector.has_table.return_value = has_version_table
                upgrade = MagicMock()
                with (
                    patch.object(cleanup_harness, "inspect", return_value=inspector),
                    self.assertRaisesRegex(RuntimeError, "known pre-0011 revision"),
                ):
                    reset_pre_0011_schema_for_isolated_test_database(engine, upgrade)
                engine.begin.assert_not_called()
                upgrade.assert_not_called()

    def test_canonical_reset_rebuilds_only_after_exact_known_revision(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = [
            "0010_apple_provider_lifecycle"
        ]
        inspector = MagicMock()
        inspector.has_table.return_value = True
        upgrade = MagicMock()
        with patch.object(cleanup_harness, "inspect", return_value=inspector):
            reset_pre_0011_schema_for_isolated_test_database(engine, upgrade)

        statements = tuple(
            str(call.args[0])
            for call in engine.begin.return_value.__enter__.return_value.execute.call_args_list
        )
        self.assertIn("DROP SCHEMA IF EXISTS ntubtob CASCADE", statements[0])
        self.assertIn("CREATE SCHEMA", statements[1])
        upgrade.assert_called_once_with("0010_apple_provider_lifecycle")


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class EventManagementRolloutPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            local_database.require_local_database_url(DATABASE_URL)
        )
        cls.config = Config("alembic.ini")

    @classmethod
    def tearDownClass(cls):
        try:
            reset_pre_0011_schema_for_isolated_test_database(cls.engine, cls._upgrade)
        finally:
            cls.engine.dispose()

    @classmethod
    def _upgrade(cls, revision: str) -> None:
        with cls.engine.begin() as connection:
            cls.config.attributes["connection"] = connection
            try:
                command.upgrade(cls.config, revision)
            finally:
                cls.config.attributes.pop("connection", None)

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
            connection.execute(text(LEGACY_FIXTURE_SQL))
        self._upgrade("0004_phase_c_identity_lifecycle")
        self.engine.dispose()

    def test_dry_run_is_read_only_and_execute_is_atomic_with_zero_application_dml(self):
        with self.engine.begin() as connection:
            result = rollout._run_locked(connection, execute=False)
        self.assertEqual(result["status"], "ready")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0004_phase_c_identity_lifecycle",
            )
            self.assertEqual(
                rollout._constraint_actions(connection), rollout.OLD_ACTIONS
            )
            self.assertIsNone(
                connection.scalar(text("SELECT to_regclass('ntubtob.mobile_sessions')"))
            )

        with self.engine.begin() as connection:
            result = rollout._run_locked(connection, execute=True)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["application_dml_count"], 0)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0009_event_management_writes",
            )

    def test_injected_failure_rolls_back_revision_and_constraint(self):
        with self.assertRaisesRegex(rollout.RolloutError, "injected"):
            with self.engine.begin() as connection:
                rollout._run_locked(connection, execute=True, fail_after_migration=True)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0004_phase_c_identity_lifecycle",
            )
            self.assertIsNone(
                connection.scalar(text("SELECT to_regclass('ntubtob.mobile_sessions')"))
            )

    def test_catalog_drift_and_already_forward_are_rejected(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.event_audit DROP CONSTRAINT ck_event_audit_action; "
                    "ALTER TABLE ntubtob.event_audit ADD CONSTRAINT ck_event_audit_action "
                    "CHECK (action IN ('published'))"
                )
            )
        with self.assertRaises(rollout.RolloutError):
            with self.engine.begin() as connection:
                rollout._run_locked(connection, execute=False)

        self.setUp()
        self._upgrade("0010_apple_provider_lifecycle")
        with self.assertRaises(rollout.RolloutError):
            with self.engine.begin() as connection:
                rollout._run_locked(connection, execute=False)

    def test_existing_future_object_is_rejected_before_upgrade(self):
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE ntubtob.mobile_sessions (id text)"))
        self.engine.dispose()
        with self.assertRaisesRegex(rollout.RolloutError, "future migration objects"):
            with self.engine.begin() as connection:
                rollout._run_locked(connection, execute=False)

    def test_phase_c_identity_drift_is_rejected(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.people "
                    "DROP CONSTRAINT ck_people_formal_name; "
                    "ALTER TABLE ntubtob.access_audit "
                    "ADD CONSTRAINT ck_people_formal_name CHECK (TRUE)"
                )
            )
        self.engine.dispose()
        with self.assertRaisesRegex(rollout.RolloutError, "identity catalog"):
            with self.engine.begin() as connection:
                rollout._run_locked(connection, execute=False)

    def test_postcheck_rejects_material_schema_drift_categories(self):
        cases = (
            (
                "column_type",
                "ALTER TABLE ntubtob.mobile_sessions ALTER COLUMN status TYPE text",
                "column fingerprint",
            ),
            (
                "column_default",
                "ALTER TABLE ntubtob.mobile_sessions "
                "ALTER COLUMN status SET DEFAULT 'active'",
                "column fingerprint",
            ),
            (
                "identity_generation",
                "ALTER TABLE ntubtob.mobile_refresh_tokens "
                "ALTER COLUMN id SET GENERATED ALWAYS",
                "column fingerprint",
            ),
            (
                "constraint_definition",
                "ALTER TABLE ntubtob.mobile_sessions "
                "DROP CONSTRAINT ck_mobile_sessions_status; "
                "ALTER TABLE ntubtob.mobile_sessions "
                "ADD CONSTRAINT ck_mobile_sessions_status CHECK (TRUE)",
                "constraint fingerprint",
            ),
            (
                "constraint_boolean_grouping",
                "ALTER TABLE ntubtob.mobile_notifications "
                "DROP CONSTRAINT ck_mobile_notification_destination; "
                "ALTER TABLE ntubtob.mobile_notifications ADD CONSTRAINT "
                "ck_mobile_notification_destination CHECK ("
                "destination_type = 'notification' AND ("
                "destination_game_id IS NULL OR destination_type = 'game'"
                ") AND destination_game_id IS NOT NULL)",
                "check definition",
            ),
            (
                "constraint_literal_case",
                "ALTER TABLE ntubtob.mobile_device_registrations "
                "DROP CONSTRAINT ck_mobile_device_provider; "
                "ALTER TABLE ntubtob.mobile_device_registrations ADD CONSTRAINT "
                "ck_mobile_device_provider CHECK (provider = 'FAKE')",
                "check definition",
            ),
            (
                "constraint_negated_regex",
                "ALTER TABLE ntubtob.staging_broker_operations "
                "DROP CONSTRAINT ck_staging_broker_fingerprint; "
                "ALTER TABLE ntubtob.staging_broker_operations ADD CONSTRAINT "
                "ck_staging_broker_fingerprint CHECK ("
                "inspect_fingerprint !~ '^[0-9a-f]{64}$')",
                "check definition",
            ),
            (
                "constraint_signed_number",
                "ALTER TABLE ntubtob.mobile_notification_deliveries "
                "DROP CONSTRAINT ck_mobile_notification_attempt_count; "
                "ALTER TABLE ntubtob.mobile_notification_deliveries ADD CONSTRAINT "
                "ck_mobile_notification_attempt_count CHECK (attempt_count >= -1)",
                "check definition",
            ),
            (
                "foreign_key_update_action",
                "ALTER TABLE ntubtob.mobile_sessions "
                "DROP CONSTRAINT mobile_sessions_person_id_fkey; "
                "ALTER TABLE ntubtob.mobile_sessions ADD CONSTRAINT "
                "mobile_sessions_person_id_fkey FOREIGN KEY (person_id) "
                "REFERENCES ntubtob.people(id) ON UPDATE CASCADE ON DELETE RESTRICT",
                "constraint reference",
            ),
            (
                "foreign_key_reference_schema",
                "CREATE SCHEMA IF NOT EXISTS task164_rogue; "
                "CREATE TABLE IF NOT EXISTS task164_rogue.people (id bigint PRIMARY KEY); "
                "ALTER TABLE ntubtob.mobile_sessions "
                "DROP CONSTRAINT mobile_sessions_person_id_fkey; "
                "ALTER TABLE ntubtob.mobile_sessions ADD CONSTRAINT "
                "mobile_sessions_person_id_fkey FOREIGN KEY (person_id) "
                "REFERENCES task164_rogue.people(id) ON DELETE RESTRICT",
                "constraint reference",
            ),
            (
                "index",
                "DROP INDEX ntubtob.ix_mobile_sessions_person_status",
                "index set",
            ),
            (
                "function_body",
                "CREATE OR REPLACE FUNCTION "
                "ntubtob.reject_mobile_notification_mutation() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN RETURN OLD; END; $$",
                "function body",
            ),
            (
                "function_security",
                "CREATE OR REPLACE FUNCTION "
                "ntubtob.reject_mobile_notification_mutation() RETURNS trigger "
                "LANGUAGE plpgsql SECURITY DEFINER AS $$ BEGIN RAISE EXCEPTION "
                "'mobile notification content is immutable'; END; $$",
                "function identity",
            ),
            (
                "trigger_function_schema",
                "CREATE SCHEMA IF NOT EXISTS task164_rogue; "
                "CREATE OR REPLACE FUNCTION "
                "task164_rogue.reject_mobile_notification_mutation() "
                "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
                "'mobile notification content is immutable'; END; $$; "
                "DROP TRIGGER mobile_notification_content_immutable "
                "ON ntubtob.mobile_notifications; "
                "CREATE TRIGGER mobile_notification_content_immutable "
                "BEFORE UPDATE OR DELETE ON ntubtob.mobile_notifications "
                "FOR EACH ROW EXECUTE FUNCTION "
                "task164_rogue.reject_mobile_notification_mutation()",
                "trigger identity",
            ),
            (
                "trigger",
                "ALTER TABLE ntubtob.mobile_notifications DISABLE TRIGGER "
                "mobile_notification_content_immutable",
                "trigger definition",
            ),
        )
        for label, mutation, reason in cases:
            with self.subTest(label=label):
                self.setUp()
                self._upgrade("0010_apple_provider_lifecycle")
                with self.engine.begin() as connection:
                    connection.execute(text(mutation))
                self.engine.dispose()
                with self.assertRaisesRegex(rollout.RolloutError, reason):
                    with self.engine.begin() as connection:
                        rollout._future_schema_safe(connection)
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS task164_rogue CASCADE"))

    def test_canonical_reset_restores_final_drift_and_exact_0010(self):
        self._upgrade("0010_apple_provider_lifecycle")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.mobile_notifications DISABLE TRIGGER "
                    "mobile_notification_content_immutable"
                )
            )
        with self.engine.connect() as connection:
            with self.assertRaisesRegex(rollout.RolloutError, "trigger definition"):
                rollout._future_schema_safe(connection)

        reset_pre_0011_schema_for_isolated_test_database(self.engine, self._upgrade)

        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0010_apple_provider_lifecycle",
            )
            rollout._future_schema_safe(connection)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class EventManagementRolloutZZCanonicalFollowerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            local_database.require_local_database_url(DATABASE_URL)
        )

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_previous_drift_suite_left_canonical_exact_0010(self):
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0010_apple_provider_lifecycle",
            )
            rollout._future_schema_safe(connection)


if __name__ == "__main__":
    unittest.main()
