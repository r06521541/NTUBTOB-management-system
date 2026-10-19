"""Distinct cryptographic purpose; only fictional provider assertions."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from shared_module.erasure_cancellation_proof import (
    CancellationContext,
    CancellationProofRejected,
    CancellationProofService,
)
from shared_module.erasure_receipt_proof import (
    RECEIPT_VERIFICATION_PURPOSE,
    FreshReceiptVerificationProof,
    ReceiptVerificationContext,
    ReceiptVerificationProofService,
)
from shared_module.mobile_api import VerifiedAssertion


class ReceiptProofTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.verifier = Mock()
        config = dict(
            audience="fictional",
            lifetime=timedelta(minutes=2),
            providers={"apple": (self.verifier, "fictional-client")},
            clock=lambda: self.now,
        )
        self.service = ReceiptVerificationProofService(b"f" * 32, **config)
        self.cancellation = CancellationProofService(b"f" * 32, **config)
        args = (
            "11111111-1111-4111-8111-111111111111",
            "person",
            "22222222-2222-4222-8222-222222222222",
            self.now,
        )
        self.context = ReceiptVerificationContext(*args)
        self.cancel_context = CancellationContext(*args)

    def authenticate(self, service, challenge, subject="fictional-subject"):
        self.verifier.verify.return_value = VerifiedAssertion(
            "apple",
            subject,
            "fictional-client",
            challenge["nonce"],
            self.now + timedelta(minutes=3),
        )
        return service.authenticate(challenge["challenge_credential"], "fake-assertion")

    def test_same_key_and_audience_cannot_cross_cancellation_domains(self):
        first = self.service.begin(self.context, "apple")
        second = self.cancellation.begin(self.cancel_context, "apple")
        for destination, challenge in (
            (self.service, second),
            (self.cancellation, first),
        ):
            with self.assertRaises(CancellationProofRejected):
                destination.authenticate(challenge["challenge_credential"], "fake")
        self.verifier.verify.assert_not_called()
        verified = self.authenticate(self.service, first)
        with self.assertRaises(CancellationProofRejected):
            self.cancellation(verified)
        cancellation = self.authenticate(self.cancellation, second)
        with self.assertRaises(CancellationProofRejected):
            self.service(cancellation)

    def test_typed_contexts_are_not_interchangeable(self):
        for service, context in (
            (self.service, self.cancel_context),
            (self.cancellation, self.context),
        ):
            with self.assertRaises(CancellationProofRejected):
                service.begin(context, "apple")

    def test_subject_is_provider_resolved_and_proof_has_separate_type(self):
        challenge = self.service.begin(self.context, "apple")
        for subject in ("fictional-first", "fictional-second"):
            proof = self.service(self.authenticate(self.service, challenge, subject))
            self.assertIs(type(proof), FreshReceiptVerificationProof)
            self.assertEqual(proof.purpose, RECEIPT_VERIFICATION_PURPOSE)
            self.assertEqual(proof.provider_subject, subject)
            self.assertEqual(proof.target_generation, self.context.target_generation)
            self.assertNotIn(subject, repr(proof))

    def test_challenge_and_verified_expiry_cannot_be_renewed(self):
        challenge = self.service.begin(self.context, "apple")
        token = self.authenticate(self.service, challenge)
        self.now += timedelta(minutes=2)
        for operation in (
            lambda: self.service(token),
            lambda: self.authenticate(self.service, challenge),
        ):
            with self.assertRaises(CancellationProofRejected):
                operation()
