"""Fictional opt-in access fencing; no provider or database calls."""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import AccountUnavailable
from shared_module.portal_data import mobile_repository as module
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
)


class MobileErasureGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.session_patch = patch.object(module, "Session", return_value=self.session)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.gate_patch = patch.object(module, "require_account_not_erasing")
        self.gate = self.gate_patch.start()
        self.addCleanup(self.gate_patch.stop)
        self.repo = module.MobileRepository(object(), erasure_checks_enabled=True)
        self.repo.lifecycle = MagicMock()
        self.repo.lifecycle.resolve_principal.return_value = SimpleNamespace(
            identity=SimpleNamespace(id=11), person=SimpleNamespace(id=7)
        )

    def block(self, error=ErasureAccessBlocked):
        self.gate.side_effect = error("fictional-sensitive-diagnostic")

    def assert_no_write(self):
        self.session.add.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()

    def test_default_is_off_and_constructor_rejects_non_boolean(self):
        repo = module.MobileRepository(object())
        repo._require_account_available(self.session, person_id=7, identity_id=11)
        self.gate.assert_not_called()
        for value in (1, "true", None):
            with self.assertRaises(ValueError):
                module.MobileRepository(object(), erasure_checks_enabled=value)

    def test_exchange_blocks_before_apple_code_or_session_rows(self):
        self.block()
        with self.assertRaises(AccountUnavailable) as raised:
            self.repo.exchange(
                provider="apple",
                subject="fake",
                now=self.now,
                installation_id_hash="fake",
                platform="ios",
            )
        self.gate.assert_called_once_with(self.session, person_id=7, identity_id=11)
        self.session.scalar.assert_not_called()
        self.assertNotIn("fictional-sensitive", str(raised.exception))
        self.assert_no_write()

    def test_pending_exchange_cannot_bypass_gate(self):
        self.repo.lifecycle.resolve_principal.return_value = None
        self.session.scalar.return_value = SimpleNamespace(
            id=11, person_id=None, status="pending"
        )
        self.block()
        with self.assertRaises(AccountUnavailable):
            self.repo.exchange(provider="apple", subject="fake", now=self.now)
        self.gate.assert_called_once_with(self.session, person_id=None, identity_id=11)
        self.assert_no_write()

    def test_access_token_resolution_is_blocked_before_lifecycle_lookup(self):
        self.session.get.return_value = SimpleNamespace(
            id="fake",
            status="active",
            person_id=7,
            auth_identity_id=11,
            access_epoch=1,
            refresh_family_expires_at=self.now.replace(year=2027),
        )
        self.block()
        with self.assertRaises(AccountUnavailable):
            self.repo.principal("fake", 7, 11, 1, self.now)
        self.repo.lifecycle.resolve_principal_by_ids.assert_not_called()
        self.assert_no_write()

    def test_refresh_blocks_before_token_row_lock_and_saved_successor_replay(self):
        self.session.execute.return_value.first.return_value = (11, 7)
        self.block()
        with self.assertRaises(AccountUnavailable):
            self.repo.rotate(now=self.now, refresh_hash="fake")
        self.gate.assert_called_once_with(self.session, person_id=7, identity_id=11)
        self.session.scalar.assert_not_called()
        self.assert_no_write()

    def test_link_blocks_proof_account_before_identity_row_locks(self):
        self.block()
        with self.assertRaises(AccountUnavailable):
            self.repo.confirm_identity_link(
                candidate=SimpleNamespace(jti="fake", identity_id=12),
                proof=SimpleNamespace(identity_id=11, person_id=7),
                codec=MagicMock(),
                now=self.now,
            )
        self.gate.assert_called_once_with(self.session, person_id=7, identity_id=11)
        self.session.scalar.assert_not_called()
        self.assert_no_write()

    def test_unavailable_gate_does_not_fall_back_to_allow(self):
        self.block(ErasureGuardUnavailable)
        with self.assertRaisesRegex(AccountUnavailable, "account access unavailable"):
            self.repo._require_account_available(self.session, person_id=7)

    def test_logout_cleanup_does_not_call_business_gate(self):
        self.session.scalar.return_value = None
        self.block()
        self.repo.logout("fake", self.now)
        self.gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
