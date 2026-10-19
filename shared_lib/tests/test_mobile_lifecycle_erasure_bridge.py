"""Mobile child lifecycle retains erasure policy and fixed public errors."""

import unittest
from unittest.mock import Mock

from shared_module.mobile_api import AccountUnavailable
from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.mobile_repository import MobileRepository


class MobileLifecycleErasureBridgeTests(unittest.TestCase):
    def test_child_receives_parent_opt_in_and_default_remains_off(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                repo = MobileRepository(None, erasure_checks_enabled=enabled)
                self.assertIs(repo.lifecycle.erasure_checks_enabled, enabled)

    def test_line_candidate_denial_translates_without_followup_or_private_detail(self):
        repo = MobileRepository(None, erasure_checks_enabled=True)
        repo.lifecycle = Mock()
        repo.lifecycle.ensure_pending_line_identity.side_effect = AuthorizationError(
            "private-sentinel"
        )
        repo.identity_link_candidate = Mock()
        with self.assertRaisesRegex(AccountUnavailable, "^account access unavailable$"):
            repo.ensure_line_link_candidate(
                "fictional", "Fictional", "fictional-request", None
            )
        repo.identity_link_candidate.assert_not_called()
