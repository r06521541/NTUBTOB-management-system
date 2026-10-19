"""Lifecycle principal fences against only the explicitly isolated ledger DB."""

import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from shared_module.mobile_api import AccountUnavailable
from shared_module.portal_data import identity_lifecycle as module
from shared_module.portal_data import repository as portal
from shared_module.portal_data.domain import AuthorizationError, ConflictError
from shared_module.portal_data.mobile_repository import MobileRepository
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.portal_data import test_erasure_ledger as ledger


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL required")
class LifecycleErasureGatePostgresTests(unittest.TestCase):
    def test_new_publication_excludes_erasing_qualification_and_manual_targets(self):
        repo = portal.PostgresTeamPortalRepository(
            self.engine,
            erasure_checks_enabled=True,
            allow_persisted_event_managers=True,
        )
        actor, target = self.fixture.other_person, self.fixture.person
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level='officer' WHERE id=:id"
            ),
            {"id": actor},
        )
        with patch.object(
            portal,
            "Session",
            side_effect=lambda *_: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        ):
            for person in (actor, target):
                repo.grant_qualification(person, "staff")
            events = [
                repo.create_event(actor, "Fictional", "other", ledger.NOW, ["staff"])
                for _ in range(2)
            ]
            request = str(uuid4())
            repo.set_invitee_override(
                actor,
                events[1],
                target,
                "include",
                "staff",
                "Fictional reason",
                request,
            )
            job = self.fixture.job()
            self.fixture.update(job, status="verified", verified_at=ledger.NOW)
            for request_id in (request, str(uuid4())):
                with self.assertRaisesRegex(
                    AuthorizationError, "account access unavailable"
                ):
                    repo.set_invitee_override(
                        actor,
                        events[1],
                        target,
                        "include",
                        "staff",
                        "Fictional reason",
                        request_id,
                    )
            for event_id in events:
                invitees = repo.publish_event(actor, event_id, str(uuid4()))
                self.assertEqual({row.person_id for row in invitees}, {actor})

            # Default-off compatibility and unknown-ledger atomicity are distinct.
            repo.erasure_checks_enabled = False
            event_id = repo.create_event(
                actor, "Fictional default off", "other", ledger.NOW, ["staff"]
            )
            self.assertEqual(
                {
                    row.person_id
                    for row in repo.publish_event(actor, event_id, str(uuid4()))
                },
                {actor, target},
            )
            repo.erasure_checks_enabled = True
            event_id = repo.create_event(
                actor, "Fictional unavailable", "other", ledger.NOW, ["staff"]
            )
            with patch.object(
                repo,
                "_erasure_eligible_people",
                side_effect=AuthorizationError("account access unavailable"),
            ):
                with self.assertRaises(AuthorizationError):
                    repo.publish_event(actor, event_id, str(uuid4()))
            self.assertEqual(repo.event_invitees(event_id), [])
            self.assertEqual(
                self.connection.scalar(
                    text("SELECT status FROM ntubtob.events WHERE id=:id"),
                    {"id": event_id},
                ),
                "draft",
            )

    def test_mobile_line_candidate_creation_keeps_parent_guard(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        repo = MobileRepository(self.engine, erasure_checks_enabled=True)
        with self.assertRaisesRegex(AccountUnavailable, "^account access unavailable$"):
            repo.ensure_line_link_candidate(
                self.subject, "Changed fictional", "fictional-request", ledger.NOW
            )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT person_id FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": self.fixture.identity},
            ),
            self.fixture.person,
        )

    def test_lifecycle_own_reads_recheck_verified_account(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        for method, args in (
            ("scoped_games", (self.fixture.person,)),
            ("scoped_events", (self.fixture.person,)),
            ("own_attendance_reply", (self.fixture.person, 99)),
            ("own_attendance_reply_state", (self.fixture.person, 99)),
        ):
            with (
                self.subTest(method=method),
                self.assertRaisesRegex(
                    AuthorizationError, "^account access unavailable$"
                ),
            ):
                getattr(self.repo, method)(*args)

    def test_lifecycle_event_bridge_blocks_verified_person_with_real_ledger(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with patch.object(
            portal,
            "Session",
            side_effect=lambda *_: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        ):
            for method, args in (
                ("event_attendance", (self.fixture.person, 99)),
                (
                    "reply_to_event_attendance",
                    (self.fixture.person, 99, "attending", True),
                ),
                (
                    "reply_to_activity_attendance",
                    (self.fixture.person, 99, 100, "maybe"),
                ),
            ):
                with (
                    self.subTest(method=method),
                    self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ),
                ):
                    getattr(self.repo, method)(*args)

    def test_lifecycle_admin_targets_use_real_ledger_before_audit_or_write(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        actor, person, identity = (
            self.fixture.other_person,
            self.fixture.person,
            self.fixture.identity,
        )
        reason, request = "Fictional reason", "fictional-target-request"
        operations = (
            ("change_access", (actor, person, "officer", reason, request)),
            ("change_admin_access", (actor, person, "admin", 1, reason, request)),
            ("set_identity_status", (actor, identity, "disabled", reason, request)),
            ("unlink_identity", (actor, identity, reason, request)),
            ("change_person_status", (actor, person, "disabled", reason, request)),
            ("grant_qualification", (actor, person, "staff", reason, request)),
            ("revoke_qualification", (actor, person, "staff", reason, request)),
            ("remap_member_identity", (actor, identity, 999999, reason, request)),
        )
        with (
            patch.object(self.repo, "_require_admin"),
            patch.object(self.repo, "_audit_exists") as audit,
        ):
            for method, args in operations:
                with (
                    self.subTest(method=method),
                    self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ),
                ):
                    getattr(self.repo, method)(*args)
            audit.assert_not_called()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT version FROM ntubtob.people WHERE id=:id"),
                {"id": person},
            ),
            1,
        )

    def test_lifecycle_pending_targets_cannot_be_approved_or_messaged(self):
        identity, actor = self.fixture.other_identity, self.fixture.other_person
        job = self.fixture.job(
            target_kind="pending_identity", person_id=None, auth_identity_id=identity
        )
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        reason, request = "Fictional reason", "fictional-pending-request"
        with (
            patch.object(self.repo, "_require_admin"),
            patch.object(self.repo, "_audit_exists") as audit,
        ):
            for method, args, kwargs in (
                ("approve_member", (actor, identity, 999999, reason, request), {}),
                (
                    "approve_non_member",
                    (actor, identity, "Fictional", reason, request),
                    {},
                ),
                (
                    "post_review_message",
                    (identity, "Fictional message", request),
                    {"actor_person_id": actor},
                ),
            ):
                with (
                    self.subTest(method=method),
                    self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ),
                ):
                    getattr(self.repo, method)(*args, **kwargs)
            audit.assert_not_called()

    def test_portal_notification_rechecks_recipients_before_confirm(self):
        repo = portal.PostgresTeamPortalRepository(
            self.engine,
            erasure_checks_enabled=True,
            allow_persisted_event_managers=True,
        )
        actor = self.fixture.other_person
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level='officer' WHERE id=:id"
            ),
            {"id": actor},
        )
        with patch.object(
            portal,
            "Session",
            side_effect=lambda *_: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        ):
            for person in (self.fixture.person, actor):
                repo.grant_qualification(person, "staff")
            event = repo.create_event(
                actor, "Fictional event", "other", ledger.NOW, ["staff"]
            )
            repo.publish_event(actor, event, str(uuid4()))
            before = repo.preview_event_notification(actor, event)
            self.assertEqual(before["recipient_count"], 2)
            job = self.fixture.job()
            self.fixture.update(job, status="verified", verified_at=ledger.NOW)
            after = repo.preview_event_notification(actor, event)
            self.assertEqual(after["recipient_count"], 1)
            self.assertNotEqual(before["revision"], after["revision"])
            with self.assertRaises(ConflictError):
                repo.confirm_event_notification(
                    actor,
                    event,
                    notification_type=before["notification_type"],
                    preview_revision=before["revision"],
                    typed_confirmation=before["confirmation_text"],
                    request_id=str(uuid4()),
                )
            result = repo.confirm_event_notification(
                actor,
                event,
                notification_type=after["notification_type"],
                preview_revision=after["revision"],
                typed_confirmation=after["confirmation_text"],
                request_id=str(uuid4()),
            )
            self.assertEqual(result["recipient_count"], 1)

    def test_portal_pending_identity_and_destination_cannot_be_modified(self):
        repo = portal.PostgresTeamPortalRepository(
            self.engine, erasure_checks_enabled=True
        )
        pending_job = self.fixture.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.fixture.other_identity,
        )
        self.fixture.update(pending_job, status="verified", verified_at=ledger.NOW)
        with (
            patch.object(
                portal,
                "Session",
                side_effect=lambda *_: Session(
                    bind=self.connection, join_transaction_mode="create_savepoint"
                ),
            ),
            patch.object(repo, "_require_admin"),
        ):
            for method in ("approve_identity", "block_identity"):
                with self.assertRaisesRegex(
                    AuthorizationError, "account access unavailable"
                ):
                    getattr(repo, method)(
                        self.fixture.other_person,
                        self.fixture.other_identity,
                        "fictional reason",
                        str(uuid4()),
                    )
        status = self.connection.scalar(
            text("SELECT status FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.fixture.other_identity},
        )
        self.assertEqual(status, "pending")

    def test_portal_erasing_destination_and_guest_target_are_denied(self):
        repo = portal.PostgresTeamPortalRepository(
            self.engine, erasure_checks_enabled=True
        )
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with (
            patch.object(
                portal,
                "Session",
                side_effect=lambda *_: Session(
                    bind=self.connection, join_transaction_mode="create_savepoint"
                ),
            ),
            patch.object(repo, "_require_admin"),
            patch.object(repo, "_require_guest_manager"),
        ):
            with self.assertRaisesRegex(
                AuthorizationError, "account access unavailable"
            ):
                repo.approve_identity(
                    self.fixture.other_person,
                    self.fixture.other_identity,
                    "fictional reason",
                    str(uuid4()),
                    person_id=self.fixture.person,
                )
            with self.assertRaisesRegex(
                AuthorizationError, "account access unavailable"
            ):
                repo.mutate_guest_qualification(
                    self.fixture.other_person,
                    self.fixture.person,
                    "grant",
                    expected_version=0,
                    reason="fictional reason",
                    request_id=str(uuid4()),
                    valid_from=ledger.NOW,
                    valid_until=ledger.NOW + timedelta(days=1),
                    at=ledger.NOW,
                )

    @classmethod
    def setUpClass(cls):
        ledger.ErasureLedgerPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.connection = self.fixture.connection
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET provider='line', person_id=:person,status='linked' WHERE id=:identity"
            ),
            {"person": self.fixture.person, "identity": self.fixture.identity},
        )
        self.subject = self.connection.scalar(
            text("SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.fixture.identity},
        )
        self.repo = module.IdentityLifecycleRepository(
            self.engine, erasure_checks_enabled=True
        )
        self.session_patch = patch.object(
            module,
            "Session",
            side_effect=lambda *_: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        )
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    def tearDown(self):
        self.fixture.tearDown()

    def principals(self):
        return (
            self.repo.resolve_line_principal(self.subject),
            self.repo.resolve_principal("line", self.subject),
            self.repo.resolve_principal_by_ids(
                self.fixture.identity, self.fixture.person
            ),
        )

    def test_requested_is_allowed_verified_denied_and_default_off_unchanged(self):
        job = self.fixture.job()
        self.assertTrue(all(value is not None for value in self.principals()))
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        self.assertEqual(self.principals(), (None, None, None))
        self.repo.erasure_checks_enabled = False
        self.assertTrue(all(value is not None for value in self.principals()))

    def test_other_person_does_not_block_and_scope_mismatch_never_authenticates(self):
        job = self.fixture.job(person_id=self.fixture.other_person)
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        self.assertTrue(all(value is not None for value in self.principals()))
        self.assertIsNone(
            self.repo.resolve_principal_by_ids(
                self.fixture.identity, self.fixture.other_person
            )
        )

    def test_verified_administrator_denied_before_authority_mode(self):
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"),
            {"id": self.fixture.person},
        )
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            with self.assertRaisesRegex(
                AuthorizationError, "^account access unavailable$"
            ):
                self.repo._require_admin(session, self.fixture.person)

    def test_selfservice_writes_and_existing_line_candidate_are_blocked(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        for method, args in (
            (
                "ensure_pending_line_identity",
                (self.subject, "Fictional name", "fictional-line-request"),
            ),
            (
                "update_profile",
                (
                    self.fixture.person,
                    self.fixture.person,
                    "Fictional changed",
                    "fictional-profile",
                ),
            ),
            ("reply_to_game", (self.fixture.person, 99, 1)),
        ):
            with (
                self.subTest(method=method),
                self.assertRaisesRegex(
                    AuthorizationError, "^account access unavailable$"
                ),
            ):
                getattr(self.repo, method)(*args)
        pending_job = self.fixture.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.fixture.other_identity,
        )
        self.fixture.update(pending_job, status="verified", verified_at=ledger.NOW)
        with self.assertRaisesRegex(AuthorizationError, "^account access unavailable$"):
            self.repo.post_review_message(
                self.fixture.other_identity, "Fictional message", "fictional-review"
            )

    def test_portal_manager_and_attendance_gate_use_actual_ledger(self):
        repo = portal.PostgresTeamPortalRepository(
            self.engine,
            allow_persisted_event_managers=True,
            erasure_checks_enabled=True,
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level='officer' WHERE id=:id"
            ),
            {"id": self.fixture.person},
        )
        job = self.fixture.job()
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            self.assertEqual(
                repo._require_event_manager(session, self.fixture.person).id,
                self.fixture.person,
            )
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with patch.object(
            portal,
            "Session",
            side_effect=lambda *_: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        ):
            for method, args in (
                ("event_attendance", (self.fixture.person, 99)),
                (
                    "reply_to_event_attendance",
                    (self.fixture.person, 99, "attending", True),
                ),
                (
                    "reply_to_activity_attendance",
                    (self.fixture.person, 99, 100, "maybe"),
                ),
            ):
                with (
                    self.subTest(method=method),
                    self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ),
                ):
                    getattr(repo, method)(*args)
            with patch.object(repo, "_require_admin"):
                for method, args in (
                    (
                        "change_access",
                        (
                            self.fixture.other_person,
                            self.fixture.person,
                            "basic",
                            "fictional",
                            "fictional-access",
                        ),
                    ),
                    (
                        "change_status",
                        (
                            self.fixture.other_person,
                            self.fixture.person,
                            "disabled",
                            "fictional",
                            "fictional-status",
                        ),
                    ),
                    ("grant_qualification", (self.fixture.person, "staff")),
                    ("revoke_qualification", (self.fixture.person, "staff")),
                ):
                    with (
                        self.subTest(method=method),
                        self.assertRaisesRegex(
                            AuthorizationError, "^account access unavailable$"
                        ),
                    ):
                        getattr(repo, method)(*args)
        for method in (
            "_require_admin",
            "_require_event_manager",
            "_require_guest_manager",
        ):
            with (
                Session(
                    bind=self.connection, join_transaction_mode="create_savepoint"
                ) as session,
                session.begin(),
            ):
                with (
                    self.subTest(method=method),
                    self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ),
                ):
                    getattr(repo, method)(session, self.fixture.person)
