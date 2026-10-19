"""Management-only transaction-entry fences; fictional ports, no database.

Each patch is scoped to one named caller test. These probes do not replace the
real gate/ACL/integration suites or claim independent-transaction race evidence.
"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import AccountUnavailable
from shared_module.portal_data import identity_lifecycle as lifecycle
from shared_module.portal_data import mobile_repository as mobile
from shared_module.portal_data import repository as portal
from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.erasure_management_guard import (
    ManagementGuardUnavailable,
    ManagementWritesSuspended,
)
from sqlalchemy.exc import IntegrityError

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
REASON = "Fictional management operation"
REQUEST = "fictional-management-request"

LIFECYCLE_WRITES = (
    ("create_member", (1, "Fictional member", "Fictional", REASON, REQUEST), {}),
    ("change_access", (1, 2, "officer", REASON, REQUEST), {}),
    ("change_admin_access", (1, 2, "admin", 1, REASON, REQUEST), {}),
    ("create_member_person", (1, 2, "Fictional", REASON, REQUEST), {}),
    ("approve_member", (1, 2, 3, REASON, REQUEST), {}),
    ("approve_non_member", (1, 2, "Fictional", REASON, REQUEST), {}),
    ("set_ignored", (1, 2, True, REASON, REQUEST), {}),
    ("remap_member_identity", (1, 2, 3, REASON, REQUEST), {}),
    ("set_identity_status", (1, 2, "disabled", REASON, REQUEST), {}),
    ("unlink_identity", (1, 2, REASON, REQUEST), {}),
    ("change_person_status", (1, 2, "disabled", REASON, REQUEST), {}),
    ("grant_qualification", (1, 2, "staff", REASON, REQUEST), {}),
    ("revoke_qualification", (1, 2, "staff", REASON, REQUEST), {}),
    ("bootstrap_zero_admin_member", (2, 3, REASON, REQUEST), {}),
    ("update_profile", (1, 2, "Fictional", REQUEST), {"admin_edit": True}),
    ("post_review_message", (2, "Fictional review", REQUEST), {"actor_person_id": 1}),
    ("redact_closed_reviews", (), {"now": NOW, "dry_run": False}),
)
PORTAL_WRITES = (
    ("create_person", ("Fictional",), {}),
    ("grant_qualification", (2, "staff"), {}),
    ("revoke_qualification", (2, "staff"), {}),
    ("approve_identity", (1, 2, REASON, REQUEST), {"person_id": 3}),
    ("block_identity", (1, 2, REASON, REQUEST), {}),
    ("change_access", (1, 2, "officer", REASON, REQUEST), {}),
    ("change_status", (1, 2, "disabled", REASON, REQUEST), {}),
    ("create_event", (1, "Fictional", "game", NOW, ("staff",)), {}),
    (
        "update_event",
        (1, 2, "Fictional", "game", NOW, None, ("staff",), 1, REQUEST),
        {},
    ),
    ("add_activity", (1, 2, "Fictional", "meal", NOW, None), {}),
    ("update_activity", (1, 2, 3, "Fictional", "meal", NOW, None, REQUEST), {}),
    ("delete_activity", (1, 2, 3), {}),
    ("move_activity", (1, 2, 3, "up"), {}),
    ("cancel_event", (1, 2, REQUEST), {}),
    ("set_invitee_override", (1, 2, 3, "include", "staff", REASON, REQUEST), {}),
    ("publish_event", (1, 2, REQUEST), {}),
    (
        "confirm_event_notification",
        (1, 2),
        dict(
            notification_type="event_published",
            preview_revision="a" * 64,
            typed_confirmation="Fictional",
            request_id=REQUEST,
        ),
    ),
    (
        "mutate_guest_qualification",
        (1, 2, "revoke"),
        dict(expected_version=1, reason=REASON, request_id=REQUEST),
    ),
    ("backfill_members", (), {}),
)


class RowReached(RuntimeError):
    """A test sentinel: an unguarded row/ORM operation was reached."""


def session_probe():
    session = MagicMock()
    session.__enter__.return_value = session
    for name in (
        "scalar",
        "scalars",
        "execute",
        "get",
        "add",
        "add_all",
        "flush",
        "delete",
    ):
        getattr(session, name).side_effect = RowReached(name)
    return session


class ManagementSuspensionCallerTests(unittest.TestCase):
    def assert_blocked(self, module, repo, case, exception=AuthorizationError):
        method, args, kwargs = case
        for error_type in (ManagementWritesSuspended, ManagementGuardUnavailable):
            with self.subTest(method=method, error=error_type.__name__):
                session = session_probe()

                def deny(current):
                    self.assertIs(current, session)
                    session.begin.return_value.__enter__.assert_called_once()
                    for name in (
                        "scalar",
                        "scalars",
                        "execute",
                        "get",
                        "add",
                        "add_all",
                        "flush",
                        "delete",
                    ):
                        getattr(session, name).assert_not_called()
                    raise error_type("fictional-private-detail")

                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module,
                        "require_management_mutation",
                        create=True,
                        side_effect=deny,
                    ) as gate,
                    self.assertRaisesRegex(
                        exception, "^management writes unavailable$"
                    ) as caught,
                ):
                    getattr(repo, method)(*args, **kwargs)
                gate.assert_called_once_with(session)
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)
                for name in (
                    "scalar",
                    "scalars",
                    "execute",
                    "get",
                    "add",
                    "add_all",
                    "flush",
                    "delete",
                ):
                    getattr(session, name).assert_not_called()

    def test_regression_default_off_create_person_is_not_suspension_permission(self):
        self.assert_blocked(
            portal, portal.PostgresTeamPortalRepository(None), PORTAL_WRITES[0]
        )

    def test_every_lifecycle_management_entry_precedes_rows_with_either_legacy_flag(
        self,
    ):
        for enabled in (False, True):
            repo = lifecycle.IdentityLifecycleRepository(
                None, erasure_checks_enabled=enabled
            )
            for case in LIFECYCLE_WRITES:
                with self.subTest(erasure_checks_enabled=enabled):
                    self.assert_blocked(lifecycle, repo, case)

    def test_every_portal_management_entry_precedes_rows_with_either_legacy_flag(self):
        for enabled in (False, True):
            repo = portal.PostgresTeamPortalRepository(
                None, erasure_checks_enabled=enabled
            )
            for case in PORTAL_WRITES:
                with self.subTest(erasure_checks_enabled=enabled):
                    self.assert_blocked(portal, repo, case)

    def test_mobile_publish_and_retry_are_guarded_before_rows_or_adapter(self):
        for enabled in (False, True):
            repo = mobile.MobileRepository(None, erasure_checks_enabled=enabled)
            adapter = MagicMock()
            for case in (
                (
                    "commit_notification_publish",
                    (),
                    dict(
                        actor_person_id=1,
                        session_id="fictional",
                        key_hash="a" * 64,
                        request_hash="b" * 64,
                    ),
                ),
                (
                    "attempt_rejecting_delivery",
                    (),
                    dict(delivery_id=2, adapter=adapter, now=NOW),
                ),
            ):
                self.assert_blocked(mobile, repo, case, AccountUnavailable)
            adapter.deliver.assert_not_called()

    def test_publish_integrity_replay_rechecks_new_transaction_before_saved_reply(self):
        repo = mobile.MobileRepository(None)
        first, second = session_probe(), session_probe()
        first.scalar.side_effect = IntegrityError(
            "fictional", {}, Exception("fictional")
        )
        with (
            patch.object(mobile, "Session", side_effect=[first, second]),
            patch.object(mobile, "acquire_admin_event_locks"),
            patch.object(
                mobile,
                "require_management_mutation",
                create=True,
                side_effect=[None, ManagementWritesSuspended("private")],
            ) as gate,
            self.assertRaisesRegex(
                AccountUnavailable, "^management writes unavailable$"
            ),
        ):
            repo.commit_notification_publish(
                actor_person_id=1, session_id="fictional", key_hash="a" * 64
            )
        self.assertEqual(
            [call.args[0] for call in gate.call_args_list], [first, second]
        )
        first.scalar.assert_called_once()
        second.scalar.assert_not_called()

    def test_legacy_race_hook_stays_before_management_locks(self):
        session = session_probe()
        events = []

        def deny(current):
            self.assertIs(current, session)
            events.append("management")
            raise ManagementWritesSuspended("private")

        with (
            patch.object(lifecycle, "Session", return_value=session),
            patch.object(lifecycle, "acquire_admin_event_locks"),
            patch.object(
                lifecycle, "require_management_mutation", create=True, side_effect=deny
            ),
            self.assertRaisesRegex(
                AuthorizationError, "^management writes unavailable$"
            ),
        ):
            lifecycle.IdentityLifecycleRepository(None).set_ignored(
                1,
                2,
                True,
                REASON,
                REQUEST,
                lock_boundary=lambda: events.append("pre-lock-hook"),
            )
        self.assertEqual(events, ["pre-lock-hook", "management"])

    def test_successful_gate_does_not_replace_existing_actor_authorization(self):
        for module, repo, method, args, checker in (
            (
                lifecycle,
                lifecycle.IdentityLifecycleRepository(None),
                "change_access",
                (1, 2, "officer", REASON, REQUEST),
                "_require_admin",
            ),
            (
                portal,
                portal.PostgresTeamPortalRepository(None),
                "create_event",
                (1, "Fictional", "game", NOW, ("staff",)),
                "_require_event_manager",
            ),
        ):
            with self.subTest(module=module.__name__):
                session = session_probe()
                order = []

                def denied_actor(*args, **kwargs):
                    order.append("actor")
                    raise AuthorizationError("existing actor denied")

                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module,
                        "require_management_mutation",
                        create=True,
                        side_effect=lambda current: order.append("management"),
                    ),
                    patch.object(repo, checker, side_effect=denied_actor),
                    self.assertRaisesRegex(
                        AuthorizationError, "^existing actor denied$"
                    ),
                ):
                    getattr(repo, method)(*args)
                self.assertEqual(order, ["management", "actor"])

    def test_allowed_mobile_replay_retains_existing_payload(self):
        repo = mobile.MobileRepository(None)
        session = session_probe()
        session.scalar.side_effect = None
        session.scalar.return_value = SimpleNamespace(
            request_hash="b" * 64,
            state="completed",
            response_body={"notification_id": 8},
        )
        with (
            patch.object(mobile, "Session", return_value=session),
            patch.object(mobile, "require_management_mutation", create=True) as gate,
        ):
            result = repo.commit_notification_publish(
                actor_person_id=1,
                session_id="fictional",
                key_hash="a" * 64,
                request_hash="b" * 64,
            )
        self.assertEqual(result, {"notification_id": 8, "idempotent_replay": True})
        gate.assert_called_once_with(session)
        session.add.assert_not_called()

    def test_mixed_selfservice_read_and_cleanup_paths_do_not_use_management_gate(self):
        cases = (
            (
                lifecycle,
                lifecycle.IdentityLifecycleRepository(None),
                "update_profile",
                (1, 1, "Fictional", REQUEST),
                {},
            ),
            (
                lifecycle,
                lifecycle.IdentityLifecycleRepository(None),
                "post_review_message",
                (2, "Fictional", REQUEST),
                {},
            ),
            (
                lifecycle,
                lifecycle.IdentityLifecycleRepository(None),
                "review_messages",
                (2,),
                {},
            ),
            (
                lifecycle,
                lifecycle.IdentityLifecycleRepository(None),
                "redact_closed_reviews",
                (),
                {"dry_run": True},
            ),
            (
                portal,
                portal.PostgresTeamPortalRepository(None),
                "managed_events",
                (1,),
                {},
            ),
            (
                portal,
                portal.PostgresTeamPortalRepository(None),
                "reply_to_event_attendance",
                (1, 2, "attending", False),
                {},
            ),
            (
                mobile,
                mobile.MobileRepository(None),
                "notification_unread_count",
                (1, NOW),
                {},
            ),
            (mobile, mobile.MobileRepository(None), "logout", ("fictional", NOW), {}),
        )
        for module, repo, method, args, kwargs in cases:
            with self.subTest(module=module.__name__, method=method):
                session = session_probe()
                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module,
                        "require_management_mutation",
                        create=True,
                        side_effect=ManagementWritesSuspended("private"),
                    ) as gate,
                    self.assertRaises(RowReached),
                ):
                    getattr(repo, method)(*args, **kwargs)
                gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
