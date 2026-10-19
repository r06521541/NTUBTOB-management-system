"""Real recovery composition with fictional provider and opt-in isolated PG.

Only fixture setup/cleanup writes. Repository Sessions join the existing outer
fixture transaction using savepoints: this is not independent-commit, lock-wait,
or concurrency evidence, and never enables bootstrap/native/provider access.
"""

import hashlib
import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from shared_module.erasure_proof import ErasureProofService
from shared_module.erasure_recovery_proof import (
    ErasureReceiptRecoveryProofService,
    FreshReceiptRecoveryProof,
)
from shared_module.erasure_restricted_proof import ErasureRestrictedProofService
from shared_module.mobile_api import VerifiedAssertion
from shared_module.portal_data import erasure_receipt_recovery as recovery
from shared_module.portal_data import erasure_service
from shared_module.portal_data.erasure_request import AccountErasureRequestRepository
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import (
    ReleaseSavepointClause,
    RollbackToSavepointClause,
    SavepointClause,
    TextClause,
)

from apps.mobile_api.app import Dependencies, create_app
from tests.portal_data import test_erasure_cancellation_schema as fixture

KEY = b"fictional-recovery-api-key-only-12345"
AUDIENCE = "fictional-recovery-api"
PROVIDER_ASSERTION = "fictional-recovery-provider-assertion"
CHALLENGE_PATH = "/api/v1/account-erasure/recovery/challenge"
RECOVERY_PATH = "/api/v1/account-erasure/recovery"
HEADERS = {"X-Request-ID": "fictional-recovery-api-request"}
TABLES = (
    "account_erasure_jobs",
    "account_erasure_request_attempts",
    "account_erasure_steps",
    "auth_identities",
    "people",
    "mobile_sessions",
)


def read_or_fixture_control(statement):
    return type(statement) in (
        SavepointClause,
        ReleaseSavepointClause,
        RollbackToSavepointClause,
    ) or (type(statement) is TextClause and str(statement).startswith("SELECT "))


class RecoveryApiFixtureTests(unittest.TestCase):
    def test_read_observer_does_not_allow_dml_or_arbitrary_transaction_sql(self):
        for statement in (
            text("SELECT 1"),
            SavepointClause("fixture"),
            ReleaseSavepointClause("fixture"),
            RollbackToSavepointClause("fixture"),
        ):
            self.assertTrue(read_or_fixture_control(statement))
        for sql in (
            "INSERT INTO fictional VALUES (1)",
            "UPDATE fictional SET id=1",
            "DELETE FROM fictional",
            "TRUNCATE fictional",
            "CREATE TABLE fictional (id int)",
            "SAVEPOINT arbitrary",
            "RELEASE SAVEPOINT arbitrary",
            "ROLLBACK TO SAVEPOINT arbitrary",
            "COMMIT",
        ):
            self.assertFalse(read_or_fixture_control(text(sql)))

    def test_exact_dtos_use_the_same_module_family_as_flask_service(self):
        self.assertIs(recovery.FreshReceiptRecoveryProof, FreshReceiptRecoveryProof)
        self.assertIs(
            erasure_service.RecoveredErasureReceipt, recovery.RecoveredErasureReceipt
        )


@unittest.skipUnless(
    fixture.DATABASE_URL, "dedicated isolated erasure URL not configured"
)
class RecoveryApiPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        fixture.ErasureCancellationPostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        fixture.ErasureCancellationPostgresTests.tearDownClass.__func__
    )
    upgrade = fixture.ErasureCancellationPostgresTests.upgrade
    job = fixture.ErasureCancellationPostgresTests.job
    update = fixture.ErasureCancellationPostgresTests.update

    def setUp(self):
        fixture.ErasureCancellationPostgresTests.setUp(self)
        self.upgrade()
        self.now = fixture.NOW + timedelta(minutes=2)
        self.provider, self.subject = self.connection.execute(
            text(
                "SELECT provider,provider_subject FROM ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.identity},
        ).one()
        self.events = []
        self.verifier = Mock()
        config = dict(
            audience=AUDIENCE,
            lifetime=timedelta(minutes=5),
            providers={self.provider: (self.verifier, "fictional-client")},
            clock=lambda: self.now,
        )
        self.proofs = ErasureReceiptRecoveryProofService(KEY, **config)
        self.request_proofs = ErasureRestrictedProofService(KEY, **config)
        self.repo = recovery.ReceiptRecoveryRepository(
            self.engine,
            KEY,
            verifier=self.proofs,
            audience=AUDIENCE,
            clock=lambda: self.now,
        )
        self.ordinary = Mock()
        self.ordinary.request.side_effect = AssertionError("ordinary request forbidden")
        self.service = erasure_service.AccountErasureService(
            self.ordinary,
            ErasureProofService(KEY, **config),
            recovery_proofs=self.proofs,
            recovery_repository=self.repo,
        )

        def session_factory(*args):
            self.events.append("repository_session")
            return Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            )

        patcher = patch.object(recovery, "Session", side_effect=session_factory)
        self.session_factory = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(
            erasure_service,
            "Session",
            side_effect=AssertionError("service must not open a transaction"),
        )
        self.service_session = patcher.start()
        self.addCleanup(patcher.stop)
        self.auth = Mock()
        self.auth.authenticate.side_effect = AssertionError("session auth forbidden")
        self.client = create_app(
            Dependencies(
                self.auth, Mock(), Mock(), lambda: True, account_erasure=self.service
            )
        ).test_client()

    def seed_receipt(self, *, person=False):
        if person:
            self.connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='blocked' WHERE id=:id"
                ),
                {"person": self.person, "id": self.identity},
            )
            table, target = "people", self.person
        else:
            table, target = "auth_identities", self.identity
        generation = self.connection.scalar(
            text(f"SELECT account_generation FROM ntubtob.{table} WHERE id=:id"),
            {"id": target},
        )
        self.job_id = str(uuid4())
        self.secret = AccountErasureRequestRepository(
            self.engine, KEY, lambda: None
        )._secret(self.job_id)
        self.job(
            id=self.job_id,
            target_kind="person" if person else "pending_identity",
            person_id=self.person if person else None,
            auth_identity_id=None if person else self.identity,
            expected_generation=str(generation),
            receipt_secret_hash=hashlib.sha256(self.secret.encode("ascii")).hexdigest(),
        )
        # Existing immutable attempt is evidence too; recovery must not replace it.
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_request_attempts "
                "(attempt_id,job_id,assertion_binding,created_at,proof_expires_at) "
                "VALUES (:id,:job,:binding,:created,:expiry)"
            ),
            dict(
                id=str(uuid4()),
                job=self.job_id,
                binding="f" * 64,
                created=fixture.NOW,
                expiry=fixture.NOW + timedelta(minutes=1),
            ),
        )

    def snapshot(self):
        return {
            table: self.connection.execute(
                text(f"SELECT * FROM ntubtob.{table} ORDER BY 1")
            ).all()
            for table in TABLES
        }

    @contextmanager
    def unchanged_recovery(self):
        before = self.snapshot()
        statements = []

        def observe(_connection, statement, _multiparams, _params, _options):
            statements.append(statement)

        event.listen(self.connection, "before_execute", observe)
        try:
            yield
        finally:
            event.remove(self.connection, "before_execute", observe)
        self.assertTrue(
            all(read_or_fixture_control(statement) for statement in statements),
            "recovery executed non-read SQL outside typed fixture savepoint controls",
        )
        self.assertEqual(before, self.snapshot())
        self.auth.authenticate.assert_not_called()
        self.ordinary.assert_not_called()
        self.ordinary.request.assert_not_called()
        self.service_session.assert_not_called()

    def challenge(self, *, subject=None, nonce=None):
        before_calls = self.session_factory.call_count
        response = self.client.post(
            CHALLENGE_PATH, json={"provider": self.provider}, headers=HEADERS
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(
            set(response.json),
            {"challenge_credential", "provider", "nonce", "expires_in"},
        )
        self.assertEqual(self.session_factory.call_count, before_calls)
        value = response.json
        issued = self.now

        def verify(assertion, audience, received_nonce, received_now):
            self.assertEqual(self.events, [])
            self.assertEqual(self.session_factory.call_count, before_calls)
            self.assertEqual(assertion, PROVIDER_ASSERTION)
            self.assertEqual(audience, "fictional-client")
            self.assertEqual(received_nonce, value["nonce"])
            self.assertEqual(received_now, self.now)
            self.events.append("provider")
            return VerifiedAssertion(
                self.provider,
                subject or self.subject,
                audience,
                nonce or received_nonce,
                issued + timedelta(minutes=10),
            )

        self.verifier.verify.side_effect = verify
        return value

    def recover(self, challenge):
        self.events.clear()
        return self.client.post(
            RECOVERY_PATH,
            json={
                "challenge_credential": challenge["challenge_credential"],
                "provider_assertion": PROVIDER_ASSERTION,
                "confirmed": True,
            },
            headers=HEADERS,
        )

    def assert_receipt(self, response, status, updated):
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(
            response.json,
            {
                "id": self.job_id,
                "status": status,
                "receipt_secret": self.secret,
                "requested_at": fixture.NOW.isoformat(),
                "updated_at": updated.isoformat(),
                "receipt_expires_at": (fixture.NOW + timedelta(hours=3)).isoformat(),
            },
        )
        self.assertNotIn(self.subject, response.get_data(as_text=True))
        self.assertNotIn(PROVIDER_ASSERTION, response.get_data(as_text=True))
        self.assertEqual(self.events, ["provider", "repository_session"])

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 401, response.json)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        error = response.json["error"]
        self.assertEqual(error["message"], "account erasure recovery rejected")
        self.assertFalse(error["retryable"])
        for private in (self.subject, self.secret, PROVIDER_ASSERTION):
            self.assertNotIn(private, response.get_data(as_text=True))
        return response.json

    def test_pending_current_status_original_receipt_and_no_dml(self):
        self.seed_receipt()
        for status in ("requested", "verified", "processing", "needs_attention"):
            with self.subTest(status=status):
                updated = fixture.NOW
                if status != "requested":
                    updated = fixture.NOW + timedelta(seconds=30)
                    changes = dict(status=status, updated_at=updated)
                    if status == "verified":
                        changes["verified_at"] = updated
                    self.update(self.job_id, **changes)
                with self.unchanged_recovery():
                    challenge = self.challenge()
                    self.assert_receipt(self.recover(challenge), status, updated)

    def test_blocked_person_recovers_without_reviving_session_or_changing_deadline(
        self,
    ):
        self.seed_receipt(person=True)
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_status='blocked' WHERE id=:id"),
            {"id": self.person},
        )
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.mobile_sessions "
                "(id,auth_identity_id,person_id,installation_id_hash,platform,status,"
                "access_epoch,refresh_family_expires_at,created_at,updated_at) "
                "VALUES (:id,:identity,:person,:hash,'ios','revoked',2,:expiry,:now,:now)"
            ),
            dict(
                id=str(uuid4()),
                identity=self.identity,
                person=self.person,
                hash="a" * 64,
                expiry=fixture.NOW + timedelta(hours=1),
                now=fixture.NOW,
            ),
        )
        with self.unchanged_recovery():
            self.assert_receipt(
                self.recover(self.challenge()), "requested", fixture.NOW
            )
        self.now += timedelta(seconds=20)
        with self.unchanged_recovery():
            self.assert_receipt(
                self.recover(self.challenge()), "requested", fixture.NOW
            )

    def test_wrong_nonce_wrong_purpose_and_missing_target_share_generic_error(self):
        self.seed_receipt()
        with self.unchanged_recovery():
            missing = self.recover(self.challenge(subject="fictional-missing-subject"))
            expected = self.assert_rejected(missing)
            self.assertEqual(self.events, ["provider", "repository_session"])
            wrong_nonce = self.recover(self.challenge(nonce="fictional-wrong-nonce"))
            self.assertEqual(self.assert_rejected(wrong_nonce), expected)
            self.assertEqual(self.events, ["provider"])
            wrong_purpose = self.recover(self.request_proofs.begin(self.provider))
            self.assertEqual(self.assert_rejected(wrong_purpose), expected)
            self.assertEqual(self.events, [])

    def test_expired_challenge_is_rejected_before_provider_or_repository(self):
        self.seed_receipt()
        with self.unchanged_recovery():
            challenge = self.challenge()
            self.now += self.proofs.lifetime
            self.assert_rejected(self.recover(challenge))
            self.verifier.verify.assert_not_called()
            self.session_factory.assert_not_called()
            self.assertEqual(self.events, [])

    def test_challenge_issued_before_job_cannot_recover_later_request(self):
        self.now = fixture.NOW - timedelta(seconds=1)
        challenge = self.challenge()
        self.seed_receipt()
        self.now = fixture.NOW + timedelta(seconds=1)
        with self.unchanged_recovery():
            self.assert_rejected(self.recover(challenge))
            self.assertEqual(self.events, ["provider", "repository_session"])

    def test_detached_completed_job_is_not_recovered_from_fresh_subject(self):
        self.seed_receipt()
        self.update(
            self.job_id,
            status="verified",
            verified_at=fixture.NOW,
            updated_at=fixture.NOW,
        )
        self.update(
            self.job_id, status="processing", irreversible_started_at=fixture.NOW
        )
        self.update(
            self.job_id,
            status="online_completed",
            online_completed_at=self.now,
            updated_at=self.now,
            auth_identity_id=None,
        )
        self.now += timedelta(seconds=1)
        with self.unchanged_recovery():
            self.assert_rejected(self.recover(self.challenge()))
            self.assertEqual(self.events, ["provider", "repository_session"])


if __name__ == "__main__":
    unittest.main()
