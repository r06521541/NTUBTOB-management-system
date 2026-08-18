import json
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

from shared_module.mobile_api import AuthenticationError

from apps.mobile_api.line_verifier import (
    VERIFY_URL,
    LineIdTokenVerifier,
    LineVerificationRateLimited,
    LineVerificationUnavailable,
)

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, status=200, payload=None, error=None):
        self.status, self.payload, self.error = status, payload, error
        self.calls = []

    def __call__(self, url, body, timeout):
        self.calls.append((url, body, timeout))
        if self.error:
            raise self.error
        return self.status, json.dumps(self.payload).encode("utf-8")


class LineIdTokenVerifierTest(unittest.TestCase):
    def claims(self, **overrides):
        values = {
            "iss": "https://access.line.me",
            "aud": "fake-native-client",
            "sub": "fake-line-subject",
            "nonce": "fake-nonce-123456",
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        }
        values.update(overrides)
        return values

    def test_valid_response_posts_official_fields_with_bounded_timeout(self):
        transport = FakeTransport(payload=self.claims())
        result = LineIdTokenVerifier(transport).verify(
            "raw.fake.id-token", "fake-native-client", "fake-nonce-123456", NOW
        )
        self.assertEqual(result.subject, "fake-line-subject")
        url, body, timeout = transport.calls[0]
        self.assertEqual(url, VERIFY_URL)
        self.assertLessEqual(timeout, 10)
        self.assertEqual(
            parse_qs(body.decode("ascii")),
            {
                "id_token": ["raw.fake.id-token"],
                "client_id": ["fake-native-client"],
                "nonce": ["fake-nonce-123456"],
            },
        )

    def test_claim_schema_audience_nonce_and_expiry_fail_closed(self):
        cases = (
            self.claims(aud="wrong"),
            self.claims(nonce="wrong"),
            self.claims(exp=int((NOW - timedelta(seconds=1)).timestamp())),
            {"sub": "incomplete"},
            ["not", "an", "object"],
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(AuthenticationError):
                    LineIdTokenVerifier(FakeTransport(payload=payload)).verify(
                        "raw-secret-token",
                        "fake-native-client",
                        "fake-nonce-123456",
                        NOW,
                    )

    def test_provider_rejections_and_malformed_body_do_not_leak_token(self):
        for status, payload in ((400, {}), (401, {}), (200, "not-json")):
            with self.subTest(status=status):
                transport = FakeTransport(status=status, payload=payload)
                with self.assertRaises(AuthenticationError) as raised:
                    LineIdTokenVerifier(transport).verify(
                        "raw-secret-token",
                        "fake-native-client",
                        "fake-nonce-123456",
                        NOW,
                    )
                self.assertNotIn("raw-secret-token", str(raised.exception))

    def test_rate_limit_is_safe_and_retryable(self):
        with self.assertRaises(LineVerificationRateLimited) as raised:
            LineIdTokenVerifier(FakeTransport(status=429, payload={})).verify(
                "raw-secret-token", "fake-native-client", "fake-nonce-123456", NOW
            )
        self.assertNotIn("raw-secret-token", str(raised.exception))

    def test_server_failure_timeout_and_transport_error_are_unavailable(self):
        cases = (
            FakeTransport(status=500, payload={}),
            FakeTransport(error=TimeoutError("raw-secret-token")),
        )
        for transport in cases:
            with self.subTest(transport=transport):
                with self.assertRaises(LineVerificationUnavailable) as raised:
                    LineIdTokenVerifier(transport).verify(
                        "raw-secret-token",
                        "fake-native-client",
                        "fake-nonce-123456",
                        NOW,
                    )
                self.assertNotIn("raw-secret-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
