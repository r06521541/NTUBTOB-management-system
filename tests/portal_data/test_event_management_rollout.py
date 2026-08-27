from __future__ import annotations

import os
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data import local_database
from tools import portal_data_event_management_rollout as rollout
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


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
        cls._upgrade("head")
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
        self._upgrade("0008_mobile_notification_delivery")

    def test_dry_run_is_read_only_and_execute_is_atomic_with_zero_application_dml(self):
        with self.engine.begin() as connection:
            result = rollout._run_locked(connection, execute=False)
        self.assertEqual(result["status"], "ready")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0008_mobile_notification_delivery",
            )
            self.assertEqual(
                rollout._constraint_actions(connection), rollout.OLD_ACTIONS
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
                "0008_mobile_notification_delivery",
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
        self._upgrade("head")
        with self.assertRaises(rollout.RolloutError):
            with self.engine.begin() as connection:
                rollout._run_locked(connection, execute=False)


if __name__ == "__main__":
    unittest.main()
