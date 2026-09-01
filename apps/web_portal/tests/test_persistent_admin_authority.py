from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from werkzeug.exceptions import Forbidden

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from admin_security import (  # noqa: E402
    configure_phase_c_principal_loader,
    get_current_principal,
    mark_fresh_admin_reauthentication,
    require_fresh_admin_reauthentication,
)
from role_policy import (  # noqa: E402
    MANAGE_MEMBERS,
    ROLE_BASIC,
    VIEW_MEMBER_PORTAL,
    Principal,
    has_capability,
)


class PersistentAdminWebSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "fictional-persistent-admin-test-key"

    def test_fresh_reauthentication_is_bounded_and_rollback_safe(self):
        with self.app.test_request_context("/"):
            mark_fresh_admin_reauthentication(1000)
            require_fresh_admin_reauthentication(1300)
            with self.assertRaises(Forbidden):
                require_fresh_admin_reauthentication(1301)
            with self.assertRaises(Forbidden):
                require_fresh_admin_reauthentication(999)

    def test_memberless_admin_gets_admin_not_member_capability(self):
        principal = Principal(role="admin", person_id=9, member_id=None)
        self.assertTrue(has_capability(principal, MANAGE_MEMBERS))
        self.assertFalse(has_capability(principal, VIEW_MEMBER_PORTAL))

    def test_absent_or_malformed_mode_preserves_basic_auth_but_denies_admin(self):
        configure_phase_c_principal_loader(lambda _values: False)
        try:
            for mode in (None, "persistent "):
                environment = {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}
                if mode is not None:
                    environment["WEB_PORTAL_ADMIN_AUTHORITY_MODE"] = mode
                with (
                    self.subTest(mode=mode),
                    patch.dict(os.environ, environment, clear=True),
                    self.app.test_request_context("/"),
                ):
                    from flask import session

                    session.update(user_id="fictional-user", member_id=7)
                    principal = get_current_principal()
                    self.assertEqual(principal.role, ROLE_BASIC)
                    self.assertFalse(has_capability(principal, MANAGE_MEMBERS))
        finally:
            configure_phase_c_principal_loader(None)

    def test_route_contract_requires_csrf_reauth_reason_request_and_version(self):
        source = (WEB_PORTAL_DIR / "app.py").read_text(encoding="utf-8")
        body = source.split("def change_person_access(person_id):", 1)[1].split(
            "\n\n@app.", 1
        )[0]
        for required in (
            "require_valid_csrf()",
            "require_fresh_admin_reauthentication()",
            'request.form.get("reason", "")',
            "_required_request_id(",
            'request.form.get("expected_version", "")',
            "repository.change_admin_access(",
        ):
            self.assertIn(required, body)


if __name__ == "__main__":
    unittest.main()
