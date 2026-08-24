import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "shared_lib"))

from flask import Flask, abort, session
from shared_module.identity_linking import IdentityLinkResult, InternalWebPrincipal

from identity_link_web import create_identity_link_blueprint


class Port:
    def redirect_uri(self, provider):
        return (
            f"https://portal.example/api/v1/auth/identity-link/web/callback/{provider}"
        )

    def authorization_url(self, **values):
        return "https://provider.example/authorize?state=" + values["state"]

    exchange_code = Mock(return_value="raw-id-token-never-in-cookie")
    verify_id_token = Mock(return_value=SimpleNamespace(subject="verified-subject"))


class IdentityLinkWebRoutesTest(unittest.TestCase):
    def setUp(self):
        self.service = SimpleNamespace(
            begin_candidate=Mock(
                return_value={"candidate_credential": "opaque-candidate"}
            ),
            issue_fresh_proof=Mock(
                return_value={
                    "proof_credential": "opaque-proof",
                    "candidate_provider": "google",
                    "proof_provider": "line",
                    "person": {"display_name": "Safe Name"},
                }
            ),
            confirm_web=Mock(
                return_value=IdentityLinkResult(
                    "linked", web_principal=InternalWebPrincipal(23, 7, 7001)
                )
            ),
        )
        app = Flask(__name__)
        app.secret_key = "s" * 32

        def csrf():
            if (
                session.get("csrf") != "valid"
                or request.form.get("csrf_token") != "valid"
            ):
                abort(400)

        from flask import request

        app.register_blueprint(
            create_identity_link_blueprint(
                provider_port=Port(),
                service=self.service,
                require_csrf=csrf,
                allowed_redirects={
                    Port().redirect_uri("google"),
                    Port().redirect_uri("line"),
                },
                current_person_id=lambda: session.get("person_id"),
            )
        )
        self.client = app.test_client()

    def test_begin_requires_csrf_and_callback_consumes_state_without_raw_token_cookie(
        self,
    ):
        with self.client.session_transaction() as values:
            values.update(csrf="valid", person_id=23)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/identity-link/web/begin/google",
                data={"purpose": "self_link", "stage": "candidate"},
            ).status_code,
            400,
        )
        begun = self.client.post(
            "/api/v1/auth/identity-link/web/begin/google",
            data={"csrf_token": "valid", "purpose": "self_link", "stage": "candidate"},
        )
        state = begun.location.split("state=", 1)[1]
        callback = self.client.get(
            "/api/v1/auth/identity-link/web/callback/google",
            query_string={"state": state, "code": "fake-code"},
        )
        self.assertEqual(callback.status_code, 302)
        self.assertNotIn("raw-id-token", callback.headers.get("Set-Cookie", ""))
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/identity-link/web/callback/google",
                query_string={"state": state, "code": "fake-code"},
            ).status_code,
            400,
        )

    def test_confirm_uses_internal_principal_but_public_response_is_redacted(self):
        with self.client.session_transaction() as values:
            values.update(
                csrf="valid",
                identity_link_candidate="opaque-candidate",
                identity_link_proof="opaque-proof",
                identity_link_binding="binding",
                identity_link_purpose="recovery_link",
                attacker_fixed="must-be-removed",
                user_id="old-subject",
            )
        response = self.client.post(
            "/api/v1/auth/identity-link/web/confirm",
            data={
                "csrf_token": "valid",
                "confirmed": "true",
                "purpose": "recovery_link",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("23", response.get_data(as_text=True))
        with self.client.session_transaction() as values:
            self.assertEqual(values["person_id"], 23)
            self.assertNotIn("user_id", values)
            self.assertNotIn("attacker_fixed", values)
