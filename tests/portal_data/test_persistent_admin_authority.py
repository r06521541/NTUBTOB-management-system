from __future__ import annotations

import concurrent.futures
import os
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text

from shared_lib.shared_module.portal_data.domain import (
    AuthIdentity,
    AuthorizationError,
    ConflictError,
    Person,
    Principal,
    ValidationError,
)
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.mobile_repository import (
    APPLE_ADMIN_RECOVERY_REQUIRED,
    MobileRepository,
)
from shared_lib.shared_module.portal_data.models import PersonRecord
from shared_lib.shared_module.portal_data.runtime import (
    ADMIN_LOCK_KEY,
    EVENT_SNAPSHOT_LOCK_KEY,
    acquire_admin_event_locks,
    admin_authority_mode,
)
from tests.portal_data import (
    _persistent_admin_authority_test_harness as admin_cleanup_harness,
)
from tests.portal_data._apple_lifecycle_test_harness import (
    remove_retained_apple_evidence_from_isolated_test_database,
)
from tests.portal_data._event_guest_lifecycle_test_harness import (
    prepare_event_guest_lifecycle_downgrade_for_isolated_test_database,
    reset_pre_0011_schema_for_isolated_test_database,
)
from tests.portal_data._persistent_admin_authority_test_harness import (
    remove_retained_admin_authority_from_isolated_test_database,
)

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class PersistentAdminAuthorityStaticTests(unittest.TestCase):
    def test_mode_parser_is_exact_and_has_no_fallback(self):
        self.assertEqual(
            admin_authority_mode(
                {"WEB_PORTAL_ADMIN_AUTHORITY_MODE": "legacy_allowlist"}
            ),
            "legacy_allowlist",
        )
        self.assertEqual(
            admin_authority_mode({"WEB_PORTAL_ADMIN_AUTHORITY_MODE": "persistent"}),
            "persistent",
        )
        for value in (None, "", "Persistent", "legacy", "persistent "):
            environment = {}
            if value is not None:
                environment["WEB_PORTAL_ADMIN_AUTHORITY_MODE"] = value
            with self.subTest(value=value):
                self.assertIsNone(admin_authority_mode(environment))

    def test_canonical_lock_helper_is_admin_then_event(self):
        session = MagicMock()
        acquire_admin_event_locks(session)
        keys = [call.args[1]["key"] for call in session.execute.call_args_list]
        self.assertEqual(keys, [ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY])

    def test_migration_is_linear_additive_and_evidence_retaining(self):
        source = (
            ROOT / "migrations" / "versions" / "0012_persistent_admin_authority.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'down_revision: Union[str, None] = "0011_event_notification_guest_lifecycle"',
            source,
        )
        self.assertIn("CREATE TABLE ntubtob.portal_authority_state", source)
        self.assertIn("VALUES (1, 'legacy_allowlist', 1, now())", source)
        downgrade = source.split("def downgrade() -> None:", 1)[1]
        self.assertNotRegex(downgrade.upper(), r"\b(DROP|DELETE|TRUNCATE)\b")

    def test_reachability_writers_take_canonical_order_before_rows(self):
        source = (
            ROOT
            / "shared_lib"
            / "shared_module"
            / "portal_data"
            / "identity_lifecycle.py"
        ).read_text(encoding="utf-8")
        for method in (
            "change_access",
            "change_admin_access",
            "remap_member_identity",
            "set_identity_status",
            "unlink_identity",
            "change_person_status",
        ):
            with self.subTest(method=method):
                body = source.split(f"    def {method}(", 1)[1].split("\n    def ", 1)[
                    0
                ]
                self.assertLess(
                    body.index("acquire_admin_event_locks(session)"),
                    body.index(".with_for_update()"),
                )

    def test_apple_provider_disable_takes_canonical_order_before_identity_rows(self):
        source = (
            ROOT
            / "shared_lib"
            / "shared_module"
            / "portal_data"
            / "mobile_repository.py"
        ).read_text(encoding="utf-8")
        body = source.split("    def apply_apple_notification(", 1)[1].split(
            "\n    def ", 1
        )[0]
        self.assertLess(
            body.index("acquire_admin_event_locks(session)"),
            body.index("select(AuthIdentityRecord)"),
        )
        self.assertNotIn("UPDATE ntubtob.portal_authority_state", body)

    def test_test_cleanup_rejects_unknown_or_branched_revision_before_ddl(self):
        for revisions in (
            ("0013_future",),
            ("0012_persistent_admin_authority", "branch"),
        ):
            with self.subTest(revisions=revisions):
                engine = MagicMock()
                engine.url = SimpleNamespace(
                    drivername="postgresql",
                    host="localhost",
                    database=admin_cleanup_harness.LOCAL_DATABASE_NAME,
                )
                engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = (
                    revisions
                )
                inspector = MagicMock()
                inspector.has_table.return_value = True
                with patch.object(
                    admin_cleanup_harness, "inspect", return_value=inspector
                ):
                    with self.assertRaises(RuntimeError):
                        remove_retained_admin_authority_from_isolated_test_database(
                            engine
                        )
                engine.begin.assert_not_called()


class PersistentAdminMutationUnitTests(unittest.TestCase):
    @staticmethod
    def _person(person_id: int, access: str, version: int = 1) -> PersonRecord:
        now = datetime.now(timezone.utc)
        return PersonRecord(
            id=person_id,
            display_name=f"Fictional {person_id}",
            formal_name=None,
            admin_note=None,
            portal_access_level=access,
            portal_status="active",
            version=version,
            created_at=now,
            updated_at=now,
        )

    def _session_patch(self, scalar_values):
        session = MagicMock()
        session.scalar.side_effect = scalar_values
        session.scalars.side_effect = self._exact_authority_rows("legacy_allowlist")
        factory = MagicMock()
        factory.return_value.__enter__.return_value = session
        return session, patch(
            "shared_lib.shared_module.portal_data.identity_lifecycle.Session",
            factory,
        )

    @staticmethod
    def _exact_authority_rows(mode):
        revision = MagicMock()
        revision.all.return_value = ["0012_persistent_admin_authority"]
        presence = MagicMock()
        presence.one_or_none.return_value = "ntubtob.portal_authority_state"
        state = MagicMock()
        state.all.return_value = [SimpleNamespace(singleton_id=1, mode=mode, epoch=3)]
        return [revision, presence, state]

    def test_grant_uses_expected_version_and_append_only_audit(self):
        actor = self._person(1, "admin")
        target = self._person(2, "basic", version=4)
        # actor Person, actor Member, actor linked count, target, prior audit,
        # target linked count, target Member
        session, session_patch = self._session_patch(
            [actor, MagicMock(id=7), 1, target, None, 1, None]
        )
        repository = IdentityLifecycleRepository(
            MagicMock(), (7,), authority_mode="legacy_allowlist"
        )
        with session_patch:
            result = repository.change_admin_access(
                1, 2, "admin", 4, "approved fictional promotion", "admin-grant-1"
            )
        self.assertEqual(result.access_level, "admin")
        self.assertEqual(target.version, 5)
        audits = [
            call.args[0]
            for call in session.add.call_args_list
            if call.args and call.args[0].__class__.__name__ == "AccessAuditRecord"
        ]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].after_state["expected_version"], 4)
        self.assertEqual(audits[0].after_state["resulting_version"], 5)

    def test_persistent_admin_requires_no_member_and_does_not_use_allowlist(self):
        actor = self._person(9, "admin")
        session = MagicMock()
        session.scalar.side_effect = [actor, 1]
        session.scalars.side_effect = self._exact_authority_rows("persistent")
        repository = IdentityLifecycleRepository(
            MagicMock(), (), authority_mode="persistent"
        )
        self.assertIs(repository._require_admin(session, 9), actor)
        self.assertEqual(session.scalar.call_count, 2)

    def test_runtime_and_durable_modes_must_match_exactly(self):
        principal = Principal(
            Person(9, "Fictional", "admin", "active", member_id=7),
            AuthIdentity(10, "line", "fictional", "linked", 9),
            frozenset(),
        )
        for runtime_mode, durable_mode in (
            ("legacy_allowlist", "persistent"),
            ("persistent", "legacy_allowlist"),
        ):
            with self.subTest(runtime_mode=runtime_mode, durable_mode=durable_mode):
                repository = IdentityLifecycleRepository(
                    MagicMock(),
                    (7,) if runtime_mode == "legacy_allowlist" else (),
                    authority_mode=runtime_mode,
                )
                session = MagicMock()
                session.scalars.side_effect = self._exact_authority_rows(durable_mode)
                factory = MagicMock()
                factory.return_value.__enter__.return_value = session
                with patch(
                    "shared_lib.shared_module.portal_data.identity_lifecycle.Session",
                    factory,
                ):
                    self.assertIsNone(repository.web_role_for_principal(principal))

    def test_missing_malformed_or_multiple_durable_state_fails_closed(self):
        repository = IdentityLifecycleRepository(
            MagicMock(), (7,), authority_mode="legacy_allowlist"
        )
        invalid_states = (
            (),
            (SimpleNamespace(singleton_id=1, mode="legacy_allowlist", epoch=0),),
            (
                SimpleNamespace(singleton_id=1, mode="legacy_allowlist", epoch=1),
                SimpleNamespace(singleton_id=1, mode="legacy_allowlist", epoch=2),
            ),
        )
        for states in invalid_states:
            with self.subTest(states=states):
                session = MagicMock()
                revision = MagicMock()
                revision.all.return_value = ["0012_persistent_admin_authority"]
                presence = MagicMock()
                presence.one_or_none.return_value = "ntubtob.portal_authority_state"
                durable = MagicMock()
                durable.all.return_value = list(states)
                session.scalars.side_effect = [revision, presence, durable]
                self.assertFalse(repository.authority_mode_is_ready(session=session))

    def test_known_person_era_revisions_allow_only_table_absent_legacy_mode(self):
        known_revisions = (
            "0004_phase_c_identity_lifecycle",
            "0005_mobile_auth_api_foundation",
            "0006_staging_broker_operation_journal",
            "0007_mobile_notifications",
            "0008_mobile_notification_delivery",
            "0009_event_management_writes",
            "0010_apple_provider_lifecycle",
            "0011_event_notification_guest_lifecycle",
        )
        for revision_value in known_revisions:
            for mode, expected in (("legacy_allowlist", True), ("persistent", False)):
                repository = IdentityLifecycleRepository(
                    MagicMock(),
                    (7,) if mode == "legacy_allowlist" else (),
                    authority_mode=mode,
                )
                session = MagicMock()
                revision = MagicMock()
                revision.all.return_value = [revision_value]
                presence = MagicMock()
                presence.one_or_none.return_value = None
                session.scalars.side_effect = [revision, presence]
                with self.subTest(revision=revision_value, mode=mode):
                    self.assertIs(
                        repository.authority_mode_is_ready(session=session), expected
                    )

            for mode in ("legacy_allowlist", "persistent"):
                retained = IdentityLifecycleRepository(
                    MagicMock(),
                    (7,) if mode == "legacy_allowlist" else (),
                    authority_mode=mode,
                )
                session = MagicMock()
                revision = MagicMock()
                revision.all.return_value = [revision_value]
                presence = MagicMock()
                presence.one_or_none.return_value = "ntubtob.portal_authority_state"
                state = MagicMock()
                session.scalars.side_effect = [revision, presence, state]
                with self.subTest(revision=revision_value, retained=True, mode=mode):
                    self.assertFalse(retained.authority_mode_is_ready(session=session))
                    state.all.assert_not_called()

    def test_pre_person_unknown_future_and_multi_revision_fail_closed(self):
        repository = IdentityLifecycleRepository(
            MagicMock(), (7,), authority_mode="legacy_allowlist"
        )
        revision_rows = (
            ("0003_legacy_bigint_activity_game",),
            ("0013_future",),
            ("unknown",),
            (
                "0009_event_management_writes",
                "0010_apple_provider_lifecycle",
            ),
        )
        for rows in revision_rows:
            session = MagicMock()
            revision = MagicMock()
            revision.all.return_value = list(rows)
            session.scalars.return_value = revision
            with self.subTest(rows=rows):
                self.assertFalse(repository.authority_mode_is_ready(session=session))
                self.assertEqual(session.scalars.call_count, 1)

    def test_pre_0012_preview_compatibility_uses_persisted_role_without_state(self):
        actor = self._person(9, "admin")
        session = MagicMock()
        session.scalar.side_effect = [actor, 1]
        repository = IdentityLifecycleRepository(
            MagicMock(), (), allow_persisted_admins=True
        )
        self.assertIs(repository._require_admin(session, 9), actor)
        session.get.assert_not_called()

    def test_disabled_or_unlinked_persistent_principal_fails_before_state_read(self):
        repository = IdentityLifecycleRepository(
            MagicMock(), (), authority_mode="persistent"
        )
        active = Person(9, "Fictional", "admin", "active")
        disabled = Person(9, "Fictional", "admin", "disabled")
        linked = AuthIdentity(10, "line", "fictional", "linked", 9)
        unlinked = AuthIdentity(10, "line", "fictional", "disabled", 9)
        self.assertIsNone(
            repository.web_role_for_principal(Principal(disabled, linked, frozenset()))
        )
        self.assertIsNone(
            repository.web_role_for_principal(Principal(active, unlinked, frozenset()))
        )

    def test_constructor_rejects_simultaneous_authority_sources(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            IdentityLifecycleRepository(
                MagicMock(),
                (7,),
                authority_mode="legacy_allowlist",
                allow_persisted_admins=True,
            )
        with self.assertRaisesRegex(ValueError, "rejects an allowlist"):
            IdentityLifecycleRepository(MagicMock(), (7,), authority_mode="persistent")

    def test_self_change_and_stale_version_fail_closed(self):
        actor = self._person(1, "admin", version=2)
        repository = IdentityLifecycleRepository(
            MagicMock(), (7,), authority_mode="legacy_allowlist"
        )
        session, session_patch = self._session_patch([actor, MagicMock(id=7), 1, actor])
        with session_patch, self.assertRaises(AuthorizationError):
            repository.change_admin_access(
                1, 1, "basic", 2, "no self lockout", "admin-self-1"
            )
        target = self._person(2, "basic", version=3)
        session, session_patch = self._session_patch(
            [actor, MagicMock(id=7), 1, target, None]
        )
        with session_patch, self.assertRaisesRegex(ConflictError, "stale"):
            repository.change_admin_access(
                1, 2, "admin", 2, "stale fictional change", "admin-stale-1"
            )

    def test_admin_request_id_is_bounded_before_database_access(self):
        repository = IdentityLifecycleRepository(
            MagicMock(), (7,), authority_mode="legacy_allowlist"
        )
        for request_id in ("", "x" * 101, "non ascii 值", "has space"):
            with (
                self.subTest(request_id=request_id),
                self.assertRaises(ValidationError),
            ):
                repository.change_admin_access(
                    1,
                    2,
                    "admin",
                    1,
                    "bounded fictional request",
                    request_id,
                )


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PersistentAdminAuthorityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))

    @classmethod
    def tearDownClass(cls):
        remove_retained_admin_authority_from_isolated_test_database(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        remove_retained_admin_authority_from_isolated_test_database(self.engine)
        prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(self.engine)
        remove_retained_apple_evidence_from_isolated_test_database(self.engine)
        reset_pre_0011_schema_for_isolated_test_database(
            self.engine,
            lambda revision: command.upgrade(Config("alembic.ini"), revision),
            target_revision="0010_apple_provider_lifecycle",
        )
        command.upgrade(Config("alembic.ini"), "head")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.portal_authority_state "
                    "SET mode='persistent', epoch=2, updated_at=now() "
                    "WHERE singleton_id=1"
                )
            )
            self.actor_one = self._insert_person(connection, "Actor One", "admin")
            self.actor_two = self._insert_person(connection, "Actor Two", "admin")
            self.target = self._insert_person(connection, "Target", "basic")
        self.repository = IdentityLifecycleRepository(
            self.engine, (), authority_mode="persistent"
        )

    def tearDown(self):
        remove_retained_admin_authority_from_isolated_test_database(self.engine)

    @staticmethod
    def _insert_person(connection, name: str, access: str) -> int:
        person_id = connection.scalar(
            text(
                "INSERT INTO ntubtob.people "
                "(display_name,portal_access_level,portal_status,version,"
                "created_at,updated_at) "
                "VALUES (:name,:access,'active',1,now(),now()) RETURNING id"
            ),
            {"name": name, "access": access},
        )
        connection.execute(
            text(
                "INSERT INTO ntubtob.auth_identities "
                "(provider,provider_subject,person_id,status,created_at,updated_at) "
                "VALUES ('line',:subject,:person_id,'linked',now(),now())"
            ),
            {"subject": f"fictional-admin-{person_id}", "person_id": person_id},
        )
        return person_id

    def test_upgrade_state_grant_exact_replay_and_append_only_audit(self):
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0012_persistent_admin_authority",
            )
        first = self.repository.change_admin_access(
            self.actor_one,
            self.target,
            "admin",
            1,
            "Approve fictional persistent admin",
            "persistent-admin-grant-exact",
        )
        replay = self.repository.change_admin_access(
            self.actor_one,
            self.target,
            "admin",
            1,
            "Approve fictional persistent admin",
            "persistent-admin-grant-exact",
        )
        self.assertEqual((first.access_level, replay.access_level), ("admin", "admin"))
        with self.assertRaisesRegex(ConflictError, "replay does not match"):
            self.repository.change_admin_access(
                self.actor_one,
                self.target,
                "admin",
                1,
                "Different fictional reason",
                "persistent-admin-grant-exact",
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit "
                        "WHERE request_id='persistent-admin-grant-exact'"
                    )
                ),
                1,
            )
        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ntubtob.access_audit SET reason='forbidden' "
                        "WHERE request_id='persistent-admin-grant-exact'"
                    )
                )

    def test_concurrent_last_admin_removals_allow_exactly_one(self):
        barrier = threading.Barrier(2)

        def revoke(actor_id, target_id, request_id):
            barrier.wait(timeout=5)
            try:
                self.repository.change_admin_access(
                    actor_id,
                    target_id,
                    "basic",
                    1,
                    "Concurrent fictional revoke",
                    request_id,
                )
                return "applied"
            except (AuthorizationError, ConflictError):
                return "denied"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(
                future.result(timeout=10)
                for future in (
                    executor.submit(
                        revoke,
                        self.actor_one,
                        self.actor_two,
                        "persistent-admin-revoke-one",
                    ),
                    executor.submit(
                        revoke,
                        self.actor_two,
                        self.actor_one,
                        "persistent-admin-revoke-two",
                    ),
                )
            )
        self.assertEqual(sorted(results), ["applied", "denied"])
        with self.engine.connect() as connection:
            reachable = connection.scalar(
                text(
                    "SELECT count(DISTINCT p.id) FROM ntubtob.people p "
                    "JOIN ntubtob.auth_identities i ON i.person_id=p.id "
                    "WHERE p.portal_status='active' "
                    "AND p.portal_access_level='admin' AND i.status='linked'"
                )
            )
        self.assertEqual(reachable, 1)

    def test_event_holder_can_lock_actor_before_admin_writer_rows(self):
        writer_requested_event = threading.Event()

        def observe(_connection, _cursor, statement, parameters, _context, _many):
            if (
                threading.current_thread() is not threading.main_thread()
                and "pg_advisory_xact_lock" in statement
                and parameters == {"key": EVENT_SNAPSHOT_LOCK_KEY}
            ):
                writer_requested_event.set()

        event.listen(self.engine, "before_cursor_execute", observe)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": EVENT_SNAPSHOT_LOCK_KEY},
                )
                future = executor.submit(
                    self.repository.change_admin_access,
                    self.actor_one,
                    self.target,
                    "admin",
                    1,
                    "Prove Admin then Event ordering",
                    "persistent-admin-lock-order",
                )
                self.assertTrue(writer_requested_event.wait(timeout=5))
                connection.execute(
                    text("SELECT id FROM ntubtob.people WHERE id=:id FOR UPDATE"),
                    {"id": self.actor_one},
                )
            result = future.result(timeout=10)
        finally:
            event.remove(self.engine, "before_cursor_execute", observe)
            executor.shutdown(wait=True)
        self.assertEqual(result.access_level, "admin")

    def test_last_apple_admin_revocation_is_terminal_and_requires_recovery(self):
        subject = "fictional-last-apple-admin"
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='basic' "
                    "WHERE id=:person_id"
                ),
                {"person_id": self.actor_two},
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET provider='apple', "
                    "provider_subject=:subject WHERE person_id=:person_id"
                ),
                {"subject": subject, "person_id": self.actor_one},
            )
        result = MobileRepository(self.engine).apply_apple_notification(
            jti_hash="a" * 64,
            event_type="consent-revoked",
            subject=subject,
            event_at=datetime.now(timezone.utc),
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(result, APPLE_ADMIN_RECOVERY_REQUIRED)
        with self.engine.connect() as connection:
            state = connection.execute(
                text(
                    "SELECT i.status, s.mode FROM ntubtob.auth_identities i "
                    "CROSS JOIN ntubtob.portal_authority_state s "
                    "WHERE i.provider='apple' AND i.provider_subject=:subject"
                ),
                {"subject": subject},
            ).one()
            audit = connection.execute(
                text(
                    "SELECT action, after_state FROM ntubtob.access_audit "
                    "WHERE request_id=:request_id"
                ),
                {"request_id": f"apple-admin-recovery-{'a' * 64}"},
            ).one()
        self.assertEqual(tuple(state), ("disabled", "persistent"))
        self.assertEqual(audit.action, "identity_disabled")
        self.assertEqual(audit.after_state["admin_recovery"], "required")

    def test_provider_disable_and_admin_revoke_share_deadlock_free_order(self):
        subject = "fictional-competing-apple-admin"
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET provider='apple', "
                    "provider_subject=:subject WHERE person_id=:person_id"
                ),
                {"subject": subject, "person_id": self.actor_one},
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' "
                    "WHERE id=:person_id"
                ),
                {"person_id": self.target},
            )
        provider_requested_event = threading.Event()

        def observe(_connection, _cursor, statement, parameters, _context, _many):
            if (
                threading.current_thread() is not threading.main_thread()
                and "pg_advisory_xact_lock" in statement
                and parameters == {"key": EVENT_SNAPSHOT_LOCK_KEY}
            ):
                provider_requested_event.set()

        event.listen(self.engine, "before_cursor_execute", observe)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": EVENT_SNAPSHOT_LOCK_KEY},
                )
                provider = executor.submit(
                    MobileRepository(self.engine).apply_apple_notification,
                    jti_hash="b" * 64,
                    event_type="account-deleted",
                    subject=subject,
                    event_at=datetime.now(timezone.utc),
                    now=datetime.now(timezone.utc),
                )
                self.assertTrue(provider_requested_event.wait(timeout=5))
                revoke = executor.submit(
                    self.repository.change_admin_access,
                    self.actor_two,
                    self.target,
                    "basic",
                    1,
                    "Concurrent provider disable and admin revoke",
                    "provider-disable-admin-revoke",
                )
                connection.execute(
                    text(
                        "SELECT id FROM ntubtob.auth_identities "
                        "WHERE provider='apple' AND provider_subject=:subject "
                        "FOR UPDATE"
                    ),
                    {"subject": subject},
                )
            self.assertTrue(provider.result(timeout=10))
            self.assertEqual(revoke.result(timeout=10).access_level, "basic")
        finally:
            event.remove(self.engine, "before_cursor_execute", observe)
            executor.shutdown(wait=True)
        with self.engine.connect() as connection:
            identity_status, durable_mode = connection.execute(
                text(
                    "SELECT i.status, s.mode FROM ntubtob.auth_identities i "
                    "CROSS JOIN ntubtob.portal_authority_state s "
                    "WHERE i.provider='apple' AND i.provider_subject=:subject"
                ),
                {"subject": subject},
            ).one()
            reachable_admins = connection.scalar(
                text(
                    "SELECT count(DISTINCT p.id) FROM ntubtob.people p "
                    "JOIN ntubtob.auth_identities i ON i.person_id=p.id "
                    "WHERE p.portal_status='active' "
                    "AND p.portal_access_level='admin' AND i.status='linked'"
                )
            )
            revoke_audits = connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.access_audit "
                    "WHERE request_id='provider-disable-admin-revoke' "
                    "AND action='access_changed'"
                )
            )
            recovery_audits = connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.access_audit "
                    "WHERE request_id=:request_id"
                ),
                {"request_id": f"apple-admin-recovery-{'b' * 64}"},
            )
        self.assertEqual(identity_status, "disabled")
        self.assertEqual(durable_mode, "persistent")
        self.assertEqual(reachable_admins, 1)
        self.assertEqual(revoke_audits, 1)
        self.assertEqual(recovery_audits, 0)


if __name__ == "__main__":
    unittest.main()
