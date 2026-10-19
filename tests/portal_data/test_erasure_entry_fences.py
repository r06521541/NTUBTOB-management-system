"""Offline entry-lock contracts; no database, providers, or erasure activation."""

import ast
import inspect
import textwrap
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from shared_module.portal_data import identity_lifecycle, repository
from shared_module.portal_data.runtime import ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY

PORTAL_ENTRIES = (
    "preview_event_notification",
    "confirm_event_notification",
    "mutate_guest_qualification",
    "create_person",
    "create_pending_identity",
    "grant_qualification",
    "approve_identity",
    "block_identity",
    "change_access",
    "change_status",
    "revoke_qualification",
    "create_event",
    "update_event",
    "add_activity",
    "update_activity",
    "delete_activity",
    "move_activity",
    "cancel_event",
    "set_invitee_override",
    "publish_event",
    "reply_to_event_attendance",
    "reply_to_activity_attendance",
    "backfill_members",
)
IDENTITY_ENTRIES = (
    "ensure_pending_line_identity",
    "create_member",
    "change_access",
    "change_admin_access",
    "create_member_person",
    "approve_member",
    "bootstrap_zero_admin_member",
    "approve_non_member",
    "set_ignored",
    "remap_member_identity",
    "set_identity_status",
    "unlink_identity",
    "change_person_status",
    "update_profile",
    "grant_qualification",
    "revoke_qualification",
    "post_review_message",
    "redact_closed_reviews",
    "reply_to_game",
)
# These existing reads now own an explicit transaction for opt-in erasure guards.
# Unlike mutation entries, their default-off contract intentionally takes no lock.
IDENTITY_READ_ENTRIES = (
    "scoped_games",
    "scoped_events",
    "own_attendance_reply",
    "own_attendance_reply_state",
)
REPOSITORIES = (
    (repository, repository.PostgresTeamPortalRepository, PORTAL_ENTRIES),
    (
        identity_lifecycle,
        identity_lifecycle.IdentityLifecycleRepository,
        IDENTITY_ENTRIES,
    ),
)


class ProbeStopped(RuntimeError):
    pass


class EntryFenceTests(unittest.TestCase):
    def setUp(self):
        # These probes exercise the existing entry locks on raw Mock sessions.
        # Real management-gate locks/rejection have their own unit and PG suites.
        for module, _cls, _entries in REPOSITORIES:
            patcher = patch.object(module, "require_management_mutation")
            patcher.start()
            self.addCleanup(patcher.stop)
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.operations = []
        self.session.execute.side_effect = self.execute
        for operation in ("scalar", "scalars", "get", "add", "flush"):
            getattr(self.session, operation).side_effect = self.row_operation

    def execute(self, statement, parameters=None, *args, **kwargs):
        if str(statement) == "SELECT pg_advisory_xact_lock(:key)":
            self.operations.append(parameters["key"])
            if len(self.operations) == 2:
                raise ProbeStopped()
            return None
        self.row_operation()

    def row_operation(self, *args, **kwargs):
        self.operations.append("row operation")
        raise ProbeStopped()

    @staticmethod
    def arguments(method):
        values = {
            "actor_id": 1,
            "actor_person_id": 1,
            "target_id": 2,
            "target_person_id": 1,
            "person_id": 1,
            "identity_id": 3,
            "member_id": 4,
            "target_member_id": 5,
            "event_id": 6,
            "activity_id": 7,
            "game_id": 8,
            "provider": "line",
            "subject": "fictional-subject",
            "nickname": "Fictional applicant",
            "name": "Fictional member",
            "display_name": "Fictional person",
            "title": "Fictional event",
            "body": "Fictional review message",
            "reason": "Fictional test reason",
            "request_id": "fictional-entry-fence",
            "access_level": "basic",
            "status": "blocked",
            "ignored": True,
            "qualification": "affiliate",
            "eligibility": ("affiliate",),
            "event_type": "social",
            "activity_type": "gathering",
            "start_at": datetime(2030, 1, 1, tzinfo=timezone.utc),
            "end_at": None,
            "expected_version": 1,
            "notification_type": "event_published",
            "preview_revision": "a" * 64,
            "typed_confirmation": "Fictional event",
            "action": (
                "revoke"
                if method.__name__ == "mutate_guest_qualification"
                else "include"
            ),
            "participation_category": "affiliate",
            "direction": "up",
            "reply": 1 if method.__name__ == "reply_to_game" else "attending",
            "apply_all": False,
        }
        return {
            name: values[name]
            for name, parameter in inspect.signature(method).parameters.items()
            if parameter.default is inspect.Parameter.empty
        }

    def test_transaction_entry_inventory_is_explicit(self):
        for _module, cls, entries in REPOSITORIES:
            with self.subTest(repository=cls.__name__):
                found = []
                for name, function in vars(cls).items():
                    if not inspect.isfunction(function):
                        continue
                    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
                    if any(
                        isinstance(node, ast.With)
                        and any(
                            isinstance(item.context_expr, ast.Call)
                            and isinstance(item.context_expr.func, ast.Attribute)
                            and item.context_expr.func.attr == "begin"
                            for item in node.items
                        )
                        for node in ast.walk(tree)
                    ):
                        found.append(name)
                expected = entries + (
                    IDENTITY_READ_ENTRIES
                    if cls is identity_lifecycle.IdentityLifecycleRepository
                    else ()
                )
                self.assertEqual(tuple(found), expected)

    def test_every_transaction_takes_canonical_locks_before_rows(self):
        for module, cls, entries in REPOSITORIES:
            for name in entries:
                with self.subTest(repository=cls.__name__, entry=name):
                    self.operations.clear()
                    method = getattr(cls(object()), name)
                    with patch.object(module, "Session", return_value=self.session):
                        with self.assertRaises(ProbeStopped):
                            method(**self.arguments(method))
                    self.assertEqual(
                        self.operations, [ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY]
                    )
        self.session.add.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()

    def test_admin_review_message_is_fenced_before_identity_lock(self):
        with patch.object(identity_lifecycle, "Session", return_value=self.session):
            with self.assertRaises(ProbeStopped):
                identity_lifecycle.IdentityLifecycleRepository(
                    object()
                ).post_review_message(
                    3, "Fictional message", "fictional-admin-message", actor_person_id=1
                )
        self.assertEqual(self.operations, [ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY])

    def test_ignored_test_boundary_remains_before_lock_acquisition(self):
        boundary = MagicMock(side_effect=lambda: self.assertEqual(self.operations, []))
        with patch.object(identity_lifecycle, "Session", return_value=self.session):
            with self.assertRaises(ProbeStopped):
                identity_lifecycle.IdentityLifecycleRepository(object()).set_ignored(
                    1,
                    3,
                    True,
                    "Fictional reason",
                    "fictional-ignore",
                    lock_boundary=boundary,
                )
        boundary.assert_called_once()
        self.assertEqual(self.operations, [ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY])

    def test_failed_first_lock_does_not_touch_rows(self):
        self.session.execute.side_effect = RuntimeError("fictional lock unavailable")
        for module, cls, entries in REPOSITORIES:
            for name in entries:
                with self.subTest(repository=cls.__name__, entry=name):
                    method = getattr(cls(object()), name)
                    with patch.object(module, "Session", return_value=self.session):
                        with self.assertRaisesRegex(RuntimeError, "lock unavailable"):
                            method(**self.arguments(method))
        self.session.scalar.assert_not_called()
        self.session.scalars.assert_not_called()
        self.session.get.assert_not_called()
        self.session.add.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()

    def test_failed_second_lock_exits_transaction_without_touching_rows(self):
        for module, cls, entries in REPOSITORIES:
            for name in entries:
                with self.subTest(repository=cls.__name__, entry=name):
                    failure = RuntimeError("fictional event lock unavailable")
                    self.session.execute.side_effect = [None, failure]
                    method = getattr(cls(object()), name)
                    with patch.object(module, "Session", return_value=self.session):
                        with self.assertRaisesRegex(RuntimeError, "lock unavailable"):
                            method(**self.arguments(method))
                    self.assertIs(
                        self.session.begin.return_value.__exit__.call_args.args[1],
                        failure,
                    )
        self.session.scalar.assert_not_called()
        self.session.scalars.assert_not_called()
        self.session.get.assert_not_called()
        self.session.add.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()
