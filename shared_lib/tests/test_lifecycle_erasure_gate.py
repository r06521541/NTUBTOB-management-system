"""Default-off lifecycle authority gates, no database or real identities."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_module.portal_data import identity_lifecycle as module
from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
)


class LifecycleErasureGateTests(unittest.TestCase):
    def test_opt_in_requires_boolean(self):
        for value in (1, 0, "true", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.IdentityLifecycleRepository(None, erasure_checks_enabled=value)

    def test_default_off_does_not_call_ledger(self):
        repo = module.IdentityLifecycleRepository(None)
        with patch.object(module, "require_account_not_erasing") as gate:
            repo._require_account_available(MagicMock(), person_id=7)
        gate.assert_not_called()

    def test_principal_denial_fails_closed_before_person_or_qualifications(self):
        for method, args in (
            ("resolve_line_principal", ("fictional-line",)),
            ("resolve_principal", ("google", "fictional-google")),
            ("resolve_principal_by_ids", (9, 7)),
        ):
            for error in (ErasureAccessBlocked, ErasureGuardUnavailable):
                with self.subTest(method=method, error=error):
                    repo = module.IdentityLifecycleRepository(
                        None, erasure_checks_enabled=True
                    )
                    session = MagicMock()
                    session.__enter__.return_value = session
                    row = SimpleNamespace(id=9, person_id=7, status="linked")
                    events = []
                    session.scalar.side_effect = (
                        lambda *a: events.append("identity") or row
                    )
                    session.get.side_effect = (
                        lambda *a: events.append("identity") or row
                    )

                    def deny(current, **scope):
                        self.assertIs(current, session)
                        self.assertEqual(scope, {"person_id": 7, "identity_id": 9})
                        self.assertEqual(events, ["locks", "identity"])
                        raise error("fictional-private-detail")

                    with (
                        patch.object(module, "Session", return_value=session),
                        patch.object(
                            module,
                            "acquire_admin_event_locks",
                            side_effect=lambda s: events.append("locks"),
                        ),
                        patch.object(
                            module, "require_account_not_erasing", side_effect=deny
                        ),
                    ):
                        self.assertIsNone(getattr(repo, method)(*args))
                    self.assertEqual(events, ["locks", "identity"])
                    session.scalars.assert_not_called()
                    session.add.assert_not_called()

    def test_admin_denial_precedes_authority_query(self):
        repo = module.IdentityLifecycleRepository(None, erasure_checks_enabled=True)
        session = MagicMock()
        with (
            patch.object(
                module,
                "require_account_not_erasing",
                side_effect=ErasureAccessBlocked("fictional-private"),
            ),
            patch.object(module, "acquire_admin_event_locks"),
            patch.object(repo, "_authority_mode_matches_in_session") as mode,
        ):
            with self.assertRaisesRegex(
                AuthorizationError, "^account access unavailable$"
            ):
                repo._require_admin(session, 7)
        mode.assert_not_called()
        session.scalar.assert_not_called()
