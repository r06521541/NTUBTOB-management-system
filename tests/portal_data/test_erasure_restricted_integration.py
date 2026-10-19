"""Fake provider -> real proof -> default-off API -> isolated PostgreSQL."""

import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

from shared_module.erasure_proof import ErasureProofService
from shared_module.erasure_receipt_proof import ReceiptVerificationProofService
from shared_module.erasure_restricted_proof import ErasureRestrictedProofService
from shared_module.mobile_api import VerifiedAssertion
from shared_module.portal_data import erasure_restricted_request, erasure_service
from shared_module.portal_data.erasure_request import ErasureRequestPlan
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.mobile_api.app import Dependencies, create_app
from tests.portal_data import test_erasure_restricted_request as fixture


@unittest.skipUnless(
    fixture.fixture.DATABASE_URL, "isolated erasure URL not configured"
)
class RestrictedErasureIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(fixture.RestrictedRequestPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(
        fixture.RestrictedRequestPostgresTests.tearDownClass.__func__
    )
    upgrade = fixture.RestrictedRequestPostgresTests.upgrade
    count = fixture.RestrictedRequestPostgresTests.count

    def setUp(self):
        fixture.RestrictedRequestPostgresTests.setUp(self)
        self.events = []
        self.verifier = Mock()
        config = dict(
            audience="fictional-erasure",
            lifetime=timedelta(minutes=2),
            providers={self.proof.provider: (self.verifier, "fake-client")},
            clock=lambda: fixture.NOW,
        )
        self.proofs = ErasureRestrictedProofService(fixture.KEY, **config)
        self.repo = erasure_restricted_request.RestrictedErasureRequestRepository(
            self.engine,
            fixture.KEY,
            lambda **kwargs: ErasureRequestPlan(**vars(fixture.plan())),
            verifier=self.proofs,
            audience=self.proofs.audience,
            clock=self.proofs.clock,
        )
        self.service = erasure_service.AccountErasureService(
            self.repo,
            ErasureProofService(fixture.KEY, **config),
            restricted_proofs=self.proofs,
            restricted_repository=self.repo,
            receipt_proofs=ReceiptVerificationProofService(fixture.KEY, **config),
        )

        def session_factory(*args):
            self.events.append("session")
            return Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            )

        patcher = patch.object(
            erasure_restricted_request, "Session", side_effect=session_factory
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        service_patch = patch.object(
            erasure_service, "Session", side_effect=session_factory
        )
        service_patch.start()
        self.addCleanup(service_patch.stop)
        self.auth = Mock()
        self.client = create_app(
            Dependencies(
                self.auth, Mock(), Mock(), lambda: True, account_erasure=self.service
            )
        ).test_client()

    def challenge(self):
        response = self.client.post(
            "/api/v1/account-erasure/request/challenge",
            json={"provider": self.proof.provider},
        )
        self.assertEqual(response.status_code, 200, response.json)
        challenge = response.json

        def verify(*args):
            self.events.append("provider")
            return VerifiedAssertion(
                self.proof.provider,
                self.proof.provider_subject,
                "fake-client",
                challenge["nonce"],
                fixture.NOW + timedelta(minutes=3),
            )

        self.verifier.verify.side_effect = verify
        return challenge

    def request_intent(self, challenge):
        return self.client.post(
            "/api/v1/account-erasure/request",
            json={
                "challenge_credential": challenge["challenge_credential"],
                "provider_assertion": "fictional-provider-assertion",
                "confirmed": True,
            },
        )

    def receipt_challenge(self, intent, subject=None):
        response = self.client.post(
            "/api/v1/account-erasure/receipt/challenge",
            json={
                "job_id": intent["id"],
                "receipt_secret": intent["receipt_secret"],
                "provider": self.proof.provider,
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        challenge = response.json
        self.verifier.verify.side_effect = lambda *args: (
            self.events.append("provider")
            or VerifiedAssertion(
                self.proof.provider,
                subject or self.proof.provider_subject,
                "fake-client",
                challenge["nonce"],
                fixture.NOW + timedelta(minutes=3),
            )
        )
        return challenge

    def verify_receipt(self, challenge):
        return self.client.post(
            "/api/v1/account-erasure/receipt/verify",
            json={
                "challenge_credential": challenge["challenge_credential"],
                "provider_assertion": "fictional-proof",
                "confirmed": True,
            },
        )

    def test_receipt_verification_pending_and_wrong_purpose(self):
        request_challenge = self.challenge()
        intent = self.request_intent(request_challenge).json
        self.assertEqual(self.verify_receipt(request_challenge).status_code, 401)
        challenge = self.receipt_challenge(intent)
        self.events.clear()
        response = self.verify_receipt(challenge)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.events, ["provider", "session"])
        self.assertEqual(response.json, {"id": intent["id"], "status": "verified"})
        self.assertEqual(self.verify_receipt(challenge).status_code, 401)
        self.auth.authenticate.assert_not_called()

    def test_blocked_person_can_verify_using_another_current_owned_identity(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='blocked' "
                "WHERE id IN (:first,:second)"
            ),
            {
                "person": self.person,
                "first": self.identity,
                "second": self.other_identity,
            },
        )
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_status='blocked' WHERE id=:id"),
            {"id": self.person},
        )
        subject = self.connection.scalar(
            text("SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.other_identity},
        )
        before = {
            table: self.count(table)
            for table in ("people", "auth_identities", "mobile_sessions")
        }
        intent = self.request_intent(self.challenge()).json
        challenge = self.receipt_challenge(intent, subject)
        self.events.clear()
        result = self.verify_receipt(challenge)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.events, ["provider", "session"])
        self.assertEqual({table: self.count(table) for table in before}, before)
        self.auth.authenticate.assert_not_called()

    def test_receipt_does_not_authorize_unowned_subject_or_remapped_identity(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.person, "id": self.identity},
        )
        intent = self.request_intent(self.challenge()).json
        unknown = self.receipt_challenge(intent, "unknown-fictional-subject")
        self.assertEqual(self.verify_receipt(unknown).status_code, 401)
        challenge = self.receipt_challenge(intent)
        self.connection.execute(
            text("UPDATE ntubtob.auth_identities SET person_id=:person WHERE id=:id"),
            {"person": self.other_person, "id": self.identity},
        )
        self.assertEqual(self.verify_receipt(challenge).status_code, 401)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": intent["id"]},
            ),
            "requested",
        )

    def test_pending_api_commits_intent_only_and_never_authenticates_app_session(self):
        challenge = self.challenge()
        self.assertEqual(self.events, [])
        response = self.request_intent(challenge)
        self.assertEqual(response.status_code, 202, response.json)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.events, ["provider", "session"])
        self.assertEqual(response.json["status"], "requested")
        self.auth.authenticate.assert_not_called()
        self.assertEqual(self.request_intent(challenge).json, response.json)
        self.assertEqual(self.count("account_erasure_jobs"), 1)
        self.assertEqual(self.count("account_erasure_request_attempts"), 1)

    def test_pending_receipt_can_verify_with_separate_fresh_provider_proof(self):
        request_challenge = self.challenge()
        intent = self.request_intent(request_challenge).json
        wrong_purpose = self.client.post(
            "/api/v1/account-erasure/verify",
            json={
                "challenge_credential": request_challenge["challenge_credential"],
                "provider_assertion": "fictional-proof",
            },
        )
        self.assertEqual(wrong_purpose.status_code, 401)
        response = self.client.post(
            "/api/v1/account-erasure/pending/challenge",
            json={"job_id": intent["id"], "receipt_secret": intent["receipt_secret"]},
        )
        self.assertEqual(response.status_code, 200, response.json)
        challenge = response.json
        self.verifier.verify.side_effect = lambda *args: (
            self.events.append("provider")
            or VerifiedAssertion(
                self.proof.provider,
                self.proof.provider_subject,
                "fake-client",
                challenge["nonce"],
                fixture.NOW + timedelta(minutes=3),
            )
        )
        self.events.clear()
        result = self.client.post(
            "/api/v1/account-erasure/verify",
            json={
                "challenge_credential": challenge["challenge_credential"],
                "provider_assertion": "fictional-proof",
            },
        )
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json, {"id": intent["id"], "status": "verified"})
        self.assertEqual(self.events, ["provider", "session"])
        self.auth.authenticate.assert_not_called()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": intent["id"]},
            ),
            "verified",
        )

    def test_pending_receipt_cannot_be_used_after_identity_mapping_changes(self):
        intent = self.request_intent(self.challenge()).json
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.person, "id": self.identity},
        )
        response = self.client.post(
            "/api/v1/account-erasure/pending/challenge",
            json={"job_id": intent["id"], "receipt_secret": intent["receipt_secret"]},
        )
        self.assertEqual(response.status_code, 401, response.json)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": intent["id"]},
            ),
            "requested",
        )

    def test_old_challenge_after_cancellation_cannot_create_replacement(self):
        challenge = self.challenge()
        response = self.request_intent(challenge)
        self.assertEqual(response.status_code, 202, response.json)
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',auth_identity_id=NULL,"
                "cancelled_at=:now,updated_at=:now WHERE id=:id"
            ),
            {"id": response.json["id"], "now": fixture.NOW},
        )
        self.assertEqual(self.request_intent(challenge).status_code, 401)
        self.assertEqual(self.count("account_erasure_jobs"), 1)
        fresh = self.request_intent(self.challenge())
        self.assertEqual(fresh.status_code, 202, fresh.json)
        self.assertNotEqual(fresh.json["id"], response.json["id"])

    def test_provider_failure_is_sanitized_without_repository_transaction(self):
        challenge = self.challenge()
        self.verifier.verify.side_effect = RuntimeError("private-sentinel")
        response = self.request_intent(challenge)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("private-sentinel", response.get_data(as_text=True))
        self.assertEqual(self.events, [])
        self.assertEqual(self.count("account_erasure_jobs"), 0)


if __name__ == "__main__":
    unittest.main()
