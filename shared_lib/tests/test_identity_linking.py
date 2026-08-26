import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from shared_module.identity_linking import (
    IdentityLinkConflict,
    IdentityLinkProofCodec,
    IdentityLinkService,
    IdentityLinkResult,
    InternalWebPrincipal,
)
from shared_module.mobile_api import HmacAccessTokenCodec
from shared_module.mobile_api import AuthenticationError
from shared_module.portal_data.mobile_repository import MobileRepository


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

    def test_public_proofs_are_confidential_not_base64_json(self):
        candidate = self.codec.issue_candidate(
            identity_id=41,
            provider="google",
            identity_updated_at=NOW,
            assertion_hash="a" * 64,
            attempt_hash="b" * 64,
            binding_hash="c" * 64,
            jti="candidate-jti-123456",
            now=NOW,
        )
        fresh = self.codec.issue_fresh_proof(
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
        for token in (candidate, fresh):
            decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            with self.assertRaises((UnicodeDecodeError, json.JSONDecodeError)):
                json.loads(decoded.decode("utf-8"))
            self.assertNotIn(b'"iid"', decoded)
            self.assertNotIn(b'"pid"', decoded)

        tampered = candidate[:-1] + ("A" if candidate[-1] != "A" else "B")
        with self.assertRaises(AuthenticationError):
            self.codec.verify_candidate(tampered, NOW)

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

    def test_fictional_negative_bigint_identity_proof_is_valid(self):
        token = self.codec.issue_fresh_proof(
            identity_id=-112001,
            person_id=-112001,
            provider="line",
            identity_updated_at=NOW,
            candidate_jti="candidate-jti-123456",
            attempt_hash="d" * 64,
            binding_hash="c" * 64,
            jti="proof-jti-123456789",
            now=NOW,
        )
        proof = self.codec.verify_fresh_proof(token, NOW)
        self.assertEqual((proof.identity_id, proof.person_id), (-112001, -112001))

    def test_zero_and_out_of_bigint_identity_proofs_are_rejected(self):
        for identity_id, person_id in (
            (0, 9),
            (7, 0),
            (-(2**63) - 1, 9),
            (7, 2**63),
        ):
            with self.subTest(identity_id=identity_id, person_id=person_id):
                token = self.codec.issue_fresh_proof(
                    identity_id=identity_id,
                    person_id=person_id,
                    provider="line",
                    identity_updated_at=NOW,
                    candidate_jti="candidate-jti-123456",
                    attempt_hash="d" * 64,
                    binding_hash="c" * 64,
                    jti="proof-jti-123456789",
                    now=NOW,
                )
                with self.assertRaises(AuthenticationError):
                    self.codec.verify_fresh_proof(token, NOW)

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

    def test_repository_proof_snapshot_uses_exact_orm_version_timestamp(self):
        repository = MobileRepository(Mock())
        repository.lifecycle.resolve_principal = Mock(
            return_value=SimpleNamespace(
                identity=SimpleNamespace(id=-112001, provider="line"),
                person=SimpleNamespace(id=-112001, display_name="Fictional Tester"),
            )
        )
        session = MagicMock()
        session.__enter__.return_value = session
        session.scalar.return_value = NOW
        with patch(
            "shared_module.portal_data.mobile_repository.Session",
            return_value=session,
        ):
            snapshot = repository.linked_identity_for_proof(
                "line", "private-subject", NOW
            )
        self.assertEqual(snapshot["updated_at"], NOW)
        self.assertEqual(snapshot["identity_id"], -112001)
        self.assertNotIn("private-subject", str(snapshot))

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
