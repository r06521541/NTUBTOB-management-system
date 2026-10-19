"""Committed fictional PG HTTP -> sealed plan -> reconstructed executor evidence.

No Session/savepoint replacement and no retained caller snapshot. Only provider
assertions, Apple HTTP/cipher and an external-custody-shaped store are fictional.
This opt-in suite does not enable bootstrap, demonstrate live providers or prove
real restore custody. Its explicit short deadlines are fixture data, not policy.
"""

import hashlib
import json
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from alembic import command
from alembic.config import Config
from shared_module.apple_token_revocation import AppleTokenRevoker
from shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_module.mobile_api import MobilePrincipal, VerifiedAssertion
from shared_module.portal_data.erasure_apple_preparation import AppleErasurePreparation
from shared_module.portal_data.erasure_components import build_erasure_components
from shared_module.portal_data.erasure_composition import (
    ErasurePlanPolicy,
    TrustedErasurePlanBuilder,
)
from shared_module.portal_data.erasure_plan_codec import ErasurePlanCodec
from shared_module.portal_data.erasure_plan_store import SealedPlanRejected
from shared_module.portal_data.local_database import require_local_database_url
from sqlalchemy import create_engine, event, text

from apps.mobile_api.app import Dependencies, create_app
from tests.portal_data import test_erasure_fulfillment as fulfillment_fixture
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)

TOKEN = b"fictional-refresh-token"
PROVIDER_AUDIENCE = "fictional-apple-client"
REQUEST_KEYS = {"id", "status", "receipt_secret", "requested_at"}
STATUS_KEYS = {"id", "status", "requested_at", "updated_at"}
CHALLENGE_KEYS = {"challenge_credential", "nonce", "provider", "expires_in"}
RECOVERY_KEYS = STATUS_KEYS | {"receipt_secret", "receipt_expires_at"}


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class ErasureComponentsIntegrationTests(unittest.TestCase):
    scalar = fulfillment_fixture.PendingFulfillmentPostgresTests.scalar

    def setUp(self):
        self.engine = self.create_fixture_engine()
        self.addCleanup(self.engine.dispose)
        self.prepare_fixture_schema()
        # Reuse only existing fictional row seeding, never its job() helper.
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.ids = {}
        self.session_id = None
        self.saved_authority = None
        self.addCleanup(self.cleanup_fixture)
        self.fixture.setUp()
        self.fixture.transaction.commit()
        self.fixture.connection.close()
        self.now = ledger.NOW + timedelta(seconds=10)
        with self.engine.begin() as connection:
            for identity in (self.fixture.identity, self.fixture.other_identity):
                self.seed_provider(connection, identity)
            self.subject = connection.scalar(
                text(
                    "SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": self.fixture.identity},
            )
        self.assertion_subject = self.subject
        self.namespace = str(uuid4())
        self.capture_calls = 0
        self.http_calls = 0
        self.http_status = 200
        self.job_id = None
        self.verifier = Mock()
        self.verifier.verify.side_effect = self.verify_provider
        self.cipher = Mock()
        self.cipher.open.return_value = TOKEN
        self.restore_store = fulfillment_fixture.FictionalRestoreStore()
        self.auth = Mock()
        self.auth.authenticate.side_effect = AssertionError("no session auth expected")
        self.make_components(capture_allowed=True)

    def create_fixture_engine(self):
        return create_engine(
            require_local_database_url(ledger.DATABASE_URL),
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=5000 -c lock_timeout=5000",
            },
            pool_timeout=5,
        )

    def prepare_fixture_schema(self):
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_erasure_privacy_mutation")

    def cleanup_fixture(self):
        if self.session_id is not None:
            with self.engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM ntubtob.mobile_sessions WHERE id=:id"),
                    {"id": self.session_id},
                )
        # Existing isolated-only reset deletes recorded fictional IDs, not broad
        # Person data, and removes retained immutable ledger evidence first.
        try:
            fulfillment_fixture.PendingFulfillmentPostgresTests.cleanup_fixture(self)
        finally:
            if self.saved_authority is not None:
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            "UPDATE ntubtob.portal_authority_state "
                            "SET mode=:mode,epoch=:epoch,updated_at=:updated_at WHERE singleton_id=1"
                        ),
                        self.saved_authority,
                    )

    def seed_provider(self, connection, identity):
        values = {
            "identity": identity,
            "now": ledger.NOW,
            "token_hash": hashlib.sha256(TOKEN).hexdigest(),
            "code_hash": uuid4().hex * 2,
        }
        statements = {
            "apple_provider_credentials": (
                "INSERT INTO ntubtob.apple_provider_credentials "
                "(auth_identity_id,encrypted_refresh_token,refresh_token_hash,status,created_at,updated_at) "
                "VALUES (:identity,decode('66616b65','hex'),:token_hash,'active',:now,:now) RETURNING id"
            ),
            "apple_provider_code_exchanges": (
                "INSERT INTO ntubtob.apple_provider_code_exchanges "
                "(auth_identity_id,code_hash,login_attempt_hash,state,created_at,updated_at) "
                "VALUES (:identity,:code_hash,:code_hash,'completed',:now,:now) RETURNING id"
            ),
        }
        for table, statement in statements.items():
            self.ids.setdefault(table, []).append(
                connection.scalar(text(statement), values)
            )

    def make_components(self, *, capture_allowed):
        def review_source(**values):
            self.assertTrue(capture_allowed, "restart must not recapture a plan")
            self.capture_calls += 1
            if values["person_id"] is None:
                return ()  # Explicit reviewed-empty; fixture contains no audit/UGC.
            return json.dumps(
                {
                    "version": 1,
                    "person_id": values["person_id"],
                    "generation": values["target_generation"],
                    "dispositions": [],
                }
            ).encode("utf-8")

        def policy_source(**values):
            self.assertTrue(capture_allowed, "restart must not replace policy")
            requested = values["requested_at"]
            return ErasurePlanPolicy(
                1,
                requested + timedelta(hours=2),
                requested + timedelta(hours=3),
                requested + timedelta(hours=4),
            )

        builder = TrustedErasurePlanBuilder(
            review_source=review_source,
            policy_source=policy_source,
            restore_codec=RestoreBindingCodec(
                namespace=self.namespace,
                active_key="fictional",
                keys={"fictional": b"r" * 32},
            ),
            provider_audiences={"apple": PROVIDER_AUDIENCE},
        )
        self.components = build_erasure_components(
            engine=self.engine,
            receipt_key=b"s" * 32,
            proof_key=b"p" * 32,
            audience="fictional-erasure",
            proof_lifetime=timedelta(minutes=2),
            providers={"apple": (self.verifier, PROVIDER_AUDIENCE)},
            plan_builder=builder,
            active_plan_key_id="fictional",
            plan_codecs={
                "fictional": ErasurePlanCodec(namespace=self.namespace, key=b"k" * 32)
            },
            prepare_provider=AppleErasurePreparation(
                provider_cipher=self.cipher,
                client_id=PROVIDER_AUDIENCE,
                client_secret="fictional-client-secret",
                revoker=AppleTokenRevoker(transport=self.transport),
            ),
            restore_store=self.restore_store,
            clock=lambda: self.now,
        )
        self.client = create_app(
            Dependencies(
                self.auth,
                Mock(),
                Mock(),
                lambda: True,
                account_erasure=self.components.service,
            )
        ).test_client()

    def verify_provider(self, assertion, audience, nonce, now):
        self.assertEqual(assertion, "fictional-provider-assertion")
        self.assertEqual(audience, PROVIDER_AUDIENCE)
        self.assertEqual(self.engine.pool.checkedout(), 0, "provider I/O outside TX")
        return VerifiedAssertion(
            "apple", self.assertion_subject, audience, nonce, now + timedelta(minutes=3)
        )

    def transport(self, url, body, timeout):
        self.http_calls += 1
        self.assertEqual(url, "https://appleid.apple.com/auth/revoke")
        self.assertEqual(timeout, 5.0)
        self.assertEqual(self.engine.pool.checkedout(), 0)
        self.assertIsNotNone(
            self.scalar(
                "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            "separate connection must see committed fence before HTTP",
        )
        return self.http_status, b""

    def post(self, path, payload, *, status=200, headers=None):
        response = self.client.post(path, json=payload, headers=headers)
        self.assertEqual(response.status_code, status, response.json)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        return response.json

    def assert_times(self, payload, *keys):
        for key in keys:
            value = payload[key]
            self.assertIs(type(value), str)
            self.assertLessEqual(len(value), 40)
            self.assertRegex(
                value,
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$",
            )
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            self.assertEqual(instant.utcoffset(), timedelta(0))
            self.assertGreaterEqual(instant, ledger.NOW)
            self.assertLess(instant, ledger.NOW + timedelta(days=1))

    def challenge(self, purpose, **payload):
        result = self.post("/api/v1/account-erasure/" + purpose + "/challenge", payload)
        self.assertEqual(set(result), CHALLENGE_KEYS)
        self.assertEqual(result["provider"], "apple")
        self.assertIs(type(result["expires_in"]), int)
        self.assertEqual(result["expires_in"], 120)
        self.assertTrue(result["nonce"])
        return result

    @staticmethod
    def proof_payload(challenge):
        return {
            "challenge_credential": challenge["challenge_credential"],
            "provider_assertion": "fictional-provider-assertion",
            "confirmed": True,
        }

    def request(self, *, linked=False):
        if linked:
            self.link_person()
            receipt = self.post(
                "/api/v1/me/account-erasure",
                {"confirmed": True},
                status=202,
                headers={"Authorization": "Bearer fictional-access"},
            )
        else:
            challenge = self.challenge("request", provider="apple")
            receipt = self.post(
                "/api/v1/account-erasure/request",
                self.proof_payload(challenge),
                status=202,
            )
        self.assertEqual(set(receipt), REQUEST_KEYS)
        self.assertEqual(receipt["status"], "requested")
        self.assertRegex(receipt["receipt_secret"], r"^[0-9a-f]{64}$")
        self.assert_times(receipt, "requested_at")
        self.receipt = receipt
        self.job_id = receipt["id"]
        self.assertEqual(self.capture_calls, 1)
        self.assertEqual(self.http_calls, 0)
        self.assertEqual(self.job()["status"], "requested")
        self.sealed_before = self.sealed_fingerprint()
        self.assertTrue(self.sealed_before)
        self.auth.authenticate.reset_mock()
        self.auth.authenticate.side_effect = AssertionError(
            "receipt flows need no session"
        )
        return receipt

    def link_person(self):
        self.session_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                ),
                {"person": self.fixture.person, "id": self.fixture.identity},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions "
                    "(id,auth_identity_id,person_id,installation_id_hash,platform,status,access_epoch,refresh_family_expires_at,created_at,updated_at) "
                    "VALUES (:id,:identity,:person,:hash,'ios','active',1,:expiry,:now,:now)"
                ),
                dict(
                    id=self.session_id,
                    identity=self.fixture.identity,
                    person=self.fixture.person,
                    hash=uuid4().hex * 2,
                    expiry=self.now + timedelta(hours=1),
                    now=ledger.NOW,
                ),
            )
        self.auth.authenticate.side_effect = None
        self.auth.authenticate.return_value = MobilePrincipal(
            self.session_id,
            self.fixture.person,
            self.fixture.identity,
            "basic",
            "Fictional",
            1,
        )

    def receipt_input(self):
        return {"job_id": self.job_id, "receipt_secret": self.receipt["receipt_secret"]}

    def verify(self):
        self.now += timedelta(seconds=1)
        challenge = self.challenge("receipt", provider="apple", **self.receipt_input())
        result = self.post(
            "/api/v1/account-erasure/receipt/verify", self.proof_payload(challenge)
        )
        self.assertEqual(result, {"id": self.job_id, "status": "verified"})
        self.status("verified")
        if self.session_id is not None:
            self.assertEqual(
                self.scalar(
                    "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                    id=self.session_id,
                ),
                "revoked",
            )

    def status(self, expected):
        result = self.post("/api/v1/account-erasure/status", self.receipt_input())
        self.assertEqual(set(result), STATUS_KEYS)
        self.assertEqual(result["id"], self.job_id)
        self.assertEqual(result["status"], expected)
        self.assertEqual(result["requested_at"], self.receipt["requested_at"])
        self.assert_times(result, "requested_at", "updated_at")
        self.auth.authenticate.assert_not_called()
        return result

    def job(self):
        with self.engine.connect() as connection:
            return dict(
                connection.execute(
                    text("SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                    {"id": self.job_id},
                )
                .mappings()
                .one()
            )

    def sealed_fingerprint(self):
        return self.scalar(
            "SELECT encode(sha256(ciphertext),'hex') FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:id",
            id=self.job_id,
        )

    def restart(self):
        # New service/repositories/proofs/codecs/executors and fresh connection
        # pool, with only persistent keys/namespace and external fake ports reused.
        self.assertEqual(self.engine.pool.checkedout(), 0)
        self.engine.dispose()
        self.make_components(capture_allowed=False)
        self.assertEqual(self.sealed_fingerprint(), self.sealed_before)

    def assert_other_owner_unchanged(self):
        for table, column, identifier in (
            ("people", "id", self.fixture.other_person),
            ("auth_identities", "id", self.fixture.other_identity),
            (
                "apple_provider_credentials",
                "auth_identity_id",
                self.fixture.other_identity,
            ),
            (
                "apple_provider_code_exchanges",
                "auth_identity_id",
                self.fixture.other_identity,
            ),
        ):
            self.assertEqual(
                self.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE {column}=:id",
                    id=identifier,
                ),
                1,
            )

    def assert_local_provider_rows(self, *, credentials, exchanges, identity):
        for table, count in (
            ("apple_provider_credentials", credentials),
            ("apple_provider_code_exchanges", exchanges),
        ):
            self.assertEqual(
                self.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE auth_identity_id=:id",
                    id=self.fixture.identity,
                ),
                count,
            )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.identity,
            ),
            identity,
        )

    def assert_online_completed(self, *, person_deleted):
        self.status("online_completed")
        job = self.job()
        self.assertIsNone(job["person_id"])
        self.assertIsNone(job["auth_identity_id"])
        self.assertIsNone(
            job["completed_at"], "online does not mean backup-horizon completion"
        )
        self.assertIsNotNone(job["online_completed_at"])
        self.assert_local_provider_rows(credentials=0, exchanges=0, identity=0)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            0 if person_deleted else 1,
        )
        self.assertEqual(self.http_calls, 1)
        self.assertEqual(self.capture_calls, 1)
        self.assertEqual(self.restore_store.calls, 1)
        self.assertEqual(self.sealed_fingerprint(), self.sealed_before)
        self.assert_other_owner_unchanged()

    def test_pending_http_to_reconstructed_stored_plan_and_receipt(self):
        self.request()
        self.verify()
        self.restart()
        self.now += timedelta(seconds=1)
        result = self.components.execute(job_id=self.job_id)
        self.assertEqual(result.classification, "confirmed", result)
        self.assert_online_completed(person_deleted=False)

    def test_last_admin_intake_seals_plan_and_can_cancel_without_granting_authority(
        self,
    ):
        with self.engine.begin() as connection:
            self.saved_authority = dict(
                connection.execute(
                    text(
                        "SELECT mode,epoch,updated_at FROM ntubtob.portal_authority_state WHERE singleton_id=1"
                    )
                )
                .mappings()
                .one()
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.portal_authority_state SET mode='persistent' WHERE singleton_id=1"
                )
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"
                ),
                {"id": self.fixture.person},
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.people WHERE portal_access_level='admin' AND id<>:id"
                    ),
                    {"id": self.fixture.person},
                ),
                0,
                "fixture must have no other admin; never demote unrelated rows",
            )
        self.request(linked=True)
        self.restart()
        self.status("requested")
        # Intake/custody is not executor authority or a completed recovery path.
        with self.assertRaisesRegex(SealedPlanRejected, "verified_job_required"):
            self.components.execute(job_id=self.job_id)
        self.now += timedelta(seconds=1)
        challenge = self.challenge("cancel", provider="apple", **self.receipt_input())
        self.assertEqual(
            self.post("/api/v1/account-erasure/cancel", self.proof_payload(challenge)),
            {"id": self.job_id, "status": "cancelled"},
        )
        self.status("cancelled")
        self.assertIsNone(self.job()["irreversible_started_at"])
        self.assertEqual(self.http_calls, 0)
        self.assertEqual(self.capture_calls, 1)
        self.assertEqual(
            self.scalar(
                "SELECT portal_access_level FROM ntubtob.people WHERE id=:id",
                id=self.fixture.other_person,
            ),
            "basic",
        )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "active",
        )  # Never verified/revoked; cancellation did not create a session.
        self.assert_local_provider_rows(credentials=1, exchanges=1, identity=1)
        self.assert_other_owner_unchanged()

    def test_person_http_to_restart_deletes_revoked_session_and_only_target(self):
        self.request(linked=True)
        self.verify()
        self.restart()
        self.now += timedelta(seconds=1)
        result = self.components.execute(job_id=self.job_id)
        self.assertEqual(result.classification, "confirmed", result)
        self.assert_online_completed(person_deleted=True)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            0,
        )

    def test_cancellation_survives_restart_without_session_resurrection_or_dispatch(
        self,
    ):
        self.request(linked=True)
        self.verify()
        self.now += timedelta(seconds=1)
        challenge = self.challenge("cancel", provider="apple", **self.receipt_input())
        payload = self.proof_payload(challenge)
        self.assertEqual(
            self.post("/api/v1/account-erasure/cancel", payload),
            {"id": self.job_id, "status": "cancelled"},
        )
        self.restart()
        self.status("cancelled")
        self.assertIsNone(self.job()["irreversible_started_at"])
        with self.assertRaisesRegex(SealedPlanRejected, "receipt_read_required"):
            self.components.execute(job_id=self.job_id)
        self.post("/api/v1/account-erasure/cancel", payload, status=401)
        self.assertEqual(self.http_calls, 0)
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "revoked",
        )
        self.assert_local_provider_rows(credentials=1, exchanges=1, identity=1)
        self.assert_other_owner_unchanged()

    def test_uncertain_provider_result_cleans_local_rows_but_restart_never_resends(
        self,
    ):
        self.request()
        self.verify()
        self.http_status = 500
        self.restart()
        self.assertEqual(
            self.components.execute(job_id=self.job_id).classification,
            "needs_attention",
        )
        self.status("needs_attention")
        self.assert_local_provider_rows(credentials=1, exchanges=0, identity=1)
        self.restart()
        self.assertEqual(
            self.components.execute(job_id=self.job_id).classification,
            "needs_attention",
        )
        self.assertEqual(self.http_calls, 1)
        self.cipher.open.assert_called_once_with(b"fake")
        self.assertEqual(self.capture_calls, 1)
        self.assertIsNone(self.job()["online_completed_at"])
        self.status("needs_attention")
        self.assert_other_owner_unchanged()

    def recover(self, challenge, *, status=200):
        return self.post(
            "/api/v1/account-erasure/recovery",
            self.proof_payload(challenge),
            status=status,
        )

    def assert_recovery_read_only(self, callback):
        before = self.job()
        counts = tuple(
            self.scalar(f"SELECT count(*) FROM ntubtob.{table}")
            for table in (
                "account_erasure_jobs",
                "account_erasure_request_attempts",
                "account_erasure_steps",
                "account_erasure_items",
                "account_erasure_item_events",
                "account_erasure_sealed_plans",
            )
        )
        statements = []

        def observed(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", observed)
        try:
            result = callback()
        finally:
            event.remove(self.engine, "before_cursor_execute", observed)
        self.assertTrue(statements)
        for statement in statements:
            self.assertRegex(statement.lstrip().upper(), r"^(SELECT\b|SET LOCAL\b)")
            self.assertIsNone(
                re.match(r"\s*(INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b", statement, re.I)
            )
        self.assertEqual(self.job(), before)
        self.assertEqual(
            tuple(
                self.scalar(f"SELECT count(*) FROM ntubtob.{table}")
                for table in (
                    "account_erasure_jobs",
                    "account_erasure_request_attempts",
                    "account_erasure_steps",
                    "account_erasure_items",
                    "account_erasure_item_events",
                    "account_erasure_sealed_plans",
                )
            ),
            counts,
        )
        self.auth.authenticate.assert_not_called()
        return result

    def test_live_recovery_after_restart_returns_original_secret_expiry_and_status(
        self,
    ):
        self.request()
        self.verify()
        original_deadline = self.job()["receipt_expires_at"]
        self.restart()
        self.now += timedelta(seconds=1)
        challenge = self.challenge("recovery", provider="apple")
        result = self.assert_recovery_read_only(lambda: self.recover(challenge))
        self.assertEqual(set(result), RECOVERY_KEYS)
        self.assertEqual(result["id"], self.job_id)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["receipt_secret"], self.receipt["receipt_secret"])
        self.assertEqual(result["requested_at"], self.receipt["requested_at"])
        self.assertEqual(
            datetime.fromisoformat(result["receipt_expires_at"]), original_deadline
        )
        self.assert_times(result, "requested_at", "updated_at", "receipt_expires_at")
        self.assertEqual(self.capture_calls, 1)
        self.assertEqual(self.http_calls, 0)

    def test_wrong_subject_and_pre_request_challenge_cannot_recover_or_create_job(self):
        old = self.challenge("recovery", provider="apple")
        self.now += timedelta(seconds=1)
        self.request()
        self.restart()
        self.now += timedelta(seconds=1)
        fresh = self.challenge("recovery", provider="apple")
        self.assertion_subject = self.scalar(
            "SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id",
            id=self.fixture.other_identity,
        )
        missing = self.assert_recovery_read_only(
            lambda: self.recover(fresh, status=401)
        )
        self.assertion_subject = self.subject
        stale = self.assert_recovery_read_only(lambda: self.recover(old, status=401))
        for result in (missing, stale):
            self.assertEqual(
                result["error"]["message"], "account erasure recovery rejected"
            )
            self.assertFalse(result["error"]["retryable"])
        self.assertEqual(missing["error"]["code"], stale["error"]["code"])
        self.status("requested")
        self.assertEqual(self.http_calls, 0)

    def test_cross_purpose_and_expired_recovery_challenges_fail_before_provider(self):
        self.request()
        request_challenge = self.challenge("request", provider="apple")
        calls = self.verifier.verify.call_count
        self.recover(request_challenge, status=401)
        self.assertEqual(self.verifier.verify.call_count, calls)
        self.now += timedelta(seconds=1)
        expired = self.challenge("recovery", provider="apple")
        self.now += timedelta(seconds=121)
        self.recover(expired, status=401)
        self.assertEqual(self.verifier.verify.call_count, calls)
        self.status("requested")
        self.assertEqual(self.capture_calls, 1)

    def test_deleted_target_cannot_be_recovered_but_original_receipt_still_works(self):
        self.request()
        self.verify()
        self.restart()
        self.now += timedelta(seconds=1)
        self.assertEqual(
            self.components.execute(job_id=self.job_id).classification, "confirmed"
        )
        self.now += timedelta(seconds=1)
        self.restart()
        challenge = self.challenge("recovery", provider="apple")
        result = self.assert_recovery_read_only(
            lambda: self.recover(challenge, status=401)
        )
        self.assertEqual(
            result["error"]["message"], "account erasure recovery rejected"
        )
        self.assert_online_completed(person_deleted=False)


if __name__ == "__main__":
    unittest.main()
