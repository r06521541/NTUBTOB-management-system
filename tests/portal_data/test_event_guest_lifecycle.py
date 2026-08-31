from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data import local_database
from shared_lib.shared_module.portal_data.domain import (
    AuthorizationError,
    ConflictError,
)
from shared_lib.shared_module.portal_data.repository import (
    EVENT_LIFECYCLE_REVISION,
    PostgresTeamPortalRepository,
    _guest_state,
)
from tests.portal_data import _event_guest_lifecycle_test_harness as cleanup_harness
from tests.portal_data._event_guest_lifecycle_test_harness import (
    prepare_event_guest_lifecycle_downgrade_for_isolated_test_database,
)
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class EventGuestLifecycleStaticTests(unittest.TestCase):
    def test_migration_is_linear_additive_and_retains_evidence_on_downgrade(self):
        source = (
            ROOT / "migrations/versions/0011_event_notification_guest_lifecycle.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'down_revision: Union[str, None] = "0010_apple_provider_lifecycle"', source
        )
        self.assertIn("event_notification_publish_audits", source)
        self.assertIn("guest_qualification_audits", source)
        self.assertIn("destination_event_id", source)
        self.assertIn("event_notification_publish_audits_append_only", source)
        self.assertIn("guest_qualification_audits_append_only", source)
        downgrade = source.split("def downgrade() -> None:", 1)[1]
        for destructive in ("DROP TABLE", "DELETE FROM", "TRUNCATE"):
            self.assertNotIn(destructive, downgrade.upper())

    def test_guest_state_is_derived_at_the_requested_time(self):
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        self.assertEqual(
            _guest_state(
                "active", now + timedelta(days=1), now + timedelta(days=2), now
            ),
            "scheduled",
        )
        self.assertEqual(
            _guest_state(
                "active", now - timedelta(days=1), now + timedelta(days=2), now
            ),
            "active",
        )
        self.assertEqual(
            _guest_state("active", now - timedelta(days=2), now, now), "expired"
        )
        self.assertEqual(
            _guest_state(
                "revoked", now - timedelta(days=1), now + timedelta(days=1), now
            ),
            "revoked",
        )

    def test_test_cleanup_rejects_nonlocal_or_unproven_revision_without_ddl(self):
        nonlocal_engine = SimpleNamespace(
            url=SimpleNamespace(
                drivername="postgresql",
                host="database.example.invalid",
                database="production",
            )
        )
        with self.assertRaisesRegex(RuntimeError, "isolated test database"):
            prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(
                nonlocal_engine
            )

        for revisions in (
            (),
            ("0012_future",),
            ("0011_event_notification_guest_lifecycle", "branch"),
        ):
            with self.subTest(revisions=revisions):
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
                inspector.has_table.return_value = True
                with patch.object(cleanup_harness, "inspect", return_value=inspector):
                    with self.assertRaisesRegex(RuntimeError, "exact revision 0011"):
                        prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(
                            engine
                        )
                engine.begin.assert_not_called()

    def test_test_cleanup_treats_exact_known_pre_0011_revision_as_noop(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = [
            "0004_phase_c_identity_lifecycle"
        ]
        inspector = MagicMock()
        inspector.has_table.return_value = True
        with patch.object(cleanup_harness, "inspect", return_value=inspector):
            prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(engine)
        engine.begin.assert_not_called()

    def test_test_cleanup_treats_fresh_schema_as_noop(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        inspector = MagicMock()
        inspector.has_table.return_value = False
        with patch.object(cleanup_harness, "inspect", return_value=inspector):
            prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(engine)
        engine.connect.assert_not_called()
        engine.begin.assert_not_called()

    def test_test_cleanup_reverses_only_exact_0011_in_isolated_database(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = [
            "0011_event_notification_guest_lifecycle"
        ]
        inspector = MagicMock()
        inspector.has_table.return_value = True
        with patch.object(cleanup_harness, "inspect", return_value=inspector):
            prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(engine)
        engine.begin.assert_called_once_with()
        statement = str(
            engine.begin.return_value.__enter__.return_value.execute.call_args.args[0]
        )
        self.assertIn("DROP TABLE", statement)
        self.assertIn("event_notification_publish_audits", statement)
        self.assertIn("guest_qualification_audits", statement)
        self.assertIn("SET version_num = '0010_apple_provider_lifecycle'", statement)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class EventGuestLifecyclePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            local_database.require_local_database_url(DATABASE_URL)
        )
        cls.config = Config("alembic.ini")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
            connection.execute(text(LEGACY_FIXTURE_SQL))
            self.config.attributes["connection"] = connection
            try:
                command.upgrade(self.config, "head")
            finally:
                self.config.attributes.pop("connection", None)
        self.repository = PostgresTeamPortalRepository(
            self.engine, allow_persisted_event_managers=True
        )
        self.officer = self.repository.create_person(
            "Fictional Officer", access_level="officer"
        )

    def test_event_notification_uses_snapshot_only_and_creates_no_push_work(self):
        included = self.repository.create_person(
            "Fictional Included", qualifications=("affiliate",)
        )
        excluded = self.repository.create_person(
            "Fictional Excluded", qualifications=("affiliate",)
        )
        event_id = self.repository.create_event(
            self.officer.id,
            "Fictional Published Event",
            "other",
            datetime.now(timezone.utc) + timedelta(days=2),
            ("affiliate",),
        )
        self.repository.set_invitee_override(
            self.officer.id,
            event_id,
            excluded.id,
            "exclude",
            "other",
            "Fictional exclusion",
            "exclude-fictional-person",
        )
        self.repository.publish_event(
            self.officer.id, event_id, "publish-fictional-event"
        )
        self.repository.revoke_qualification(included.id, "affiliate")

        preview = self.repository.preview_event_notification(self.officer.id, event_id)
        self.assertEqual(preview["recipient_count"], 1)
        result = self.repository.confirm_event_notification(
            self.officer.id,
            event_id,
            notification_type=preview["notification_type"],
            preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"],
            request_id="notify-fictional-event",
        )
        replay = self.repository.confirm_event_notification(
            self.officer.id,
            event_id,
            notification_type=preview["notification_type"],
            preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"],
            request_id="notify-fictional-event",
        )
        self.assertFalse(result["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(result["notification_id"], replay["notification_id"])
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_notification_recipients "
                        "WHERE notification_id=:notification_id AND person_id=:person_id"
                    ),
                    {
                        "notification_id": result["notification_id"],
                        "person_id": included.id,
                    },
                ),
                1,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_notification_deliveries "
                        "WHERE notification_id=:notification_id AND channel='push'"
                    ),
                    {"notification_id": result["notification_id"]},
                ),
                0,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_notification_deliveries "
                        "WHERE notification_id=:notification_id AND channel='in_app' "
                        "AND status='succeeded' AND retryable IS FALSE"
                    ),
                    {"notification_id": result["notification_id"]},
                ),
                1,
            )

    def test_guest_lifecycle_is_versioned_idempotent_and_event_time_eligible(self):
        guest = self.repository.create_person("Fictional Guest")
        now = datetime.now(timezone.utc)
        valid_from = now + timedelta(days=1)
        valid_until = now + timedelta(days=10)
        granted = self.repository.mutate_guest_qualification(
            self.officer.id,
            guest.id,
            "grant",
            expected_version=0,
            reason="Fictional guest invitation",
            request_id="guest-grant-fictional",
            valid_from=valid_from,
            valid_until=valid_until,
            at=now,
        )
        replay = self.repository.mutate_guest_qualification(
            self.officer.id,
            guest.id,
            "grant",
            expected_version=0,
            reason="Fictional guest invitation",
            request_id="guest-grant-fictional",
            valid_from=valid_from,
            valid_until=valid_until,
            at=now,
        )
        self.assertEqual(granted["state"], "scheduled")
        self.assertTrue(replay["replayed"])

        event_id = self.repository.create_event(
            self.officer.id,
            "Future Guest Event",
            "other",
            now + timedelta(days=2),
            ("guest_player",),
        )
        invitees = self.repository.publish_event(
            self.officer.id, event_id, "publish-future-guest-event"
        )
        self.assertEqual(
            [(row.person_id, row.participation_category) for row in invitees],
            [(guest.id, "guest_player")],
        )
        with self.assertRaises(ConflictError):
            self.repository.mutate_guest_qualification(
                self.officer.id,
                guest.id,
                "revoke",
                expected_version=0,
                reason="Stale fictional version",
                request_id="guest-stale-fictional",
                at=now,
            )

    def test_guest_grant_rejects_member_and_active_team_player_overlap(self):
        now = datetime.now(timezone.utc)
        for person in (
            self.repository.create_person("Fictional Existing Member", member_id=9301),
            self.repository.create_person(
                "Fictional Existing Team Player", qualifications=("team_player",)
            ),
        ):
            with self.subTest(person_id=person.id):
                with self.assertRaises(ConflictError):
                    self.repository.mutate_guest_qualification(
                        self.officer.id,
                        person.id,
                        "grant",
                        expected_version=0,
                        reason="Fictional rejected overlap",
                        request_id=f"guest-overlap-{person.id}",
                        valid_from=now,
                        valid_until=now + timedelta(days=1),
                        at=now,
                    )

    def test_allowlisted_active_member_can_manage_without_persisted_admin_access(self):
        manager = self.repository.create_person("Fictional Allowlisted Manager")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.members (id,name,person_id) "
                    "VALUES (9201,'Fictional Allowlisted Member',:person_id)"
                ),
                {"person_id": manager.id},
            )
        repository = PostgresTeamPortalRepository(
            self.engine, event_manager_member_ids={9201}
        )
        candidate = repository.create_person(
            "Fictional Guest Candidate", qualifications=("affiliate",)
        )
        self.assertIn(
            candidate.id,
            {row["person_id"] for row in repository.guest_candidates(manager.id)},
        )
        event_id = repository.create_event(
            manager.id,
            "Fictional Allowlisted Event",
            "other",
            datetime.now(timezone.utc) + timedelta(days=2),
            ("affiliate",),
        )
        repository.publish_event(manager.id, event_id, "publish-allowlisted-event")
        self.assertEqual(
            repository.preview_event_notification(manager.id, event_id)["event_id"],
            event_id,
        )

        persisted_admin = repository.create_person(
            "Fictional Non-Allowlisted Admin", access_level="admin"
        )
        with self.assertRaises(AuthorizationError):
            repository.guest_candidates(persisted_admin.id)

    def test_new_writes_fail_closed_before_exact_head(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.alembic_version SET version_num=:revision"),
                {"revision": "0010_apple_provider_lifecycle"},
            )
        with self.assertRaises(ConflictError):
            self.repository.guest_candidates(self.officer.id)
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.alembic_version SET version_num=:revision"),
                {"revision": EVENT_LIFECYCLE_REVISION},
            )


if __name__ == "__main__":
    unittest.main()
