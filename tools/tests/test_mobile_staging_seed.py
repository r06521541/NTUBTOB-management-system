from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from tools.mobile_staging_contract import DatabaseIdentity
from tools.mobile_staging_preflight import database_inventory
from tools.mobile_staging_seed import (
    FIXTURE_REPLY_AT,
    REPLY_TYPES,
    StagingSeedError,
    cleanup,
    inspect_attendance_repair,
    repair_attendance_fixture,
    seed,
)

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
        with self.engine.connect() as connection:
            timestamps = connection.execute(
                text(
                    "SELECT updated_at FROM ntubtob.game_attendance_replies "
                    "WHERE id BETWEEN -112003 AND -112001 ORDER BY id"
                )
            ).scalars().all()
        self.assertEqual(timestamps, [FIXTURE_REPLY_AT] * 3)
        self.assertLess(FIXTURE_REPLY_AT, datetime.now(timezone.utc))
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

    def test_exact_attendance_repair_is_retry_safe_and_rejects_drift(self):
        seed(self.engine, "fake-private-tester-subject")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.game_attendance_replies SET updated_at=:old "
                    "WHERE id BETWEEN -112003 AND -112001"
                ),
                {"old": datetime(2035, 1, 10, 10, tzinfo=timezone.utc)},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, user_id, member_id, person_id, reply, updated_at) "
                    "VALUES (-112001, NULL, NULL, -112001, 5, :first), "
                    "(-112001, NULL, NULL, -112001, 5, :second)"
                ),
                {
                    "first": datetime(
                        2026, 8, 19, 15, 39, 23, 883620, tzinfo=timezone.utc
                    ),
                    "second": datetime(
                        2026, 8, 19, 15, 44, 55, 572527, tzinfo=timezone.utc
                    ),
                },
            )
        self.assertEqual(inspect_attendance_repair(self.engine)["state"], "required")
        first = repair_attendance_fixture(self.engine)
        second = repair_attendance_fixture(self.engine)
        self.assertEqual(first, {"state": "repaired", "removed_hidden_rows": 2})
        self.assertEqual(second, {"state": "repaired", "removed_hidden_rows": 0})

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) "
                    "VALUES (-112001, -112001, 4, :now)"
                ),
                {"now": datetime(2026, 8, 18, 3, tzinfo=timezone.utc)},
            )
        with self.assertRaisesRegex(StagingSeedError, "drifted"):
            inspect_attendance_repair(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM ntubtob.game_attendance_replies "
                    "WHERE person_id=-112001 AND game_id=-112001 AND reply=4"
                )
            )


if __name__ == "__main__":
    unittest.main()
