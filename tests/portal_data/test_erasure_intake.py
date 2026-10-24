"""Fresh disposable PG intake -> proof -> reviewed immutable job -> erasure.

Only the Main runner supplies the opt-in local URL. Each test owns a cloned
database; cleanup never disables evidence triggers or rewinds shared schema.
All keys/provider/restore ports are fictional, with real commit boundaries.
"""

import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_module.mobile_api import (
    AuthenticationError,
    MobilePrincipal,
    VerifiedAssertion,
)
from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.erasure_components import build_erasure_components
from shared_module.portal_data.erasure_composition import (
    ErasurePlanPolicy,
    TrustedErasurePlanBuilder,
)
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    require_account_not_erasing,
)
from shared_module.portal_data.erasure_plan_codec import ErasurePlanCodec
from shared_module.portal_data.erasure_provider_execution import PreparedProviderEffect
from shared_module.portal_data.erasure_request import (
    ErasureRequestRejected,
    ErasureRequestUnavailable,
)
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository
from shared_module.portal_data.repository import ConflictError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.portal_data._fresh_erasure_database import FreshErasureDatabases
from tests.portal_data.test_erasure_fulfillment import FictionalRestoreStore
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

URL = os.environ.get("ACCOUNT_ERASURE_LEDGER_TEST_DATABASE_URL")
NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
REVISION = "0020_erasure_intake"


def migrate(connection, revision, *, downgrade=False):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    (command.downgrade if downgrade else command.upgrade)(config, revision)


@unittest.skipUnless(URL, "isolated erasure URL required")
class IntakePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.databases = FreshErasureDatabases(URL)
        cls.addClassCleanup(cls.close_databases)

        def initialize(engine):
            with engine.begin() as connection:
                connection.execute(text(LEGACY_FIXTURE_SQL))
                migrate(connection, REVISION)

        cls.databases.create_template(initialize)

    @classmethod
    def close_databases(cls):
        errors = cls.databases.close()
        if errors:
            raise AssertionError("fresh_database_cleanup_incomplete", errors)

    def setUp(self):
        self.engine = self.databases.clone()
        self.addCleanup(self.databases.release, self.engine)
        self.now = NOW
        self.subject = "fictional-intake-" + uuid4().hex
        with self.engine.begin() as connection:
            self.person = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people(display_name,portal_access_level,portal_status,version,created_at,updated_at) VALUES ('Fictional intake','basic','active',1,:now,:now) RETURNING id"
                ),
                {"now": NOW},
            )
            self.other = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people(display_name,portal_access_level,portal_status,version,created_at,updated_at) VALUES ('Other fictional','basic','active',1,:now,:now) RETURNING id"
                ),
                {"now": NOW},
            )
            self.identity = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities(provider,provider_subject,status,created_at,updated_at) VALUES ('apple',:subject,'pending',:now,:now) RETURNING id"
                ),
                {"subject": self.subject, "now": NOW},
            )
        self.review_ready = False
        self.review_calls = self.provider_calls = 0
        self.namespace = str(uuid4())
        self.verifier = Mock()
        self.verifier.verify.side_effect = self.provider_proof
        self.restore = FictionalRestoreStore()
        self.builder = TrustedErasurePlanBuilder(
            review_source=self.review,
            policy_source=lambda **values: ErasurePlanPolicy.initial_request(
                values["requested_at"]
            ),
            restore_codec=RestoreBindingCodec(
                namespace=self.namespace,
                active_key="fictional",
                keys={"fictional": b"r" * 32},
            ),
            provider_audiences={"apple": "fictional-apple"},
        )
        self.components = self.assemble()
        self.service = self.components.service

    def assemble(self):
        return build_erasure_components(
            engine=self.engine,
            receipt_key=b"s" * 32,
            proof_key=b"p" * 32,
            audience="fictional-erasure",
            proof_lifetime=timedelta(minutes=2),
            providers={"apple": (self.verifier, "fictional-apple")},
            plan_builder=self.builder,
            active_plan_key_id="fictional",
            plan_codecs={
                "fictional": ErasurePlanCodec(namespace=self.namespace, key=b"k" * 32)
            },
            prepare_provider=self.prepare_provider,
            restore_store=self.restore,
            clock=lambda: self.now,
            intake_enabled=True,
        )

    def provider_proof(self, assertion, audience, nonce, now):
        self.assertEqual(self.engine.pool.checkedout(), 0, "provider proof outside TX")
        return VerifiedAssertion(
            "apple", self.subject, audience, nonce, now + timedelta(minutes=3)
        )

    def prepare_provider(self, connection, job, item, *identity):
        def invoke():
            self.provider_calls += 1
            self.assertEqual(self.engine.pool.checkedout(), 0)
            return "credential_missing"

        return PreparedProviderEffect(
            item["binding_hash"],
            job["scope_hash"],
            str(job["expected_generation"]),
            invoke,
        )

    def review(self, **values):
        self.review_calls += 1
        if not self.review_ready:
            return None
        if values["person_id"] is None:
            return ()
        return json.dumps(
            {
                "version": 1,
                "person_id": values["person_id"],
                "generation": values["target_generation"],
                "dispositions": [],
            }
        ).encode()

    def scalar(self, sql, **values):
        with self.engine.connect() as connection:
            return connection.scalar(text(sql), values)

    def link(self, *, blocked=False):
        self.session_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status=:status WHERE id=:id"
                ),
                {
                    "person": self.person,
                    "id": self.identity,
                    "status": "blocked" if blocked else "linked",
                },
            )
            connection.execute(
                text("UPDATE ntubtob.people SET portal_status=:status WHERE id=:id"),
                {"id": self.person, "status": "blocked" if blocked else "active"},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions(id,person_id,auth_identity_id,installation_id_hash,platform,status,access_epoch,refresh_family_expires_at,created_at,updated_at) VALUES (:id,:person,:identity,:hash,'ios','active',1,:expiry,:now,:now)"
                ),
                {
                    "id": self.session_id,
                    "person": self.person,
                    "identity": self.identity,
                    "hash": uuid4().hex * 2,
                    "expiry": NOW + timedelta(days=365),
                    "now": NOW,
                },
            )
        return MobilePrincipal(
            self.session_id, self.person, self.identity, "basic", "Fictional", 1
        )

    def request(self, principal=None):
        if principal is None:
            self.challenge = self.service.restricted_challenge("apple")
            self.receipt = self.service.request_restricted(
                self.challenge["challenge_credential"], "fictional", True
            )
        else:
            self.receipt = self.service.request(principal, True)
        self.job_id = self.receipt["id"]
        self.assertEqual(self.review_calls, 0)
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )
        self.assertEqual(self.status()["status"], "requested")
        return self.receipt

    def status(self):
        return self.service.status(self.job_id, self.receipt["receipt_secret"])

    def verify(self):
        self.now += timedelta(seconds=1)
        challenge = self.service.receipt_challenge(
            self.job_id, self.receipt["receipt_secret"], "apple"
        )
        return self.service.verify_receipt(
            challenge["challenge_credential"], "fictional", True
        )

    def cancel(self):
        challenge = self.service.cancellation_challenge(
            self.job_id, self.receipt["receipt_secret"], "apple"
        )
        return self.service.cancel(challenge["challenge_credential"], "fictional", True)

    def materialize(self):
        return self.components.materialize(
            job_id=self.job_id, identity_id=self.identity
        )

    def guard(self, *, linked=False):
        with Session(self.engine) as session, session.begin():
            require_account_not_erasing(
                session,
                person_id=self.person if linked else None,
                identity_id=self.identity,
            )

    def test_pending_receipt_review_later_same_identity_and_original_dates_execute(
        self,
    ):
        original = self.request()
        self.guard()
        self.assertEqual(
            self.service.request_restricted(
                self.challenge["challenge_credential"], "fictional", True
            ),
            original,
        )
        self.verify()
        with self.assertRaises(ErasureAccessBlocked):
            self.guard()
        with self.assertRaises(AuthenticationError):
            self.service.request_restricted(
                self.challenge["challenge_credential"], "fictional", True
            )
        with self.assertRaises(ErasureRequestUnavailable):
            self.materialize()
        self.assertEqual(self.status()["status"], "verified")
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )
        self.review_ready = True
        self.now = NOW + timedelta(days=31)
        self.materialize()
        self.assertEqual(self.status()["requested_at"], original["requested_at"])
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT requested_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at,verified_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job_id},
            ).one()
            self.assertEqual(
                tuple(row),
                (
                    NOW,
                    NOW + timedelta(days=30),
                    NOW + timedelta(days=180),
                    NOW + timedelta(days=180),
                    NOW + timedelta(seconds=1),
                ),
            )
        self.assertEqual(
            self.scalar(
                "SELECT person_id IS NULL AND auth_identity_id IS NULL AND materialized_job_id=id FROM ntubtob.account_erasure_intakes WHERE id=:id",
                id=self.job_id,
            ),
            True,
        )
        self.components = self.assemble()
        result = self.components.execute(job_id=self.job_id)
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(self.status()["status"], "online_completed")
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.identity,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id", id=self.other
            ),
            1,
        )

    def test_linked_sessions_revoked_then_fresh_capture_executes_same_person(self):
        principal = self.link()
        self.request(principal)
        self.verify()
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "revoked",
        )
        self.review_ready = True
        self.materialize()
        result = self.components.execute(job_id=self.job_id)
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id", id=self.person
            ),
            0,
        )
        self.assertEqual(self.status()["status"], "online_completed")

    def test_blocked_restricted_intake_and_cancel_need_no_ordinary_session(self):
        self.link(blocked=True)
        self.request()
        self.verify()
        self.cancel()
        self.assertEqual(self.status()["status"], "cancelled")
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "revoked",
        )
        with self.assertRaises(AuthenticationError):
            self.service.request_restricted(
                self.challenge["challenge_credential"], "fictional", True
            )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_intakes"), 1
        )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )
        with self.assertRaises(ErasureRequestRejected):
            self.materialize()

    def test_plan_storage_failure_and_policy_change_preserve_verified_intake(self):
        self.request()
        self.verify()
        self.review_ready = True
        original = self.components.plan_store.store_requested

        def fail_after_store(*args):
            original(*args)
            raise RuntimeError("fictional-private-sentinel")

        with patch.object(
            self.components.plan_store, "store_requested", side_effect=fail_after_store
        ):
            with self.assertRaises(ErasureRequestUnavailable) as caught:
                self.materialize()
        self.assertNotIn("sentinel", str(caught.exception))
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_sealed_plans"), 0
        )
        self.assertEqual(self.status()["status"], "verified")
        self.builder._policy_source = lambda **values: replace(
            ErasurePlanPolicy.initial_request(values["requested_at"]),
            retention_policy_version=9,
        )
        with self.assertRaisesRegex(ErasureRequestRejected, "intake_policy_changed"):
            self.materialize()
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )

    def test_wrong_subject_and_replayed_verification_do_not_change_scope(self):
        self.request(self.link())
        original = self.subject
        self.subject = "fictional-wrong-subject"
        with self.assertRaises(AuthenticationError):
            self.verify()
        self.subject = original
        self.assertEqual(self.status()["status"], "requested")
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "active",
        )
        self.verify()
        with self.assertRaises(AuthenticationError):
            self.verify()

    def test_receipt_recovery_and_expiry_keep_original_180_day_boundary(self):
        self.request()
        self.now += timedelta(seconds=1)
        challenge = self.service.recovery_challenge("apple")
        recovered = self.service.recover_receipt(
            challenge["challenge_credential"], "fictional", True
        )
        self.assertEqual(recovered["id"], self.job_id)
        self.assertEqual(recovered["receipt_secret"], self.receipt["receipt_secret"])
        self.now = NOW + timedelta(days=31)
        self.assertEqual(self.status()["status"], "requested")
        self.now = NOW + timedelta(days=180)
        with self.assertRaises(AuthenticationError):
            self.status()

    def test_immutable_metadata_null_materialization_and_retaining_downgrade(self):
        self.request()
        for sql in (
            "UPDATE ntubtob.account_erasure_intakes SET receipt_expires_at=receipt_expires_at+interval '1 day'",
            "UPDATE ntubtob.account_erasure_intakes SET status='materialized',person_id=NULL,auth_identity_id=NULL,materialized_job_id=NULL",
            "DELETE FROM ntubtob.account_erasure_intakes",
        ):
            with self.assertRaises(DBAPIError), self.engine.begin() as connection:
                connection.execute(text(sql))
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            migrate(connection, "0019_erasure_admin_recovery", downgrade=True)
        self.assertEqual(
            self.scalar("SELECT version_num FROM ntubtob.alembic_version"), REVISION
        )

    def test_requested_admin_counts_then_verified_intake_excludes_only_target(self):
        self.link()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id IN (:a,:b)"
                ),
                {"a": self.person, "b": self.other},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.auth_identities(provider,provider_subject,person_id,status,created_at,updated_at) VALUES ('apple',:subject,:person,'linked',:now,:now)"
                ),
                {
                    "subject": "fictional-other-" + uuid4().hex,
                    "person": self.other,
                    "now": NOW,
                },
            )
            connection.execute(
                text("UPDATE ntubtob.portal_authority_state SET mode='persistent'")
            )
        self.request()

        def count(enabled):
            with Session(self.engine) as session, session.begin():
                return IdentityLifecycleRepository(
                    self.engine, erasure_checks_enabled=enabled
                )._reachable_persistent_admin_count(session)

        self.assertEqual(count(True), 2)
        self.verify()
        self.assertEqual(count(True), 1)
        self.assertEqual(count(False), 2)
        with Session(self.engine) as session, session.begin():
            repository = IdentityLifecycleRepository(
                self.engine, erasure_checks_enabled=True
            )
            with self.assertRaises(ConflictError):
                repository._assert_reachable_admin_remains(
                    session, excluding_person_id=self.other
                )

    def test_provider_proof_crossing_receipt_expiry_never_blocks_or_revokes(self):
        self.request(self.link())
        self.now = NOW + timedelta(days=180, seconds=-30)
        challenge = self.service.receipt_challenge(
            self.job_id, self.receipt["receipt_secret"], "apple"
        )

        def crosses_expiry(*values):
            assertion = self.provider_proof(*values)
            self.now += timedelta(seconds=30)
            return assertion

        self.verifier.verify.side_effect = crosses_expiry
        with self.assertRaises(AuthenticationError):
            self.service.verify_receipt(
                challenge["challenge_credential"], "fictional", True
            )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.account_erasure_intakes WHERE id=:id",
                id=self.job_id,
            ),
            "requested",
        )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "active",
        )
        self.guard(linked=True)

    def test_verification_transaction_rollback_restores_requested_and_active_session(
        self,
    ):
        self.request(self.link())
        challenge = self.service.receipt_challenge(
            self.job_id, self.receipt["receipt_secret"], "apple"
        )
        assertion = self.service.receipt_proofs.authenticate(
            challenge["challenge_credential"], "fictional"
        )
        with self.assertRaisesRegex(RuntimeError, "fictional rollback"):
            with Session(self.engine) as session, session.begin():
                self.service.receipt_coordinator.verify(session, assertion=assertion)
                self.assertEqual(
                    session.scalar(
                        text(
                            "SELECT status FROM ntubtob.account_erasure_intakes WHERE id=:id"
                        ),
                        {"id": self.job_id},
                    ),
                    "verified",
                )
                raise RuntimeError("fictional rollback")
        self.assertEqual(self.status()["status"], "requested")
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            "active",
        )
        self.assertEqual(
            self.scalar(
                "SELECT access_epoch FROM ntubtob.mobile_sessions WHERE id=:id",
                id=self.session_id,
            ),
            1,
        )
        self.guard(linked=True)

    def test_pending_identity_remap_rejects_old_proof_and_new_person_intake(self):
        self.request()
        challenge = self.service.receipt_challenge(
            self.job_id, self.receipt["receipt_secret"], "apple"
        )
        principal = self.link()
        with self.assertRaises(AuthenticationError):
            self.service.verify_receipt(
                challenge["challenge_credential"], "fictional", True
            )
        with self.assertRaises(AuthenticationError):
            self.service.request(principal, True)
        self.assertEqual(self.status()["status"], "requested")
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_intakes"), 1
        )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )

    def test_job_cannot_commit_before_plan_and_intake_materialization(self):
        self.request()
        self.verify()
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_jobs (id,target_kind,person_id,auth_identity_id,expected_generation,status,scope_version,scope_hash,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) SELECT id,target_kind,person_id,auth_identity_id,expected_generation,'requested',1,:hash,receipt_secret_hash,retention_policy_version,requested_at,requested_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at FROM ntubtob.account_erasure_intakes WHERE id=:id"
                ),
                {"id": self.job_id, "hash": "f" * 64},
            )
            self.assertEqual(
                connection.scalar(
                    text("SELECT count(*) FROM ntubtob.account_erasure_jobs")
                ),
                1,
            )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )
        self.assertEqual(self.status()["status"], "verified")

    def test_cancel_commit_wins_against_waiting_materialization(self):
        self.request()
        self.verify()
        self.review_ready = True
        challenge = self.service.cancellation_challenge(
            self.job_id, self.receipt["receipt_secret"], "apple"
        )
        assertion = self.service.cancellation_proofs.authenticate(
            challenge["challenge_credential"], "fictional"
        )
        cancelled, started, release = Event(), Event(), Event()

        def cancel():
            with Session(self.engine) as session, session.begin():
                self.service.cancellation_coordinator.cancel(
                    session, job_id=self.job_id, assertion=assertion
                )
                cancelled.set()
                if not release.wait(10):
                    raise AssertionError("cancellation release deadline exceeded")

        def materialize():
            started.set()
            with self.assertRaisesRegex(
                ErasureRequestRejected, "verified_intake_required"
            ):
                self.materialize()

        with ThreadPoolExecutor(max_workers=2) as workers:
            cancellation = workers.submit(cancel)
            try:
                self.assertTrue(cancelled.wait(5))
                materialization = workers.submit(materialize)
                self.assertTrue(started.wait(2))
                deadline, waiting = monotonic() + 2, False
                with self.engine.connect() as observer:
                    while monotonic() < deadline:
                        waiting = observer.scalar(
                            text(
                                "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=70070 AND NOT granted AND database=(SELECT oid FROM pg_database WHERE datname=current_database()))"
                            )
                        )
                        if waiting or materialization.done():
                            break
                        release.wait(0.01)
                self.assertTrue(waiting, "materialization must wait on canonical lock")
                self.assertFalse(materialization.done())
            finally:
                release.set()
            cancellation.result(timeout=7)
            materialization.result(timeout=7)
        # Both workers and the observer must return their connections before the
        # owned fixture can wait for server-side close acknowledgement and DROP.
        self.assertEqual(
            self.engine.pool.checkedout(),
            0,
            "race connections must be returned before fixture cleanup",
        )
        self.assertEqual(self.status()["status"], "cancelled")
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_sealed_plans"), 0
        )

    def test_last_admin_materialized_job_uses_0020_controlled_suspension(self):
        self.link()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"
                ),
                {"id": self.person},
            )
            connection.execute(
                text("UPDATE ntubtob.portal_authority_state SET mode='persistent'")
            )
        self.request()
        self.verify()
        self.review_ready = True
        self.materialize()
        result = self.components.execute(job_id=self.job_id)
        self.assertEqual(result.reason, "admin_recovery_required", result)
        self.assertEqual(self.provider_calls, 0)
        with self.engine.begin() as connection:
            generation = connection.scalar(
                text(
                    "SELECT expected_generation::text FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job_id},
            )
            epoch = connection.scalar(
                text("SELECT epoch FROM ntubtob.portal_authority_state")
            )
            connection.execute(
                text(
                    "SELECT ntubtob.suspend_management_for_erasure(CAST(:job AS uuid),CAST(:generation AS uuid),:epoch,CAST(:operation AS uuid))"
                ),
                dict(
                    job=self.job_id,
                    generation=generation,
                    epoch=epoch,
                    operation=str(uuid4()),
                ),
            )
        result = self.components.execute(job_id=self.job_id)
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT management_suspension_operation_id IS NOT NULL FROM ntubtob.portal_authority_state"
            ),
            True,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id", id=self.person
            ),
            0,
        )

    def test_direct_legacy_job_cannot_overlap_pending_intake_after_person_mapping(self):
        self.request()
        self.link()
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_jobs (id,target_kind,person_id,expected_generation,status,scope_version,scope_hash,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) SELECT :job,'person',id,account_generation,'requested',1,:hash,:hash,1,:now,:now,:due,:expiry,:expiry FROM ntubtob.people WHERE id=:person"
                ),
                dict(
                    job=str(uuid4()),
                    person=self.person,
                    hash="f" * 64,
                    now=NOW,
                    due=NOW + timedelta(days=30),
                    expiry=NOW + timedelta(days=180),
                ),
            )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_jobs"), 0
        )

    def test_direct_person_intake_cannot_overlap_existing_pending_job(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_jobs (id,target_kind,auth_identity_id,expected_generation,status,scope_version,scope_hash,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) SELECT :job,'pending_identity',id,account_generation,'requested',1,:hash,:hash,1,:now,:now,:due,:expiry,:expiry FROM ntubtob.auth_identities WHERE id=:identity"
                ),
                dict(
                    job=str(uuid4()),
                    identity=self.identity,
                    hash="f" * 64,
                    now=NOW,
                    due=NOW + timedelta(days=30),
                    expiry=NOW + timedelta(days=180),
                ),
            )
        self.link()
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_intakes (id,target_kind,person_id,expected_generation,status,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) SELECT :id,'person',id,account_generation,'requested',:hash,1,:now,:now,:due,:expiry,:expiry FROM ntubtob.people WHERE id=:person"
                ),
                dict(
                    id=str(uuid4()),
                    person=self.person,
                    hash="f" * 64,
                    now=NOW,
                    due=NOW + timedelta(days=30),
                    expiry=NOW + timedelta(days=180),
                ),
            )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM ntubtob.account_erasure_intakes"), 0
        )

    def test_named_default_acl_grants_are_removed_from_only_new_objects(self):
        runtime = "fictional_intake_runtime_" + uuid4().hex
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                migrate(connection, "0019_erasure_admin_recovery", downgrade=True)
                # Role/default ACL creation is rollback-only in this isolated DB.
                connection.execute(text(f'CREATE ROLE "{runtime}" NOLOGIN'))
                connection.execute(
                    text(
                        f'ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT ALL ON TABLES TO "{runtime}"'
                    )
                )
                connection.execute(
                    text(
                        f'ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT EXECUTE ON FUNCTIONS TO "{runtime}"'
                    )
                )
                migrate(connection, REVISION)
                for table in (
                    "account_erasure_intakes",
                    "account_erasure_intake_attempts",
                ):
                    for privilege in (
                        "SELECT",
                        "INSERT",
                        "UPDATE",
                        "DELETE",
                        "TRUNCATE",
                        "REFERENCES",
                        "TRIGGER",
                    ):
                        self.assertFalse(
                            connection.scalar(
                                text(
                                    "SELECT has_table_privilege(:role,:object,:privilege)"
                                ),
                                dict(
                                    role=runtime,
                                    object="ntubtob." + table,
                                    privilege=privilege,
                                ),
                            )
                        )
                    self.assertTrue(
                        connection.scalar(
                            text(
                                "SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:object AS regclass)"
                            ),
                            {"object": "ntubtob." + table},
                        )
                    )
                for function in (
                    "guard_erasure_intake",
                    "guard_erasure_intake_job",
                    "guard_erasure_intake_atomic",
                    "guard_erasure_intake_attempt",
                ):
                    self.assertFalse(
                        connection.scalar(
                            text(
                                "SELECT has_function_privilege(:role,:function,'EXECUTE')"
                            ),
                            dict(role=runtime, function="ntubtob." + function + "()"),
                        )
                    )
            finally:
                transaction.rollback()
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM pg_roles WHERE rolname=:role", role=runtime
            ),
            0,
        )

    def test_verified_intake_does_not_reopen_allowlist_bootstrap(self):
        self.request(self.link())
        self.verify()
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.portal_authority_state SET mode='persistent'")
            )
        repository = IdentityLifecycleRepository(
            self.engine, authority_mode="persistent", erasure_checks_enabled=True
        )
        with self.assertRaisesRegex(
            AuthorizationError, "allowlisted bootstrap Member required"
        ):
            repository.bootstrap_zero_admin_member(
                self.identity, 987654321, "fictional no promotion", str(uuid4())
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                tuple(
                    connection.execute(
                        text(
                            "SELECT portal_access_level,portal_status FROM ntubtob.people WHERE id=:id"
                        ),
                        {"id": self.person},
                    ).one()
                ),
                ("basic", "active"),
            )
        self.assertEqual(self.status()["status"], "verified")


if __name__ == "__main__":
    unittest.main()
