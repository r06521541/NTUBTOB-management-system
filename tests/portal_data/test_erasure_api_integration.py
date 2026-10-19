"""Fictional PostgreSQL composition; no bootstrap enablement or provider I/O."""

import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

from shared_module.erasure_proof import ErasureProofService
from shared_module.mobile_api import MobilePrincipal, VerifiedAssertion
from shared_module.portal_data import erasure_request, erasure_service
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.mobile_api.app import Dependencies, create_app
from tests.portal_data import test_erasure_request as fixture


@unittest.skipUnless(
    fixture.verification_fixture.ledger_fixture.DATABASE_URL,
    "isolated ledger URL not configured",
)
class ErasureApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RequestPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        fixture.RequestPostgresTests.setUp(self)
        self.principal = MobilePrincipal(
            self.session_id,
            self.fixture.person,
            self.fixture.identity,
            "basic",
            "Fictional",
            1,
        )
        self.provider, self.subject = self.connection.execute(
            text(
                "SELECT provider,provider_subject FROM ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        ).one()
        self.verifier = Mock()
        self.proofs = ErasureProofService(
            b"f" * 32,
            audience="fictional-erasure",
            lifetime=timedelta(minutes=2),
            providers={self.provider: (self.verifier, "fake-client")},
            clock=lambda: fixture.NOW,
        )

        def plan(**kwargs):
            value = fixture.plan(**kwargs)
            return erasure_request.ErasureRequestPlan(**vars(value))

        self.repo = erasure_request.AccountErasureRequestRepository(
            self.engine, fixture.KEY, plan, lambda: fixture.NOW
        )
        self.service = erasure_service.AccountErasureService(self.repo, self.proofs)

        def session_factory(*args):
            return Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            )

        for module in (erasure_request, erasure_service):
            patcher = patch.object(module, "Session", side_effect=session_factory)
            patcher.start()
            self.addCleanup(patcher.stop)
        auth = Mock()
        self.auth = auth
        auth.authenticate.return_value = self.principal
        self.client = create_app(
            Dependencies(
                auth, Mock(), Mock(), lambda: True, account_erasure=self.service
            )
        ).test_client()
        self.headers = {"Authorization": "Bearer fictional-access"}

    def start(self):
        response = self.client.post(
            "/api/v1/me/account-erasure", headers=self.headers, json={"confirmed": True}
        )
        self.assertEqual(response.status_code, 202, response.json)
        receipt = response.json
        response = self.client.post(
            "/api/v1/me/account-erasure/challenge",
            headers=self.headers,
            json={"job_id": receipt["id"], "receipt_secret": receipt["receipt_secret"]},
        )
        self.assertEqual(response.status_code, 200, response.json)
        challenge = response.json
        self.verifier.verify.return_value = VerifiedAssertion(
            self.provider,
            self.subject,
            "fake-client",
            challenge["nonce"],
            fixture.NOW + timedelta(minutes=3),
        )
        return receipt, {
            "challenge_credential": challenge["challenge_credential"],
            "provider_assertion": "fictional-provider-token",
        }

    def test_request_challenge_verified_session_revoke_and_replay(self):
        receipt, payload = self.start()
        response = self.client.post("/api/v1/account-erasure/verify", json=payload)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": receipt["id"]},
            ),
            "verified",
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.mobile_sessions WHERE id=:id"),
                {"id": self.session_id},
            ),
            "revoked",
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id AND stage='verification'"
                ),
                {"id": receipt["id"]},
            ),
            1,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/account-erasure/verify", json=payload
            ).status_code,
            401,
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": receipt["id"]},
            ),
            1,
        )

    def test_generation_change_after_challenge_rejects_without_revocation(self):
        receipt, payload = self.start()
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=NULL,status='pending' WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"id": self.fixture.identity, "person": self.fixture.person},
        )
        response = self.client.post("/api/v1/account-erasure/verify", json=payload)
        self.assertEqual(response.status_code, 401, response.json)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": receipt["id"]},
            ),
            "requested",
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.mobile_sessions WHERE id=:id"),
                {"id": self.session_id},
            ),
            "active",
        )

    def test_receipt_reconciles_verification_without_replaying_or_session(self):
        receipt, payload = self.start()
        body = {"job_id": receipt["id"], "receipt_secret": receipt["receipt_secret"]}
        path = "/api/v1/account-erasure/status"
        self.assertEqual(self.client.post(path, json=body).json["status"], "requested")
        self.assertEqual(
            self.client.post(
                "/api/v1/account-erasure/verify", json=payload
            ).status_code,
            200,
        )
        self.auth.authenticate.side_effect = AssertionError("no session permitted")
        self.verifier.verify.reset_mock()
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["status"], "verified")
        self.assertEqual(
            set(response.json), {"id", "status", "requested_at", "updated_at"}
        )
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.verifier.verify.assert_not_called()
        self.assertEqual(
            self.client.post(
                path, json={**body, "receipt_secret": "wrong" * 10}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": receipt["id"]},
            ),
            1,
        )
