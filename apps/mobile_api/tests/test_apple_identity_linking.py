import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shared_module.identity_linking import IdentityLinkProofCodec, IdentityLinkService
from shared_module.portal_data.mobile_repository import MobileRepository
from shared_module.portal_data.models import AccessAuditRecord, AuthIdentityRecord

NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)


class IdentityRepositoryDouble:
    def __init__(self):
        self.ensure_apple_link_candidate = Mock(
            return_value={
                "identity_id": 31,
                "provider": "apple",
                "status": "pending",
                "person_id": None,
                "updated_at": NOW,
            }
        )
        self.linked_identity_for_proof = Mock(
            return_value={
                "identity_id": 32,
                "person_id": 41,
                "provider": "google",
                "updated_at": NOW,
                "display_name": "測試球員",
            }
        )


class AppleIdentityLinkingTest(unittest.TestCase):
    def setUp(self):
        self.repository = IdentityRepositoryDouble()
        self.codec = IdentityLinkProofCodec(b"fictional-proof-key" * 2)
        self.service = IdentityLinkService(
            self.repository, self.codec, clock=lambda: NOW
        )

    def test_apple_candidate_is_keyed_only_by_verified_subject(self):
        result = self.service.begin_candidate(
            provider="apple",
            subject="fictional-apple-stable-subject",
            raw_assertion="fictional-apple-assertion",
            attempt_id="fictional-attempt-id",
            binding="fictional-installation-id",
        )

        self.assertEqual(result["candidate_provider"], "apple")
        self.repository.ensure_apple_link_candidate.assert_called_once()
        call = self.repository.ensure_apple_link_candidate.call_args.args
        self.assertEqual(call[0], "fictional-apple-stable-subject")
        self.assertTrue(call[1].startswith("identity-pending-"))
        self.assertNotIn("email", repr(call).lower())
        self.assertNotIn("name", repr(call).lower())
        proof = self.codec.verify_candidate(result["candidate_credential"], NOW)
        self.assertEqual(proof.provider, "apple")

    def test_apple_candidate_accepts_a_fresh_different_provider_proof(self):
        candidate = self.service.begin_candidate(
            provider="apple",
            subject="fictional-apple-stable-subject",
            raw_assertion="fictional-apple-assertion",
            attempt_id="fictional-attempt-id",
            binding="fictional-installation-id",
        )
        proof_result = self.service.issue_fresh_proof(
            candidate_credential=candidate["candidate_credential"],
            provider="google",
            subject="fictional-google-stable-subject",
            attempt_id="fictional-proof-attempt",
            binding="fictional-installation-id",
        )

        self.assertEqual(proof_result["candidate_provider"], "apple")
        self.assertEqual(proof_result["proof_provider"], "google")
        proof = self.codec.verify_fresh_proof(proof_result["proof_credential"], NOW)
        self.assertEqual(proof.provider, "google")

    def test_repository_creates_pending_apple_identity_without_profile_merge(self):
        session = _FakeSession()
        repository = MobileRepository(object())
        repository.lifecycle._thread = Mock(return_value=SimpleNamespace())

        with patch(
            "shared_module.portal_data.mobile_repository.Session",
            return_value=session,
        ):
            result = repository.ensure_apple_link_candidate(
                "fictional-apple-stable-subject", "fictional-request-id", NOW
            )

        identity = next(
            item for item in session.added if isinstance(item, AuthIdentityRecord)
        )
        audit = next(
            item for item in session.added if isinstance(item, AccessAuditRecord)
        )
        self.assertEqual(identity.provider, "apple")
        self.assertEqual(identity.provider_subject, "fictional-apple-stable-subject")
        self.assertIsNone(identity.person_id)
        self.assertEqual(identity.status, "pending")
        self.assertFalse(hasattr(identity, "email"))
        self.assertFalse(hasattr(identity, "name"))
        self.assertEqual(audit.action, "identity_pending")
        self.assertEqual(result["identity_id"], 73)


class _FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False


class _FakeSession:
    def __init__(self):
        self.added = []

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def begin(self):
        return _FakeTransaction()

    def scalar(self, _statement):
        return None

    def add(self, value):
        self.added.append(value)

    def flush(self):
        identity = next(
            item for item in self.added if isinstance(item, AuthIdentityRecord)
        )
        identity.id = 73


if __name__ == "__main__":
    unittest.main()
