import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from shared_lib.shared_module.account_deletion import AccountDeletionUnavailable
from shared_lib.shared_module.mobile_api import (
    AccountUnavailable,
    AuthenticationError,
    MobilePrincipal,
)
from shared_lib.shared_module.portal_data.account_deletion import (
    AccountDeletionRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.mobile_repository import MobileRepository
from shared_lib.shared_module.portal_data.models import (
    AccountDeletionRequestRecord,
    AuthIdentityRecord,
    MobileSessionRecord,
    PersonRecord,
)

NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)
MODULE = "shared_lib.shared_module.portal_data.account_deletion"


class AccountDeletionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.principal = MobilePrincipal("fake-session", 1, 2, "basic", "Fake", 3)
        self.identity = SimpleNamespace(id=2, person_id=1, status="linked")
        self.person = SimpleNamespace(id=1, portal_status="active")
        self.device = SimpleNamespace(
            id="fake-session",
            person_id=1,
            auth_identity_id=2,
            status="active",
            access_epoch=3,
            refresh_family_expires_at=NOW + timedelta(days=1),
        )
        self.existing = AccountDeletionRequestRecord(
            id=str(uuid4()), person_id=1, status="requested", requested_at=NOW
        )
        self.session = MagicMock()
        self.factory = MagicMock()
        self.factory.return_value.__enter__.return_value = self.session
        self.repository = AccountDeletionRepository(MagicMock(), clock=lambda: NOW)

    def invoke(self, method="request", existing=None):
        self.session.scalar.side_effect = [
            self.identity,
            self.person,
            self.device,
            existing,
        ]
        with patch(MODULE + ".Session", self.factory):
            return getattr(self.repository, method)(self.principal)

    def test_new_request_only_adds_request_and_uses_locked_current_tuple(self):
        result = self.invoke()
        self.assertEqual(result.requested_at, NOW)
        self.assertEqual(self.session.add.call_count, 1)
        row = self.session.add.call_args.args[0]
        self.assertIsInstance(row, AccountDeletionRequestRecord)
        self.assertEqual((row.person_id, row.status), (1, "requested"))
        for call in self.session.scalar.call_args_list[:3]:
            self.assertIn("FOR UPDATE", str(call.args[0]))
        self.assertEqual(self.device.status, "active")
        self.assertEqual(self.person.portal_status, "active")
        self.assertEqual(self.identity.status, "linked")

    def test_status_does_not_create_and_replay_keeps_original_receipt(self):
        self.assertIsNone(self.invoke("status"))
        for method in ("status", "request"):
            self.assertEqual(self.invoke(method, self.existing).id, self.existing.id)
        self.session.add.assert_not_called()

    def test_stale_or_cross_person_tuple_never_replays_existing_receipt(self):
        variants = (
            ("identity", "status", "disabled", AuthenticationError),
            ("identity", "status", "pending", AuthenticationError),
            ("identity", "person_id", 9, AuthenticationError),
            ("person", "portal_status", "disabled", AccountUnavailable),
            ("person", "portal_status", "pending", AccountUnavailable),
            ("device", "person_id", 9, AuthenticationError),
            ("device", "auth_identity_id", 9, AuthenticationError),
            ("device", "status", "revoked", AuthenticationError),
            ("device", "access_epoch", 4, AuthenticationError),
            ("device", "refresh_family_expires_at", NOW, AuthenticationError),
        )
        for target, name, value, error in variants:
            for method in ("status", "request"):
                with self.subTest(target=target, name=name, method=method):
                    row = getattr(self, target)
                    original = getattr(row, name)
                    setattr(row, name, value)
                    try:
                        with self.assertRaises(error):
                            self.invoke(method, self.existing)
                    finally:
                        setattr(row, name, original)
        self.session.add.assert_not_called()

    def test_clock_is_sampled_after_all_auth_rows_are_locked(self):
        def clock():
            self.assertEqual(self.session.scalar.call_count, 3)
            return NOW + timedelta(days=2)

        self.repository.clock = clock
        with self.assertRaises(AuthenticationError):
            self.invoke(existing=self.existing)

    def test_missing_auth_rows_never_read_or_return_a_receipt(self):
        for name in ("identity", "person", "device"):
            original = getattr(self, name)
            try:
                setattr(self, name, None)
                with (
                    self.subTest(name=name),
                    self.assertRaises((AuthenticationError, AccountUnavailable)),
                ):
                    self.invoke(existing=self.existing)
            finally:
                setattr(self, name, original)

    def test_database_failure_is_sanitized_and_not_retryable(self):
        self.session.execute.side_effect = OperationalError(
            "private statement", {}, Exception("private error")
        )
        with patch(MODULE + ".Session", self.factory):
            with self.assertRaises(AccountDeletionUnavailable) as caught:
                self.repository.request(self.principal)
        self.assertFalse(caught.exception.retryable)
        self.assertNotIn("private", str(caught.exception))

    def test_commit_acknowledgement_loss_is_unknown_not_automatically_retried(self):
        self.session.begin.return_value.__exit__.side_effect = OperationalError(
            "private commit", {}, Exception("private connection failure")
        )
        with self.assertRaises(AccountDeletionUnavailable):
            self.invoke()
        self.assertEqual(self.session.add.call_count, 1)
        self.assertEqual(self.session.begin.call_count, 1)

    def test_migration_is_additive_rls_and_retains_requests_on_downgrade(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "migrations/versions/0013_account_deletion_requests.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'down_revision: Union[str, None] = "0012_persistent_admin_authority"',
            source,
        )
        self.assertIn("ENABLE ROW LEVEL SECURITY", source)
        self.assertIn("UNIQUE (person_id)", source)
        self.assertNotRegex(source.upper(), r"\b(GRANT|CREATE POLICY|DELETE FROM)\b")
        self.assertNotRegex(
            source.split("def downgrade() -> None:")[1].upper(),
            r"\b(DROP|DELETE|TRUNCATE)\b",
        )


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class AccountDeletionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))
        with cls.engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0013_account_deletion_requests")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.repository = AccountDeletionRepository(self.engine, clock=lambda: NOW)
        self.principals = []
        self.extra_sessions = []
        for _index in range(2):
            with Session(self.engine) as session, session.begin():
                person = PersonRecord(
                    display_name="Fictional deletion tester",
                    portal_access_level="basic",
                    portal_status="active",
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                )
                session.add(person)
                session.flush()
                identity = AuthIdentityRecord(
                    provider="line",
                    provider_subject="fake-deletion-" + str(uuid4()),
                    person_id=person.id,
                    status="linked",
                    created_at=NOW,
                    updated_at=NOW,
                )
                session.add(identity)
                session.flush()
                device = MobileSessionRecord(
                    id=str(uuid4()),
                    auth_identity_id=identity.id,
                    person_id=person.id,
                    installation_id_hash="f" * 64,
                    platform="ios",
                    status="active",
                    access_epoch=1,
                    refresh_family_expires_at=NOW + timedelta(days=1),
                    created_at=NOW,
                    updated_at=NOW,
                )
                session.add(device)
                self.principals.append(
                    MobilePrincipal(
                        device.id, person.id, identity.id, "basic", "Fictional", 1
                    )
                )
        self.principal = self.principals[0]

    def tearDown(self):
        with self.engine.begin() as connection:
            for session_id in self.extra_sessions:
                connection.execute(
                    text("DELETE FROM ntubtob.mobile_sessions WHERE id=:id"),
                    {"id": session_id},
                )
            for principal in self.principals:
                for table, column, value in (
                    ("account_deletion_requests", "person_id", principal.person_id),
                    ("mobile_sessions", "id", principal.session_id),
                    ("auth_identities", "id", principal.identity_id),
                    ("people", "id", principal.person_id),
                ):
                    connection.execute(
                        text(f"DELETE FROM ntubtob.{table} WHERE {column}=:value"),
                        {"value": value},
                    )

    def test_concurrent_requests_across_sessions_reuse_one_row(self):
        other_session_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions (id,auth_identity_id,person_id,installation_id_hash,platform,status,access_epoch,refresh_family_expires_at,created_at,updated_at) SELECT :other,auth_identity_id,person_id,installation_id_hash,platform,status,access_epoch,refresh_family_expires_at,created_at,updated_at FROM ntubtob.mobile_sessions WHERE id=:id"
                ),
                {"other": other_session_id, "id": self.principal.session_id},
            )
        self.extra_sessions.append(other_session_id)
        other = MobilePrincipal(
            other_session_id,
            self.principal.person_id,
            self.principal.identity_id,
            "basic",
            "Fictional",
            1,
        )
        barrier = threading.Barrier(2)

        def submit(principal):
            barrier.wait(timeout=10)
            return self.repository.request(principal)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(submit, principal)
                for principal in (self.principal, other)
            ]
            records = [future.result(timeout=15) for future in futures]
        self.assertEqual(records[0], records[1])
        self.assertEqual(records[0], self.repository.status(self.principal))
        self.assertIsNone(self.repository.status(self.principals[1]))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_deletion_requests WHERE person_id=:person"
                    ),
                    {"person": self.principal.person_id},
                ),
                1,
            )

    def test_database_constraints_reject_duplicate_person_and_completed_status(self):
        self.repository.request(self.principal)
        for person_id, status in (
            (self.principal.person_id, "requested"),
            (self.principals[1].person_id, "completed"),
        ):
            with self.subTest(status=status), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_deletion_requests (id,person_id,status,requested_at) VALUES (:id,:person,:status,:now)"
                        ),
                        {
                            "id": str(uuid4()),
                            "person": person_id,
                            "status": status,
                            "now": NOW,
                        },
                    )

    def test_existing_receipt_is_unavailable_after_logout(self):
        self.repository.request(self.principal)
        MobileRepository(self.engine).logout(self.principal.session_id, NOW)
        for method in ("request", "status"):
            with self.assertRaises(AuthenticationError):
                getattr(self.repository, method)(self.principal)

    def test_request_waiting_on_logout_lock_observes_revocation(self):
        waiting = threading.Event()

        def before_execute(
            _connection, _cursor, statement, _parameters, _context, _many
        ):
            if "mobile_sessions" in statement and "FOR UPDATE" in statement:
                waiting.set()

        with self.engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(
                text("SELECT id FROM ntubtob.mobile_sessions WHERE id=:id FOR UPDATE"),
                {"id": self.principal.session_id},
            )
            event.listen(self.engine, "before_cursor_execute", before_execute)
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.repository.request, self.principal)
                    try:
                        self.assertTrue(waiting.wait(timeout=10))
                        connection.execute(
                            text(
                                "UPDATE ntubtob.mobile_sessions SET status='revoked', revoked_at=:now WHERE id=:id"
                            ),
                            {"now": NOW, "id": self.principal.session_id},
                        )
                        transaction.commit()
                    finally:
                        if transaction.is_active:
                            transaction.rollback()
                    with self.assertRaises(AuthenticationError):
                        future.result(timeout=15)
            finally:
                event.remove(self.engine, "before_cursor_execute", before_execute)

    def test_existing_receipt_rechecks_person_and_identity_changes(self):
        self.repository.request(self.principal)
        for table, column, identifier, value, error in (
            (
                "people",
                "portal_status",
                self.principal.person_id,
                "disabled",
                AccountUnavailable,
            ),
            (
                "auth_identities",
                "status",
                self.principal.identity_id,
                "disabled",
                AuthenticationError,
            ),
            (
                "auth_identities",
                "person_id",
                self.principal.identity_id,
                self.principals[1].person_id,
                AuthenticationError,
            ),
        ):
            with self.engine.connect() as connection:
                original = connection.scalar(
                    text(f"SELECT {column} FROM ntubtob.{table} WHERE id=:id"),
                    {"id": identifier},
                )
            try:
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            f"UPDATE ntubtob.{table} SET {column}=:value WHERE id=:id"
                        ),
                        {"id": identifier, "value": value},
                    )
                for method in ("request", "status"):
                    with self.assertRaises(error):
                        getattr(self.repository, method)(self.principal)
            finally:
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            f"UPDATE ntubtob.{table} SET {column}=:value WHERE id=:id"
                        ),
                        {"id": identifier, "value": original},
                    )

    def test_waiting_requests_observe_person_and_identity_revocation(self):
        for table, column, identifier, active, error in (
            (
                "people",
                "portal_status",
                self.principal.person_id,
                "active",
                AccountUnavailable,
            ),
            (
                "auth_identities",
                "status",
                self.principal.identity_id,
                "linked",
                AuthenticationError,
            ),
        ):
            waiting = threading.Event()

            def before_execute(
                _connection, _cursor, statement, _parameters, _context, _many
            ):
                if f"ntubtob.{table}" in statement and "FOR UPDATE" in statement:
                    waiting.set()

            with self.engine.connect() as connection:
                transaction = connection.begin()
                connection.execute(
                    text(f"SELECT id FROM ntubtob.{table} WHERE id=:id FOR UPDATE"),
                    {"id": identifier},
                )
                event.listen(self.engine, "before_cursor_execute", before_execute)
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            self.repository.request, self.principal
                        )
                        try:
                            self.assertTrue(waiting.wait(timeout=10))
                            connection.execute(
                                text(
                                    f"UPDATE ntubtob.{table} SET {column}='disabled' WHERE id=:id"
                                ),
                                {"id": identifier},
                            )
                            transaction.commit()
                        finally:
                            if transaction.is_active:
                                transaction.rollback()
                        with self.assertRaises(error):
                            future.result(timeout=15)
                finally:
                    event.remove(self.engine, "before_cursor_execute", before_execute)
                    with self.engine.begin() as restore:
                        restore.execute(
                            text(
                                f"UPDATE ntubtob.{table} SET {column}=:active WHERE id=:id"
                            ),
                            {"id": identifier, "active": active},
                        )


if __name__ == "__main__":
    unittest.main()
