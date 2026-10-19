"""Default-off Portal actor and attendance gates; no database."""

import unittest
from unittest.mock import MagicMock, patch

from shared_module.portal_data import repository as module
from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
)


class PortalErasureGateTests(unittest.TestCase):
    def test_recipient_filter_excludes_blocked_but_unavailable_fails_closed(self):
        repo = module.PostgresTeamPortalRepository(None, erasure_checks_enabled=True)
        session = MagicMock()

        def guard(_session, *, person_id):
            if person_id == 7:
                raise ErasureAccessBlocked("fixed")

        with patch.object(module, "require_account_not_erasing", side_effect=guard):
            self.assertEqual(repo._erasure_eligible_people(session, {7, 8}), {8})
        with patch.object(
            module,
            "require_account_not_erasing",
            side_effect=ErasureGuardUnavailable("private"),
        ):
            with self.assertRaisesRegex(
                AuthorizationError, "^account access unavailable$"
            ):
                repo._erasure_eligible_people(session, {7, 8})
        repo.erasure_checks_enabled = False
        with patch.object(module, "require_account_not_erasing") as guard:
            self.assertEqual(repo._erasure_eligible_people(session, {7, 8}), {7, 8})
        guard.assert_not_called()

    def test_pending_identity_mutations_gate_before_loading_target(self):
        for method in ("approve_identity", "block_identity"):
            repo = module.PostgresTeamPortalRepository(
                None, erasure_checks_enabled=True
            )
            session = MagicMock()
            session.__enter__.return_value = session
            with (
                patch.object(module, "Session", return_value=session),
                patch.object(module, "acquire_admin_event_locks"),
                patch.object(module, "require_management_mutation") as management,
                patch.object(repo, "_require_admin"),
                patch.object(
                    module,
                    "require_account_not_erasing",
                    side_effect=ErasureAccessBlocked("fixed"),
                ) as guard,
                self.assertRaisesRegex(
                    AuthorizationError, "^account access unavailable$"
                ),
            ):
                getattr(repo, method)(3, 7, "fictional", "fictional-request")
            management.assert_called_once_with(session)
            guard.assert_called_once_with(session, identity_id=7)
            session.scalar.assert_not_called()
            session.add.assert_not_called()

    def test_target_mutations_deny_after_actor_before_target_rows(self):
        for name, args in (
            (
                "change_access",
                (3, 7, "officer", "fictional reason", "fictional-request"),
            ),
            (
                "change_status",
                (3, 7, "disabled", "fictional reason", "fictional-request"),
            ),
            ("grant_qualification", (7, "staff")),
            ("revoke_qualification", (7, "staff")),
        ):
            with self.subTest(name=name):
                repo = module.PostgresTeamPortalRepository(
                    None, erasure_checks_enabled=True
                )
                session = MagicMock()
                session.__enter__.return_value = session
                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(module, "require_management_mutation") as management,
                    patch.object(repo, "_require_admin"),
                    patch.object(
                        module,
                        "require_account_not_erasing",
                        side_effect=ErasureAccessBlocked("fictional"),
                    ) as guard,
                ):
                    with self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ):
                        getattr(repo, name)(*args)
                management.assert_called_once_with(session)
                guard.assert_called_once_with(session, person_id=7)
                session.scalar.assert_not_called()
                session.add.assert_not_called()

    def test_strict_boolean_and_default_off(self):
        for value in (None, 1, "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.PostgresTeamPortalRepository(None, erasure_checks_enabled=value)
        repo = module.PostgresTeamPortalRepository(None)
        with patch.object(module, "require_account_not_erasing") as guard:
            repo._require_account_available(MagicMock(), 7)
        guard.assert_not_called()

    def test_actor_gates_deny_before_authority_rows(self):
        for name in (
            "_require_admin",
            "_require_event_manager",
            "_require_guest_manager",
        ):
            for error in (ErasureAccessBlocked, ErasureGuardUnavailable):
                with self.subTest(name=name, error=error):
                    repo = module.PostgresTeamPortalRepository(
                        None, erasure_checks_enabled=True
                    )
                    session = MagicMock()
                    events = []
                    with (
                        patch.object(
                            module,
                            "acquire_admin_event_locks",
                            side_effect=lambda s: events.append("locks"),
                        ),
                        patch.object(
                            module,
                            "require_account_not_erasing",
                            side_effect=error("fictional-private"),
                        ) as guard,
                    ):
                        with self.assertRaisesRegex(
                            AuthorizationError, "^account access unavailable$"
                        ):
                            getattr(repo, name)(session, 7)
                    self.assertEqual(events, ["locks"])
                    guard.assert_called_once_with(session, person_id=7)
                    session.scalar.assert_not_called()

    def test_attendance_denied_before_reads_and_writes(self):
        for name, args in (
            ("event_attendance", (7, 9)),
            ("reply_to_event_attendance", (7, 9, "attending", True)),
            ("reply_to_activity_attendance", (7, 9, 11, "attending")),
        ):
            with self.subTest(name=name):
                repo = module.PostgresTeamPortalRepository(
                    None, erasure_checks_enabled=True
                )
                session = MagicMock()
                session.__enter__.return_value = session
                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module,
                        "require_account_not_erasing",
                        side_effect=ErasureAccessBlocked("fictional"),
                    ),
                ):
                    with self.assertRaises(AuthorizationError):
                        getattr(repo, name)(*args)
                session.scalar.assert_not_called()
                session.execute.assert_not_called()
