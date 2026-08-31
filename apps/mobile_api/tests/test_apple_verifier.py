import base64
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from shared_module.mobile_api import AuthenticationError
from shared_module.provider_verifiers import (
    APPLE_TOKEN_URL,
    AppleAuthorizationCodeExchanger,
    AppleExchangeOutcomeUnknown,
    AppleServerNotificationVerifier,
)

from apps.mobile_api.apple_verifier import (
    JWKS_URL,
    AppleIdTokenVerifier,
    AppleJwkCache,
    AppleVerificationUnavailable,
)

NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)
AUDIENCE = "fictional.ios.client"
RAW_NONCE = "fictional-raw-nonce-123456"


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AppleIdTokenVerifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )

    def jwk(self, private_key=None, **overrides):
        public = (private_key or self.private_key).public_key().public_numbers()
        values = {
            "kty": "RSA",
            "kid": "fictional-key-one",
            "use": "sig",
            "alg": "RS256",
            "n": encoded(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")),
            "e": encoded(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")),
        }
        values.update(overrides)
        return values

    def jwks_response(self, *keys):
        return 200, json.dumps({"keys": list(keys or (self.jwk(),))}).encode()

    def claims(self, **overrides):
        values = {
            "iss": "https://appleid.apple.com",
            "aud": AUDIENCE,
            "sub": "fictional-apple-stable-subject",
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
            "iat": int(NOW.timestamp()),
            "nonce": hashlib.sha256(RAW_NONCE.encode()).hexdigest(),
            "email": "untrusted@example.test",
            "name": "Untrusted name",
            "real_user_status": 2,
        }
        values.update(overrides)
        return values

    def token(self, *, claims=None, header=None, key=None):
        header = header or {"alg": "RS256", "kid": "fictional-key-one"}
        body = self.claims() if claims is None else claims
        signing_input = (
            encoded(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + encoded(json.dumps(body, separators=(",", ":")).encode())
        )
        signature = (key or self.private_key).sign(
            signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
        )
        return signing_input + "." + encoded(signature)

    def verifier(self, transport):
        return AppleIdTokenVerifier(AppleJwkCache(transport=transport))

    def test_valid_token_uses_only_subject_and_nonce_with_cached_key(self):
        transport = FakeTransport(self.jwks_response())
        verifier = self.verifier(transport)

        first = verifier.verify(self.token(), AUDIENCE, RAW_NONCE, NOW)
        second = verifier.verify(self.token(), AUDIENCE, RAW_NONCE, NOW)

        self.assertEqual(first.provider, "apple")
        self.assertEqual(first.subject, "fictional-apple-stable-subject")
        self.assertEqual(first.nonce, RAW_NONCE)
        self.assertNotIn("untrusted", repr(first).lower())
        self.assertEqual(second.subject, first.subject)
        self.assertEqual(transport.calls, [(JWKS_URL, 5.0)])

    def test_rotated_unknown_kid_forces_one_bounded_refresh(self):
        second_jwk = self.jwk(self.other_private_key, kid="fictional-key-two")
        transport = FakeTransport(
            self.jwks_response(self.jwk()), self.jwks_response(second_jwk)
        )
        verifier = self.verifier(transport)
        token = self.token(
            header={"alg": "RS256", "kid": "fictional-key-two"},
            key=self.other_private_key,
        )

        self.assertEqual(
            verifier.verify(token, AUDIENCE, RAW_NONCE, NOW).provider, "apple"
        )
        self.assertEqual(len(transport.calls), 2)

    def test_early_rotation_recovers_once_at_failure_backoff_deadline(self):
        second_jwk = self.jwk(self.other_private_key, kid="fictional-key-two")
        transport = FakeTransport(
            self.jwks_response(self.jwk()),
            (503, b"fictional-sensitive-provider-body"),
            self.jwks_response(second_jwk),
        )
        verifier = self.verifier(transport)
        verifier.verify(self.token(), AUDIENCE, RAW_NONCE, NOW)
        rotated = self.token(
            header={"alg": "RS256", "kid": "fictional-key-two"},
            key=self.other_private_key,
        )

        with self.assertRaises(AppleVerificationUnavailable) as failed_refresh:
            verifier.verify(rotated, AUDIENCE, RAW_NONCE, NOW)
        self.assertNotIn("fictional-sensitive", str(failed_refresh.exception))
        with self.assertRaises(AppleVerificationUnavailable):
            verifier.verify(rotated, AUDIENCE, RAW_NONCE, NOW + timedelta(seconds=59))
        self.assertEqual(len(transport.calls), 2)

        deadline = NOW + timedelta(minutes=1)
        with ThreadPoolExecutor(max_workers=8) as executor:
            providers = tuple(
                executor.map(
                    lambda _index: verifier.verify(
                        rotated, AUDIENCE, RAW_NONCE, deadline
                    ).provider,
                    range(8),
                )
            )
        self.assertEqual(providers, ("apple",) * 8)
        self.assertEqual(len(transport.calls), 3)

    def test_unknown_kids_share_one_thread_safe_early_refresh_per_cache_window(self):
        transport = FakeTransport(self.jwks_response(), self.jwks_response())
        verifier = self.verifier(transport)
        self.assertEqual(
            verifier.verify(self.token(), AUDIENCE, RAW_NONCE, NOW).provider, "apple"
        )

        assertions = [
            self.token(header={"alg": "RS256", "kid": f"unknown-key-{index % 2}"})
            for index in range(8)
        ]

        def rejected(assertion):
            with self.assertRaises(AuthenticationError):
                verifier.verify(assertion, AUDIENCE, RAW_NONCE, NOW)

        with ThreadPoolExecutor(max_workers=8) as executor:
            tuple(executor.map(rejected, assertions))

        self.assertEqual(len(transport.calls), 2)

        transport.responses.append(self.jwks_response())
        later = NOW + timedelta(minutes=16)
        later_token = self.token(
            claims=self.claims(
                iat=int(later.timestamp()),
                exp=int((later + timedelta(minutes=5)).timestamp()),
            )
        )
        self.assertEqual(
            verifier.verify(later_token, AUDIENCE, RAW_NONCE, later).provider, "apple"
        )
        self.assertEqual(len(transport.calls), 3)

    def test_algorithm_key_metadata_signature_and_unknown_key_fail_closed(self):
        cases = (
            (
                self.token(header={"alg": "HS256", "kid": "fictional-key-one"}),
                self.jwk(),
            ),
            (self.token(), self.jwk(use="enc")),
            (self.token(), self.jwk(kty="EC")),
            (self.token(), self.jwk(alg="HS256")),
            (self.token(key=self.other_private_key), self.jwk()),
            (
                self.token(header={"alg": "RS256", "kid": "unknown-key"}),
                self.jwk(),
            ),
        )
        for token, jwk in cases:
            with self.subTest(jwk=jwk["kid"], token_header=token.split(".")[0]):
                transport = FakeTransport(
                    self.jwks_response(jwk), self.jwks_response(jwk)
                )
                with self.assertRaises(AuthenticationError):
                    self.verifier(transport).verify(token, AUDIENCE, RAW_NONCE, NOW)

    def test_issuer_audience_nonce_expiry_and_subject_are_exact(self):
        cases = (
            self.claims(iss="https://example.invalid"),
            self.claims(aud="wrong-client"),
            self.claims(aud=[AUDIENCE]),
            self.claims(nonce="wrong-nonce"),
            self.claims(exp=int(NOW.timestamp())),
            self.claims(iat=int((NOW + timedelta(minutes=2)).timestamp())),
            self.claims(sub=""),
        )
        for claims in cases:
            with self.subTest(claim_keys=set(claims)):
                with self.assertRaises(AuthenticationError):
                    self.verifier(FakeTransport(self.jwks_response())).verify(
                        self.token(claims=claims), AUDIENCE, RAW_NONCE, NOW
                    )

    def test_malformed_or_oversized_token_and_jwks_fail_without_claim_leak(self):
        malformed_cases = (
            "not-a-jwt",
            "a.b.c",
            "x" * 16_385,
        )
        for assertion in malformed_cases:
            with (
                self.subTest(length=len(assertion)),
                self.assertRaises(AuthenticationError) as raised,
            ):
                self.verifier(FakeTransport(self.jwks_response())).verify(
                    assertion, AUDIENCE, RAW_NONCE, NOW
                )
            self.assertNotIn(assertion[:20], str(raised.exception))

        noncanonical_jwk = self.jwk()
        noncanonical_jwk["n"] = encoded(
            b"\x00" + base64.urlsafe_b64decode(noncanonical_jwk["n"] + "==")
        )
        for response in (
            (200, b"{"),
            (200, b"x" * 65_537),
            (200, json.dumps({"keys": [self.jwk(), self.jwk()]}).encode()),
            self.jwks_response(noncanonical_jwk),
        ):
            with (
                self.subTest(response_length=len(response[1])),
                self.assertRaises(AuthenticationError),
            ):
                self.verifier(FakeTransport(response)).verify(
                    self.token(), AUDIENCE, RAW_NONCE, NOW
                )

    def test_transport_failure_is_unavailable_and_never_exposes_token(self):
        assertion = self.token()
        for response in (
            TimeoutError("fictional-sensitive-assertion"),
            (500, b"fictional-sensitive-provider-body"),
        ):
            with (
                self.subTest(response=response),
                self.assertRaises(AppleVerificationUnavailable) as raised,
            ):
                self.verifier(FakeTransport(response)).verify(
                    assertion, AUDIENCE, RAW_NONCE, NOW
                )
            self.assertNotIn("fictional-sensitive", str(raised.exception))

    def test_refresh_failures_share_one_backoff_attempt_without_data_leak(self):
        assertion = self.token()

        def timeout_failure():
            return TimeoutError("fictional-sensitive-timeout")

        def server_failure():
            return 503, b"fictional-sensitive-provider-body"

        def malformed_failure():
            return 200, b'{"fictional-sensitive-malformed"'

        def oversized_failure():
            return 200, b"fictional-sensitive-oversized" + b"x" * 65_537

        for name, failure in (
            ("timeout", timeout_failure),
            ("5xx", server_failure),
            ("malformed", malformed_failure),
            ("oversized", oversized_failure),
        ):
            with self.subTest(name=name):
                transport = FakeTransport(failure(), failure())
                verifier = self.verifier(transport)

                def rejected(at):
                    try:
                        verifier.verify(assertion, AUDIENCE, RAW_NONCE, at)
                    except (AuthenticationError, AppleVerificationUnavailable) as error:
                        return error
                    self.fail("refresh failure unexpectedly verified an assertion")

                with ThreadPoolExecutor(max_workers=8) as executor:
                    errors = tuple(executor.map(rejected, (NOW,) * 8))

                self.assertEqual(len(transport.calls), 1)
                self.assertTrue(errors)
                for error in errors:
                    self.assertNotIn("fictional-sensitive", str(error))
                    self.assertNotIn(assertion[:20], str(error))

                rollback_error = rejected(NOW - timedelta(days=1))
                before_deadline_error = rejected(NOW + timedelta(seconds=59))
                self.assertIsInstance(rollback_error, AppleVerificationUnavailable)
                self.assertIsInstance(
                    before_deadline_error, AppleVerificationUnavailable
                )
                self.assertEqual(len(transport.calls), 1)

                deadline = NOW + timedelta(minutes=1)
                with ThreadPoolExecutor(max_workers=8) as executor:
                    deadline_errors = tuple(executor.map(rejected, (deadline,) * 8))
                self.assertEqual(len(transport.calls), 2)
                for error in deadline_errors:
                    self.assertIsInstance(
                        error,
                        (AuthenticationError, AppleVerificationUnavailable),
                    )
                    self.assertNotIn("fictional-sensitive", str(error))
                    self.assertNotIn(assertion[:20], str(error))

    def test_successful_retry_clears_backoff_and_preserves_early_rotation(self):
        second_jwk = self.jwk(self.other_private_key, kid="fictional-key-two")
        transport = FakeTransport(
            (503, b"fictional-sensitive-provider-body"),
            self.jwks_response(self.jwk()),
            self.jwks_response(second_jwk),
        )
        verifier = self.verifier(transport)
        with self.assertRaises(AppleVerificationUnavailable):
            verifier.verify(self.token(), AUDIENCE, RAW_NONCE, NOW)

        retry_at = NOW + timedelta(minutes=1)
        self.assertEqual(
            verifier.verify(self.token(), AUDIENCE, RAW_NONCE, retry_at).provider,
            "apple",
        )
        rotated = self.token(
            header={"alg": "RS256", "kid": "fictional-key-two"},
            key=self.other_private_key,
        )
        self.assertEqual(
            verifier.verify(rotated, AUDIENCE, RAW_NONCE, retry_at).provider,
            "apple",
        )
        self.assertEqual(len(transport.calls), 3)

    def test_authorization_code_exchange_is_exact_and_subject_correlated(self):
        token = self.token()
        calls = []

        def transport(url, body, timeout):
            calls.append((url, body, timeout))
            return (
                200,
                "application/json",
                json.dumps(
                    {
                        "access_token": "fictional-short-lived-access",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "refresh_token": "fictional-durable-refresh",
                        "id_token": token,
                    }
                ).encode(),
            )

        verifier = self.verifier(FakeTransport(self.jwks_response()))
        exchanger = AppleAuthorizationCodeExchanger(
            verifier,
            client_id=AUDIENCE,
            client_secret="fictional-runtime-client-secret",
            transport=transport,
        )
        result = exchanger.exchange(
            "fictional-single-use-code",
            expected_subject="fictional-apple-stable-subject",
            nonce=RAW_NONCE,
            now=NOW,
        )

        self.assertEqual(result.refresh_token, "fictional-durable-refresh")
        self.assertEqual(result.subject, "fictional-apple-stable-subject")
        self.assertEqual(calls[0][0], APPLE_TOKEN_URL)
        self.assertIn(b"grant_type=authorization_code", calls[0][1])
        self.assertNotIn("fictional-runtime-client-secret", repr(result))

    def test_authorization_code_exchange_accepts_case_insensitive_bearer(self):
        token = self.token()
        for token_type in ("bearer", "Bearer"):
            payload = {
                "access_token": "fictional-short-lived-access",
                "token_type": token_type,
                "expires_in": 3600,
                "refresh_token": "fictional-durable-refresh",
                "id_token": token,
            }

            def transport(_url, _body, _timeout, payload=payload):
                return 200, "application/json", json.dumps(payload).encode()

            exchanger = AppleAuthorizationCodeExchanger(
                self.verifier(FakeTransport(self.jwks_response())),
                client_id=AUDIENCE,
                client_secret="fictional-runtime-client-secret",
                transport=transport,
            )
            with self.subTest(token_type=token_type):
                result = exchanger.exchange(
                    "fictional-single-use-code",
                    expected_subject="fictional-apple-stable-subject",
                    nonce=RAW_NONCE,
                    now=NOW,
                )
                self.assertEqual(result.refresh_token, "fictional-durable-refresh")

    def test_authorization_code_unknown_outcome_is_not_retryable(self):
        verifier = self.verifier(FakeTransport(self.jwks_response()))
        for response in (
            TimeoutError("provider-body-must-not-leak"),
            (503, "application/json", b"provider-body-must-not-leak"),
        ):

            def transport(_url, _body, _timeout, response=response):
                if isinstance(response, Exception):
                    raise response
                return response

            exchanger = AppleAuthorizationCodeExchanger(
                verifier,
                client_id=AUDIENCE,
                client_secret="fictional-runtime-client-secret",
                transport=transport,
            )
            with (
                self.subTest(response=response),
                self.assertRaises(AppleExchangeOutcomeUnknown) as raised,
            ):
                exchanger.exchange(
                    "fictional-single-use-code",
                    expected_subject="fictional-apple-stable-subject",
                    nonce=RAW_NONCE,
                    now=NOW,
                )
            self.assertNotIn("provider-body", str(raised.exception))

    def test_authorization_code_response_rejects_wrong_subject_and_extra_fields(self):
        wrong_subject = self.token(
            claims=self.claims(sub="different-fictional-subject")
        )
        for payload in (
            {
                "access_token": "fictional-access",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "fictional-refresh",
                "id_token": wrong_subject,
            },
            {
                "access_token": "fictional-access",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "fictional-refresh",
                "id_token": self.token(),
                "email": "must-not-be-accepted@example.invalid",
            },
            {
                "access_token": "fictional-access",
                "token_type": "unrelated",
                "expires_in": 3600,
                "refresh_token": "fictional-refresh",
                "id_token": self.token(),
            },
        ):

            def transport(_url, _body, _timeout, payload=payload):
                return 200, "application/json", json.dumps(payload).encode()

            exchanger = AppleAuthorizationCodeExchanger(
                self.verifier(FakeTransport(self.jwks_response())),
                client_id=AUDIENCE,
                client_secret="fictional-runtime-client-secret",
                transport=transport,
            )
            with (
                self.subTest(keys=set(payload)),
                self.assertRaises(AuthenticationError),
            ):
                exchanger.exchange(
                    "fictional-single-use-code",
                    expected_subject="fictional-apple-stable-subject",
                    nonce=RAW_NONCE,
                    now=NOW,
                )

    def test_authorization_code_exchange_configuration_is_bounded(self):
        verifier = self.verifier(FakeTransport(self.jwks_response()))
        for client_id, client_secret in (
            ("x" * 256, "fictional-secret"),
            (AUDIENCE, "x" * 8193),
            ("non-ascii-用戶端", "fictional-secret"),
        ):
            with (
                self.subTest(client_id_length=len(client_id)),
                self.assertRaises(ValueError),
            ):
                AppleAuthorizationCodeExchanger(
                    verifier,
                    client_id=client_id,
                    client_secret=client_secret,
                )

    def test_server_notification_accepts_official_shape_seconds_and_no_exp(self):
        event = {
            "type": "consent-revoked",
            "sub": "fictional-apple-stable-subject",
            "event_time": int(NOW.timestamp()),
            "email": "ignored@example.invalid",
            "is_private_email": "true",
        }
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": AUDIENCE,
            "iat": int(NOW.timestamp()),
            "jti": "fictional-notification-jti-0001",
            "events": json.dumps(event, separators=(",", ":")),
        }
        verifier = AppleServerNotificationVerifier(
            AppleJwkCache(transport=FakeTransport(self.jwks_response()))
        )

        result = verifier.verify(self.token(claims=claims), AUDIENCE, NOW)

        self.assertEqual(result.event_type, "consent-revoked")
        self.assertEqual(result.subject, "fictional-apple-stable-subject")
        self.assertEqual(result.jti, "fictional-notification-jti-0001")
        self.assertNotIn("email", repr(result).lower())

    def test_server_notification_rejects_unknown_and_unexpected_claims(self):
        base = {
            "iss": "https://appleid.apple.com",
            "aud": AUDIENCE,
            "iat": int(NOW.timestamp()),
            "jti": "fictional-notification-jti-0001",
            "events": json.dumps(
                {
                    "type": "unknown-event",
                    "sub": "fictional-apple-stable-subject",
                    "event_time": int(NOW.timestamp()),
                },
                separators=(",", ":"),
            ),
        }
        event_extra = {
            **base,
            "events": json.dumps(
                {
                    "type": "account-deleted",
                    "sub": "fictional-apple-stable-subject",
                    "event_time": int(NOW.timestamp()),
                    "unexpected": "must-fail",
                },
                separators=(",", ":"),
            ),
        }
        for claims in (
            base,
            {**base, "exp": int((NOW + timedelta(minutes=5)).timestamp())},
            {**base, "extra": "must-fail"},
            {**base, "aud": "wrong"},
            event_extra,
        ):
            verifier = AppleServerNotificationVerifier(
                AppleJwkCache(transport=FakeTransport(self.jwks_response()))
            )
            with self.subTest(keys=set(claims)), self.assertRaises(AuthenticationError):
                verifier.verify(self.token(claims=claims), AUDIENCE, NOW)

    def test_server_notification_rejects_milliseconds_stale_and_future(self):
        def claims(iat, event_time):
            return {
                "iss": "https://appleid.apple.com",
                "aud": AUDIENCE,
                "iat": iat,
                "jti": "fictional-notification-jti-0001",
                "events": json.dumps(
                    {
                        "type": "account-deleted",
                        "sub": "fictional-apple-stable-subject",
                        "event_time": event_time,
                    },
                    separators=(",", ":"),
                ),
            }

        now_seconds = int(NOW.timestamp())
        cases = (
            claims(now_seconds, now_seconds * 1000),
            claims(now_seconds - 86_401, now_seconds - 86_401),
            claims(now_seconds + 61, now_seconds + 61),
            claims(now_seconds, now_seconds - 86_401),
            claims(now_seconds, now_seconds + 61),
        )
        for candidate in cases:
            verifier = AppleServerNotificationVerifier(
                AppleJwkCache(transport=FakeTransport(self.jwks_response()))
            )
            with (
                self.subTest(iat=candidate["iat"]),
                self.assertRaises(AuthenticationError),
            ):
                verifier.verify(self.token(claims=candidate), AUDIENCE, NOW)


if __name__ == "__main__":
    unittest.main()
