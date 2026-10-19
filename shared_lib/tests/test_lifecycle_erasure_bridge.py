"""Erasure policy propagation through lifecycle attendance delegation."""

import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from shared_module.portal_data import identity_lifecycle as module
from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.erasure_guard import ErasureAccessBlocked
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository


class LifecycleErasureBridgeTests(unittest.TestCase):
    def test_own_reads_recheck_before_querying_in_their_own_transaction(self):
        for method, args in (
            ("scoped_games", (7,)),
            ("scoped_events", (7,)),
            ("own_attendance_reply", (7, 11)),
            ("own_attendance_reply_state", (7, 11)),
        ):
            with self.subTest(method=method):
                repo = IdentityLifecycleRepository(None, erasure_checks_enabled=True)
                session = MagicMock()
                session.__enter__.return_value = session

                def deny(current, **scope):
                    self.assertIs(current, session)
                    session.begin.assert_called_once()
                    session.get.assert_not_called()
                    session.scalar.assert_not_called()
                    session.scalars.assert_not_called()
                    self.assertEqual(scope, {"person_id": 7, "identity_id": None})
                    raise ErasureAccessBlocked("fictional")

                # scoped_events must recheck even after its earlier games read passed.
                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(
                        module, "require_account_not_erasing", side_effect=deny
                    ),
                    (
                        patch.object(repo, "scoped_games", return_value=())
                        if method == "scoped_events"
                        else nullcontext()
                    ),
                    self.assertRaisesRegex(
                        AuthorizationError, "^account access unavailable$"
                    ),
                ):
                    getattr(repo, method)(*args)

    def test_event_delegation_preserves_explicit_erasure_policy(self):
        operations = (
            ("event_attendance", (7, 11)),
            ("reply_to_event_attendance", (7, 11, "attending", True)),
            ("reply_to_activity_attendance", (7, 11, 13, "maybe")),
        )
        for enabled in (True, False):
            for method, args in operations:
                with self.subTest(enabled=enabled, method=method):
                    repo = IdentityLifecycleRepository(
                        None, erasure_checks_enabled=enabled
                    )
                    with patch(
                        "shared_module.portal_data.repository.PostgresTeamPortalRepository"
                    ) as child:
                        result = getattr(repo, method)(*args)
                        child.assert_called_once_with(
                            None, erasure_checks_enabled=enabled
                        )
                        delegated = getattr(child.return_value, method)
                        delegated.assert_called_once_with(*args, None)
                        self.assertIs(result, delegated.return_value)
