"""Restricted intent proof tests use only fictional keys and local verifiers."""

import base64
import hashlib
import hmac
import json
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from shared_module.erasure_restricted_proof import (
    RESTRICTED_ERASURE_PROOF_PURPOSE,
    ErasureRestrictedProofService,
    FreshRestrictedErasureProof,
    RestrictedErasureProofRejected,
)
from shared_module.mobile_api import VerifiedAssertion

KEY = b"fictional-restricted-master-key-32-bytes"
KEY_DOMAIN = b"account-erasure-restricted-intent-aead-v1"
AAD = "account-erasure-restricted-intent:"


class RestrictedProofTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.verifier = Mock()
        self.config = dict(
            audience="fictional-restricted-intent",
            lifetime=timedelta(minutes=2),
            providers={"google": (self.verifier, "fictional-google-client")},
            clock=lambda: self.now,
        )
        self.service = ErasureRestrictedProofService(KEY, **self.config)

    def begin(self, provider="google"):
        challenge = self.service.begin(provider)
        self.verifier.verify.return_value = VerifiedAssertion(
            provider,
            "fictional-subject",
            self.service.providers[provider][1],
            challenge["nonce"],
            self.now + timedelta(minutes=3),
        )
        return challenge

    def exchange(self, challenge=None):
        challenge = challenge or self.begin()
        return self.service.authenticate(
            challenge["challenge_credential"], "fake-assertion"
        )

    def decrypt(self, token, domain):
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        key = hmac.new(KEY, KEY_DOMAIN, hashlib.sha256).digest()
        return json.loads(
            AESGCM(key).decrypt(raw[:12], raw[12:], (AAD + domain).encode())
        )

    def forge(
        self, payload, domain="verified", *, key_domain=KEY_DOMAIN, aad_prefix=AAD
    ):
        plaintext = payload if type(payload) is str else json.dumps(payload)
        key = hmac.new(KEY, key_domain, hashlib.sha256).digest()
        nonce = b"fictional-IV"
        raw = nonce + AESGCM(key).encrypt(
            nonce, plaintext.encode(), (aad_prefix + domain).encode()
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    def rejected(self, operation):
        with self.assertRaisesRegex(
            RestrictedErasureProofRejected, "^invalid_restricted_erasure_proof$"
        ) as raised:
            operation()
        self.assertTrue(raised.exception.__suppress_context__)

    def test_round_trip_uses_server_attempt_nonce_and_exact_frozen_hidden_dto(self):
        challenge = self.begin()
        self.assertEqual(
            set(challenge), {"challenge_credential", "nonce", "provider", "expires_in"}
        )
        self.assertEqual(len(challenge["nonce"]), 43)
        self.assertEqual(challenge["expires_in"], 120)
        token = self.exchange(challenge)
        proof = self.service(token)
        self.assertIs(type(proof), FreshRestrictedErasureProof)
        self.assertEqual(str(UUID(proof.attempt_id)), proof.attempt_id)
        self.assertEqual(UUID(proof.attempt_id).version, 4)
        self.assertEqual(proof.provider_subject, "fictional-subject")
        self.assertEqual(proof.purpose, RESTRICTED_ERASURE_PROOF_PURPOSE)
        self.assertEqual(proof.audience, self.config["audience"])
        self.assertEqual(proof.authenticated_at, self.now)
        self.assertEqual(proof.expires_at, self.now + timedelta(minutes=2))
        self.assertEqual(
            {item.name for item in fields(proof)},
            {
                "attempt_id",
                "provider",
                "provider_subject",
                "authenticated_at",
                "expires_at",
                "purpose",
                "audience",
            },
        )
        self.verifier.verify.assert_called_once_with(
            "fake-assertion", "fictional-google-client", challenge["nonce"], self.now
        )
        with self.assertRaises(FrozenInstanceError):
            proof.provider_subject = "changed"
        self.assertNotIn("fictional-subject", repr(proof))
        self.assertNotIn(proof.attempt_id, repr(proof))
        self.assertNotIn("fictional-subject", token)

    def test_repeated_exchange_is_stateless_and_keeps_same_attempt_not_new_intent(self):
        challenge = self.begin()
        first = self.service(self.exchange(challenge))
        second = self.service(self.exchange(challenge))
        self.assertEqual(first.attempt_id, second.attempt_id)
        next_challenge = self.begin()
        third = self.service(self.exchange(next_challenge))
        self.assertNotEqual(first.attempt_id, third.attempt_id)
        self.assertNotEqual(challenge["nonce"], next_challenge["nonce"])

    def test_each_configured_provider_uses_its_own_audience(self):
        for provider in ("apple", "line", "google"):
            with self.subTest(provider=provider):
                self.service.providers[provider] = (
                    self.verifier,
                    "fictional-" + provider,
                )
                challenge = self.begin(provider)
                self.verifier.reset_mock()
                proof = self.service(self.exchange(challenge))
                self.assertEqual(proof.provider, provider)
                self.verifier.verify.assert_called_once_with(
                    "fake-assertion",
                    "fictional-" + provider,
                    challenge["nonce"],
                    self.now,
                )

    def test_provider_result_requires_exact_type_and_binding(self):
        challenge = self.begin()
        original = self.verifier.verify.return_value
        for value in (
            True,
            {},
            None,
            replace(original, provider="apple"),
            replace(original, provider=["google"]),
            replace(original, audience="other"),
            replace(original, nonce="other"),
            replace(original, nonce=None),
            replace(original, subject=""),
            replace(original, subject=" "),
            replace(original, subject=True),
            replace(original, subject="x" * 256),
            replace(original, expires_at=self.now),
            replace(original, expires_at=self.now.replace(tzinfo=None)),
        ):
            with self.subTest(value_type=type(value)):
                self.verifier.verify.return_value = value
                self.verifier.verify.reset_mock()
                self.rejected(lambda: self.exchange(challenge))
                self.verifier.verify.assert_called_once()

    def test_assertion_bounds_reject_before_verifier(self):
        challenge = self.begin()
        for assertion in (None, True, b"fake", "", "x" * 16385):
            self.rejected(
                lambda: self.service.authenticate(
                    challenge["challenge_credential"], assertion
                )
            )
        self.verifier.verify.assert_not_called()

    def test_unconfigured_or_untyped_provider_rejects_without_verifier(self):
        for provider in (None, True, [], {}, "apple", "unknown", "Google"):
            self.rejected(lambda: self.service.begin(provider))
        self.verifier.verify.assert_not_called()

    def test_provider_failure_is_fixed_and_not_retried(self):
        challenge = self.begin()
        self.verifier.verify.side_effect = RuntimeError("fictional-private-assertion")
        self.rejected(lambda: self.exchange(challenge))
        self.verifier.verify.assert_called_once()

    def test_expired_challenge_rejects_before_provider_call(self):
        challenge = self.begin()
        self.now += timedelta(minutes=2)
        self.rejected(lambda: self.exchange(challenge))
        self.verifier.verify.assert_not_called()

    def test_challenge_and_provider_expiry_are_rechecked_after_io(self):
        for expiry in (timedelta(minutes=2), timedelta(seconds=10)):
            self.setUp()
            challenge = self.begin()
            result = replace(
                self.verifier.verify.return_value, expires_at=self.now + expiry
            )

            def slow(*_):
                self.now += expiry
                return result

            self.verifier.verify.side_effect = slow
            self.rejected(lambda: self.exchange(challenge))
            self.verifier.verify.assert_called_once()

    def test_authentication_never_renews_original_window_and_caps_provider_expiry(self):
        challenge = self.begin()
        issued = self.now
        self.now += timedelta(seconds=30)
        result = replace(
            self.verifier.verify.return_value, expires_at=issued + timedelta(seconds=70)
        )
        self.verifier.verify.return_value = result
        token = self.exchange(challenge)
        proof = self.service(token)
        self.assertEqual(proof.authenticated_at, self.now)
        self.assertEqual(proof.expires_at, issued + timedelta(seconds=70))
        self.now = issued + timedelta(seconds=70)
        self.rejected(lambda: self.service(token))

    def test_clock_rollback_during_verification_rejects(self):
        challenge = self.begin()
        self.now += timedelta(seconds=30)
        result = self.verifier.verify.return_value

        def backward(*_):
            self.now -= timedelta(seconds=1)
            return result

        self.verifier.verify.side_effect = backward
        self.rejected(lambda: self.exchange(challenge))
        self.verifier.verify.assert_called_once()

    def test_clock_failures_are_fixed_at_each_boundary(self):
        challenge = self.begin()
        token = self.exchange(challenge)
        for clock in (
            Mock(side_effect=RuntimeError("fictional-private-clock")),
            lambda: None,
            lambda: self.now.replace(tzinfo=None),
        ):
            self.service.clock = clock
            for call in (
                lambda: self.service.begin("google"),
                lambda: self.exchange(challenge),
                lambda: self.service(token),
            ):
                self.rejected(call)

    def test_post_provider_clock_failure_cannot_issue_proof(self):
        challenge = self.begin()
        for value in (
            RuntimeError("fictional-private-clock"),
            None,
            self.now.replace(tzinfo=None),
        ):
            with self.subTest(value_type=type(value)):
                self.service.clock = Mock(side_effect=[self.now, value])
                self.verifier.verify.reset_mock()
                self.rejected(lambda: self.exchange(challenge))
                self.verifier.verify.assert_called_once()

    def test_encoded_size_bound_applies_after_provider_verification(self):
        self.service = ErasureRestrictedProofService(
            KEY, **{**self.config, "audience": "\U0001f642" * 200}
        )
        challenge = self.begin()
        self.verifier.verify.return_value = replace(
            self.verifier.verify.return_value, subject="\U0001f642" * 255
        )
        self.rejected(lambda: self.exchange(challenge))
        self.verifier.verify.assert_called_once()

    def test_challenge_verified_and_other_key_domains_cannot_cross(self):
        challenge = self.begin()
        token = self.exchange(challenge)
        self.rejected(lambda: self.service(challenge["challenge_credential"]))
        self.verifier.reset_mock()
        self.rejected(lambda: self.service.authenticate(token, "fake"))
        self.verifier.verify.assert_not_called()
        payload = self.decrypt(token, "verified")
        for domain in (
            b"account-erasure-proof-aead-v1",
            b"account-erasure-cancellation-aead-v1",
            b"fictional-login-or-link",
        ):
            self.rejected(lambda: self.service(self.forge(payload, key_domain=domain)))
        for aad in (
            "account-erasure:",
            "account-erasure-cancellation:",
            "identity-link:",
        ):
            self.rejected(lambda: self.service(self.forge(payload, aad_prefix=aad)))

    def test_wrong_key_audience_and_tampering_reject(self):
        token = self.exchange()
        self.rejected(
            lambda: ErasureRestrictedProofService(b"x" * 32, **self.config)(token)
        )
        other = ErasureRestrictedProofService(
            KEY, **{**self.config, "audience": "other"}
        )
        self.rejected(lambda: other(token))
        offset = len(token) // 2
        changed = "A" if token[offset] != "A" else "B"
        self.rejected(
            lambda: self.service(token[:offset] + changed + token[offset + 1 :])
        )

    def test_noncanonical_base64_types_and_bounds_reject(self):
        token = self.exchange()
        for value in (
            None,
            True,
            b"fake",
            "",
            "x" * 79,
            "x" * 4097,
            token + "=",
            token + "\n",
            "ordinary.login.token",
        ):
            self.rejected(lambda: self.service(value))
        payload = self.decrypt(token, "verified")
        for size in range(3):
            encoded = self.forge(json.dumps(payload) + " " * size)
            if len(encoded) % 4 in (2, 3):
                alphabet = (
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                )
                alias = encoded[:-1] + alphabet[alphabet.index(encoded[-1]) + 1]
                self.rejected(lambda: self.service(alias))
                break
        else:
            self.fail("fixture must include unused base64 bits")

    def test_duplicate_fields_nonobjects_nonfinite_and_deep_json_reject(self):
        payload = self.decrypt(self.exchange(), "verified")
        serialized = json.dumps(payload)
        for value in (
            serialized[:-1] + ',"provider":"google"}',
            "[]",
            "null",
            "true",
            "NaN",
            serialized.replace('"google"', "NaN"),
            "[" * 1100 + "0" + "]" * 1100,
        ):
            self.rejected(lambda: self.service(self.forge(value)))

    def test_verified_fieldset_types_uuid_subject_purpose_and_dates_are_strict(self):
        original = self.decrypt(self.exchange(), "verified")
        changes = (
            {"attempt_id": "AAAAAAAA-AAAA-4AAA-AAAA-AAAAAAAAAAAA"},
            {"attempt_id": "0" * 32},
            {"attempt_id": None},
            {"provider": []},
            {"provider": "unknown"},
            {"provider_subject": ""},
            {"provider_subject": 7},
            {"provider_subject": "x" * 256},
            {"purpose": "account_erasure_verification"},
            {"purpose": True},
            {"audience": []},
            {"issued_at": None},
            {"issued_at": self.now.timestamp()},
            {"issued_at": self.now.replace(tzinfo=None).isoformat()},
            {"issued_at": "2035-01-01T08:00:00+08:00"},
            {"issued_at": "2035-01-01 00:00:00+00:00"},
            {"authenticated_at": (self.now - timedelta(seconds=1)).isoformat()},
            {"authenticated_at": (self.now + timedelta(seconds=1)).isoformat()},
            {"expires_at": (self.now + timedelta(minutes=6)).isoformat()},
            {"job_id": "client-selected"},
            {"identity_id": 9},
            {"person_id": 7},
        )
        for change in changes:
            with self.subTest(fields=tuple(change)):
                self.rejected(lambda: self.service(self.forge({**original, **change})))
        for name in original:
            self.rejected(
                lambda: self.service(
                    self.forge({k: v for k, v in original.items() if k != name})
                )
            )

    def test_challenge_nonce_fieldset_and_dates_are_strict_before_io(self):
        challenge = self.begin()
        payload = self.decrypt(challenge["challenge_credential"], "challenge")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        alias = (
            payload["nonce"][:-1] + alphabet[alphabet.index(payload["nonce"][-1]) + 1]
        )
        for change in (
            {"nonce": None},
            {"nonce": "x" * 42},
            {"nonce": alias},
            {"provider_subject": "client-selected"},
            {"person_id": 7},
            {"issued_at": (self.now + timedelta(seconds=1)).isoformat()},
            {"expires_at": (self.now + timedelta(minutes=6)).isoformat()},
        ):
            self.rejected(
                lambda: self.service.authenticate(
                    self.forge({**payload, **change}, "challenge"), "fake"
                )
            )
        self.verifier.verify.assert_not_called()

    def test_configuration_bounds_are_fixed(self):
        for changes in (
            {"audience": ""},
            {"audience": "x" * 201},
            {"audience": True},
            {"lifetime": timedelta(0)},
            {"lifetime": timedelta(minutes=5, microseconds=1)},
            {"lifetime": 120},
            {"providers": []},
            {"clock": None},
            {"providers": {"unknown": (self.verifier, "client")}},
            {"providers": {"google": [self.verifier, "client"]}},
            {"providers": {"google": (None, "client")}},
            {"providers": {"google": (self.verifier, "")}},
        ):
            self.rejected(
                lambda: ErasureRestrictedProofService(KEY, **{**self.config, **changes})
            )
        for key in (None, "fake", b"x" * 31):
            self.rejected(lambda: ErasureRestrictedProofService(key, **self.config))


if __name__ == "__main__":
    unittest.main()
