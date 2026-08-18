from __future__ import annotations

import os
import unittest

from sqlalchemy import create_engine, text

from tools.mobile_staging_contract import DatabaseIdentity
from tools.mobile_staging_preflight import database_inventory
from tools.mobile_staging_seed import REPLY_TYPES, StagingSeedError, cleanup, seed

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL is required")
class MobileStagingSeedIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        cleanup(self.engine, "fake-private-tester-subject")

    def tearDown(self):
        cleanup(self.engine, "fake-private-tester-subject")

    def test_seed_retry_exact_one_private_tester_and_cleanup(self):
        staging_hash = DatabaseIdentity.from_url(DATABASE_URL).fingerprint
        production_hash = "f" * 64
        before = database_inventory(
            self.engine, DATABASE_URL, staging_hash, production_hash
        )
        self.assertEqual(before["fixture_state"], "clean")
        first = seed(self.engine, "fake-private-tester-subject")
        second = seed(self.engine, "fake-private-tester-subject")
        self.assertEqual(first["tester_mappings"], 1)
        self.assertEqual(first["reused"], 0)
        self.assertEqual(second["reused"], 1)
        after = database_inventory(
            self.engine, DATABASE_URL, staging_hash, production_hash
        )
        self.assertEqual(after["fixture_state"], "seeded")
        with self.engine.connect() as connection:
            count = connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.auth_identities WHERE provider='line' AND provider_subject=:subject"
                ),
                {"subject": "fake-private-tester-subject"},
            )
        self.assertEqual(count, 1)
        result = cleanup(self.engine, "fake-private-tester-subject")
        self.assertEqual(sum(result.values()), 0)

    def test_partial_or_unknown_fixture_drift_fails_closed(self):
        seed(self.engine, "fake-private-tester-subject")
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.people SET display_name='drift' WHERE id=-112002")
            )
        with self.assertRaises(StagingSeedError):
            seed(self.engine, "fake-private-tester-subject")
        with self.assertRaises(StagingSeedError):
            cleanup(self.engine, "fake-private-tester-subject")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET display_name='虛構 Staging 隊友甲' WHERE id=-112002"
                )
            )

    def test_wrong_private_subject_never_reuses_mapping(self):
        seed(self.engine, "fake-private-tester-subject")
        with self.assertRaises(StagingSeedError):
            seed(self.engine, "another-private-tester-subject")

    def test_existing_reply_type_reference_rows_survive_seed_and_cleanup(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.attendance_reply_types (id, description) "
                    "VALUES (:id, :description)"
                ),
                [
                    {"id": key, "description": value}
                    for key, value in REPLY_TYPES.items()
                ],
            )
            before = connection.execute(
                text(
                    "SELECT id, description FROM ntubtob.attendance_reply_types "
                    "ORDER BY id"
                )
            ).all()
        seed(self.engine, "fake-private-tester-subject")
        cleanup(self.engine, "fake-private-tester-subject")
        with self.engine.connect() as connection:
            after = connection.execute(
                text(
                    "SELECT id, description FROM ntubtob.attendance_reply_types "
                    "ORDER BY id"
                )
            ).all()
        self.assertEqual(after, before)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM ntubtob.attendance_reply_types " "WHERE id = ANY(:ids)"
                ),
                {"ids": list(REPLY_TYPES)},
            )


if __name__ == "__main__":
    unittest.main()
