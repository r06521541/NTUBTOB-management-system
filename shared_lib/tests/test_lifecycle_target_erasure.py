"""Admin target fences with fictional records and no database connection."""

import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
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
OPERATIONS = (
    "access",
    "admin_access",
    "member",
    "non_member",
    "ignore",
    "remap",
    "identity_status",
    "unlink",
    "person_status",
    "grant",
    "revoke",
    "message",
)


class LifecycleTargetErasureTests(unittest.TestCase):
    @contextmanager
    def scenario(self, operation, *, replay=False, enabled=True, deny=None):
        repo = module.IdentityLifecycleRepository(None, erasure_checks_enabled=enabled)
        session = MagicMock()
        session.__enter__.return_value = session
        events, scopes = [], []
        active = [False]
        identity = SimpleNamespace(
            id=9,
            provider="line",
            provider_subject="fictional-line",
            status="linked",
            person_id=19,
            updated_at=NOW,
        )
        person = SimpleNamespace(
            id=19,
            portal_status="active",
            portal_access_level="basic",
            version=1,
            display_name="Fictional",
            formal_name=None,
            updated_at=NOW,
        )
        member = SimpleNamespace(id=41, person_id=19, name="Fictional Member")
        legacy = SimpleNamespace(member_id=41, ignored=False)
        qualification = SimpleNamespace(
            status="active", reason="Fictional", updated_at=NOW
        )
        thread = SimpleNamespace(
            id=12,
            status="open",
            closed_at=None,
            redacted_at=None,
            last_applicant_message_at=None,
            updated_at=NOW,
        )
        old_person = SimpleNamespace(
            id=7, portal_status="active", portal_access_level="admin"
        )
        audit = SimpleNamespace(
            action="access_changed",
            actor_person_id=1,
            target_person_id=19,
            reason="Fictional reason",
            auth_identity_id=9,
            after_state={
                "access_level": "admin",
                "expected_version": 1,
                "resulting_version": 2,
            },
        )
        if operation in {"member", "non_member", "ignore", "message"}:
            identity.status, identity.person_id = "pending", None
            legacy.member_id = None
        if operation == "member":
            qualification = None
            audit.action, audit.after_state = "identity_linked", {
                "status": "linked",
                "member_id": 41,
            }
            if replay:
                identity.status, identity.person_id = "linked", 19
        if operation == "remap":
            identity.person_id = 19 if replay else 7
        if operation == "admin_access" and replay:
            person.portal_access_level, person.version = "admin", 2
        if operation == "ignore" and replay:
            legacy.ignored = True
        if operation == "identity_status" and replay:
            identity.status = "disabled"
        if operation == "grant" and not replay:
            qualification = None
        original_identity = vars(identity).copy()
        original_person = vars(person).copy()
        original_legacy = vars(legacy).copy()

        @contextmanager
        def transaction():
            active[0] = True
            try:
                yield
            finally:
                active[0] = False

        def locks(current):
            self.assertIs(current, session)
            self.assertTrue(active[0])
            events.append("canonical")

        def management_available(current):
            self.assertIs(current, session)
            self.assertTrue(active[0])
            session.add.assert_not_called()
            session.flush.assert_not_called()

        def gate(current, **scope):
            self.assertIs(current, session)
            self.assertTrue(active[0])
            self.assertEqual(events[0], "canonical")
            session.add.assert_not_called()
            session.flush.assert_not_called()
            self.assertEqual(vars(identity), original_identity)
            self.assertEqual(vars(person), original_person)
            self.assertEqual(vars(legacy), original_legacy)
            scopes.append(scope)
            events.append("gate")
            if deny is not None:
                raise deny("fictional-sensitive-detail")

        def scalar(statement):
            self.assertTrue(active[0])
            self.assertEqual(events[0], "canonical")
            events.append("read")
            if "count(" in str(statement):
                return 1
            entity = statement.column_descriptions[0]["entity"]
            return {
                module.AuthIdentityRecord: identity,
                module.PersonRecord: person,
                module.LegacyMemberRecord: member,
                module.LegacyLineUserRecord: legacy,
                module.PersonQualificationRecord: qualification,
                module.AccessAuditRecord: audit if replay else None,
            }[entity]

        def flush():
            for call in session.add.call_args_list:
                row = call.args[0]
                if isinstance(row, module.PersonRecord):
                    row.id = 29

        session.begin.side_effect = transaction
        session.scalar.side_effect = scalar
        session.get.side_effect = lambda model, key: (
            identity if model is module.AuthIdentityRecord else old_person
        )
        session.flush.side_effect = flush
        repo._require_admin = Mock(side_effect=lambda *args: events.append("admin"))
        repo._audit_exists = Mock(
            side_effect=lambda *args: events.append("audit") or replay
        )
        repo._assert_reachable_admin_remains = Mock()
        repo._thread = Mock(return_value=thread)
        repo.resolve_principal_by_ids = Mock(return_value="fictional-principal")
        repo.resolve_line_principal = Mock(return_value="fictional-principal")
        reason, request_id = "Fictional reason", "fictional-request"
        calls = {
            "access": lambda: repo.change_access(1, 19, "officer", reason, request_id),
            "admin_access": lambda: repo.change_admin_access(
                1, 19, "admin", 1, reason, request_id
            ),
            "member": lambda: repo.approve_member(1, 9, 41, reason, request_id),
            "non_member": lambda: repo.approve_non_member(
                1, 9, "Fictional", reason, request_id
            ),
            "ignore": lambda: repo.set_ignored(1, 9, True, reason, request_id),
            "remap": lambda: repo.remap_member_identity(1, 9, 41, reason, request_id),
            "identity_status": lambda: repo.set_identity_status(
                1, 9, "disabled", reason, request_id
            ),
            "unlink": lambda: repo.unlink_identity(1, 9, reason, request_id),
            "person_status": lambda: repo.change_person_status(
                1, 19, "disabled", reason, request_id
            ),
            "grant": lambda: repo.grant_qualification(
                1, 19, "staff", reason, request_id
            ),
            "revoke": lambda: repo.revoke_qualification(
                1, 19, "staff", reason, request_id
            ),
            "message": lambda: repo.post_review_message(
                9, "Fictional body", request_id, actor_person_id=1
            ),
        }
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(module, "utc_now", return_value=NOW),
            patch.object(module, "acquire_admin_event_locks", side_effect=locks),
            patch.object(
                module, "require_management_mutation", side_effect=management_available
            ) as management,
            patch.object(
                module, "require_account_not_erasing", side_effect=gate
            ) as checked,
        ):
            yield SimpleNamespace(
                repo=repo,
                session=session,
                identity=identity,
                person=person,
                member=member,
                legacy=legacy,
                qualification=qualification,
                scopes=scopes,
                events=events,
                checked=checked,
                management=management,
                call=calls[operation],
            )

    def test_all_targets_fail_closed_before_mutation_or_replay(self):
        for operation in OPERATIONS:
            for replay in (False, True):
                for error in (ErasureAccessBlocked, ErasureGuardUnavailable):
                    with (
                        self.subTest(operation=operation, replay=replay, error=error),
                        self.scenario(operation, replay=replay, deny=error) as case,
                    ):
                        with self.assertRaisesRegex(
                            AuthorizationError, "^account access unavailable$"
                        ):
                            case.call()
                        case.session.add.assert_not_called()
                        case.session.flush.assert_not_called()
                        case.repo._audit_exists.assert_not_called()
                        case.repo._thread.assert_not_called()
                        self.assertEqual(case.checked.call_count, 1)
                        case.management.assert_called_once_with(case.session)

    def test_successful_mutations_check_current_target_before_dirtying(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation), self.scenario(operation) as case:
                case.call()
                self.assertTrue(case.scopes)
                self.assertLess(
                    case.events.index("gate"),
                    (
                        case.events.index("audit")
                        if "audit" in case.events
                        else len(case.events)
                    ),
                )
                self.assertTrue(case.session.add.called)

    def test_default_off_preserves_mutation_and_successful_replays(self):
        for operation in OPERATIONS:
            with (
                self.subTest(operation=operation),
                self.scenario(operation, enabled=False) as case,
            ):
                case.call()
                case.checked.assert_not_called()
        for operation in (
            "admin_access",
            "member",
            "ignore",
            "remap",
            "identity_status",
            "grant",
        ):
            with (
                self.subTest(replay=operation),
                self.scenario(operation, replay=True, enabled=False) as case,
            ):
                case.call()
                case.checked.assert_not_called()
                case.session.add.assert_not_called()

    def test_successful_replays_still_check_targets(self):
        for operation in (
            "admin_access",
            "member",
            "ignore",
            "remap",
            "identity_status",
            "grant",
        ):
            with (
                self.subTest(operation=operation),
                self.scenario(operation, replay=True) as case,
            ):
                case.call()
                self.assertTrue(case.scopes)
                case.session.add.assert_not_called()

    def test_member_approval_checks_pending_identity_and_existing_person(self):
        with self.scenario("member") as case:
            case.call()
            self.assertEqual(
                case.scopes,
                [
                    {"person_id": None, "identity_id": 9},
                    {"person_id": 19, "identity_id": None},
                ],
            )

    def test_nonmember_only_checks_existing_identity_not_new_person(self):
        with self.scenario("non_member") as case:
            case.call()
            self.assertEqual(case.scopes, [{"person_id": None, "identity_id": 9}])
            self.assertEqual(case.identity.person_id, 29)

    def test_remap_checks_old_mapping_and_new_person_before_any_write(self):
        with self.scenario("remap") as case:
            case.call()
            self.assertEqual(
                case.scopes,
                [
                    {"person_id": 7, "identity_id": 9},
                    {"person_id": 19, "identity_id": None},
                ],
            )
            case.repo._assert_reachable_admin_remains.assert_called_once_with(
                case.session, excluding_identity_id=9
            )

    def test_second_person_gate_can_stop_approval_or_remap(self):
        for operation in ("member", "remap"):
            with self.subTest(operation=operation), self.scenario(operation) as case:
                real_gate = case.checked.side_effect

                def deny_new(current, **scope):
                    real_gate(current, **scope)
                    if scope == {"person_id": 19, "identity_id": None}:
                        raise ErasureAccessBlocked("fictional")

                case.checked.side_effect = deny_new
                with self.assertRaises(AuthorizationError):
                    case.call()
                self.assertEqual(case.checked.call_count, 2)
                case.repo._audit_exists.assert_not_called()
                case.session.add.assert_not_called()

    def test_last_admin_rejection_still_applies_after_target_gate(self):
        for operation in ("remap", "unlink", "identity_status", "person_status"):
            with self.subTest(operation=operation), self.scenario(operation) as case:
                case.person.portal_access_level = "admin"
                # This case checks authority preservation, not the fake object snapshots.
                case.checked.side_effect = None
                case.repo._assert_reachable_admin_remains.side_effect = ConflictError(
                    "last administrator"
                )
                with self.assertRaisesRegex(ConflictError, "last administrator"):
                    case.call()
                self.assertTrue(case.checked.called)
                case.session.add.assert_not_called()

    def test_admin_message_gates_identity_mapping_before_thread_or_replay(self):
        with self.scenario("message") as case:
            case.call()
            self.assertEqual(case.scopes, [{"person_id": None, "identity_id": 9}])
            self.assertLess(case.events.index("admin"), case.events.index("gate"))

    def test_admin_demotion_preserves_last_admin_check(self):
        with self.scenario("admin_access") as case:
            case.person.portal_access_level = "admin"
            case.checked.side_effect = None
            case.repo._assert_reachable_admin_remains.side_effect = ConflictError(
                "last administrator"
            )
            with self.assertRaisesRegex(ConflictError, "last administrator"):
                case.repo.change_admin_access(
                    1, 19, "basic", 1, "Fictional reason", "fictional-request"
                )
            case.checked.assert_called_once_with(
                case.session, person_id=19, identity_id=None
            )
            case.session.add.assert_not_called()

    def test_bootstrap_shared_approval_core_cannot_replay_erasing_target(self):
        with self.scenario("member", replay=True, deny=ErasureAccessBlocked) as case:
            with case.session.begin():
                with self.assertRaisesRegex(
                    AuthorizationError, "^account access unavailable$"
                ):
                    case.repo._approve_member_in_transaction(
                        case.session,
                        9,
                        41,
                        "Fictional reason",
                        "fictional-request",
                        NOW,
                        None,
                        strict_bootstrap=True,
                    )
            case.repo._audit_exists.assert_not_called()
            case.session.add.assert_not_called()

    def test_all_guards_see_clean_real_orm_session(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation), self.scenario(operation) as case:
                session = Session()
                pending = operation in {"member", "non_member", "ignore", "message"}
                identity = module.AuthIdentityRecord(
                    id=9,
                    provider="line",
                    provider_subject="fictional-line",
                    person_id=None if pending else (7 if operation == "remap" else 19),
                    status="pending" if pending else "linked",
                )
                member = module.LegacyMemberRecord(
                    id=41, person_id=19, name="Fictional"
                )
                person = module.PersonRecord(
                    id=19,
                    portal_status="active",
                    portal_access_level="basic",
                    version=1,
                    display_name="Fictional",
                )
                for row in (identity, member, person):
                    make_transient_to_detached(row)

                def read(statement):
                    row = {
                        module.AuthIdentityRecord: identity,
                        module.LegacyMemberRecord: member,
                        module.PersonRecord: person,
                    }[statement.column_descriptions[0]["entity"]]
                    session.add(row)
                    return row

                scopes = []
                expected_checks = 2 if operation in {"member", "remap"} else 1

                def clean(current, **scope):
                    self.assertIs(current, session)
                    self.assertTrue(session.in_transaction())
                    self.assertFalse(session.new or session.dirty or session.deleted)
                    scopes.append(scope)
                    if len(scopes) == expected_checks:
                        raise ErasureAccessBlocked("fictional")

                def clean_management(current):
                    self.assertIs(current, session)
                    self.assertTrue(session.in_transaction())
                    self.assertFalse(session.new or session.dirty or session.deleted)

                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module,
                        "require_management_mutation",
                        side_effect=clean_management,
                    ) as management,
                    patch.object(
                        module, "require_account_not_erasing", side_effect=clean
                    ),
                    patch.object(session, "scalar", side_effect=read),
                    patch.object(
                        session, "connection", side_effect=AssertionError("NO DATABASE")
                    ),
                ):
                    with self.assertRaises(AuthorizationError):
                        case.call()
                self.assertEqual(len(scopes), expected_checks)
                management.assert_called_once_with(session)
                self.assertFalse(session.in_transaction())


if __name__ == "__main__":
    unittest.main()
