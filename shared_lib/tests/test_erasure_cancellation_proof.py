"""Cancellation-only cryptographic boundary; fictional providers, no DB/network."""

import base64
import hashlib
import json
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from shared_module.erasure_cancellation_proof import (
    CANCELLATION_PROOF_PURPOSE,
    CancellationContext,
    CancellationProofRejected,
    CancellationProofService,
    FreshCancellationProof,
)
from shared_module.mobile_api import VerifiedAssertion
from shared_module.provider_verifiers import GoogleIdTokenVerifier, LineIdTokenVerifier


class CancellationProofTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.context = CancellationContext(
            "11111111-1111-4111-8111-111111111111",
            "person",
            "22222222-2222-4222-8222-222222222222",
            self.now,
        )
        self.verifier = Mock()
        self.service = self.make_service()

    def make_service(self, **changes):
        values = dict(
            audience="fictional-cancellation",
            lifetime=timedelta(minutes=2),
            providers={"google": (self.verifier, "fictional-client")},
            clock=lambda: self.now,
        )
        values.update(changes)
        return CancellationProofService(b"f" * 32, **values)

    def begin(self):
        result = self.service.begin(self.context, "google")
        self.verifier.verify.return_value = VerifiedAssertion(
            "google",
            "fictional-subject",
            "fictional-client",
            result["nonce"],
            self.now + timedelta(minutes=3),
        )
        return result

    def assert_rejected(self, callback):
        with self.assertRaises(CancellationProofRejected) as caught:
            callback()
        self.assertEqual(str(caught.exception), "invalid_cancellation_proof")

    def test_round_trip_preserves_origin_time_and_has_no_identity_claim(self):
        start = self.now
        challenge = self.begin()
        self.now += timedelta(seconds=20)
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        proof = self.service(token)
        self.assertIs(type(proof), FreshCancellationProof)
        self.assertEqual(proof.issued_at, start)
        self.assertEqual(proof.authenticated_at, self.now)
        self.assertEqual(proof.expires_at, start + timedelta(minutes=2))
        self.assertEqual(proof.job_id, self.context.job_id)
        self.assertEqual(proof.target_generation, self.context.target_generation)
        self.assertEqual(proof.purpose, CANCELLATION_PROOF_PURPOSE)
        self.assertEqual(proof.provider_subject, "fictional-subject")
        for field in ("identity_id", "person_id", "identity_generation"):
            self.assertNotIn(field, asdict(proof))
        self.verifier.verify.assert_called_once_with(
            "fake", "fictional-client", challenge["nonce"], self.now
        )
        self.assertNotIn("fictional-subject", token)
        self.assertNotIn("fictional-subject", repr(proof))
        self.assertNotEqual(challenge["nonce"], self.begin()["nonce"])

    def test_subject_is_resolved_by_provider_not_preselected_for_person(self):
        challenge = self.begin()
        original = self.verifier.verify.return_value
        for subject in ("fictional-first", "fictional-second"):
            self.verifier.verify.return_value = replace(original, subject=subject)
            proof = self.service(
                self.service.authenticate(challenge["challenge_credential"], "fake")
            )
            self.assertEqual(proof.provider_subject, subject)
        # Neither success says this subject currently belongs to the target.
        pending = self.service.begin(
            replace(self.context, target_kind="pending_identity"), "google"
        )
        self.assertEqual(pending["provider"], "google")

    def test_provider_binding_and_subject_shape_are_strict(self):
        challenge = self.begin()
        original = self.verifier.verify.return_value
        for changes in (
            {"provider": "apple"},
            {"audience": "other-client"},
            {"nonce": None},
            {"nonce": "other"},
            {"expires_at": self.now},
            {"expires_at": self.now.replace(tzinfo=None)},
            {"subject": ""},
            {"subject": True},
            {"subject": "f" * 256},
        ):
            with self.subTest(changes=changes):
                self.verifier.verify.return_value = replace(original, **changes)
                self.assert_rejected(
                    lambda: self.service.authenticate(
                        challenge["challenge_credential"], "fake"
                    )
                )
        self.verifier.verify.return_value = asdict(original)
        self.assert_rejected(
            lambda: self.service.authenticate(challenge["challenge_credential"], "fake")
        )

    def test_expired_challenge_never_calls_provider(self):
        challenge = self.begin()
        self.now += timedelta(minutes=2)
        self.assert_rejected(
            lambda: self.service.authenticate(challenge["challenge_credential"], "fake")
        )
        self.verifier.verify.assert_not_called()

    def test_assertion_from_another_challenge_is_rejected(self):
        first = self.begin()
        original = self.verifier.verify.return_value
        second = self.begin()
        self.verifier.verify.return_value = original
        self.assertNotEqual(first["nonce"], second["nonce"])
        self.assert_rejected(
            lambda: self.service.authenticate(second["challenge_credential"], "fake")
        )

    def test_provider_io_cannot_extend_expiry_or_move_clock_backwards(self):
        for elapsed in (timedelta(minutes=2), timedelta(seconds=-1)):
            self.setUp()
            challenge = self.begin()
            original = self.verifier.verify.return_value

            def slow(*args):
                self.now += elapsed
                return original

            self.verifier.verify.side_effect = slow
            self.assert_rejected(
                lambda: self.service.authenticate(
                    challenge["challenge_credential"], "fake"
                )
            )
            self.verifier.verify.assert_called_once()

    def test_provider_expiry_caps_proof_and_origin_age_is_not_renewed(self):
        challenge = self.begin()
        expiry = self.now + timedelta(seconds=50)
        self.verifier.verify.return_value = replace(
            self.verifier.verify.return_value, expires_at=expiry
        )
        self.now += timedelta(seconds=20)
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        self.assertEqual(self.service(token).expires_at, expiry)
        self.now = expiry
        self.assert_rejected(lambda: self.service(token))

    def test_challenge_and_verified_domains_and_wrong_keys_are_separate(self):
        challenge = self.begin()
        self.assert_rejected(lambda: self.service(challenge["challenge_credential"]))
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        self.assert_rejected(lambda: self.service.authenticate(token, "fake"))
        other = CancellationProofService(
            b"x" * 32,
            audience=self.service.audience,
            lifetime=self.service.lifetime,
            providers={},
            clock=lambda: self.now,
        )
        self.assert_rejected(lambda: other(token))
        self.assert_rejected(lambda: self.make_service(audience="other")(token))

    def test_old_erasure_proofs_and_cancellation_proofs_reject_cross_use(self):
        from shared_module.portal_data.erasure_verification import (
            ErasureVerificationRejected,
        )

        from shared_lib.tests.test_erasure_proof import ErasureProofTests

        old = ErasureProofTests()
        old.setUp()
        old.service.audience = self.service.audience
        old_challenge = old.begin()
        old_token = old.service.authenticate(
            old_challenge["challenge_credential"], "fake"
        )
        for value in (old_token, old_challenge["challenge_credential"]):
            self.assert_rejected(lambda: self.service(value))
            self.assert_rejected(lambda: self.service.authenticate(value, "fake"))
        challenge = self.begin()
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        with self.assertRaises(ErasureVerificationRejected):
            old.service(token)

    def test_valid_base64_ciphertext_tamper_and_transport_bounds(self):
        challenge = self.begin()
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        raw = bytearray(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        raw[-1] ^= 1
        tampered = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        for bad in (
            True,
            "",
            "ordinary-access-token",
            tampered,
            token + "=",
            token + "\n",
            "a" * 4097,
        ):
            self.assert_rejected(lambda: self.service(bad))
        self.verifier.reset_mock()
        for bad in (True, "", "f" * 16385):
            self.assert_rejected(
                lambda: self.service.authenticate(
                    challenge["challenge_credential"], bad
                )
            )
        self.verifier.verify.assert_not_called()

    def test_authenticated_malformed_json_and_extra_fields_reject(self):
        challenge = self.begin()
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        payload = self.service._open("verified", token)
        bad_payloads = (
            {**payload, "identity_generation": self.context.target_generation},
            {**payload, "job_id": self.context.job_id + "\n"},
            {**payload, "purpose": "account_erasure_verification"},
            {**payload, "target_kind": "unknown"},
            {**payload, "issued_at": (self.now + timedelta(seconds=1)).isoformat()},
            {
                **payload,
                "authenticated_at": (self.now - timedelta(seconds=1)).isoformat(),
            },
            {
                **payload,
                "authenticated_at": (self.now + timedelta(seconds=1)).isoformat(),
            },
            {**payload, "expires_at": (self.now + timedelta(minutes=6)).isoformat()},
        )
        for bad in bad_payloads:
            self.assert_rejected(
                lambda: self.service(self.service._seal("verified", bad))
            )
        valid_json = json.dumps(payload, separators=(",", ":")).encode("ascii")
        duplicate = (
            b'{"job_id":"'
            + self.context.job_id.encode("ascii")
            + b'",'
            + valid_json[1:]
        )
        for raw_json in (
            duplicate,
            b'{"value":NaN,"padding":"' + b"x" * 80 + b'"}',
            b"[" * 1000 + b"]" * 1000,
            b"[" + b" " * 80 + b"]",
        ):
            nonce = b"n" * 12
            raw = nonce + AESGCM(self.service._key).encrypt(
                nonce, raw_json, b"account-erasure-cancellation:verified"
            )
            bad = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
            self.assertGreaterEqual(len(bad), 80)
            self.assertLessEqual(len(bad), 4096)
            self.assert_rejected(lambda: self.service(bad))

    def test_untrusted_context_configuration_and_clock_reject_safely(self):
        for value in (
            {},
            replace(self.context, job_id="bad"),
            replace(self.context, target_generation=True),
            replace(self.context, requested_at=self.now + timedelta(seconds=1)),
            replace(self.context, requested_at=self.now.replace(tzinfo=None)),
        ):
            self.assert_rejected(lambda: self.service.begin(value, "google"))
        for provider in ("unknown", True, []):
            self.assert_rejected(lambda: self.service.begin(self.context, provider))
        for changes in (
            {"lifetime": timedelta(0)},
            {"lifetime": timedelta(minutes=5, microseconds=1)},
            {"audience": ""},
            {"providers": {"unknown": (self.verifier, "fake")}},
            {"clock": None},
        ):
            self.assert_rejected(lambda: self.make_service(**changes))
        self.service.clock = Mock(side_effect=RuntimeError("fictional-private-clock"))
        self.assert_rejected(lambda: self.service.begin(self.context, "google"))
        self.verifier.verify.assert_not_called()

    def test_oversized_output_and_provider_exception_are_fixed_rejections(self):
        self.service = self.make_service(audience="\u754c" * 200)
        challenge = self.begin()
        self.verifier.verify.return_value = replace(
            self.verifier.verify.return_value, subject="\U0001f642" * 255
        )
        self.assert_rejected(
            lambda: self.service.authenticate(challenge["challenge_credential"], "fake")
        )
        self.verifier.verify.side_effect = RuntimeError("fictional-private-token")
        self.assert_rejected(
            lambda: self.service.authenticate(challenge["challenge_credential"], "fake")
        )
        self.assertEqual(self.verifier.verify.call_count, 2)

    def test_google_and_line_canonical_adapters_use_only_fake_io(self):
        for provider in ("google", "line"):
            claims = dict(
                iss=(
                    "https://accounts.google.com"
                    if provider == "google"
                    else "https://access.line.me"
                ),
                aud="fictional-client",
                sub="fictional-subject",
                exp=int((self.now + timedelta(minutes=3)).timestamp()),
            )
            adapter = (
                GoogleIdTokenVerifier(
                    lambda _: claims, audiences={"fictional-client", "other"}
                )
                if provider == "google"
                else LineIdTokenVerifier(
                    Mock(side_effect=lambda *_: (200, json.dumps(claims).encode()))
                )
            )
            self.service.providers[provider] = (adapter, "fictional-client")
            challenge = self.service.begin(self.context, provider)
            self.assert_rejected(
                lambda: self.service.authenticate(
                    challenge["challenge_credential"], "fake"
                )
            )
            claims["nonce"] = challenge["nonce"]
            token = self.service.authenticate(challenge["challenge_credential"], "fake")
            self.assertEqual(self.service(token).provider, provider)
            claims["aud"] = "other"
            self.assert_rejected(
                lambda: self.service.authenticate(
                    challenge["challenge_credential"], "fake"
                )
            )

    def test_apple_fixture_signature_and_hashed_server_nonce(self):
        from apps.mobile_api.tests.test_apple_verifier import (
            AppleIdTokenVerifierTest,
            FakeTransport,
        )

        AppleIdTokenVerifierTest.setUpClass()
        fixture = AppleIdTokenVerifierTest()
        adapter = fixture.verifier(FakeTransport(fixture.jwks_response()))
        self.service.providers["apple"] = (adapter, "fictional-client")
        challenge = self.service.begin(self.context, "apple")
        claims = fixture.claims(
            aud="fictional-client",
            sub="fictional-subject",
            iat=int(self.now.timestamp()),
            exp=int((self.now + timedelta(minutes=3)).timestamp()),
            nonce=hashlib.sha256(challenge["nonce"].encode()).hexdigest(),
        )
        token = self.service.authenticate(
            challenge["challenge_credential"], fixture.token(claims=claims)
        )
        self.assertEqual(self.service(token).provider, "apple")
        claims["nonce"] = hashlib.sha256(b"old-login-nonce").hexdigest()
        self.assert_rejected(
            lambda: self.service.authenticate(
                challenge["challenge_credential"], fixture.token(claims=claims)
            )
        )
