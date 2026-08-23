import unittest
from datetime import datetime, timedelta, timezone

from shared_module.mobile_api import AuthenticationError

from apps.mobile_api.google_verifier import GoogleIdTokenVerifier


NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


class GoogleIdTokenVerifierTest(unittest.TestCase):
    def test_verified_subject_requires_google_issuer_allowlisted_audience_and_expiry(self):
        verifier = GoogleIdTokenVerifier(
            lambda token: {
                "iss": "https://accounts.google.com",
                "aud": "approved-client.apps.googleusercontent.com",
                "sub": "google-stable-subject",
                "exp": int((NOW + timedelta(minutes=5)).timestamp()),
                "email": "untrusted@example.test",
                "name": "Untrusted name",
            },
            audiences=("approved-client.apps.googleusercontent.com",),
        )

        verified = verifier.verify("raw-google-id-token", "", None, NOW)

        self.assertEqual(verified.provider, "google")
        self.assertEqual(verified.subject, "google-stable-subject")
        self.assertEqual(verified.audience, "approved-client.apps.googleusercontent.com")
        self.assertIsNone(verified.nonce)
        self.assertNotIn("untrusted", repr(verified))

    def test_wrong_issuer_audience_expiry_or_subject_fail_closed(self):
        for claims in (
            {"iss": "evil.example", "aud": "approved-client.apps.googleusercontent.com", "sub": "s", "exp": int((NOW + timedelta(minutes=5)).timestamp())},
            {"iss": "accounts.google.com", "aud": "wrong-client", "sub": "s", "exp": int((NOW + timedelta(minutes=5)).timestamp())},
            {"iss": "accounts.google.com", "aud": "approved-client.apps.googleusercontent.com", "sub": "s", "exp": int((NOW - timedelta(seconds=1)).timestamp())},
            {"iss": "accounts.google.com", "aud": "approved-client.apps.googleusercontent.com", "sub": "", "exp": int((NOW + timedelta(minutes=5)).timestamp())},
        ):
            with self.subTest(claims=claims):
                verifier = GoogleIdTokenVerifier(
                    lambda token, claims=claims: claims,
                    audiences=("approved-client.apps.googleusercontent.com",),
                )
                with self.assertRaises(AuthenticationError):
                    verifier.verify("raw-google-id-token", "", None, NOW)

    def test_provider_errors_do_not_expose_raw_token(self):
        verifier = GoogleIdTokenVerifier(
            lambda token: (_ for _ in ()).throw(ValueError(token)),
            audiences=("approved-client.apps.googleusercontent.com",),
        )

        with self.assertRaises(AuthenticationError) as raised:
            verifier.verify("raw-google-id-token", "", None, NOW)

        self.assertNotIn("raw-google", str(raised.exception))
