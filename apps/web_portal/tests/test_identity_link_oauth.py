import unittest

from identity_link_oauth import (
    InvalidIdentityLinkOAuth,
    begin_flow,
    clear_flow,
    consume_callback,
)


class IdentityLinkOAuthTest(unittest.TestCase):
    def setUp(self):
        self.session = {
            "identity_link_oauth_state": "stale",
            "identity_link_oauth_sealed": "stale",
        }
        self.allowed = {
            "https://portal.example/api/v1/auth/identity-link/web/callback/google"
        }

    def test_begin_replaces_old_flow_and_keeps_raw_verifier_out_of_cookie(self):
        result = begin_flow(
            self.session,
            secret_key="s" * 32,
            provider="google",
            purpose="self_link",
            redirect_uri=next(iter(self.allowed)),
            allowed_redirects=self.allowed,
        )
        self.assertEqual(result["code_challenge_method"], "S256")
        self.assertNotIn("verifier", str(self.session))
        self.assertNotIn("subject", str(self.session))

    def test_callback_is_exact_provider_redirect_and_single_use(self):
        result = begin_flow(
            self.session,
            secret_key="s" * 32,
            provider="google",
            purpose="recovery_link",
            redirect_uri=next(iter(self.allowed)),
            allowed_redirects=self.allowed,
        )
        with self.assertRaises(InvalidIdentityLinkOAuth):
            consume_callback(
                self.session.copy(),
                secret_key="s" * 32,
                state=result["state"],
                provider="line",
                redirect_uri=next(iter(self.allowed)),
                allowed_redirects=self.allowed,
            )
        consumed = consume_callback(
            self.session,
            secret_key="s" * 32,
            state=result["state"],
            provider="google",
            redirect_uri=next(iter(self.allowed)),
            allowed_redirects=self.allowed,
        )
        self.assertTrue(consumed["code_verifier"])
        with self.assertRaises(InvalidIdentityLinkOAuth):
            consume_callback(
                self.session,
                secret_key="s" * 32,
                state=result["state"],
                provider="google",
                redirect_uri=next(iter(self.allowed)),
                allowed_redirects=self.allowed,
            )

    def test_redirect_is_exact_allowlist_and_cancel_clears_all_keys(self):
        with self.assertRaises(InvalidIdentityLinkOAuth):
            begin_flow(
                self.session,
                secret_key="s" * 32,
                provider="google",
                purpose="self_link",
                redirect_uri=next(iter(self.allowed)) + "?next=evil",
                allowed_redirects=self.allowed,
            )
        clear_flow(self.session)
        self.assertEqual(self.session, {})

    def test_missing_key_and_tampered_ciphertext_fail_closed_without_detail(self):
        with self.assertRaises(InvalidIdentityLinkOAuth):
            begin_flow(
                {},
                secret_key="short",
                provider="google",
                purpose="self_link",
                redirect_uri=next(iter(self.allowed)),
                allowed_redirects=self.allowed,
            )
        result = begin_flow(
            self.session,
            secret_key="s" * 32,
            provider="google",
            purpose="self_link",
            redirect_uri=next(iter(self.allowed)),
            allowed_redirects=self.allowed,
        )
        self.session["identity_link_oauth_sealed"] += "A"
        with self.assertRaisesRegex(InvalidIdentityLinkOAuth, "invalid or expired"):
            consume_callback(
                self.session,
                secret_key="s" * 32,
                state=result["state"],
                provider="google",
                redirect_uri=next(iter(self.allowed)),
                allowed_redirects=self.allowed,
            )
