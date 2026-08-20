from __future__ import annotations

import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.mobile_staging_broker.broker import BrokerConflict
from apps.mobile_staging_broker.journal import PostgresJournal
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


@unittest.skipUnless(DATABASE_URL, "portal-data PostgreSQL URL is required")
class StagingBrokerJournalIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        setup_legacy_fixture()
        command.upgrade(Config("alembic.ini"), "head")
        self.journal = PostgresJournal(self.engine)

    def test_revision_constraints_indexes_and_safe_downgrade(self):
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0006_staging_broker_operation_journal",
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT character_maximum_length FROM "
                        "information_schema.columns WHERE table_schema='ntubtob' "
                        "AND table_name='alembic_version' AND column_name='version_num'"
                    )
                ),
                64,
            )
            constraints = set(
                connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint WHERE "
                        "conrelid='ntubtob.staging_broker_operations'::regclass"
                    )
                )
            )
            indexes = set(
                connection.scalars(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE schemaname='ntubtob' "
                        "AND tablename='staging_broker_operations'"
                    )
                )
            )
        self.assertTrue(
            {
                "pk_staging_broker_operations",
                "ck_staging_broker_operation",
                "ck_staging_broker_target_state",
                "ck_staging_broker_lifecycle_state",
                "ck_staging_broker_reason_code",
                "ck_staging_broker_timestamps",
            }
            <= constraints
        )
        self.assertIn("ix_staging_broker_lifecycle_updated", indexes)
        command.downgrade(Config("alembic.ini"), "0005_mobile_auth_api_foundation")
        with self.engine.connect() as connection:
            self.assertIsNone(
                connection.scalar(
                    text("SELECT to_regclass('ntubtob.staging_broker_operations')")
                )
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT character_maximum_length FROM "
                        "information_schema.columns WHERE table_schema='ntubtob' "
                        "AND table_name='alembic_version' AND column_name='version_num'"
                    )
                ),
                64,
            )

    def test_insert_intent_conflict_and_compare_and_set(self):
        row = self.journal.create_or_get(
            "operation-123456", "grant", "ready_officer", "f" * 64
        )
        self.assertEqual(row.lifecycle_state, "inspected")
        self.assertEqual(
            self.journal.create_or_get(
                "operation-123456", "grant", "ready_officer", "f" * 64
            ),
            row,
        )
        with self.assertRaises(BrokerConflict):
            self.journal.create_or_get(
                "operation-123456", "restore", "ready_basic", "e" * 64
            )
        self.assertTrue(
            self.journal.compare_and_set("operation-123456", "inspected", "confirmed")
        )
        self.assertFalse(
            self.journal.compare_and_set(
                "operation-123456", "inspected", "mutation_issued"
            )
        )
        self.assertTrue(
            self.journal.compare_and_set(
                "operation-123456", "confirmed", "mutation_issued"
            )
        )
        self.assertTrue(
            self.journal.compare_and_set(
                "operation-123456", "mutation_issued", "postcheck_complete"
            )
        )

    def test_confirmed_to_mutation_issued_has_one_database_winner(self):
        self.journal.create_or_get(
            "operation-123456", "grant", "ready_officer", "f" * 64
        )
        self.assertTrue(
            self.journal.compare_and_set("operation-123456", "inspected", "confirmed")
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(
                    lambda _index: self.journal.compare_and_set(
                        "operation-123456", "confirmed", "mutation_issued"
                    ),
                    range(2),
                )
            )
        self.assertEqual(sorted(outcomes), [False, True])


if __name__ == "__main__":
    unittest.main()
