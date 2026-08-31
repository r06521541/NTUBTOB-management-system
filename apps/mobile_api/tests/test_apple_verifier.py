import base64
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from shared_module.mobile_api import AuthenticationError

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
            with self.subTest(length=len(assertion)), self.assertRaises(
                AuthenticationError
            ) as raised:
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
            with self.subTest(response_length=len(response[1])), self.assertRaises(
                AuthenticationError
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
            with self.subTest(response=response), self.assertRaises(
                AppleVerificationUnavailable
            ) as raised:
                self.verifier(FakeTransport(response)).verify(
                    assertion, AUDIENCE, RAW_NONCE, NOW
                )
            self.assertNotIn("fictional-sensitive", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
