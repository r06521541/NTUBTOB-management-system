from __future__ import annotations

import concurrent.futures
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text

from shared_lib.shared_module.portal_data import identity_lifecycle as lifecycle_module
from shared_lib.shared_module.portal_data import local_database
from shared_lib.shared_module.portal_data.domain import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.models import (
    GuestQualificationAuditRecord,
    PersonQualificationRecord,
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
    def test_person_status_uses_canonical_admin_then_event_snapshot_lock_order(self):
        repository = IdentityLifecycleRepository(MagicMock(), {7001})
        session = MagicMock()
        session_manager = MagicMock()
        session_manager.__enter__.return_value = session
        order = []
        session.execute.side_effect = lambda _statement, values: order.append(
            f"lock:{values['key']}"
        )
        revision = MagicMock()
        revision.all.return_value = ["0012_persistent_admin_authority"]
        presence = MagicMock()
        presence.one_or_none.return_value = "ntubtob.portal_authority_state"
        state = MagicMock()
        state.all.return_value = [
            SimpleNamespace(singleton_id=1, mode="legacy_allowlist", epoch=1)
        ]
        session.scalars.side_effect = [revision, presence, state]

        scalar_results = iter(
            (
                SimpleNamespace(portal_status="active", portal_access_level="admin"),
                SimpleNamespace(id=7001),
                1,
            )
        )

        def stop_at_target(*_args, **_kwargs):
            try:
                result = next(scalar_results)
            except StopIteration:
                order.append("target")
                raise RuntimeError("stop after lock order") from None
            order.append("actor" if len(order) == 3 else "admin-evidence")
            return result

        session.scalar.side_effect = stop_at_target
        with (
            patch.object(lifecycle_module, "Session", return_value=session_manager),
            self.assertRaisesRegex(RuntimeError, "lock order"),
        ):
            repository.change_person_status(
                1, 2, "disabled", "Fictional reason", "lock-order-fictional"
            )

        self.assertEqual(
            order,
            [
                f"lock:{lifecycle_module.ADMIN_LOCK_KEY}",
                f"lock:{lifecycle_module.EVENT_SNAPSHOT_LOCK_KEY}",
                f"lock:{lifecycle_module.ADMIN_LOCK_KEY}",
                "actor",
                "admin-evidence",
                "admin-evidence",
                "target",
            ],
        )
        self.assertEqual(
            [call.args[1] for call in session.execute.call_args_list],
            [
                {"key": lifecycle_module.ADMIN_LOCK_KEY},
                {"key": lifecycle_module.EVENT_SNAPSHOT_LOCK_KEY},
                {"key": lifecycle_module.ADMIN_LOCK_KEY},
            ],
        )

    def test_legacy_identity_repository_rejects_guest_lifecycle_bypass(self):
        repository = IdentityLifecycleRepository(MagicMock())
        calls = (
            lambda: repository.create_member_person(
                1,
                2,
                "Fictional",
                "Fictional reason",
                "legacy-create",
                ("guest_player",),
            ),
            lambda: repository.approve_non_member(
                1,
                2,
                "Fictional",
                "Fictional reason",
                "legacy-approve",
                qualifications=("guest_player",),
            ),
            lambda: repository.grant_qualification(
                1, 2, "guest_player", "Fictional reason", "legacy-grant"
            ),
            lambda: repository.revoke_qualification(
                1, 2, "guest_player", "Fictional reason", "legacy-revoke"
            ),
        )
        for call in calls:
            with (
                self.subTest(call=call),
                self.assertRaisesRegex(ValidationError, "guest lifecycle"),
            ):
                call()

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
        self.assertIn("ADD COLUMN version integer NOT NULL DEFAULT 1", source)
        self.assertIn("ck_person_qualification_version", source)
        downgrade = source.split("def downgrade() -> None:", 1)[1]
        for destructive in ("DROP TABLE", "DELETE FROM", "TRUNCATE"):
            self.assertNotIn(destructive, downgrade.upper())

    def test_guest_audit_metadata_matches_postgresql_migration_types(self):
        self.assertEqual(
            GuestQualificationAuditRecord.__table__.c.before_state.type.__class__.__name__,
            "JSONB",
        )
        self.assertEqual(
            GuestQualificationAuditRecord.__table__.c.after_state.type.__class__.__name__,
            "JSONB",
        )
        self.assertFalse(PersonQualificationRecord.__mapper__.eager_defaults)

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

    def test_test_cleanup_orders_exact_0012_before_existing_0011_cleanup(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        rows = (
            engine.connect.return_value.__enter__.return_value.scalars.return_value.all
        )
        rows.side_effect = [
            ("0012_persistent_admin_authority",),
            ("0011_event_notification_guest_lifecycle",),
        ]
        inspector = MagicMock()
        inspector.has_table.return_value = True
        order = []

        def cleanup(_engine):
            order.append("0012")

        begin_context = engine.begin.return_value
        engine.begin.side_effect = lambda: (order.append("0011") or begin_context)
        with (
            patch.object(cleanup_harness, "inspect", return_value=inspector),
            patch.object(
                cleanup_harness,
                "remove_retained_admin_authority_from_isolated_test_database",
                side_effect=cleanup,
            ) as admin_cleanup,
        ):
            result = prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(
                engine
            )
        self.assertEqual(result, "0010_apple_provider_lifecycle")
        self.assertEqual(order, ["0012", "0011"])
        admin_cleanup.assert_called_once_with(engine)


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
        try:
            prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(
                cls.engine
            )
        finally:
            cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
            connection.execute(text(LEGACY_FIXTURE_SQL))
            self.config.attributes["connection"] = connection
            try:
                command.upgrade(self.config, "0011_event_notification_guest_lifecycle")
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
        with self.assertRaises(ConflictError):
            self.repository.confirm_event_notification(
                self.officer.id,
                event_id,
                notification_type=preview["notification_type"],
                preview_revision=preview["revision"],
                typed_confirmation=preview["confirmation_text"] + " changed",
                request_id="notify-fictional-event",
            )
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

    def test_event_preview_and_status_change_complete_without_actor_lock_deadlock(self):
        manager_id = 9701
        actor = self.repository.create_person("Fictional Shared Lock Actor")
        target = self.repository.create_person(
            "Fictional Status Recipient", qualifications=("affiliate",)
        )
        remaining = self.repository.create_person(
            "Fictional Remaining Recipient", qualifications=("affiliate",)
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.members (id,name,person_id) "
                    "VALUES (:member_id,'Fictional Shared Lock Member',:person_id); "
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider,provider_subject,person_id,status,created_at,updated_at) "
                    "VALUES ('line','fictional-shared-lock-actor',:person_id,'linked',now(),now())"
                ),
                {"member_id": manager_id, "person_id": actor.id},
            )
        event_repository = PostgresTeamPortalRepository(
            self.engine, event_manager_member_ids={manager_id}
        )
        lifecycle_repository = IdentityLifecycleRepository(self.engine, {manager_id})
        event_id = event_repository.create_event(
            actor.id,
            "Fictional Lock Ordering Event",
            "other",
            datetime.now(timezone.utc) + timedelta(days=2),
            ("affiliate",),
        )
        event_repository.publish_event(actor.id, event_id, "publish-lock-order-event")

        event_holds_snapshot = threading.Event()
        release_event_actor_read = threading.Event()
        status_requests_snapshot = threading.Event()

        def before_statement(
            _connection, _cursor, statement, parameters, _context, _many
        ):
            if (
                threading.current_thread().name.startswith("status-change")
                and "pg_advisory_xact_lock" in statement
                and (
                    parameters == {"key": lifecycle_module.EVENT_SNAPSHOT_LOCK_KEY}
                    or parameters == (lifecycle_module.EVENT_SNAPSHOT_LOCK_KEY,)
                )
            ):
                status_requests_snapshot.set()

        def after_statement(
            _connection, _cursor, statement, parameters, _context, _many
        ):
            if (
                threading.current_thread().name.startswith("event-preview")
                and "pg_advisory_xact_lock" in statement
                and (
                    parameters == {"key": lifecycle_module.EVENT_SNAPSHOT_LOCK_KEY}
                    or parameters == (lifecycle_module.EVENT_SNAPSHOT_LOCK_KEY,)
                )
            ):
                event_holds_snapshot.set()
                if not release_event_actor_read.wait(5):
                    raise RuntimeError("status change did not request Event lock")

        event.listen(self.engine, "before_cursor_execute", before_statement)
        event.listen(self.engine, "after_cursor_execute", after_statement)
        try:
            with (
                concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="event-preview"
                ) as event_executor,
                concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="status-change"
                ) as status_executor,
            ):
                preview_future = event_executor.submit(
                    event_repository.preview_event_notification, actor.id, event_id
                )
                self.assertTrue(event_holds_snapshot.wait(2))
                status_future = status_executor.submit(
                    lifecycle_repository.change_person_status,
                    actor.id,
                    target.id,
                    "disabled",
                    "Fictional concurrent status exclusion",
                    "status-event-lock-order",
                )
                self.assertTrue(status_requests_snapshot.wait(2))
                self.assertFalse(status_future.done())
                release_event_actor_read.set()
                self.assertEqual(preview_future.result(timeout=5)["recipient_count"], 2)
                status_future.result(timeout=5)
        finally:
            release_event_actor_read.set()
            event.remove(self.engine, "before_cursor_execute", before_statement)
            event.remove(self.engine, "after_cursor_execute", after_statement)

        self.assertEqual(
            event_repository.preview_event_notification(actor.id, event_id)[
                "recipient_count"
            ],
            1,
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT portal_status FROM ntubtob.people "
                        "WHERE id=:person_id"
                    ),
                    {"person_id": target.id},
                ),
                "disabled",
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT portal_status FROM ntubtob.people "
                        "WHERE id=:person_id"
                    ),
                    {"person_id": remaining.id},
                ),
                "active",
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
        with self.assertRaises(ConflictError):
            self.repository.mutate_guest_qualification(
                self.officer.id,
                guest.id,
                "grant",
                expected_version=0,
                reason="Changed fictional payload",
                request_id="guest-grant-fictional",
                valid_from=valid_from,
                valid_until=valid_until,
                at=now,
            )

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

        extended_until = valid_until + timedelta(days=3)
        extended = self.repository.mutate_guest_qualification(
            self.officer.id,
            guest.id,
            "extend",
            expected_version=1,
            reason="Fictional guest extension",
            request_id="guest-extend-fictional",
            valid_until=extended_until,
            at=now,
        )
        self.assertEqual((extended["state"], extended["version"]), ("scheduled", 2))
        revoked = self.repository.mutate_guest_qualification(
            self.officer.id,
            guest.id,
            "revoke",
            expected_version=2,
            reason="Fictional guest revocation",
            request_id="guest-revoke-fictional",
            at=now,
        )
        self.assertEqual((revoked["state"], revoked["version"]), ("revoked", 3))

    def test_guest_mutation_rolls_back_when_audit_insert_fails(self):
        guest = self.repository.create_person("Fictional Rollback Guest")
        now = datetime.now(timezone.utc)

        def reject_audit(_connection, _cursor, statement, _parameters, _context, _many):
            if "INSERT INTO ntubtob.guest_qualification_audits" in statement:
                raise RuntimeError("fictional audit failure")

        from sqlalchemy import event

        event.listen(self.engine, "before_cursor_execute", reject_audit)
        try:
            with self.assertRaisesRegex(RuntimeError, "fictional audit failure"):
                self.repository.mutate_guest_qualification(
                    self.officer.id,
                    guest.id,
                    "grant",
                    expected_version=0,
                    reason="Fictional rollback",
                    request_id="guest-rollback-fictional",
                    valid_from=now,
                    valid_until=now + timedelta(days=2),
                    at=now,
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", reject_audit)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.person_qualifications "
                        "WHERE person_id=:person_id AND qualification='guest_player'"
                    ),
                    {"person_id": guest.id},
                ),
                0,
            )

    def test_guest_grant_rejects_member_and_active_team_player_overlap(self):
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            member_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.members (name) "
                    "VALUES ('Fictional Isolated Member') RETURNING id"
                )
            )
        for person in (
            self.repository.create_person(
                "Fictional Existing Member", member_id=member_id
            ),
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
            manager_member_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.members (name,person_id) "
                    "VALUES ('Fictional Allowlisted Member',:person_id) RETURNING id"
                ),
                {"person_id": manager.id},
            )
        repository = PostgresTeamPortalRepository(
            self.engine, event_manager_member_ids={manager_member_id}
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
        persisted_role_repository = PostgresTeamPortalRepository(
            self.engine, allow_persisted_event_managers=True
        )
        with self.assertRaises(AuthorizationError):
            persisted_role_repository.managed_events(persisted_admin.id)

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
