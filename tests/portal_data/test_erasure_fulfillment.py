"""Fictional pending-account vertical, with independent committed transactions."""

import hashlib
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from shared_lib.shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_lib.shared_module.portal_data import erasure_fulfillment as fulfillment
from shared_lib.shared_module.portal_data.erasure_fulfillment import (
    LOCK_TABLES,
    PendingIdentityFulfillment,
    _inventory,
    capture_pending_snapshot,
)
from shared_lib.shared_module.portal_data.erasure_person_fulfillment import (
    PersonFulfillment,
)
from shared_lib.shared_module.portal_data.erasure_plan_codec import ErasurePlanCodec
from shared_lib.shared_module.portal_data.erasure_plan_store import (
    ErasurePlanStore,
    SealedPlanRejected,
)
from shared_lib.shared_module.portal_data.erasure_provider_execution import (
    PreparedProviderEffect,
)
from shared_lib.shared_module.portal_data.erasure_receipt import load_erasure_receipt
from shared_lib.shared_module.portal_data.erasure_verification import (
    ErasureVerificationCoordinator,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)
from tests.portal_data.test_erasure_verification import AUDIENCE, NOW, proof


class FictionalRestoreStore:
    def __init__(self):
        self.records = {}
        self.calls = 0

    def put(self, record):
        self.calls += 1
        identifier = str(uuid4())
        self.records[identifier] = record
        return identifier

    def read(self, identifier):
        return self.records[identifier]


class FulfillmentConfigurationTests(unittest.TestCase):
    def test_pending_identity_accepts_only_exact_supported_providers(self):
        connection = MagicMock()
        row = dict(
            id=1,
            person_id=None,
            status="pending",
            generation=str(uuid4()),
            digest="a" * 64,
        )
        connection.execute.return_value.mappings.return_value.first.return_value = row
        for provider in ("apple", "google", "line"):
            row["provider"] = provider
            with self.subTest(provider=provider):
                self.assertIs(fulfillment._identity(connection, 1), row)
        for provider in ("unknown", "Apple", "", None):
            row["provider"] = provider
            with self.subTest(provider=provider):
                with self.assertRaises(ValueError):
                    fulfillment._identity(connection, 1)

    def test_nonapple_missing_apple_credential_is_not_provider_completion(self):
        for provider in ("google", "line"):
            with self.subTest(provider=provider):
                executor = object.__new__(PendingIdentityFulfillment)
                executor.engine = MagicMock()
                connection = MagicMock()
                snapshot = MagicMock(
                    identity_id=1, rows=(("apple_provider_credentials", ()),)
                )
                executor._context = MagicMock(
                    return_value=(
                        connection,
                        {},
                        {},
                        {"provider": (2, "confirmed", "credential_missing")},
                    )
                )
                executor._now = MagicMock(return_value=NOW)
                executor._fence = MagicMock(
                    side_effect=AssertionError("must not finalize")
                )
                with (
                    patch.object(fulfillment, "Session"),
                    patch.object(
                        fulfillment, "_identity", return_value={"provider": provider}
                    ),
                ):
                    result = executor._finalize(str(uuid4()), snapshot)
                self.assertEqual(
                    (result.classification, result.reason),
                    ("needs_attention", "required_outcome_unconfirmed"),
                )
                executor._fence.assert_not_called()

    def test_apple_missing_credential_retains_existing_completion_rule(self):
        executor = object.__new__(PendingIdentityFulfillment)
        executor.engine = MagicMock()
        snapshot = MagicMock(identity_id=1, rows=(("apple_provider_credentials", ()),))
        executor._context = MagicMock(
            return_value=(
                MagicMock(),
                {},
                {"final": {}},
                {"provider": (2, "confirmed", "credential_missing")},
            )
        )
        executor._now = MagicMock(return_value=NOW)
        executor._fence, executor._event, executor._delete = (
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        with (
            patch.object(fulfillment, "Session"),
            patch.object(fulfillment, "_identity", return_value={"provider": "apple"}),
            patch.object(fulfillment, "_inventory", return_value=()),
        ):
            result = executor._finalize(str(uuid4()), snapshot)
        self.assertEqual(
            (result.classification, result.reason), ("confirmed", "online_completed")
        )
        executor._fence.assert_called_once()

    def test_inventory_rechecks_every_table_rls_on_the_current_connection(self):
        for index, table in enumerate(LOCK_TABLES):
            for filtered in (True, None):
                with self.subTest(table=table, filtered=filtered):
                    connection = MagicMock()
                    connection.scalar.side_effect = [False] * index + [filtered]
                    with self.assertRaisesRegex(
                        ValueError, "unfiltered_tables_required"
                    ):
                        _inventory(connection, 1)
                    self.assertEqual(connection.scalar.call_count, index + 1)
                    self.assertEqual(connection.execute.call_count, 1)
                    self.assertIn(table, str(connection.scalar.call_args.args[0]))

    def test_outer_connection_and_missing_custody_port_reject(self):
        for engine in (None, object()):
            with self.assertRaisesRegex(ValueError, "invalid_configuration"):
                PendingIdentityFulfillment(
                    engine, lambda *a: None, FictionalRestoreStore()
                )

    def test_restore_fixture_readback_is_not_a_boolean(self):
        store = FictionalRestoreStore()
        marker = object()
        self.assertIs(store.read(store.put(marker)), marker)


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class PendingFulfillmentPostgresTests(unittest.TestCase):
    target_provider = "apple"

    def setUp(self):
        # Apple preparation reuses this setup as an unbound fixture method.
        self.target_provider = getattr(self, "target_provider", "apple")
        self.engine = create_engine(
            require_local_database_url(ledger.DATABASE_URL),
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=5000 -c lock_timeout=5000",
            },
            pool_timeout=5,
        )
        self.addCleanup(self.engine.dispose)
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_erasure_privacy_mutation")
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.ids = {}
        self.addCleanup(self.cleanup_fixture)
        self.fixture.setUp()
        self.fixture.transaction.commit()
        self.fixture.connection.close()
        with self.engine.begin() as connection:
            if self.target_provider != "apple":
                # Same subject in another provider is deliberately a distinct owner.
                connection.execute(
                    text(
                        "UPDATE ntubtob.auth_identities SET provider=:provider,provider_subject=(SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:other) WHERE id=:id"
                    ),
                    {
                        "provider": self.target_provider,
                        "id": self.fixture.identity,
                        "other": self.fixture.other_identity,
                    },
                )
            for identity in (self.fixture.identity, self.fixture.other_identity):
                self.seed(connection, identity)
            target = connection.execute(
                text(
                    "SELECT provider_subject,account_generation::text FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": self.fixture.identity},
            ).one()
            self.reviewed_audits = tuple(
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT id,encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM ntubtob.access_audit t WHERE auth_identity_id=:id ORDER BY id"
                    ),
                    {"id": self.fixture.identity},
                )
            )
        self.restore_binding = RestoreBindingCodec(
            namespace=str(uuid4()),
            active_key="fictional",
            keys={"fictional": b"fictional-test-key-" * 3},
        ).bind(
            provider=self.target_provider,
            audience="fictional",
            subject=target[0],
            generation=target[1],
        )
        with Session(self.engine) as session, session.begin():
            self.snapshot = capture_pending_snapshot(
                session,
                self.fixture.identity,
                reviewed_audits=self.reviewed_audits,
                restore_binding=self.restore_binding,
            )
        self.secret = "f" * 64

        with self.engine.begin() as connection:
            self.fixture.connection = connection
            self.job_id = self.fixture.job(
                target_kind="pending_identity",
                person_id=None,
                auth_identity_id=self.fixture.identity,
                expected_generation=self.snapshot.generation,
                scope_hash=self.snapshot.scope_hash,
                receipt_secret_hash=hashlib.sha256(self.secret.encode()).hexdigest(),
            )
            subject = connection.scalar(
                text(
                    "SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": self.fixture.identity},
            )
        fresh = proof(
            provider=self.target_provider,
            job_id=self.job_id,
            identity_id=self.fixture.identity,
            provider_subject=subject,
            identity_generation=self.snapshot.generation,
            target_kind="pending_identity",
            person_id=None,
            target_generation=self.snapshot.generation,
        )
        with Session(self.engine) as session, session.begin():
            ErasureVerificationCoordinator(
                verifier=lambda assertion: fresh,
                audience=AUDIENCE,
                max_proof_age=timedelta(minutes=1),
                clock=lambda: NOW,
            ).verify(session, job_id=self.job_id, assertion="fictional-proof")
        self.calls = 0
        self.provider_result = "succeeded"
        self.store = FictionalRestoreStore()
        self.executor = PendingIdentityFulfillment(
            self.engine,
            self.prepare_provider,
            self.store,
            clock=lambda: NOW + timedelta(seconds=1),
        )

    def seed(self, connection, identity):
        values = {"identity": identity, "now": NOW, "hash": uuid4().hex * 2}
        statements = {
            "identity_review_threads": "INSERT INTO ntubtob.identity_review_threads (auth_identity_id,status,last_activity_at,created_at,updated_at) VALUES (:identity,'open',:now,:now,:now) RETURNING id",
            "apple_provider_credentials": "INSERT INTO ntubtob.apple_provider_credentials (auth_identity_id,encrypted_refresh_token,refresh_token_hash,status,created_at,updated_at) VALUES (:identity,decode('66616b65','hex'),:hash,'active',:now,:now) RETURNING id",
            "apple_provider_code_exchanges": "INSERT INTO ntubtob.apple_provider_code_exchanges (auth_identity_id,code_hash,login_attempt_hash,state,created_at,updated_at) VALUES (:identity,:hash,:hash,'completed',:now,:now) RETURNING id",
            "apple_provider_notifications": "INSERT INTO ntubtob.apple_provider_notifications (auth_identity_id,jti_hash,event_type,disposition,event_at,created_at) VALUES (:identity,:hash,'email-disabled','receipt_only',:now,:now) RETURNING id",
            "access_audit": "INSERT INTO ntubtob.access_audit (action,auth_identity_id,reason,request_id,created_at) VALUES ('identity_pending',:identity,'Fictional pending',:hash,:now) RETURNING id",
        }
        for table, sql in statements.items():
            if (
                self.target_provider != "apple"
                and identity == self.fixture.identity
                and table.startswith("apple_")
            ):
                continue
            identifier = connection.scalar(text(sql), values)
            self.ids.setdefault(table, []).append(identifier)
            if table == "identity_review_threads":
                values["thread"] = identifier
        identifier = connection.scalar(
            text(
                "INSERT INTO ntubtob.identity_review_messages (thread_id,sender_role,body,body_redacted,created_at) VALUES (:thread,'applicant','Fictional applicant text',false,:now) RETURNING id"
            ),
            values,
        )
        self.ids.setdefault("identity_review_messages", []).append(identifier)

    def cleanup_fixture(self):
        transaction = getattr(self.fixture, "transaction", None)
        connection = getattr(self.fixture, "connection", None)
        try:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
        finally:
            if connection is not None:
                connection.close()
        # Only this guarded disposable DB, one exact trigger and recorded IDs.
        require_local_database_url(ledger.DATABASE_URL)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.access_audit DISABLE TRIGGER erasure_privacy_guard"
                )
            )
            for table in (
                "access_audit",
                "identity_review_messages",
                "identity_review_threads",
                "apple_provider_notifications",
                "apple_provider_code_exchanges",
                "apple_provider_credentials",
            ):
                connection.execute(
                    text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                    {"ids": self.ids.get(table, [])},
                )
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER erasure_privacy_guard"
                )
            )
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            for table, names in (
                ("auth_identities", ("identity", "other_identity")),
                ("people", ("person", "other_person")),
            ):
                for name in names:
                    identifier = getattr(self.fixture, name, None)
                    if type(identifier) is int:
                        connection.execute(
                            text(f"DELETE FROM ntubtob.{table} WHERE id=:id"),
                            {"id": identifier},
                        )

    def prepare_provider(self, connection, job, item):
        return PreparedProviderEffect(
            item["binding_hash"],
            job["scope_hash"],
            str(job["expected_generation"]),
            self.invoke,
        )

    def invoke(self):
        self.calls += 1
        # The existing executor must really commit its fence before dispatch.
        with self.engine.connect() as connection:
            self.assertIsNotNone(
                connection.scalar(
                    text(
                        "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    {"id": self.job_id},
                )
            )
        return self.provider_result

    def execute(self):
        return self.executor.execute(job_id=self.job_id, snapshot=self.snapshot)

    def scalar(self, sql, **values):
        with self.engine.connect() as connection:
            return connection.scalar(text(sql), values)

    def test_happy_path_purges_target_preserves_other_account_and_reads_receipt(self):
        result = self.execute()
        self.assertEqual(result.classification, "confirmed", result)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.store.calls, 1)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.identity,
            ),
            0,
        )
        for table, ids in self.ids.items():
            self.assertEqual(
                self.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE id=:id", id=ids[0]
                ),
                0,
            )
            self.assertEqual(
                self.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE id=:id", id=ids[1]
                ),
                1,
            )
        with Session(self.engine) as session, session.begin():
            receipt = load_erasure_receipt(
                session,
                job_id=self.job_id,
                receipt_secret=self.secret,
                clock=lambda: NOW + timedelta(seconds=2),
            )
        self.assertEqual(receipt.status, "online_completed")
        self.assertIsNone(
            self.scalar(
                "SELECT completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            )
        )
        self.assertEqual(self.execute().reason, "receipt_read_required")
        self.assertEqual((self.calls, self.store.calls), (1, 1))

    def test_unknown_provider_still_cleans_local_but_preserves_credential_identity(
        self,
    ):
        self.provider_result = None
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.ids["identity_review_messages"][0],
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.apple_provider_credentials WHERE auth_identity_id=:id",
                id=self.fixture.identity,
            ),
            1,
        )
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(self.calls, 1)

    def test_restore_boolean_never_proves_custody(self):
        self.store.read = lambda identifier: True
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(self.store.calls, 1)
        self.assertEqual(
            self.scalar(
                "SELECT auth_identity_id FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            self.fixture.identity,
        )

    def test_restore_wrong_snapshot_readback_never_proves_custody(self):
        self.store.read = lambda identifier: replace(
            self.store.records[identifier], scope_hash="f" * 64
        )
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(self.store.calls, 1)

    def test_new_shared_admin_message_drift_preserves_thread_and_identity(self):
        with self.engine.begin() as connection:
            identifier = connection.scalar(
                text(
                    "INSERT INTO ntubtob.identity_review_messages (thread_id,sender_role,sender_person_id,body,body_redacted,created_at) VALUES (:thread,'admin',:person,'Other author must survive',false,:now) RETURNING id"
                ),
                dict(
                    thread=self.ids["identity_review_threads"][0],
                    person=self.fixture.other_person,
                    now=NOW,
                ),
            )
            self.ids["identity_review_messages"].append(identifier)
        self.assertEqual(self.execute().classification, "not_applied")
        self.assertEqual(self.calls, 0)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=identifier,
            ),
            1,
        )
        with Session(self.engine) as session, session.begin():
            with self.assertRaisesRegex(ValueError, "shared_content_requires_review"):
                capture_pending_snapshot(
                    session,
                    self.fixture.identity,
                    reviewed_audits=self.reviewed_audits,
                    restore_binding=self.restore_binding,
                )

    def test_credential_row_change_is_caught_without_secret_projection(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.apple_provider_credentials SET encrypted_refresh_token=decode('626164','hex') WHERE auth_identity_id=:id"
                ),
                {"id": self.fixture.identity},
            )
        self.assertEqual(self.execute().classification, "not_applied")
        self.assertEqual(self.calls, 0)
        self.assertNotIn("fictional", repr(self.snapshot))

    def test_extra_item_is_rejected(self):
        self.assertEqual(
            self.executor.prepare(
                job_id=self.job_id, snapshot=self.snapshot
            ).classification,
            "confirmed",
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'online_erasure',:hash,:generation,:now)"
                ),
                dict(
                    id=str(uuid4()),
                    job=self.job_id,
                    hash="e" * 64,
                    generation=self.snapshot.generation,
                    now=NOW + timedelta(seconds=1),
                ),
            )
        self.assertEqual(self.execute().reason, "workset_changed")
        self.assertEqual(self.calls, 0)

    def test_incomplete_workset_is_rejected_without_filling_missing_items(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'online_erasure',:hash,:generation,:now)"
                ),
                dict(
                    id=str(uuid4()),
                    job=self.job_id,
                    hash="e" * 64,
                    generation=self.snapshot.generation,
                    now=NOW,
                ),
            )
        self.assertEqual(self.execute().reason, "workset_changed")
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_items WHERE job_id=:id",
                id=self.job_id,
            ),
            1,
        )
        self.assertEqual(self.calls, 0)

    def test_schema_shadow_fk_rejects_before_side_effect(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.apple_provider_code_exchanges ADD CONSTRAINT fictional_pending_shadow FOREIGN KEY(id) REFERENCES ntubtob.auth_identities(id) NOT VALID"
                )
            )
        try:
            self.assertEqual(self.execute().reason, "schema_changed")
            self.assertEqual(self.calls, 0)
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE ntubtob.apple_provider_code_exchanges DROP CONSTRAINT fictional_pending_shadow"
                    )
                )

    def test_final_delete_failure_rolls_back_completion_and_credentials(self):
        def reject_delete(
            connection, cursor, statement, parameters, context, executemany
        ):
            if statement.startswith("DELETE FROM ntubtob.auth_identities"):
                raise RuntimeError("fictional final delete fault")

        event.listen(self.engine, "before_cursor_execute", reject_delete)
        try:
            self.assertEqual(self.execute().classification, "not_applied")
        finally:
            event.remove(self.engine, "before_cursor_execute", reject_delete)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.apple_provider_credentials WHERE auth_identity_id=:id",
                id=self.fixture.identity,
            ),
            1,
        )
        self.assertIsNone(
            self.scalar(
                "SELECT online_completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            )
        )

    def test_final_commit_uncertainty_never_resubmits_provider_or_restore(self):
        def uncertain(session):
            if session.info.get("pending_fulfillment_final"):
                raise RuntimeError("fictional lost commit acknowledgement")

        event.listen(Session, "after_commit", uncertain)
        try:
            self.assertEqual(self.execute().classification, "outcome_unknown")
        finally:
            event.remove(Session, "after_commit", uncertain)
        self.assertEqual(self.execute().reason, "receipt_read_required")
        self.assertEqual((self.calls, self.store.calls), (1, 1))


class _NonApplePendingFixture:
    """Reuse fixture methods, not the Apple-only credential expectations."""

    seed = PendingFulfillmentPostgresTests.seed
    cleanup_fixture = PendingFulfillmentPostgresTests.cleanup_fixture
    prepare_provider = PendingFulfillmentPostgresTests.prepare_provider
    invoke = PendingFulfillmentPostgresTests.invoke
    scalar = PendingFulfillmentPostgresTests.scalar
    test_shared_admin_content_is_preserved = (
        PendingFulfillmentPostgresTests.test_new_shared_admin_message_drift_preserves_thread_and_identity
    )

    def plan_store(self):
        return ErasurePlanStore(
            active_key_id="fictional",
            codecs={
                "fictional": ErasurePlanCodec(namespace=self.namespace, key=b"F" * 32)
            },
            clock=lambda: NOW + timedelta(seconds=1),
        )

    def setUp(self):
        self.namespace = str(uuid4())
        original = ledger.ErasureLedgerPostgresTests.job

        def job_and_plan(fixture_instance, **values):
            job = original(fixture_instance, **values)
            self.plan_store().store_requested(
                fixture_instance.connection, job, self.snapshot
            )
            return job

        with patch.object(ledger.ErasureLedgerPostgresTests, "job", job_and_plan):
            PendingFulfillmentPostgresTests.setUp(self)

    def execute(self):
        # Reconstruct custody and the fixed executors from committed state.
        # The provider port is explicitly fictional, not an Apple adapter fallback.
        return self.plan_store().execute_stored(
            self.engine,
            job_id=self.job_id,
            pending_executor=PendingIdentityFulfillment(
                self.engine,
                self.prepare_provider,
                self.store,
                clock=lambda: NOW + timedelta(seconds=1),
            ),
            person_executor=PersonFulfillment(
                self.engine,
                self.prepare_provider,
                self.store,
                clock=lambda: NOW + timedelta(seconds=1),
            ),
        )

    def test_sealed_restart_explicit_provider_success_and_same_subject_other_owner(
        self,
    ):
        self.assertEqual(dict(self.snapshot.rows)["apple_provider_credentials"], ())
        self.assertEqual(self.execute().reason, "online_completed")
        self.assertEqual((self.calls, self.store.calls), (1, 1))
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.identity,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.other_identity,
            ),
            1,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.apple_provider_credentials WHERE auth_identity_id=:id",
                id=self.fixture.other_identity,
            ),
            1,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.ids["identity_review_messages"][1],
            ),
            1,
        )
        with Session(self.engine) as session, session.begin():
            receipt = load_erasure_receipt(
                session,
                job_id=self.job_id,
                receipt_secret=self.secret,
                clock=lambda: NOW + timedelta(seconds=2),
            )
        self.assertEqual(receipt.status, "online_completed")
        self.assertIsNone(
            self.scalar(
                "SELECT completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            )
        )
        with self.assertRaisesRegex(SealedPlanRejected, "receipt_read_required"):
            self.execute()
        self.assertEqual((self.calls, self.store.calls), (1, 1))

    def assert_unconfirmed_provider(self, outcome):
        self.provider_result = outcome
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.ids["identity_review_messages"][0],
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.identity,
            ),
            1,
        )
        self.assertIsNone(
            self.scalar(
                "SELECT online_completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            )
        )
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual((self.calls, self.store.calls), (1, 1))

    def test_missing_apple_credential_cannot_complete_nonapple(self):
        self.assert_unconfirmed_provider("credential_missing")

    def test_manual_provider_result_cannot_complete(self):
        self.assert_unconfirmed_provider("manual_action_needed")

    def test_unknown_provider_result_cannot_complete_or_resend(self):
        self.assert_unconfirmed_provider(None)

    def test_provider_remap_rejects_old_generation_before_items_or_dispatch(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET provider='apple',provider_subject=:subject WHERE id=:id"
                ),
                {
                    "subject": "fictional-remap-" + str(uuid4()),
                    "id": self.fixture.identity,
                },
            )
        self.assertNotEqual(
            self.scalar(
                "SELECT account_generation::text FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.identity,
            ),
            self.snapshot.generation,
        )
        with self.assertRaisesRegex(SealedPlanRejected, "sealed_plan_binding_changed"):
            self.execute()
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_items WHERE job_id=:id",
                id=self.job_id,
            ),
            0,
        )
        self.assertEqual((self.calls, self.store.calls), (0, 0))


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class GooglePendingFulfillmentPostgresTests(_NonApplePendingFixture, unittest.TestCase):
    target_provider = "google"


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class LinePendingFulfillmentPostgresTests(_NonApplePendingFixture, unittest.TestCase):
    target_provider = "line"


if __name__ == "__main__":
    unittest.main()
