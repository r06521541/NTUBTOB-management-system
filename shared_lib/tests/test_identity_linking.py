import unittest
from datetime import datetime, timedelta, timezone

from shared_module.identity_linking import (
    IdentityLinkConflict,
    IdentityLinkProofCodec,
    IdentityLinkService,
    IdentityLinkResult,
    InternalWebPrincipal,
)
from shared_module.mobile_api import HmacAccessTokenCodec
from shared_module.mobile_api import AuthenticationError


NOW = datetime(2026, 8, 24, 12, 0, 0, 123456, timezone.utc)


class IdentityLinkProofCodecTest(unittest.TestCase):
    def setUp(self):
        self.codec = IdentityLinkProofCodec(b"k" * 32)

    def test_candidate_is_exact_purpose_bound_redacted_and_short_lived(self):
        token = self.codec.issue_candidate(
            identity_id=41,
            provider="google",
            identity_updated_at=NOW,
            assertion_hash="a" * 64,
            attempt_hash="b" * 64,
            binding_hash="c" * 64,
            jti="candidate-jti-123456",
            now=NOW,
        )
        proof = self.codec.verify_candidate(token, NOW + timedelta(minutes=4))
        self.assertEqual(proof.identity_id, 41)
        self.assertEqual(proof.provider, "google")
        self.assertNotIn("subject", token)
        self.assertNotIn("email", token)
        with self.assertRaises(AuthenticationError):
            self.codec.verify_candidate(token, NOW + timedelta(minutes=5))
        with self.assertRaises(AuthenticationError):
            self.codec.verify_fresh_proof(token, NOW)

    def test_canonical_version_is_utc_microsecond_hmac(self):
        same = NOW.astimezone(timezone(timedelta(hours=8)))
        first = self.codec.identity_version_hash(41, NOW)
        second = self.codec.identity_version_hash(41, same)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("2026", first)

    def test_fresh_proof_is_bound_to_candidate_jti_binding_and_provider(self):
        token = self.codec.issue_fresh_proof(
            identity_id=7,
            person_id=9,
            provider="line",
            identity_updated_at=NOW,
            candidate_jti="candidate-jti-123456",
            attempt_hash="d" * 64,
            binding_hash="c" * 64,
            jti="proof-jti-123456789",
            now=NOW,
        )
        proof = self.codec.verify_fresh_proof(token, NOW)
        self.assertEqual(proof.person_id, 9)
        self.assertEqual(proof.candidate_jti, "candidate-jti-123456")
        with self.assertRaises(IdentityLinkConflict):
            self.codec.validate_pair(
                candidate=self.codec.verify_candidate(
                    self.codec.issue_candidate(
                        identity_id=41,
                        provider="google",
                        identity_updated_at=NOW,
                        assertion_hash="a" * 64,
                        attempt_hash="b" * 64,
                        binding_hash="x" * 64,
                        jti="candidate-jti-123456",
                        now=NOW,
                    ),
                    NOW,
                ),
                proof=proof,
            )

    def test_cross_provider_is_mandatory(self):
        candidate = self.codec.verify_candidate(
            self.codec.issue_candidate(
                identity_id=41,
                provider="line",
                identity_updated_at=NOW,
                assertion_hash="a" * 64,
                attempt_hash="b" * 64,
                binding_hash="c" * 64,
                jti="candidate-jti-123456",
                now=NOW,
            ),
            NOW,
        )
        proof = self.codec.verify_fresh_proof(
            self.codec.issue_fresh_proof(
                identity_id=7,
                person_id=9,
                provider="line",
                identity_updated_at=NOW,
                candidate_jti=candidate.jti,
                attempt_hash="d" * 64,
                binding_hash="c" * 64,
                jti="proof-jti-123456789",
                now=NOW,
            ),
            NOW,
        )
        with self.assertRaises(IdentityLinkConflict):
            self.codec.validate_pair(candidate=candidate, proof=proof)


class _RecoveryAuth:
    token_codec = HmacAccessTokenCodec(b"a" * 32)

    @staticmethod
    def token_factory():
        return "refresh-token-which-is-long-enough-for-a-test"


class _Repository:
    def __init__(self):
        self.confirmations = []

    def confirm_identity_link(self, **values):
        self.confirmations.append(values)
        return {"status": "linked", "session": {"session_id": "one"}}


class IdentityLinkServiceTest(unittest.TestCase):
    def test_mobile_public_serializer_never_includes_internal_principal(self):
        result = IdentityLinkResult(
            "already_linked", web_principal=InternalWebPrincipal(23, 7, 7001)
        )
        self.assertEqual(
            result.mobile_public(), {"status": "already_linked", "session": None}
        )
        self.assertNotIn("23", str(result.mobile_public()))

    def test_recovery_confirmation_passes_only_hashed_session_material(self):
        codec, repository = IdentityLinkProofCodec(b"k" * 32), _Repository()
        candidate = codec.issue_candidate(
            identity_id=41,
            provider="google",
            identity_updated_at=NOW,
            assertion_hash="a" * 64,
            attempt_hash="b" * 64,
            binding_hash=IdentityLinkService._hash("install-1234567890"),
            jti="candidate-jti-123456",
            now=NOW,
        )
        proof = codec.issue_fresh_proof(
            identity_id=7,
            person_id=9,
            provider="line",
            identity_updated_at=NOW,
            candidate_jti="candidate-jti-123456",
            attempt_hash="d" * 64,
            binding_hash=IdentityLinkService._hash("install-1234567890"),
            jti="proof-jti-123456789",
            now=NOW,
        )
        service = IdentityLinkService(
            repository, codec, clock=lambda: NOW, recovery_auth=_RecoveryAuth()
        )
        service.confirm_mobile(
            candidate_credential=candidate,
            proof_credential=proof,
            binding="install-1234567890",
            outcome="recovery_link",
            platform="android",
        )
        recovery = repository.confirmations[0]["recovery"]
        self.assertEqual(recovery["platform"], "android")
        self.assertEqual(len(recovery["refresh_hash"]), 64)
        self.assertNotEqual(recovery["refresh_hash"], recovery["refresh"])
