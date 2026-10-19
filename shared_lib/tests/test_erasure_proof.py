"""Fresh challenge exchange with fictional ID tokens; no network or real keys."""

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from shared_module.erasure_proof import ErasureProofService
from shared_module.mobile_api import VerifiedAssertion
from shared_module.portal_data.erasure_context import ErasureVerificationContext
from shared_module.portal_data.erasure_verification import ErasureVerificationRejected
from shared_module.provider_verifiers import GoogleIdTokenVerifier, LineIdTokenVerifier


class ErasureProofTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.context = ErasureVerificationContext(
            job_id="11111111-1111-4111-8111-111111111111",
            identity_id=2,
            provider="google",
            provider_subject="fictional-subject",
            identity_generation="22222222-2222-4222-8222-222222222222",
            target_kind="person",
            person_id=1,
            target_generation="33333333-3333-4333-8333-333333333333",
            requested_at=self.now,
        )
        self.verifier = Mock()
        self.service = ErasureProofService(
            b"f" * 32,
            audience="fictional-erasure",
            lifetime=timedelta(minutes=2),
            providers={"google": (self.verifier, "fictional-google-client")},
            clock=lambda: self.now,
        )

    def begin(self):
        result = self.service.begin(self.context)
        self.verifier.verify.return_value = VerifiedAssertion(
            "google",
            "fictional-subject",
            "fictional-google-client",
            result["nonce"],
            self.now + timedelta(minutes=3),
        )
        return result

    def test_oversized_encoded_payload_rejected_before_returning_challenge(self):
        self.service.audience = "界" * 200
        for subject in ("界" * 255, "\x00" * 255):
            with self.subTest(subject_length=len(subject)):
                with self.assertRaisesRegex(
                    ErasureVerificationRejected, "invalid_erasure_proof"
                ):
                    self.service.begin(replace(self.context, provider_subject=subject))
        self.verifier.verify.assert_not_called()

    def test_server_nonce_and_encrypted_proof_round_trip_without_local_io(self):
        challenge = self.begin()
        token = self.service.authenticate(
            challenge["challenge_credential"], "fake-id-token"
        )
        self.verifier.verify.assert_called_once_with(
            "fake-id-token", "fictional-google-client", challenge["nonce"], self.now
        )
        proof = self.service(token)
        self.assertEqual(proof.job_id, self.context.job_id)
        self.assertEqual(proof.identity_generation, self.context.identity_generation)
        self.assertEqual(proof.target_generation, self.context.target_generation)
        self.assertEqual(proof.provider_subject, "fictional-subject")
        self.assertEqual(proof.audience, "fictional-erasure")
        self.verifier.verify.assert_called_once()
        self.assertNotIn("fictional-subject", token)
        self.assertNotEqual(challenge["nonce"], self.begin()["nonce"])

    def test_challenge_is_not_verified_proof_and_proof_is_not_challenge(self):
        challenge = self.begin()
        with self.assertRaises(ErasureVerificationRejected):
            self.service(challenge["challenge_credential"])
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        self.verifier.reset_mock()
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(token, "fake")
        self.verifier.verify.assert_not_called()

    def test_provider_binding_mismatches_rejected(self):
        challenge = self.begin()
        original = self.verifier.verify.return_value
        for changes in (
            {"provider": "apple"},
            {"subject": "someone-else"},
            {"audience": "other-client"},
            {"nonce": None},
            {"nonce": "other"},
            {"expires_at": self.now},
        ):
            self.verifier.verify.return_value = replace(original, **changes)
            with self.assertRaises(ErasureVerificationRejected):
                self.service.authenticate(challenge["challenge_credential"], "fake")

    def test_google_real_adapter_requires_signed_nonce_and_exact_configured_audience(
        self,
    ):
        challenge = self.begin()
        claims = dict(
            iss="https://accounts.google.com",
            aud="fictional-google-client",
            sub="fictional-subject",
            exp=int((self.now + timedelta(minutes=3)).timestamp()),
        )
        adapter = GoogleIdTokenVerifier(
            lambda _: claims, audiences={"fictional-google-client", "other-client"}
        )
        self.service.providers["google"] = (adapter, "fictional-google-client")
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(challenge["challenge_credential"], "fake")
        claims["nonce"] = challenge["nonce"]
        self.assertEqual(
            self.service(
                self.service.authenticate(challenge["challenge_credential"], "fake")
            ).identity_id,
            2,
        )
        claims["aud"] = "other-client"
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(challenge["challenge_credential"], "fake")

    def test_expiry_during_provider_call_does_not_issue_proof_or_retry(self):
        challenge = self.begin()
        verified = self.verifier.verify.return_value

        def slow(*_):
            self.now += timedelta(minutes=3)
            return verified

        self.verifier.verify.side_effect = slow
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(challenge["challenge_credential"], "fake")
        self.verifier.verify.assert_called_once()

    def test_line_adapter_checks_challenge_nonce_from_fake_remote_response(self):
        claims = dict(
            iss="https://access.line.me",
            aud="fictional-line-client",
            sub="fictional-subject",
            exp=int((self.now + timedelta(minutes=3)).timestamp()),
        )
        transport = Mock(side_effect=lambda *_: (200, json.dumps(claims).encode()))
        self.service.providers["line"] = (
            LineIdTokenVerifier(transport),
            "fictional-line-client",
        )
        challenge = self.service.begin(replace(self.context, provider="line"))
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(challenge["challenge_credential"], "fake")
        claims["nonce"] = challenge["nonce"]
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        self.assertEqual(self.service(token).provider, "line")

    def test_apple_adapter_verifies_fixture_signature_and_hashed_server_nonce(self):
        from apps.mobile_api.tests.test_apple_verifier import (
            AppleIdTokenVerifierTest,
            FakeTransport,
        )

        AppleIdTokenVerifierTest.setUpClass()
        fixture = AppleIdTokenVerifierTest()
        adapter = fixture.verifier(FakeTransport(fixture.jwks_response()))
        self.service.providers["apple"] = (adapter, "fictional-apple-client")
        challenge = self.service.begin(replace(self.context, provider="apple"))
        claims = fixture.claims(
            aud="fictional-apple-client",
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
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(
                challenge["challenge_credential"], fixture.token(claims=claims)
            )

    def test_assertion_from_other_challenge_cannot_authorize_this_one(self):
        first = self.begin()
        first_verified = self.verifier.verify.return_value
        second = self.begin()
        self.verifier.verify.return_value = first_verified
        with self.assertRaises(ErasureVerificationRejected):
            self.service.authenticate(
                second["challenge_credential"], "fake-first-token"
            )
        self.assertNotEqual(first["nonce"], second["nonce"])

    def test_tampered_wrong_key_wrong_audience_and_expired_tokens_reject(self):
        challenge = self.begin()
        token = self.service.authenticate(challenge["challenge_credential"], "fake")
        for bad in (
            True,
            "",
            "ordinary-access-token",
            token[:40] + "!" + token[41:],
            token + "=",
        ):
            with self.assertRaises(ErasureVerificationRejected):
                self.service(bad)
        other = ErasureProofService(
            b"x" * 32,
            audience="fictional-erasure",
            lifetime=timedelta(minutes=2),
            providers={},
            clock=lambda: self.now,
        )
        with self.assertRaises(ErasureVerificationRejected):
            other(token)
        self.service.audience = "other-audience"
        with self.assertRaises(ErasureVerificationRejected):
            self.service(token)
        self.service.audience = "fictional-erasure"
        self.now += timedelta(minutes=2)
        with self.assertRaises(ErasureVerificationRejected):
            self.service(token)

    def test_untrusted_context_and_unknown_provider_reject_without_io(self):
        for context in (
            {},
            replace(self.context, requested_at=self.now + timedelta(seconds=1)),
            replace(self.context, provider="unknown"),
        ):
            with self.assertRaises(ErasureVerificationRejected):
                self.service.begin(context)
        self.verifier.verify.assert_not_called()

    def test_verifier_failure_is_sanitized_and_not_retried(self):
        challenge = self.begin()
        self.verifier.verify.side_effect = RuntimeError("fictional-private-token")
        with self.assertRaises(ErasureVerificationRejected) as result:
            self.service.authenticate(challenge["challenge_credential"], "fake")
        self.assertNotIn("fictional-private", str(result.exception))
        self.verifier.verify.assert_called_once()
