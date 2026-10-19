"""Recovery proof reuse: fictional keys/providers, no DB or native login."""

import base64
import hashlib
import hmac
import json
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from shared_module import erasure_restricted_proof as restricted
from shared_module.erasure_cancellation_proof import (
    CancellationContext,
    CancellationProofRejected,
    CancellationProofService,
)
from shared_module.erasure_receipt_proof import (
    ReceiptVerificationContext,
    ReceiptVerificationProofService,
)
from shared_module.erasure_recovery_proof import (
    RECEIPT_RECOVERY_PURPOSE,
    ErasureReceiptRecoveryProofService,
    FreshReceiptRecoveryProof,
)
from shared_module.mobile_api import VerifiedAssertion
from shared_module.portal_data import erasure_receipt_recovery as repository
from sqlalchemy.engine import Engine

KEY = b"fictional-recovery-proof-master-key-12345"
KEY_DOMAIN = b"account-erasure-receipt-recovery-aead-v1"
AAD = "account-erasure-receipt-recovery:"
ASSERTION = "fictional-private-provider-assertion"


class RecoveryProofTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.verifier = Mock()
        self.config = dict(
            audience="fictional-proof-audience",
            lifetime=timedelta(minutes=5),
            providers={
                provider: (self.verifier, "fictional-" + provider + "-client")
                for provider in ("apple", "google", "line")
            },
            clock=lambda: self.now,
        )
        self.service = ErasureReceiptRecoveryProofService(KEY, **self.config)

    def begin(self, service=None, provider="apple"):
        return (service or self.service).begin(provider)

    def exchange(self, challenge, service=None, **changes):
        service = service or self.service
        verified = VerifiedAssertion(
            challenge["provider"],
            "fictional-subject",
            self.config["providers"][challenge["provider"]][1],
            challenge["nonce"],
            self.now + timedelta(minutes=10),
        )
        self.verifier.verify.return_value = replace(verified, **changes)
        return service.authenticate(challenge["challenge_credential"], ASSERTION)

    def decrypt(self, token, domain="verified"):
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        return json.loads(
            AESGCM(hmac.new(KEY, KEY_DOMAIN, hashlib.sha256).digest()).decrypt(
                raw[:12], raw[12:], (AAD + domain).encode("ascii")
            )
        )

    def forge(
        self, payload, *, key_domain=KEY_DOMAIN, aad_prefix=AAD, domain="verified"
    ):
        plaintext = payload if type(payload) is str else json.dumps(payload)
        nonce = b"fictional-IV"
        raw = nonce + AESGCM(
            hmac.new(KEY, key_domain, hashlib.sha256).digest()
        ).encrypt(
            nonce, plaintext.encode("utf-8"), (aad_prefix + domain).encode("ascii")
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def rejected(self, operation):
        with self.assertRaisesRegex(
            restricted.RestrictedErasureProofRejected,
            "^invalid_restricted_erasure_proof$",
        ) as raised:
            operation()
        self.assertTrue(raised.exception.__suppress_context__)
        self.assertIsNone(raised.exception.__cause__)

    def test_each_provider_roundtrip_keeps_original_issue_and_hidden_frozen_dto(self):
        for provider in ("apple", "google", "line"):
            with self.subTest(provider=provider):
                issued = self.now
                challenge = self.begin(provider=provider)
                self.now += timedelta(seconds=10)
                self.verifier.reset_mock()
                token = self.exchange(challenge)
                result = self.service(token)
                self.assertIs(type(result), FreshReceiptRecoveryProof)
                self.assertEqual(result.issued_at, issued)
                self.assertEqual(result.authenticated_at, self.now)
                self.assertEqual(result.expires_at, issued + timedelta(minutes=5))
                self.assertEqual(result.provider, provider)
                self.assertEqual(result.purpose, RECEIPT_RECOVERY_PURPOSE)
                self.assertEqual(result.audience, self.config["audience"])
                self.assertEqual(
                    {field.name for field in fields(result)},
                    {
                        "provider",
                        "provider_subject",
                        "issued_at",
                        "authenticated_at",
                        "expires_at",
                        "purpose",
                        "audience",
                    },
                )
                self.verifier.verify.assert_called_once_with(
                    ASSERTION,
                    "fictional-" + provider + "-client",
                    challenge["nonce"],
                    self.now,
                )
                self.assertNotIn(result.provider_subject, repr(result))
                with self.assertRaises(FrozenInstanceError):
                    result.issued_at = self.now

    def test_repository_reexports_exact_dto_and_accepts_local_codec_output(self):
        self.assertIs(repository.FreshReceiptRecoveryProof, FreshReceiptRecoveryProof)
        self.assertEqual(repository.RECEIPT_RECOVERY_PURPOSE, RECEIPT_RECOVERY_PURPOSE)
        token = self.exchange(self.begin())
        engine = Mock(spec=Engine)
        engine.dialect = SimpleNamespace(name="postgresql")
        repo = repository.ReceiptRecoveryRepository(
            engine,
            KEY,
            verifier=self.service,
            audience=self.config["audience"],
            clock=lambda: self.now,
        )
        self.verifier.verify.reset_mock()
        first, now = repo._proof(token)
        second, _ = repo._proof(token)
        self.assertEqual(first, second)
        self.assertEqual(now, self.now)
        self.verifier.verify.assert_not_called()

    def test_provider_assertion_and_nonce_are_not_retained_in_verified_payload(self):
        challenge = self.begin()
        challenge_payload = self.decrypt(challenge["challenge_credential"], "challenge")
        self.assertNotIn("provider_subject", challenge_payload)
        token = self.exchange(challenge)
        payload = self.decrypt(token)
        self.assertEqual(
            set(payload),
            {
                "attempt_id",
                "provider",
                "issued_at",
                "expires_at",
                "purpose",
                "audience",
                "provider_subject",
                "authenticated_at",
            },
        )
        self.assertNotIn(ASSERTION, json.dumps(payload))
        self.assertNotIn(challenge["nonce"], json.dumps(payload))
        self.assertNotIn("job_id", payload)
        self.assertNotIn("target_generation", payload)
        self.assertNotIn("identity_id", payload)
        self.verifier.reset_mock()
        self.assertEqual(self.service(token), self.service(token))
        self.verifier.verify.assert_not_called()

    def test_server_challenges_have_distinct_nonces_and_no_target_input(self):
        first, second = self.begin(), self.begin()
        self.assertNotEqual(first["nonce"], second["nonce"])
        self.assertEqual(len(base64.urlsafe_b64decode(first["nonce"] + "=")), 32)
        with self.assertRaises(TypeError):
            self.service.begin("apple", job_id="fictional-client-job")
        for parameter in ("purpose", "key_domain", "aad_prefix", "proof_factory"):
            with self.assertRaises(TypeError):
                ErasureReceiptRecoveryProofService(
                    KEY, **dict(self.config, **{parameter: "client-selected"})
                )

    def test_restricted_intent_challenges_and_proofs_cannot_cross(self):
        old = restricted.ErasureRestrictedProofService(KEY, **self.config)
        old_challenge, new_challenge = self.begin(old), self.begin()
        for destination, challenge in (
            (old, new_challenge),
            (self.service, old_challenge),
        ):
            self.verifier.reset_mock()
            self.rejected(
                lambda: destination.authenticate(
                    challenge["challenge_credential"], ASSERTION
                )
            )
            self.verifier.verify.assert_not_called()
        old_token = self.exchange(old_challenge, old)
        new_token = self.exchange(new_challenge)
        self.rejected(lambda: old(new_token))
        self.rejected(lambda: self.service(old_token))

    def test_receipt_verification_and_cancellation_cannot_cross_recovery(self):
        args = (
            "11111111-1111-4111-8111-111111111111",
            "person",
            "22222222-2222-4222-8222-222222222222",
            self.now,
        )
        for service_type, context_type in (
            (CancellationProofService, CancellationContext),
            (ReceiptVerificationProofService, ReceiptVerificationContext),
        ):
            old = service_type(KEY, **self.config)
            old_challenge = old.begin(context_type(*args), "apple")
            new_challenge = self.begin()
            self.verifier.reset_mock()
            self.rejected(
                lambda: self.service.authenticate(
                    old_challenge["challenge_credential"], ASSERTION
                )
            )
            with self.assertRaises(CancellationProofRejected):
                old.authenticate(new_challenge["challenge_credential"], ASSERTION)
            self.verifier.verify.assert_not_called()
            old_token = self.exchange(old_challenge, old)
            new_token = self.exchange(new_challenge)
            self.rejected(lambda: self.service(old_token))
            with self.assertRaises(CancellationProofRejected):
                old(new_token)

    def test_key_aad_and_purpose_are_independently_separated(self):
        payload = self.decrypt(self.exchange(self.begin()))
        for domain in (
            b"account-erasure-restricted-intent-aead-v1",
            b"account-erasure-cancellation-aead-v1",
            b"account-erasure-receipt-verification-aead-v1",
            b"account-erasure-proof-aead-v1",
        ):
            self.rejected(lambda: self.service(self.forge(payload, key_domain=domain)))
        for aad in (
            "account-erasure-restricted-intent:",
            "account-erasure-cancellation:",
            "account-erasure-receipt-verification:",
            "account-erasure:",
        ):
            self.rejected(lambda: self.service(self.forge(payload, aad_prefix=aad)))
        for purpose in (
            restricted.RESTRICTED_ERASURE_PROOF_PURPOSE,
            "account_erasure_receipt_verification",
            "account_erasure_cancellation",
        ):
            self.rejected(
                lambda: self.service(self.forge(dict(payload, purpose=purpose)))
            )

    def test_original_five_minute_window_cannot_restart_at_authentication(self):
        issued = self.now
        challenge = self.begin()
        self.now += timedelta(minutes=4, seconds=59)
        token = self.exchange(challenge)
        result = self.service(token)
        self.assertEqual(result.issued_at, issued)
        self.assertEqual(result.expires_at, issued + timedelta(minutes=5))
        self.now += timedelta(seconds=1)
        self.rejected(lambda: self.service(token))
        self.verifier.reset_mock()
        self.rejected(lambda: self.exchange(challenge))
        self.verifier.verify.assert_not_called()

    def test_provider_expiry_can_only_shorten_the_original_deadline(self):
        issued = self.now
        challenge = self.begin()
        self.now += timedelta(seconds=30)
        expiry = issued + timedelta(seconds=70)
        result = self.service(self.exchange(challenge, expires_at=expiry))
        self.assertEqual((result.issued_at, result.expires_at), (issued, expiry))

    def test_provider_binding_exceptions_and_clock_changes_are_fixed(self):
        challenge = self.begin()
        for changes in (
            {"provider": "google"},
            {"audience": "wrong"},
            {"nonce": "wrong"},
            {"subject": " "},
            {"expires_at": self.now},
        ):
            self.verifier.reset_mock()
            self.rejected(lambda: self.exchange(challenge, **changes))
            self.verifier.verify.assert_called_once()
        self.verifier.verify.side_effect = RuntimeError(ASSERTION)
        self.rejected(lambda: self.exchange(challenge))
        self.verifier.verify.side_effect = None
        for movement in (timedelta(minutes=5), -timedelta(seconds=1)):
            start = self.now
            challenge = self.begin()
            verified = VerifiedAssertion(
                "apple",
                "fictional-subject",
                "fictional-apple-client",
                challenge["nonce"],
                self.now + timedelta(minutes=10),
            )

            def moving_clock(*args):
                self.now += movement
                return verified

            self.verifier.verify.side_effect = moving_clock
            self.rejected(lambda: self.exchange(challenge))
            self.now = start
        self.service.clock = Mock(side_effect=RuntimeError(ASSERTION))
        self.rejected(lambda: self.begin())

    def test_tampering_stage_swap_noncanonical_and_bad_input_reject(self):
        challenge = self.begin()
        token = self.exchange(challenge)
        self.rejected(lambda: self.service(challenge["challenge_credential"]))
        self.verifier.reset_mock()
        self.rejected(lambda: self.service.authenticate(token, ASSERTION))
        self.verifier.verify.assert_not_called()
        for bad in (
            None,
            True,
            "ordinary.login.token",
            token + "=",
            token + "\n",
            "x" * 79,
            "x" * 4097,
            ("A" if token[0] != "A" else "B") + token[1:],
        ):
            self.rejected(lambda: self.service(bad))
        self.rejected(
            lambda: ErasureReceiptRecoveryProofService(b"z" * 32, **self.config)(token)
        )
        self.rejected(
            lambda: ErasureReceiptRecoveryProofService(
                KEY, **dict(self.config, audience="wrong")
            )(token)
        )

    def test_strict_verified_fields_reject_client_context_and_renewed_issue(self):
        payload = self.decrypt(self.exchange(self.begin()))
        for change in (
            {"job_id": "fictional"},
            {"target_generation": "fictional"},
            {"identity_id": 42},
            {"provider_assertion": ASSERTION},
            {"issued_at": (self.now + timedelta(seconds=1)).isoformat()},
            {"issued_at": (self.now - timedelta(seconds=1)).isoformat()},
            {"authenticated_at": (self.now - timedelta(seconds=1)).isoformat()},
            {"expires_at": (self.now + timedelta(minutes=5, seconds=1)).isoformat()},
        ):
            self.rejected(lambda: self.service(self.forge(dict(payload, **change))))
        duplicated = json.dumps(payload)[:-1] + ',"purpose":"duplicate"}'
        self.rejected(lambda: self.service(self.forge(duplicated)))

    def test_default_restricted_wire_bytes_and_dto_remain_unchanged(self):
        old = restricted.ErasureRestrictedProofService(KEY, **self.config)
        nonce = base64.urlsafe_b64encode(b"n" * 32).rstrip(b"=").decode("ascii")
        with (
            patch.object(
                restricted,
                "uuid4",
                return_value=UUID("11111111-1111-4111-8111-111111111111"),
            ),
            patch.object(restricted.secrets, "token_urlsafe", return_value=nonce),
            patch.object(restricted.secrets, "token_bytes", return_value=b"v" * 12),
        ):
            challenge = self.begin(old)
            token = self.exchange(challenge, old)
        self.assertEqual(
            hashlib.sha256(challenge["challenge_credential"].encode()).hexdigest(),
            "4fc0c9b2956a979fe90649daa2ac763fbdcf627fa669526d3552373b29f06b99",
        )
        self.assertEqual(
            hashlib.sha256(token.encode()).hexdigest(),
            "ea12e062ac02a467ebaa209c9871ef5c8a37c7e8f5d115d4f032e79a75a3c5ae",
        )
        self.assertIs(type(old(token)), restricted.FreshRestrictedErasureProof)
        self.assertNotIn("issued_at", {field.name for field in fields(old(token))})


if __name__ == "__main__":
    unittest.main()
