from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHARED_LIB_ROOT = Path(__file__).resolve().parents[2] / "shared_lib"
if str(SHARED_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_LIB_ROOT))

from alembic import command
from alembic.config import Config
from shared_module.portal_data.mobile_repository import MobileRepository
from shared_module.portal_data.models import PortalDataBase
from sqlalchemy import create_engine, text

from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)
NOW = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)


class MobileNotificationModelContractTest(unittest.TestCase):
    def test_model_requires_exact_fixed_retention(self):
        table = PortalDataBase.metadata.tables["ntubtob.mobile_notifications"]
        constraints = {
            constraint.name: str(constraint.sqltext)
            for constraint in table.constraints
            if hasattr(constraint, "sqltext")
        }
        self.assertEqual(
            constraints["ck_mobile_notification_visibility"],
            "visible_until = created_at + interval '90 days'",
        )


@unittest.skipUnless(DATABASE_URL, "portal-data PostgreSQL URL is required")
class MobileNotificationIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        setup_legacy_fixture()
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", DATABASE_URL)
        command.upgrade(config, "head")
        with self.engine.begin() as connection:
            self.people = tuple(
                connection.scalars(
                    text(
                        "INSERT INTO ntubtob.people "
                        "(display_name, portal_access_level, portal_status, version, created_at, updated_at) "
                        "VALUES ('Recipient A', 'basic', 'active', 1, :now, :now), "
                        "('Recipient B', 'basic', 'active', 1, :now, :now) RETURNING id"
                    ),
                    {"now": NOW},
                )
            )
            self.notification_ids = []
            for offset in (1, 2, 91):
                created = NOW - timedelta(days=offset)
                notification_id = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.mobile_notifications "
                        "(notification_type, title, body, created_at, visible_until) "
                        "VALUES ('game_reminder', :title, :body, :created, :visible_until) RETURNING id"
                    ),
                    {
                        "title": f"Reminder {offset}",
                        "body": f"Body {offset}",
                        "created": created,
                        "visible_until": created + timedelta(days=90),
                    },
                )
                self.notification_ids.append(notification_id)
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.mobile_notification_recipients "
                        "(notification_id, person_id, created_at, read_at) "
                        "VALUES (:notification, :person, :created, NULL)"
                    ),
                    {
                        "notification": notification_id,
                        "person": self.people[0],
                        "created": created,
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_notification_recipients "
                    "(notification_id, person_id, created_at, read_at) "
                    "VALUES (:notification, :person, :created, NULL)"
                ),
                {
                    "notification": self.notification_ids[0],
                    "person": self.people[1],
                    "created": NOW - timedelta(days=1),
                },
            )
        self.repository = MobileRepository(self.engine)

    def test_migration_models_constraints_and_rls_are_exact(self):
        expected = {"mobile_notifications", "mobile_notification_recipients"}
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0007_mobile_notifications",
            )
            rls = set(
                connection.scalars(
                    text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='ntubtob' AND c.relname = ANY(:tables) AND c.relrowsecurity"
                    ),
                    {"tables": list(expected)},
                )
            )
            database_columns = {
                table: set(
                    connection.scalars(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='ntubtob' AND table_name=:table"
                        ),
                        {"table": table},
                    )
                )
                for table in expected
            }
        self.assertEqual(rls, expected)
        self.assertEqual(
            database_columns,
            {
                table: set(
                    PortalDataBase.metadata.tables[f"ntubtob.{table}"].columns.keys()
                )
                for table in expected
            },
        )
        for notification_type, visible_until in (
            ("unknown", NOW + timedelta(days=90)),
            ("game_reminder", NOW + timedelta(days=90) - timedelta(seconds=1)),
        ):
            with self.subTest(notification_type=notification_type):
                with self.assertRaises(Exception):
                    with self.engine.begin() as connection:
                        connection.execute(
                            text(
                                "INSERT INTO ntubtob.mobile_notifications "
                                "(notification_type, title, body, created_at, visible_until) "
                                "VALUES (:notification_type, 'title', 'body', :now, :until)"
                            ),
                            {
                                "notification_type": notification_type,
                                "now": NOW,
                                "until": visible_until,
                            },
                        )

    def test_visibility_recipient_scope_keyset_and_atomic_idempotent_reads(self):
        first = self.repository.notification_page(self.people[0], NOW, None, 1, False)
        second = self.repository.notification_page(
            self.people[0], NOW, (first[0]["created_at"], first[0]["id"]), 2, False
        )
        other = self.repository.notification_page(self.people[1], NOW, None, 10, False)
        self.assertEqual([row["id"] for row in first], [self.notification_ids[0]])
        self.assertEqual([row["id"] for row in second], [self.notification_ids[1]])
        self.assertEqual([row["id"] for row in other], [self.notification_ids[0]])
        self.assertEqual(
            self.repository.notification_unread_count(self.people[0], NOW), 2
        )
        self.assertIsNone(
            self.repository.notification_detail(
                self.people[1], self.notification_ids[1], NOW
            )
        )

        first_read = self.repository.mark_notification_read(
            self.people[0], self.notification_ids[0], NOW
        )
        replay = self.repository.mark_notification_read(
            self.people[0], self.notification_ids[0], NOW + timedelta(seconds=1)
        )
        self.assertEqual(first_read, (NOW, True))
        self.assertEqual(replay, (NOW, False))
        self.assertEqual(
            self.repository.mark_all_notifications_read(self.people[0], NOW),
            (1, 0),
        )
        self.assertEqual(
            self.repository.mark_all_notifications_read(
                self.people[0], NOW + timedelta(seconds=1)
            ),
            (0, 0),
        )
        self.assertEqual(
            self.repository.notification_unread_count(self.people[0], NOW), 0
        )


if __name__ == "__main__":
    unittest.main()
