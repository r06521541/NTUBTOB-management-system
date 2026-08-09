import sys
import unittest
from pathlib import Path


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from role_policy import (  # noqa: E402
    ASSIGN_ROLES,
    CONFIRM_NOTIFICATIONS,
    EDIT_PERSON_PROFILE,
    MANAGE_EVENTS,
    MANAGE_MEMBERS,
    MANAGE_PENDING_IDENTITIES,
    MANAGE_PERSON_ACCESS,
    MANAGE_QUALIFICATIONS,
    REPLY_OWN_ATTENDANCE,
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OFFICER,
    ROLE_CAPABILITIES,
    SEND_NOTIFICATIONS,
    VIEW_PERSON_DIRECTORY,
    Principal,
    has_capability,
    resolve_demo_principal,
    resolve_production_principal,
)


class RolePolicyTest(unittest.TestCase):
    def test_role_capabilities_are_inherited_and_unknown_values_deny(self):
        member = Principal(ROLE_MEMBER, 1)
        officer = Principal(ROLE_OFFICER, 2)
        admin = Principal(ROLE_ADMIN, 3)
        self.assertTrue(has_capability(member, REPLY_OWN_ATTENDANCE))
        self.assertFalse(has_capability(member, MANAGE_EVENTS))
        self.assertTrue(has_capability(officer, MANAGE_EVENTS))
        self.assertFalse(has_capability(officer, MANAGE_MEMBERS))
        self.assertTrue(has_capability(admin, MANAGE_EVENTS))
        self.assertTrue(has_capability(admin, ASSIGN_ROLES))
        self.assertFalse(has_capability(Principal("unknown", 4), MANAGE_EVENTS))
        self.assertFalse(has_capability(admin, "unknown_capability"))
        self.assertFalse(has_capability(None, REPLY_OWN_ATTENDANCE))

    def test_person_and_notification_capabilities_follow_role_boundaries(self):
        member = Principal(ROLE_MEMBER, 1)
        officer = Principal(ROLE_OFFICER, 2)
        admin = Principal(ROLE_ADMIN, 3)
        self.assertTrue(has_capability(member, VIEW_PERSON_DIRECTORY))
        for capability in (
            EDIT_PERSON_PROFILE,
            MANAGE_PENDING_IDENTITIES,
            MANAGE_QUALIFICATIONS,
            MANAGE_PERSON_ACCESS,
            CONFIRM_NOTIFICATIONS,
        ):
            with self.subTest(role="member", capability=capability):
                self.assertFalse(has_capability(member, capability))
            with self.subTest(role="officer", capability=capability):
                self.assertTrue(has_capability(officer, capability))
        self.assertFalse(has_capability(officer, ASSIGN_ROLES))
        self.assertFalse(has_capability(officer, SEND_NOTIFICATIONS))
        self.assertTrue(has_capability(admin, ASSIGN_ROLES))
        self.assertTrue(has_capability(admin, SEND_NOTIFICATIONS))

    def test_policy_mapping_and_capability_sets_are_read_only(self):
        with self.assertRaises(TypeError):
            ROLE_CAPABILITIES[ROLE_MEMBER] = frozenset()
        with self.assertRaises(AttributeError):
            ROLE_CAPABILITIES[ROLE_MEMBER].add(MANAGE_EVENTS)

    def test_unhashable_or_non_string_policy_inputs_deny_without_error(self):
        for principal, capability in (
            (Principal([], 1), MANAGE_EVENTS),
            (Principal({}, 1), MANAGE_EVENTS),
            (Principal(ROLE_ADMIN, 1), []),
            (Principal(ROLE_ADMIN, 1), {}),
            (Principal(7, 1), MANAGE_EVENTS),
            (Principal(ROLE_ADMIN, 1), 7),
        ):
            with self.subTest(principal=principal, capability=capability):
                self.assertFalse(has_capability(principal, capability))

    def test_production_resolves_only_member_or_allowlisted_admin(self):
        values = {"user_id": "line-user", "member_id": 7}
        self.assertEqual(
            resolve_production_principal(values, frozenset()).role,
            ROLE_MEMBER,
        )
        self.assertEqual(
            resolve_production_principal(values, frozenset({7})).role,
            ROLE_ADMIN,
        )
        for invalid in (
            {},
            {"user_id": "", "member_id": 7},
            {"user_id": "line-user", "member_id": True},
            {"user_id": "line-user", "member_id": "7"},
            {"user_id": "line-user", "member_id": 0},
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(
                    resolve_production_principal(invalid, frozenset({7}))
                )

    def test_demo_accepts_three_explicit_roles_and_fails_closed(self):
        for role in (ROLE_MEMBER, ROLE_OFFICER, ROLE_ADMIN):
            with self.subTest(role=role):
                principal = resolve_demo_principal(
                    {
                        "demo_authenticated": True,
                        "demo_member": {"id": "demo", "demo_role": role},
                    }
                )
                self.assertEqual(principal.role, role)
        self.assertIsNone(resolve_demo_principal({}))
        self.assertIsNone(
            resolve_demo_principal(
                {
                    "demo_authenticated": True,
                    "demo_member": {"demo_role": "owner"},
                }
            )
        )
        for invalid_member in (
            {"demo_role": ROLE_MEMBER},
            {"id": "", "demo_role": ROLE_MEMBER},
            {"id": "   ", "demo_role": ROLE_MEMBER},
            {"id": 7, "demo_role": ROLE_MEMBER},
            {"id": [], "demo_role": ROLE_MEMBER},
            {"id": "demo", "demo_role": []},
        ):
            with self.subTest(invalid_member=invalid_member):
                self.assertIsNone(
                    resolve_demo_principal(
                        {
                            "demo_authenticated": True,
                            "demo_member": invalid_member,
                        }
                    )
                )


if __name__ == "__main__":
    unittest.main()
