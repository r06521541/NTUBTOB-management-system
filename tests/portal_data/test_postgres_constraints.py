from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import PortalDataBase
from tools.seed_portal_data_fake import seed_fake_data


@unittest.skipUnless(
    os.environ.get("PORTAL_DATA_TEST_DATABASE_URL"),
    "isolated local PostgreSQL URL not configured",
)
class PostgresConstraintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = require_local_database_url(os.environ["PORTAL_DATA_TEST_DATABASE_URL"])
        cls.engine = create_engine(url)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    TRUNCATE TABLE
                      ntubtob.event_audit, ntubtob.event_managers,
                      ntubtob.activity_attendance_replies, ntubtob.event_attendance_replies,
                      ntubtob.event_invitees, ntubtob.event_invitee_overrides,
                      ntubtob.event_eligibility_rules, ntubtob.activities, ntubtob.events,
                      ntubtob.access_audit, ntubtob.person_qualifications,
                      ntubtob.auth_identities, ntubtob.members, ntubtob.people
                    RESTART IDENTITY;
                    INSERT INTO ntubtob.members (id, name) VALUES (7001, '虛構校友甲');
                    """
                )
            )

    def test_migrated_columns_match_opt_in_models(self):
        inspector = inspect(self.engine)
        for table in PortalDataBase.metadata.tables.values():
            if table.name == "members":
                expected = {"id", "name", "person_id"}
            else:
                expected = set(table.columns.keys())
            actual = {
                column["name"]
                for column in inspector.get_columns(table.name, schema="ntubtob")
            }
            self.assertEqual(actual, expected, table.fullname)
            expected_indexes = {index.name for index in table.indexes}
            actual_indexes = {
                index["name"]
                for index in inspector.get_indexes(table.name, schema="ntubtob")
            }
            self.assertTrue(expected_indexes <= actual_indexes, table.fullname)

    def test_unknown_access_and_status_are_rejected(self):
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ntubtob.people
                          (display_name, portal_access_level, portal_status, created_at, updated_at)
                        VALUES ('虛構人物', 'owner', 'active', now(), now())
                        """
                    )
                )

    def test_pending_identity_cannot_link_a_person(self):
        with self.engine.begin() as connection:
            person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, created_at, updated_at)
                    VALUES ('虛構人物', 'basic', 'active', now(), now())
                    RETURNING id
                    """
                )
            )
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ntubtob.auth_identities
                          (provider, provider_subject, person_id, status, created_at, updated_at)
                        VALUES ('line', 'fake-subject', :person_id, 'pending', now(), now())
                        """
                    ),
                    {"person_id": person_id},
                )

    def test_inverted_validity_and_event_dates_are_rejected(self):
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, created_at, updated_at)
                    VALUES ('虛構人物', 'officer', 'active', now(), now())
                    RETURNING id
                    """
                )
            )
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ntubtob.person_qualifications
                          (person_id, qualification, status, valid_from, valid_until,
                           created_at, updated_at)
                        VALUES (:person_id, 'staff', 'active', :start, :finish, now(), now())
                        """
                    ),
                    {
                        "person_id": person_id,
                        "start": now,
                        "finish": now - timedelta(days=1),
                    },
                )
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ntubtob.events
                          (title, event_type, status, start_at, end_at, created_by_person_id,
                           created_at, updated_at)
                        VALUES ('虛構活動', 'trip', 'draft', :start, :finish, :person_id,
                                now(), now())
                        """
                    ),
                    {
                        "person_id": person_id,
                        "start": now,
                        "finish": now - timedelta(days=1),
                    },
                )

    def test_audit_rows_are_append_only(self):
        with self.engine.begin() as connection:
            audit_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.access_audit
                      (action, reason, request_id, created_at)
                    VALUES ('member_backfilled', '虛構 append only audit',
                            'append-only-test', now())
                    RETURNING id
                    """
                )
            )
        with self.assertRaises(DBAPIError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ntubtob.access_audit "
                        "SET reason = '不得修改' WHERE id = :id"
                    ),
                    {"id": audit_id},
                )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT reason FROM ntubtob.access_audit WHERE id = :id"),
                    {"id": audit_id},
                ),
                "虛構 append only audit",
            )

    def test_fake_seed_is_idempotent_and_does_not_add_members(self):
        first = seed_fake_data(self.engine)
        second = seed_fake_data(self.engine)
        self.assertEqual(first["created_fake_people"], 2)
        self.assertEqual(second["created_fake_people"], 0)
        self.assertEqual(second["reused_fake_people"], 2)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.members")), 1
            )
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.auth_identities")),
                2,
            )


if __name__ == "__main__":
    unittest.main()
