"""Provider-labeled admin onboarding with the existing authorization harness."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import test_admin_security as admin_fixture

from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.models import AuthIdentityRecord


class AppleAdminOnboardingRoutesTests(unittest.TestCase):
    setUpClass = classmethod(admin_fixture.MemberMatchingRouteTest.setUpClass.__func__)
    tearDownClass = classmethod(
        admin_fixture.MemberMatchingRouteTest.tearDownClass.__func__
    )
    _module = staticmethod(admin_fixture.MemberMatchingRouteTest._module)
    login = admin_fixture.MemberMatchingRouteTest.login
    get_csrf_token = admin_fixture.MemberMatchingRouteTest.get_csrf_token

    def setUp(self):
        admin_fixture.MemberMatchingRouteTest.setUp(self)
        self.token = self.get_csrf_token()
        with self.client.session_transaction() as values:
            values.update(person_id=70, auth_identity_id=71)
        self.repository = MagicMock()
        self.repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        self.repository.admin_dashboard.return_value = {
            "people": (
                {
                    "person_id": 80,
                    "display_name": "Fictional Member",
                    "formal_name": None,
                    "member_id": 8,
                    "status": "active",
                },
            ),
            "identities": (
                {
                    "identity_id": 81,
                    "provider": "apple",
                    "nickname": "Fictional Applicant",
                    "identity_status": "pending",
                    "person_id": None,
                    "ignored": False,
                    "review_status": "open",
                },
            ),
            "audit": (),
        }
        patcher = patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(
            self.app_module, "phase_c_repository", return_value=self.repository
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, action, **values):
        return self.client.post(
            "/identity-admin/action",
            data={
                "csrf_token": self.token,
                "identity_id": "81",
                "action": action,
                "reason": "Verified applicant",
                "request_id": "identity-apple-fictional",
                **values,
            },
        )

    def test_pending_apple_card_identifies_provider_without_line_only_actions(self):
        response = self.client.get("/manage/pending-identities")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Apple 身分", body)
        self.assertIn('value="approve_member"', body)
        self.assertIn('value="approve_non_member"', body)
        self.assertIn('value="review_message"', body)
        self.assertNotIn('value="ignore"', body)
        self.assertNotIn('value="unlink"', body)
        self.assertNotIn('value="remap"', body)
        self.assertIn("不會自動授予管理員", body)

    def test_member_approval_uses_existing_protected_route(self):
        response = self.post("approve_member", member_id="8")
        self.assertEqual(response.status_code, 302)
        self.repository.approve_member.assert_called_once_with(
            70,
            81,
            8,
            "Verified applicant",
            "identity-apple-fictional",
        )

    def test_non_member_approval_remains_basic_with_explicit_qualification(self):
        response = self.post(
            "approve_non_member",
            display_name="Fictional Applicant",
            qualification="affiliate",
        )
        self.assertEqual(response.status_code, 302)
        self.repository.approve_non_member.assert_called_once_with(
            70,
            81,
            "Fictional Applicant",
            "Verified applicant",
            "identity-apple-fictional",
            formal_name=None,
            qualifications=["affiliate"],
            guest_valid_from=None,
            guest_valid_until=None,
        )

    def test_admin_csrf_maintenance_and_freeze_are_not_bypassed(self):
        for environment, values, expected in (
            ({"WEB_PORTAL_ADMIN_MEMBER_IDS": "8"}, {}, 403),
            ({}, {"csrf_token": "invalid"}, 400),
            ({"WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "false"}, {}, 503),
            ({"PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true"}, {}, 503),
        ):
            with (
                self.subTest(environment=environment),
                patch.dict(os.environ, environment),
            ):
                response = self.post(
                    "approve_non_member", display_name="Fictional", **values
                )
                self.assertEqual(response.status_code, expected)
        self.repository.approve_non_member.assert_not_called()

    def test_invalid_target_and_guest_qualification_do_not_mutate(self):
        self.assertEqual(self.post("approve_member", member_id="999").status_code, 400)
        self.assertEqual(
            self.post(
                "approve_non_member",
                display_name="Fictional",
                qualification="guest_player",
            ).status_code,
            400,
        )
        self.repository.approve_member.assert_not_called()
        self.repository.approve_non_member.assert_not_called()

    def test_linked_apple_has_no_line_only_maintenance_actions(self):
        item = self.repository.admin_dashboard.return_value["identities"][0]
        item.update(person_id=80, identity_status="linked", review_status="closed")
        response = self.client.get("/match-member")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Apple 身分", body)
        for action in (
            "unlink",
            "remap",
            "disable_identity",
            "approve_member",
            "approve_non_member",
        ):
            self.assertNotIn('value="' + action + '"', body)

    def test_line_card_keeps_legacy_actions(self):
        self.repository.admin_dashboard.return_value["identities"][0][
            "provider"
        ] = "line"
        response = self.client.get("/manage/pending-identities")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("LINE 身分", body)
        for action in ("ignore", "reject", "approve_member", "approve_non_member"):
            self.assertIn('value="' + action + '"', body)

    def test_blocked_apple_exposes_rereview_but_not_approval_or_line_ignore(self):
        item = self.repository.admin_dashboard.return_value["identities"][0]
        item.update(identity_status="blocked", review_status="closed")
        response = self.client.get("/match-member")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('value="unblock"', body)
        self.assertRegex(body, r'value="approve_member"\s+disabled')
        self.assertRegex(body, r'value="approve_non_member"\s+disabled')
        self.assertNotIn('value="ignore"', body)

    def test_crafted_apple_line_only_posts_are_rejected_by_real_domain_guard(self):
        domain = IdentityLifecycleRepository(MagicMock())
        database = MagicMock()
        identity = AuthIdentityRecord(
            id=81, provider="apple", provider_subject="fictional-colliding-subject"
        )
        self.repository.set_ignored.side_effect = domain.set_ignored
        self.repository.unlink_identity.side_effect = domain.unlink_identity
        self.repository.remap_member_identity.side_effect = domain.remap_member_identity
        with (
            patch(
                "shared_lib.shared_module.portal_data.identity_lifecycle.Session"
            ) as factory,
            # Isolate management suspension on this raw-Mock database; retain
            # the real provider/domain guard that this crafted-post test probes.
            patch(
                "shared_lib.shared_module.portal_data.identity_lifecycle.require_management_mutation"
            ),
            patch.object(domain, "_require_admin"),
            patch.object(domain, "_audit_exists") as replay,
        ):
            factory.return_value.__enter__.return_value = database
            for action in ("ignore", "unignore", "unlink", "remap"):
                with self.subTest(action=action):
                    identity.status = (
                        "pending" if action in {"ignore", "unignore"} else "linked"
                    )
                    identity.person_id = None if identity.status == "pending" else 80
                    database.reset_mock()
                    database.scalar.return_value = identity
                    response = self.post(action, member_id="8", confirm_remap="yes")
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(database.scalar.call_count, 1)
                    database.add.assert_not_called()
            replay.assert_not_called()
