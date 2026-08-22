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
from shared_module.mobile_api import Conflict, MobilePrincipal, secret_hash
from shared_module.mobile_notifications import NotificationPublishingService
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
        device = PortalDataBase.metadata.tables[
            "ntubtob.mobile_device_registrations"
        ]
        active_token = next(
            index
            for index in device.indexes
            if index.name == "uq_mobile_device_active_provider_token"
        )
        self.assertTrue(active_token.unique)
        self.assertIn(
            "status = 'active'",
            str(active_token.dialect_options["postgresql"]["where"]),
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
            connection.execute(
                text(
                    "INSERT INTO ntubtob.person_qualifications "
                    "(person_id, qualification, status, created_at, updated_at) "
                    "VALUES (:first, 'team_player', 'active', :now, :now), "
                    "(:second, 'team_player', 'active', :now, :now)"
                ),
                {"first": self.people[0], "second": self.people[1], "now": NOW},
            )
            identity_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('line', 'fictional-publisher', :person, 'linked', :now, :now) "
                    "RETURNING id"
                ),
                {"person": self.people[0], "now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions "
                    "(id, auth_identity_id, person_id, installation_id_hash, platform, "
                    "status, access_epoch, refresh_family_expires_at, created_at, updated_at) "
                    "VALUES ('publishing-session', :identity, :person, :installation, "
                    "'android', 'active', 1, :expires, :now, :now)"
                ),
                {
                    "identity": identity_id,
                    "person": self.people[0],
                    "installation": secret_hash("fictional-installation-001"),
                    "expires": NOW + timedelta(days=30),
                    "now": NOW,
                },
            )
            other_identity_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('line', 'fictional-other-device', :person, 'linked', :now, :now) "
                    "RETURNING id"
                ),
                {"person": self.people[1], "now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions "
                    "(id, auth_identity_id, person_id, installation_id_hash, platform, "
                    "status, access_epoch, refresh_family_expires_at, created_at, updated_at) "
                    "VALUES ('other-device-session', :identity, :person, :installation, "
                    "'android', 'active', 1, :expires, :now, :now)"
                ),
                {
                    "identity": other_identity_id,
                    "person": self.people[1],
                    "installation": secret_hash("fictional-installation-002"),
                    "expires": NOW + timedelta(days=30),
                    "now": NOW,
                },
            )
            self.notification_ids = []
            for offset in (1, 2, 91):
                created = NOW - timedelta(days=offset)
                notification_id = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.mobile_notifications "
                        "(notification_type, title, body, destination_type, created_at, visible_until) "
                        "VALUES ('game_reminder', :title, :body, 'notification', :created, :visible_until) RETURNING id"
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
        expected = {
            "mobile_notifications",
            "mobile_notification_recipients",
            "mobile_notification_publish_audits",
            "mobile_notification_deliveries",
            "mobile_device_registrations",
        }
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0008_mobile_notification_delivery",
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
                                "(notification_type, title, body, destination_type, created_at, visible_until) "
                                "VALUES (:notification_type, 'title', 'body', 'notification', :now, :until)"
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

    def test_publish_is_atomic_idempotent_audited_and_provider_independent(self):
        service = NotificationPublishingService(self.repository, clock=lambda: NOW)
        principal = MobilePrincipal(
            "publishing-session", self.people[0], 1, "officer", "Officer", 1
        )
        draft = {
            "type": "officer_team_broadcast",
            "title": "集合提醒",
            "body": "請準時抵達。",
            "audience": {"type": "team"},
            "destination": {"type": "notification"},
        }
        preview = service.preview(principal, draft)
        first = service.confirm(
            principal,
            draft,
            preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"],
            idempotency_key="publishing-command-0001",
        )
        replay = service.confirm(
            principal,
            draft,
            preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"],
            idempotency_key="publishing-command-0001",
        )
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(first["notification_id"], replay["notification_id"])
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT count(*) FROM ntubtob.mobile_notification_publish_audits")
                ),
                1,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_notification_deliveries "
                        "WHERE status='pending' AND channel='push'"
                    )
                ),
                1,
            )
            delivery_id = connection.scalar(
                text(
                    "SELECT id FROM ntubtob.mobile_notification_deliveries "
                    "WHERE channel='push'"
                )
            )
        failure = service.reject_delivery(delivery_id)
        self.assertEqual(failure["error_code"], "provider_not_configured")
        self.assertTrue(failure["retryable"])
        self.assertIsNotNone(
            self.repository.notification_detail(
                self.people[1], int(first["notification_id"].split("_")[1]), NOW
            )
        )
        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ntubtob.mobile_notification_publish_audits "
                        "SET recipient_count=1"
                    )
                )

    def test_device_registration_is_current_session_bound_and_token_unique(self):
        service = NotificationPublishingService(self.repository, clock=lambda: NOW)
        officer = MobilePrincipal(
            "publishing-session", self.people[0], 1, "officer", "Officer", 1
        )
        other = MobilePrincipal(
            "other-device-session", self.people[1], 2, "basic", "Other", 1
        )
        token = "fake-device-token-obvious-test-only-0001"
        active = service.register_device(
            officer,
            installation_id="fictional-installation-001",
            platform="android",
            provider="fake",
            token=token,
        )
        self.assertEqual(active["status"], "active")
        with self.assertRaisesRegex(Conflict, "device registration is unavailable"):
            service.register_device(
                officer,
                installation_id="fictional-installation-wrong",
                platform="android",
                provider="fake",
                token="fake-device-token-obvious-test-only-0002",
            )
        with self.assertRaisesRegex(Conflict, "device registration is unavailable"):
            service.register_device(
                other,
                installation_id="fictional-installation-002",
                platform="android",
                provider="fake",
                token=token,
            )
        forged = MobilePrincipal(
            "other-device-session", self.people[0], 1, "officer", "Officer", 1
        )
        with self.assertRaisesRegex(Conflict, "device registration is unavailable"):
            service.revoke_device(
                forged, installation_id="fictional-installation-001"
            )
        self.assertTrue(
            service.revoke_device(
                officer, installation_id="fictional-installation-001"
            )["changed"]
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_sessions SET status='revoked', "
                    "revoked_at=:now, updated_at=:now WHERE id='publishing-session'"
                ),
                {"now": NOW},
            )
        with self.assertRaisesRegex(Conflict, "device registration is unavailable"):
            service.register_device(
                officer,
                installation_id="fictional-installation-001",
                platform="android",
                provider="fake",
                token="fake-device-token-obvious-test-only-0003",
            )


if __name__ == "__main__":
    unittest.main()
