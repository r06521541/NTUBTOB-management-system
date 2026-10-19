"""Fictional transaction ordering probes; no database or provider calls."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import AuthenticationError
from shared_module.portal_data import mobile_repository as module
from shared_module.portal_data.runtime import ADMIN_LOCK_KEY, EVENT_SNAPSHOT_LOCK_KEY


class MobileLockOrderTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.calls = []
        self.session.execute.side_effect = lambda *args: self.calls.append(
            ("lock", args[1]["key"])
        )
        self.session.scalar.side_effect = lambda *args: self.calls.append("row")
        self.session.add.side_effect = lambda *args: self.calls.append("add")
        self.session.flush.side_effect = lambda: self.calls.append("flush")
        self.repository = module.MobileRepository(object())
        self.now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        self.session_patch = patch.object(module, "Session", return_value=self.session)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    def assert_fence_first(self):
        self.assertEqual(
            self.calls[:2],
            [("lock", ADMIN_LOCK_KEY), ("lock", EVENT_SNAPSHOT_LOCK_KEY)],
        )
        self.session.commit.assert_not_called()

    def test_refresh_fences_before_token_lookup_even_for_invalid_token(self):
        with self.assertRaises(AuthenticationError):
            self.repository.rotate(now=self.now, refresh_hash="fictional")
        self.assert_fence_first()
        self.assertEqual(self.calls[2:], ["row"])

    def test_logout_fences_before_device_lookup_without_business_deny(self):
        self.repository.logout("fictional-session", self.now)
        self.assert_fence_first()
        self.assertEqual(self.calls[2:], ["row"])

    def test_apple_receipt_fences_before_write_and_identity_lock(self):
        for event_type in ("consent-revoked", "email-enabled"):
            with self.subTest(event_type=event_type):
                self.calls.clear()
                with patch.object(
                    self.repository,
                    "_single_revision",
                    return_value="0010_apple_provider_lifecycle",
                ):
                    self.repository.apply_apple_notification(
                        jti_hash="fictional-jti",
                        event_type=event_type,
                        subject="fictional-subject",
                        event_at=self.now,
                        now=self.now,
                    )
                self.assert_fence_first()
                self.assertEqual(self.calls[2:5], ["add", "flush", "row"])
