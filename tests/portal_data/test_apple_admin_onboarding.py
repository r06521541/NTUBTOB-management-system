"""Apple admin approval regressions; no provider or live database calls."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from shared_lib.shared_module.portal_data.domain import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.models import (
    AccessAuditRecord,
    AuthIdentityRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)
from tests.portal_data import test_phase_c_lifecycle as phase_c_fixture

MODULE = "shared_lib.shared_module.portal_data.identity_lifecycle"
NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)


class AppleAdminApprovalUnitTests(unittest.TestCase):
    def setUp(self):
        self.repository = IdentityLifecycleRepository(MagicMock())
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.identity = AuthIdentityRecord(
            id=22,
            provider="apple",
            provider_subject="fictional-apple-subject",
            status="pending",
            person_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.person = PersonRecord(
            id=31,
            display_name="Fictional Member",
            portal_status="inactive",
            portal_access_level="basic",
            version=1,
        )
        self.member = LegacyMemberRecord(id=41, name="Fictional", person_id=31)
        self.thread = SimpleNamespace(
            status="open", closed_at=None, redacted_at=None, last_activity_at=NOW
        )
        self.added = []
        self.session.add.side_effect = self.added.append
        self.session.get.return_value = self.identity

        def assign_person_id():
            for row in self.added:
                if isinstance(row, PersonRecord) and row.id is None:
                    row.id = 31

        self.session.flush.side_effect = assign_person_id
        self.result = object()
        for target, kwargs in (
            ("Session", {"return_value": self.session}),
            ("utc_now", {"return_value": NOW}),
            # This unit fixture exercises approval behavior with a raw mock;
            # actual suspension rejection is covered by real-PG integration.
            ("require_management_mutation", {"return_value": None}),
        ):
            patcher = patch(MODULE + "." + target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (
            ("_require_admin", None),
            ("_audit_exists", False),
            ("_thread", self.thread),
            ("resolve_principal_by_ids", self.result),
            ("resolve_line_principal", None),
        ):
            patcher = patch.object(self.repository, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def approve_member(self):
        return self.repository.approve_member(11, 22, 41, "Verified identity", "fake-1")

    def approve_non_member(self, **kwargs):
        return self.repository.approve_non_member(
            11, 22, "Fictional Applicant", "Verified identity", "fake-2", **kwargs
        )

    def test_apple_member_approval_has_no_legacy_line_dependency(self):
        self.session.scalar.side_effect = [
            self.identity,
            self.member,
            self.person,
            None,
        ]
        self.assertIs(self.approve_member(), self.result)
        self.assertEqual(
            (self.identity.status, self.identity.person_id), ("linked", 31)
        )
        self.assertEqual(self.person.portal_status, "active")
        self.assertEqual(self.thread.status, "closed")
        self.repository.resolve_principal_by_ids.assert_called_once_with(22, 31, NOW)
        self.repository.resolve_line_principal.assert_not_called()
        self.assertFalse(any(isinstance(row, PersonRecord) for row in self.added))
        self.assertFalse(
            any(
                "line_users" in str(call.args[0])
                for call in self.session.scalar.call_args_list
            )
        )
        self.assertTrue(
            any(isinstance(row, PersonQualificationRecord) for row in self.added)
        )
        self.assertTrue(any(isinstance(row, AccessAuditRecord) for row in self.added))

    def test_apple_non_member_creates_basic_person_without_line_row(self):
        self.session.scalar.side_effect = [self.identity]
        self.assertIs(
            self.approve_non_member(qualifications=("affiliate",)), self.result
        )
        person = next(row for row in self.added if isinstance(row, PersonRecord))
        self.assertEqual(
            (person.portal_access_level, person.portal_status), ("basic", "active")
        )
        self.assertEqual(self.identity.person_id, person.id)
        self.assertEqual(self.thread.status, "closed")
        self.repository.resolve_principal_by_ids.assert_called_once_with(22, 31, NOW)
        self.assertEqual(self.session.scalar.call_count, 1)

    def test_line_member_adapter_and_revoked_qualification_are_preserved(self):
        self.identity.provider = "line"
        legacy = SimpleNamespace(member_id=None, ignored=True)
        qualification = SimpleNamespace(status="revoked")
        self.session.scalar.side_effect = [
            self.identity,
            self.member,
            self.person,
            legacy,
            qualification,
        ]
        self.assertIs(self.approve_member(), self.result)
        self.assertEqual((legacy.member_id, legacy.ignored), (41, False))
        self.assertEqual(qualification.status, "revoked")
        self.assertFalse(
            any(isinstance(row, PersonQualificationRecord) for row in self.added)
        )

    def test_missing_line_row_and_ineligible_person_fail_closed(self):
        for status in ("disabled", "blocked"):
            self.person.portal_status = status
            self.session.scalar.side_effect = [self.identity, self.member, self.person]
            with self.subTest(status=status), self.assertRaises(ConflictError):
                self.approve_member()
        self.person.portal_status = "active"
        self.identity.provider = "line"
        self.session.scalar.side_effect = [
            self.identity,
            self.member,
            self.person,
            None,
        ]
        with self.assertRaises(ConflictError):
            self.approve_member()
        self.assertEqual(self.added, [])

    def test_approval_takes_canonical_locks_before_admin_and_target_locks(self):
        def require_admin(*args):
            keys = [call.args[1]["key"] for call in self.session.execute.call_args_list]
            self.assertEqual(keys, [70070, 0x4E545542 + 0x100000])
            self.session.scalar.assert_not_called()

        self.repository._require_admin.side_effect = require_admin
        self.session.scalar.side_effect = [
            self.identity,
            self.member,
            self.person,
            None,
        ]
        self.approve_member()
        for call in self.session.scalar.call_args_list:
            self.assertIn("FOR UPDATE", str(call.args[0]))

    def test_replay_for_a_different_identity_cannot_approve(self):
        self.repository._audit_exists.return_value = True
        self.identity.status = "linked"
        self.identity.person_id = 31
        self.session.scalar.return_value = SimpleNamespace(
            action="identity_linked",
            auth_identity_id=99,
            after_state={"status": "linked", "member_id": 41},
        )
        with self.assertRaises(ConflictError):
            self.approve_member()
        self.assertEqual(self.added, [])

    def test_google_and_non_pending_apple_cannot_be_approved(self):
        for provider, status, person_id in (
            ("google", "pending", None),
            ("apple", "linked", 31),
            ("apple", "disabled", None),
            ("apple", "blocked", None),
        ):
            for action in (self.approve_member, self.approve_non_member):
                with self.subTest(provider=provider, status=status, action=action):
                    self.identity.provider = provider
                    self.identity.status = status
                    self.identity.person_id = person_id
                    self.session.scalar.side_effect = [self.identity, self.member]
                    self.added.clear()
                    with self.assertRaises(ConflictError):
                        action()
                    self.assertEqual(self.added, [])

    def test_apple_cannot_use_line_only_zero_admin_bootstrap_core(self):
        self.session.scalar.side_effect = [self.identity, self.member]
        with self.assertRaises(ConflictError):
            self.repository._approve_member_in_transaction(
                self.session,
                22,
                41,
                "Verified bootstrap",
                "fake-bootstrap",
                NOW,
                None,
                strict_bootstrap=True,
            )
        self.assertEqual(self.added, [])

    def test_approval_rechecks_admin_and_rejects_team_guest_privileges(self):
        self.repository._require_admin.side_effect = AuthorizationError("revoked")
        for action in (self.approve_member, self.approve_non_member):
            with self.assertRaises(AuthorizationError):
                action()
        self.session.scalar.assert_not_called()
        for qualification in ("team_player", "guest_player", "admin"):
            with self.assertRaises(ValidationError):
                self.approve_non_member(qualifications=(qualification,))
        self.assertEqual(self.added, [])

    def test_blocked_apple_can_be_returned_to_pending_without_line_row(self):
        self.identity.status = "blocked"
        self.thread.status = "closed"
        self.thread.closed_at = NOW
        self.session.scalar.side_effect = [self.identity]
        identity = self.repository.set_identity_status(
            11, 22, "pending", "Verified re-review", "fake-apple-unblock"
        )
        self.assertEqual((identity.provider, identity.status), ("apple", "pending"))
        self.assertIsNone(self.identity.person_id)
        self.assertEqual((self.thread.status, self.thread.closed_at), ("open", None))
        self.assertEqual(self.session.scalar.call_count, 1)
        self.assertFalse(any(isinstance(row, PersonRecord) for row in self.added))

    def test_line_only_actions_reject_apple_before_legacy_or_replay_lookup(self):
        for action in ("ignore", "unignore", "unlink", "remap"):
            for replay in (False, True):
                with self.subTest(action=action, replay=replay):
                    self.identity.provider = "apple"
                    self.identity.status = (
                        "pending" if action in {"ignore", "unignore"} else "linked"
                    )
                    self.identity.person_id = (
                        None if self.identity.status == "pending" else 31
                    )
                    legacy = SimpleNamespace(
                        member_id=None,
                        ignored=replay if action == "ignore" else not replay,
                    )
                    self.session.reset_mock()
                    self.repository._audit_exists.reset_mock()
                    self.repository._audit_exists.return_value = replay
                    self.repository.resolve_line_principal.return_value = self.result
                    self.session.get.return_value = self.person
                    self.added.clear()
                    rows = (
                        [self.identity, self.member, self.person, legacy]
                        if action == "remap"
                        else [self.identity, legacy]
                    )
                    self.session.scalar.side_effect = rows
                    with self.assertRaises(ConflictError):
                        if action in {"ignore", "unignore"}:
                            self.repository.set_ignored(
                                11,
                                22,
                                action == "ignore",
                                "Fictional collision",
                                "fake-line-only",
                            )
                        elif action == "unlink":
                            self.repository.unlink_identity(
                                11, 22, "Fictional collision", "fake-line-only"
                            )
                        else:
                            self.repository.remap_member_identity(
                                11, 22, 41, "Fictional collision", "fake-line-only"
                            )
                    self.assertEqual(self.session.scalar.call_count, 1)
                    self.repository._audit_exists.assert_not_called()
                    self.assertEqual(self.added, [])

    def test_line_only_actions_keep_original_line_adapter(self):
        self.identity.provider = "line"
        legacy = SimpleNamespace(member_id=None, ignored=False)
        self.session.scalar.side_effect = [self.identity, legacy]
        ignored = self.repository.set_ignored(
            11, 22, True, "Verified LINE", "fake-ignore"
        )
        self.assertEqual(ignored.provider, "line")
        self.assertTrue(legacy.ignored)

        self.identity.status = "linked"
        self.identity.person_id = 31
        legacy.member_id = 41
        self.session.get.return_value = self.person
        self.session.scalar.side_effect = [self.identity, legacy]
        unlinked = self.repository.unlink_identity(
            11, 22, "Verified LINE", "fake-unlink"
        )
        self.assertEqual(unlinked.status, "pending")
        self.assertIsNone(legacy.member_id)

        self.identity.status = "linked"
        self.identity.person_id = 30
        self.session.scalar.side_effect = [
            self.identity,
            self.member,
            self.person,
            legacy,
        ]
        self.repository.resolve_line_principal.return_value = self.result
        self.assertIs(
            self.repository.remap_member_identity(
                11, 22, 41, "Verified LINE", "fake-remap"
            ),
            self.result,
        )
        self.assertEqual((self.identity.person_id, legacy.member_id), (31, 41))

    def test_dashboard_is_provider_scoped_and_does_not_expose_subject(self):
        self.session.scalars.return_value.all.return_value = []
        self.session.scalars.return_value.__iter__.return_value = iter(())
        self.session.execute.return_value.all.return_value = [
            (self.identity, None, None, None, self.thread)
        ]
        self.session.execute.return_value.__iter__.return_value = iter(())
        result = self.repository.admin_dashboard(11)
        row = result["identities"][0]
        self.assertEqual(row["provider"], "apple")
        self.assertEqual(row["nickname"], "Apple applicant")
        self.assertNotIn(self.identity.provider_subject, repr(result))
        statement = self.session.execute.call_args_list[0].args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.assertIn("auth_identities.provider IN ('line', 'apple')", sql)
        self.assertIn("auth_identities.provider = 'line'", sql)


@unittest.skipUnless(
    phase_c_fixture.DATABASE_URL, "isolated local PostgreSQL URL not configured"
)
class AppleAdminApprovalPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        phase_c_fixture.PhaseCLifecyclePostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        phase_c_fixture.PhaseCLifecyclePostgresTests.tearDownClass.__func__
    )
    setUp = phase_c_fixture.PhaseCLifecyclePostgresTests.setUp

    def pending(self, provider="apple", suffix="one"):
        with self.engine.begin() as connection:
            return connection.scalar(
                text(
                    """
                INSERT INTO ntubtob.auth_identities
                  (provider, provider_subject, status, created_at, updated_at)
                VALUES (:provider, :subject, 'pending', now(), now()) RETURNING id
                """
                ),
                {"provider": provider, "subject": "fictional-" + suffix},
            )

    def test_apple_new_person_approval_and_dashboard_without_legacy_rows(self):
        identity_id = self.pending()
        dashboard = self.repository.admin_dashboard(self.admin_person_id)
        item = next(
            row for row in dashboard["identities"] if row["identity_id"] == identity_id
        )
        self.assertEqual(item["provider"], "apple")
        principal = self.repository.approve_non_member(
            self.admin_person_id,
            identity_id,
            "Fictional Apple",
            "Verified applicant",
            "fictional-apple-new",
            qualifications=("affiliate",),
        )
        self.assertEqual(principal.identity.provider, "apple")
        self.assertEqual(principal.person.access_level, "basic")
        self.assertEqual(principal.qualifications, frozenset({"affiliate"}))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.line_users")), 0
            )

    def test_apple_existing_member_approval_is_idempotent_and_preserves_line(self):
        identity_id = self.pending()
        principal = self.repository.approve_member(
            self.admin_person_id,
            identity_id,
            7001,
            "Verified existing member",
            "fictional-apple-existing",
        )
        again = self.repository.approve_member(
            self.admin_person_id,
            identity_id,
            7001,
            "Verified existing member",
            "fictional-apple-existing",
        )
        self.assertEqual(principal.person.id, self.admin_person_id)
        self.assertEqual(again.person.id, principal.person.id)
        self.assertIsNotNone(
            self.repository.resolve_line_principal("fake-admin-subject")
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.people")), 1
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit WHERE request_id = 'fictional-apple-existing'"
                    )
                ),
                1,
            )

    def test_google_admin_approval_remains_closed(self):
        identity_id = self.pending("google")
        with self.assertRaises(ConflictError):
            self.repository.approve_non_member(
                self.admin_person_id,
                identity_id,
                "Fictional Google",
                "Not approved provider",
                "fictional-google-rejected",
            )

    def test_same_subject_in_other_provider_does_not_borrow_line_profile_or_mapping(
        self,
    ):
        identity_id = self.pending()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                INSERT INTO ntubtob.line_users
                  (nickname, line_user_id, member_id, has_replied, ignored)
                VALUES ('Fictional LINE Only', 'fictional-one', 7001, true, true)
                """
                )
            )
        item = next(
            row
            for row in self.repository.admin_dashboard(self.admin_person_id)[
                "identities"
            ]
            if row["identity_id"] == identity_id
        )
        self.assertEqual(item["nickname"], "Apple applicant")
        self.assertFalse(item["ignored"])
        principal = self.repository.approve_non_member(
            self.admin_person_id,
            identity_id,
            "Fictional Apple",
            "Verified different provider",
            "fictional-distinct-subject",
        )
        self.assertNotEqual(principal.person.id, self.admin_person_id)
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT member_id, ignored FROM ntubtob.line_users WHERE line_user_id = 'fictional-one'"
                )
            ).one()
            self.assertEqual(tuple(row), (7001, True))

    def test_revoked_admin_cannot_use_previous_dashboard_to_approve(self):
        identity_id = self.pending()
        self.repository.admin_dashboard(self.admin_person_id)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_status = 'disabled' WHERE id = :id"
                ),
                {"id": self.admin_person_id},
            )
        with self.assertRaises(AuthorizationError):
            self.repository.approve_non_member(
                self.admin_person_id,
                identity_id,
                "Fictional Apple",
                "Stale administrator",
                "fictional-stale-admin",
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT status FROM ntubtob.auth_identities WHERE id = :id"),
                    {"id": identity_id},
                ),
                "pending",
            )

    def test_concurrent_new_person_approvals_create_one_person(self):
        identity_id = self.pending()
        barrier = Barrier(2)

        def approve(index):
            barrier.wait(timeout=10)
            try:
                self.repository.approve_non_member(
                    self.admin_person_id,
                    identity_id,
                    "Fictional Apple",
                    "Verified applicant",
                    "fictional-race-" + str(index),
                )
                return "approved"
            except ConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(approve, (1, 2)))
        self.assertCountEqual(results, ["approved", "conflict"])
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.people")), 2
            )

    def test_line_only_actions_cannot_mutate_colliding_apple_subject(self):
        identity_id = self.pending()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                INSERT INTO ntubtob.line_users
                  (nickname, line_user_id, member_id, has_replied, ignored)
                VALUES ('Fictional LINE Only', 'fictional-one', NULL, true, false)
                """
                )
            )
        with self.assertRaises(ConflictError):
            self.repository.set_ignored(
                self.admin_person_id,
                identity_id,
                True,
                "Not LINE",
                "fake-collision-ignore",
            )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id = :person, status = 'linked' WHERE id = :id"
                ),
                {"person": self.admin_person_id, "id": identity_id},
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.line_users SET member_id = 7001 WHERE line_user_id = 'fictional-one'"
                )
            )
        for action in ("unlink", "remap"):
            with self.subTest(action=action), self.assertRaises(ConflictError):
                if action == "unlink":
                    self.repository.unlink_identity(
                        self.admin_person_id,
                        identity_id,
                        "Not LINE",
                        "fake-collision-unlink",
                    )
                else:
                    self.repository.remap_member_identity(
                        self.admin_person_id,
                        identity_id,
                        7001,
                        "Not LINE",
                        "fake-collision-remap",
                    )
        with self.engine.connect() as connection:
            self.assertEqual(
                tuple(
                    connection.execute(
                        text(
                            "SELECT member_id, ignored FROM ntubtob.line_users WHERE line_user_id = 'fictional-one'"
                        )
                    ).one()
                ),
                (7001, False),
            )
            self.assertEqual(
                tuple(
                    connection.execute(
                        text(
                            "SELECT person_id, status FROM ntubtob.auth_identities WHERE id = :id"
                        ),
                        {"id": identity_id},
                    ).one()
                ),
                (self.admin_person_id, "linked"),
            )
