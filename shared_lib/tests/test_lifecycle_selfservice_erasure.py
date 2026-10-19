"""Fictional self-service gate regressions; never connect to a database."""

import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from shared_module.portal_data import identity_lifecycle as module
from shared_module.portal_data.domain import AuthorizationError, ConflictError
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
)
from sqlalchemy.orm import Session, make_transient_to_detached

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


class LifecycleSelfserviceErasureTests(unittest.TestCase):
    def setUp(self):
        self.repo = module.IdentityLifecycleRepository(
            None, erasure_checks_enabled=True
        )
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.session.begin.side_effect = self.transaction
        self.active = False
        self.events = []
        self.error = None
        self.scopes = []
        self.identity = SimpleNamespace(
            id=9,
            provider="line",
            provider_subject="fictional-line",
            status="pending",
            person_id=None,
        )
        self.person = SimpleNamespace(
            id=7,
            display_name="Fictional",
            formal_name=None,
            admin_note=None,
            portal_access_level="basic",
            portal_status="active",
            version=1,
        )
        self.thread = SimpleNamespace(
            id=12,
            status="open",
            last_applicant_message_at=None,
        )
        self.repo._thread = Mock(return_value=self.thread)
        self.repo._audit_exists = Mock(return_value=False)
        self.repo._eligibility_in_session = Mock(return_value=(True, None))
        self.session.get.return_value = SimpleNamespace(
            id=3,
            start_datetime=NOW + timedelta(days=1),
            cancellation_time=None,
        )
        for name, kwargs in (
            ("Session", {"return_value": self.session}),
            ("utc_now", {"return_value": NOW}),
            ("acquire_admin_event_locks", {"side_effect": self.locks}),
            ("require_account_not_erasing", {"side_effect": self.gate}),
        ):
            patcher = patch.object(module, name, **kwargs)
            value = patcher.start()
            self.addCleanup(patcher.stop)
            if name == "require_account_not_erasing":
                self.checked = value

    @contextmanager
    def transaction(self):
        self.active = True
        try:
            yield
        finally:
            self.active = False

    def locks(self, session):
        self.assertIs(session, self.session)
        self.assertTrue(self.active)
        self.events.append("canonical")

    def gate(self, session, **scope):
        self.assertIs(session, self.session)
        self.assertTrue(self.active)
        self.assertEqual(self.events[0], "canonical")
        session.add.assert_not_called()
        session.flush.assert_not_called()
        self.events.append("gate")
        self.scopes.append(scope)
        if self.error:
            raise self.error("fictional-sensitive-detail")

    def prepare(self, operation, *, replay=False):
        if operation == "line":
            self.session.scalar.return_value = self.identity
            return lambda: self.repo.ensure_pending_line_identity(
                "fictional-line", "Fictional", "fictional-request"
            )
        if operation == "profile":
            self.session.scalar.side_effect = [self.person, None]
            self.repo._audit_exists.return_value = replay
            return lambda: self.repo.update_profile(
                7, 7, "Updated", "fictional-request"
            )
        if operation == "message":
            self.session.scalar.return_value = self.identity
            self.repo._audit_exists.return_value = replay
            return lambda: self.repo.post_review_message(
                9, "Fictional body", "fictional-request"
            )
        self.session.scalar.side_effect = [
            self.person,
            SimpleNamespace(reply=1) if replay else None,
            None,
        ]
        return lambda: self.repo.reply_to_game(7, 3, 1)

    def test_each_entry_fails_closed_before_write_or_idempotent_return(self):
        for operation in ("line", "profile", "message", "reply"):
            for error in (ErasureAccessBlocked, ErasureGuardUnavailable):
                with self.subTest(operation=operation, error=error):
                    self.session.reset_mock()
                    self.session.scalar.side_effect = None
                    self.repo._thread.reset_mock()
                    self.repo._audit_exists.reset_mock()
                    self.events.clear()
                    self.error = error
                    call = self.prepare(operation, replay=True)
                    with self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ):
                        call()
                    self.session.add.assert_not_called()
                    self.session.flush.assert_not_called()
                    self.repo._thread.assert_not_called()
                    self.repo._audit_exists.assert_not_called()
                    self.assertEqual(self.person.display_name, "Fictional")
                    if operation in {"profile", "reply"}:
                        self.session.scalar.assert_not_called()
                        self.assertEqual(
                            self.scopes[-1], {"person_id": 7, "identity_id": None}
                        )
                    else:
                        self.session.scalar.assert_called_once()
                        self.assertEqual(
                            self.scopes[-1], {"person_id": None, "identity_id": 9}
                        )

    def test_existing_line_identity_uses_current_mapping_and_never_resets_it(self):
        for person_id, status in ((None, "pending"), (7, "linked"), (19, "disabled")):
            with self.subTest(person_id=person_id, status=status):
                self.identity.person_id, self.identity.status = person_id, status
                result = self.prepare("line")()
                self.assertFalse(result.created)
                self.assertEqual(result.identity.person_id, person_id)
                self.assertEqual(result.identity.status, status)
                self.assertEqual(
                    self.scopes[-1], {"person_id": person_id, "identity_id": 9}
                )
                self.session.add.assert_not_called()

    def test_canonical_fence_precedes_all_entry_reads(self):
        for operation in ("line", "profile", "reply", "message"):
            with self.subTest(operation=operation):
                self.events.clear()
                self.session.scalar.side_effect = None
                call = self.prepare(operation, replay=operation != "message")
                answers = self.session.scalar.side_effect

                def read(_statement):
                    self.assertTrue(self.active)
                    self.assertEqual(self.events[0], "canonical")
                    self.events.append("read")
                    return next(answers) if answers is not None else self.identity

                self.session.scalar.side_effect = read
                call()
                self.assertIn("gate", self.events)
                self.assertIn("read", self.events)

    def test_new_line_identity_retains_creation_without_restore_claim(self):
        self.session.scalar.side_effect = [None, None]

        def flush():
            for call in self.session.add.call_args_list:
                if isinstance(call.args[0], module.AuthIdentityRecord):
                    call.args[0].id = 9

        self.session.flush.side_effect = flush
        result = self.repo.ensure_pending_line_identity(
            "fictional-new", "Fictional", "fictional-request"
        )
        self.assertTrue(result.created)
        self.assertEqual(result.identity.status, "pending")
        self.assertIsNone(result.identity.person_id)
        self.checked.assert_not_called()
        self.assertEqual(self.session.add.call_count, 3)

    def test_profile_gate_precedes_successful_update_and_audit(self):
        result = self.prepare("profile")()
        self.assertEqual(result.display_name, "Updated")
        self.assertEqual(self.person.version, 2)
        self.assertEqual(self.scopes, [{"person_id": 7, "identity_id": None}])
        self.session.add.assert_called_once()

    def test_profile_existing_audit_replay_is_guarded(self):
        result = self.prepare("profile", replay=True)()
        self.assertEqual(result.display_name, "Fictional")
        self.checked.assert_called_once()
        self.session.add.assert_not_called()

    def test_profile_cross_account_remains_unauthorized_before_target_lookup(self):
        with self.assertRaisesRegex(AuthorizationError, "only the Person"):
            self.repo.update_profile(19, 7, "Updated", "fictional-request")
        self.checked.assert_not_called()
        self.session.scalar.assert_not_called()

    def test_admin_profile_checks_actor_before_target_and_target_before_replay(self):
        self.session.scalar.side_effect = [self.person, None]
        self.repo._audit_exists.return_value = True

        def admin(session, actor):
            self.assertIs(session, self.session)
            self.assertEqual(actor, 19)
            self.events.append("admin")

        with (
            patch.object(self.repo, "_require_admin", side_effect=admin),
            patch.object(module, "require_management_mutation") as management,
        ):
            self.repo.update_profile(
                19, 7, "Updated", "fictional-request", admin_edit=True
            )
        management.assert_called_once_with(self.session)
        self.assertEqual(self.events, ["canonical", "admin", "gate"])
        self.assertEqual(self.scopes, [{"person_id": 7, "identity_id": None}])

    def test_applicant_message_gates_exact_current_mapping_before_thread(self):
        self.identity.person_id = 19
        result = self.prepare("message")()
        self.assertEqual(result.sender_role, "applicant")
        self.assertEqual(self.scopes, [{"person_id": 19, "identity_id": 9}])
        self.assertEqual(self.session.add.call_count, 2)
        self.assertEqual(self.thread.last_applicant_message_at, NOW)

    def test_applicant_gate_precedes_duplicate_message_check(self):
        with self.assertRaisesRegex(ConflictError, "message request already applied"):
            self.prepare("message", replay=True)()
        self.checked.assert_called_once()
        self.session.add.assert_not_called()

    def test_missing_linked_or_blocked_identity_cannot_post_as_applicant(self):
        for row in (
            None,
            SimpleNamespace(id=9, person_id=7, status="linked"),
            SimpleNamespace(id=9, person_id=None, status="blocked"),
        ):
            with self.subTest(row=row):
                self.session.scalar.return_value = row
                with self.assertRaisesRegex(
                    AuthorizationError, "open pending identity required"
                ):
                    self.repo.post_review_message(9, "Fictional", "fictional-request")
        self.checked.assert_not_called()
        self.repo._thread.assert_not_called()
        self.session.add.assert_not_called()

    def test_admin_message_keeps_existing_admin_entry_contract(self):
        self.session.scalar.return_value = self.identity
        with (
            patch.object(self.repo, "_require_admin") as admin,
            patch.object(module, "require_management_mutation") as management,
        ):
            result = self.repo.post_review_message(
                9, "Fictional", "fictional-request", actor_person_id=7
            )
        management.assert_called_once_with(self.session)
        self.assertEqual(result.sender_role, "admin")
        admin.assert_called_once_with(self.session, 7)
        self.checked.assert_called_once_with(
            self.session, person_id=None, identity_id=9
        )

    def test_game_reply_new_write_and_duplicate_are_both_guarded(self):
        self.assertFalse(self.prepare("reply", replay=True)())
        self.checked.assert_called_once()
        self.session.add.assert_not_called()
        self.assertTrue(self.prepare("reply")())
        self.assertEqual(self.checked.call_count, 2)
        self.session.add.assert_called_once()

    def test_default_off_retains_each_original_success_or_replay(self):
        self.repo.erasure_checks_enabled = False
        for operation in ("line", "profile", "message", "reply"):
            with self.subTest(operation=operation):
                self.session.scalar.side_effect = None
                self.prepare(operation)()
        self.checked.assert_not_called()

    def test_review_redaction_cleanup_is_not_denied(self):
        self.error = ErasureAccessBlocked
        self.session.scalars.return_value.all.return_value = []
        # Account-erasure denial is still not a cleanup veto; management
        # availability is independently required for this broad maintenance write.
        with patch.object(module, "require_management_mutation") as management:
            self.assertEqual(self.repo.redact_closed_reviews(now=NOW, dry_run=False), 0)
        management.assert_called_once_with(self.session)
        self.checked.assert_not_called()

    def test_guards_receive_clean_real_transaction_before_any_mutation(self):
        for operation in ("line", "profile", "message", "reply"):
            with self.subTest(operation=operation):
                session = Session()
                row = module.AuthIdentityRecord(
                    id=9,
                    provider="line",
                    provider_subject="fictional-line",
                    person_id=None,
                    status="pending",
                )
                make_transient_to_detached(row)

                def read(_statement):
                    session.add(row)
                    return row

                def deny(current, **scope):
                    self.assertIs(current, session)
                    self.assertTrue(session.in_transaction())
                    self.assertFalse(session.new or session.dirty or session.deleted)
                    raise ErasureAccessBlocked("fictional")

                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module, "require_account_not_erasing", side_effect=deny
                    ) as gate,
                    patch.object(session, "scalar", side_effect=read),
                    patch.object(
                        session, "connection", side_effect=AssertionError("NO DATABASE")
                    ),
                ):
                    with self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ):
                        self.prepare(operation)()
                gate.assert_called_once()
                self.assertFalse(session.in_transaction())


if __name__ == "__main__":
    unittest.main()
