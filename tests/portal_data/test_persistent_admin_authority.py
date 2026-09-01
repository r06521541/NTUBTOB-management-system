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
)
from tests.portal_data._persistent_admin_authority_test_harness import (
    remove_retained_admin_authority_from_isolated_test_database,
)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

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
        factory = MagicMock()
        factory.return_value.__enter__.return_value = session
        return session, patch(
            "shared_lib.shared_module.portal_data.identity_lifecycle.Session",
            factory,
        )

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
        session.get.return_value = SimpleNamespace(mode="persistent", epoch=3)
        repository = IdentityLifecycleRepository(
            MagicMock(), (), authority_mode="persistent"
        )
        self.assertIs(repository._require_admin(session, 9), actor)
        self.assertEqual(session.scalar.call_count, 2)

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
        setup_legacy_fixture()
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


if __name__ == "__main__":
    unittest.main()
