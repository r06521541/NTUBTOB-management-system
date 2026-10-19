"""Fictional publish actor/replay and recipient eligibility regressions."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import AccountUnavailable
from shared_module.portal_data import mobile_repository as module
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
)
from sqlalchemy.exc import IntegrityError


class PublishErasureTests(unittest.TestCase):
    def test_integrity_recovery_rechecks_actor_before_saved_reply(self):
        repo = module.MobileRepository(None, erasure_checks_enabled=True)
        session = MagicMock()
        session.__enter__.return_value = session
        session.scalar.side_effect = IntegrityError(
            "fictional", {}, Exception("fictional")
        )
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(module, "acquire_admin_event_locks"),
            patch.object(module, "require_management_mutation") as management,
            patch.object(
                module,
                "require_account_not_erasing",
                side_effect=[None, ErasureAccessBlocked("fictional")],
            ) as gate,
        ):
            with self.assertRaisesRegex(
                AccountUnavailable, "^account access unavailable$"
            ):
                repo.commit_notification_publish(
                    actor_person_id=7, session_id="fictional", key_hash="a" * 64
                )
        self.assertEqual(
            [call.args for call in management.call_args_list], [(session,), (session,)]
        )
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(
            [call.kwargs for call in gate.call_args_list],
            [
                {"person_id": 7, "identity_id": None},
                {"person_id": 7, "identity_id": None},
            ],
        )
        self.assertEqual(session.scalar.call_count, 1)

    def test_publish_actor_denied_before_receipt_lookup(self):
        repo = module.MobileRepository(None, erasure_checks_enabled=True)
        session = MagicMock()
        session.__enter__.return_value = session
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(module, "acquire_admin_event_locks"),
            patch.object(module, "require_management_mutation") as management,
            patch.object(
                module,
                "require_account_not_erasing",
                side_effect=ErasureAccessBlocked("fictional"),
            ) as gate,
        ):
            with self.assertRaisesRegex(
                AccountUnavailable, "^account access unavailable$"
            ):
                repo.commit_notification_publish(actor_person_id=7)
        management.assert_called_once_with(session)
        gate.assert_called_once_with(session, person_id=7, identity_id=None)
        session.scalar.assert_not_called()

    def test_verified_recipient_excluded_requested_and_other_retained(self):
        repo = module.MobileRepository(None, erasure_checks_enabled=True)
        session = MagicMock()
        with (
            patch.object(
                repo, "_expand_notification_recipients", return_value=(3, 7, 9)
            ),
            patch.object(
                module,
                "require_account_not_erasing",
                side_effect=[None, ErasureAccessBlocked("fictional"), None],
            ) as gate,
        ):
            result = repo._eligible_notification_recipients(
                session, {}, datetime.now(timezone.utc)
            )
        self.assertEqual(result, (3, 9))
        self.assertEqual(
            [c.kwargs for c in gate.call_args_list],
            [{"person_id": 3}, {"person_id": 7}, {"person_id": 9}],
        )

    def test_unavailable_is_not_silently_dropped(self):
        repo = module.MobileRepository(None, erasure_checks_enabled=True)
        with (
            patch.object(repo, "_expand_notification_recipients", return_value=(7,)),
            patch.object(
                module,
                "require_account_not_erasing",
                side_effect=ErasureGuardUnavailable("fictional-private"),
            ),
        ):
            with self.assertRaisesRegex(
                AccountUnavailable, "^notification recipients unavailable$"
            ):
                repo._eligible_notification_recipients(
                    MagicMock(), {}, datetime.now(timezone.utc)
                )

    def test_default_off_has_no_ledger_queries(self):
        repo = module.MobileRepository(None)
        with (
            patch.object(repo, "_expand_notification_recipients", return_value=(7,)),
            patch.object(module, "require_account_not_erasing") as gate,
        ):
            self.assertEqual(
                repo._eligible_notification_recipients(
                    MagicMock(), {}, datetime.now(timezone.utc)
                ),
                (7,),
            )
        gate.assert_not_called()
