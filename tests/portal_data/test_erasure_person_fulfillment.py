"""Fictional linked-Person vertical; only opt-in isolated PostgreSQL is used."""

import hashlib
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from shared_lib.shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_lib.shared_module.portal_data import (
    erasure_person_fulfillment as person_module,
)
from shared_lib.shared_module.portal_data.erasure_person_fulfillment import (
    CONTENT_FIELDS,
    LOCK_TABLES,
    PersonFulfillment,
    _lock,
    capture_person_snapshot,
    seal_reviewed_person_disposition,
)
from shared_lib.shared_module.portal_data.erasure_provider_execution import (
    PreparedProviderEffect,
)
from shared_lib.shared_module.portal_data.erasure_receipt import load_erasure_receipt
from shared_lib.shared_module.portal_data.erasure_verification import (
    ErasureVerificationCoordinator,
)
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data import test_erasure_structured_execution as structured_fixture
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)
from tests.portal_data.test_erasure_fulfillment import FictionalRestoreStore
from tests.portal_data.test_erasure_verification import AUDIENCE, NOW, proof

structured = structured_fixture.module


class PersonFulfillmentConfigurationTests(unittest.TestCase):
    def test_admin_uses_existing_reachable_policy_on_same_connection_excluding_self(
        self,
    ):
        connection = Mock()
        connection.scalar.return_value = False
        connection.execute.side_effect = [
            Mock(**{"first.return_value": ("generation", "digest", "admin")}),
            Mock(**{"all.return_value": [(1, "persistent", 1)]}),
            [(2, "apple", "identity-generation", "identity-digest")],
        ]
        with (
            patch.object(person_module, "Session") as session_type,
            patch.object(
                IdentityLifecycleRepository,
                "_reachable_persistent_admin_count",
                return_value=1,
            ) as count,
        ):
            result = person_module._roots(
                connection,
                7,
                job_id=str(uuid4()),
                generation=str(uuid4()),
                scope_hash="a" * 64,
            )
        self.assertEqual(result[0], ("generation", "digest"))
        session_type.assert_called_once_with(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        count.assert_called_once_with(
            session_type.return_value.__enter__.return_value, excluding_person_id=7
        )

    def test_admin_authority_must_be_unfiltered_exact_persistent_singleton(self):
        for filtered, states in (
            (True, [(1, "persistent", 1)]),
            (None, [(1, "persistent", 1)]),
            (False, []),
            (False, [(1, "persistent", 1), (1, "persistent", 2)]),
            (False, [(1, "legacy_allowlist", 1)]),
            (False, [(1, "persistent", 0)]),
            (False, [(1, "persistent", True)]),
        ):
            with self.subTest(filtered=filtered, states=states):
                connection = Mock()
                connection.scalar.return_value = filtered
                connection.execute.return_value.all.return_value = states
                with patch.object(person_module, "Session") as session_type:
                    with self.assertRaisesRegex(
                        ValueError, "^admin_authority_unavailable$"
                    ):
                        person_module._require_admin_survivor(
                            connection,
                            7,
                            job_id=str(uuid4()),
                            generation=str(uuid4()),
                            scope_hash="a" * 64,
                        )
                session_type.assert_not_called()
                if filtered is not False:
                    connection.execute.assert_not_called()

    def test_admin_count_unavailable_has_fixed_error_without_private_detail(self):
        connection = Mock()
        connection.scalar.return_value = False
        connection.execute.return_value.all.return_value = [(1, "persistent", 1)]
        with (
            patch.object(person_module, "Session"),
            patch.object(
                IdentityLifecycleRepository,
                "_reachable_persistent_admin_count",
                side_effect=person_module.AuthorizationError(
                    "fictional private detail"
                ),
            ),
        ):
            with self.assertRaisesRegex(
                ValueError, "^admin_authority_unavailable$"
            ) as caught:
                person_module._require_admin_survivor(
                    connection,
                    7,
                    job_id=str(uuid4()),
                    generation=str(uuid4()),
                    scope_hash="a" * 64,
                )
        self.assertIsNone(caught.exception.__cause__)

    def test_each_filtered_inventory_table_rejects_before_any_row_read_or_mutation(
        self,
    ):
        for index, table in enumerate(LOCK_TABLES):
            for filtered in (True, None):
                with self.subTest(table=table, filtered=filtered):
                    connection = Mock()
                    connection.scalars.return_value = ("0018_erasure_privacy_mutation",)
                    connection.scalar.side_effect = [False] * index + [filtered]
                    with self.assertRaisesRegex(
                        ValueError, "unfiltered_tables_required"
                    ):
                        _lock(connection)
                    self.assertEqual(connection.execute.call_count, 1)
                    self.assertEqual(connection.scalar.call_count, index + 1)

    def test_non_engine_is_never_transaction_authority(self):
        for engine in (None, object()):
            with self.assertRaisesRegex(ValueError, "invalid_configuration"):
                PersonFulfillment(engine, lambda *args: None, FictionalRestoreStore())

    def test_review_requires_explicit_full_content_field_decision_before_sql(self):
        connection = Mock()
        with self.assertRaisesRegex(ValueError, "reviewed_dispositions_required"):
            seal_reviewed_person_disposition(
                connection,
                table="identity_review_messages",
                row_id=1,
                action="retain",
                patch={},
                reviewed_fields=(),
                decision="no_target_content_after_disposition",
            )
        connection.execute.assert_not_called()

    def test_game_review_accepts_only_exact_text_patch_or_retain(self):
        connection = Mock()
        connection.execute.return_value.first.return_value = ("a" * 64, "b" * 64)
        for action, patch in (
            ("update", {"location": "Reviewed shared ground", "home_team": None}),
            ("retain", {}),
        ):
            with self.subTest(action=action):
                result = seal_reviewed_person_disposition(
                    connection,
                    table="games",
                    row_id=1,
                    action=action,
                    patch=patch,
                    reviewed_fields=CONTENT_FIELDS["games"],
                    decision="no_target_content_after_disposition",
                )
                self.assertEqual(result.action, action)
        for action, patch in (
            ("delete", {}),
            ("update", {"year": 2036}),
            ("update", {"location": 123}),
            ("update", {"away_team": []}),
        ):
            with self.subTest(action=action, patch=patch):
                connection.reset_mock()
                with self.assertRaisesRegex(ValueError, "invalid_game_disposition"):
                    seal_reviewed_person_disposition(
                        connection,
                        table="games",
                        row_id=1,
                        action=action,
                        patch=patch,
                        reviewed_fields=CONTENT_FIELDS["games"],
                        decision=(
                            "own_content_delete"
                            if action == "delete"
                            else "no_target_content_after_disposition"
                        ),
                    )
                connection.execute.assert_not_called()


class _PersonFulfillmentFixture:
    insert = structured_fixture.StructuredExecutionPostgresTests.insert
    seed_person = structured_fixture.StructuredExecutionPostgresTests.seed_person

    def setUp(self):
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
        self.saved = {}
        self.owned = [{name: [] for name in structured.DELETE_ORDER} for _ in range(2)]
        self.reviews = []
        self.addCleanup(self.cleanup_fixture)
        self.fixture.setUp()
        self.fixture.transaction.commit()
        self.fixture.connection.close()
        with self.engine.begin() as connection:
            for person, identity in (
                (self.fixture.person, self.fixture.identity),
                (self.fixture.other_person, self.fixture.other_identity),
            ):
                connection.execute(
                    text(
                        "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                    ),
                    {"person": person, "id": identity},
                )
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"
                ),
                {"id": self.fixture.other_person},
            )
            self.line = self.insert(
                connection,
                "auth_identities",
                dict(
                    provider="line",
                    provider_subject="fictional-line-" + uuid4().hex,
                    person_id=self.fixture.person,
                    status="linked",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            self.event_id = self.insert(
                connection,
                "events",
                dict(
                    title="Fictional target in shared title",
                    event_type="practice",
                    status="draft",
                    start_at=NOW,
                    created_by_person_id=self.fixture.person,
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            self.activity_id = self.insert(
                connection,
                "activities",
                dict(
                    event_id=self.event_id,
                    title="Fictional target meal",
                    activity_type="meal",
                    position=1,
                    start_at=NOW,
                ),
            )
            for owner, (person, identity) in enumerate(
                (
                    (self.fixture.person, self.fixture.identity),
                    (self.fixture.other_person, self.fixture.other_identity),
                )
            ):
                self.seed_person(connection, owner, person, identity)
            self.active = self.owned[0]["mobile_sessions"][0]
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_sessions SET status='active',revoked_at=NULL,access_epoch=4,updated_at=:now WHERE id=:id"
                ),
                {"id": self.active, "now": NOW - timedelta(seconds=10)},
            )
            self.revoked = self.insert(
                connection,
                "mobile_sessions",
                dict(
                    id=str(uuid4()),
                    auth_identity_id=self.line,
                    person_id=self.fixture.person,
                    installation_id_hash=uuid4().hex * 2,
                    platform="android",
                    status="revoked",
                    access_epoch=8,
                    refresh_family_expires_at=NOW + timedelta(hours=1),
                    revoked_at=NOW - timedelta(seconds=15),
                    created_at=NOW - timedelta(seconds=20),
                    updated_at=NOW - timedelta(seconds=15),
                ),
                0,
            )
            game = self.insert(
                connection,
                "games",
                dict(
                    year=2035,
                    location="Fictional target ground",
                    home_team="Fictional target team",
                    away_team="Other shared team",
                ),
            )
            self.game = game
            self.game_before = connection.scalar(
                text("SELECT to_jsonb(t) FROM ntubtob.games t WHERE id=:id"),
                {"id": game},
            )
            self.game_patch = {
                "location": "Reviewed shared ground",
                "home_team": "Reviewed home team",
            }
            self.review(connection, "games", game, "update", self.game_patch)
            member = self.insert(
                connection,
                "members",
                dict(name="Fictional owned member", person_id=self.fixture.person),
            )
            subject = connection.scalar(
                text(
                    "SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": self.line},
            )
            user = self.insert(
                connection,
                "line_users",
                dict(
                    nickname="Fictional owned nickname",
                    line_user_id=subject,
                    member_id=member,
                    has_replied=False,
                    ignored=False,
                ),
            )
            reply_type = connection.scalar(
                text(
                    "SELECT id FROM ntubtob.attendance_reply_types ORDER BY id LIMIT 1"
                )
            )
            self.insert(
                connection,
                "game_attendance_replies",
                dict(
                    game_id=game,
                    person_id=self.fixture.person,
                    member_id=member,
                    user_id=user,
                    reply=reply_type,
                ),
            )
            thread = self.insert(
                connection,
                "identity_review_threads",
                dict(
                    auth_identity_id=self.fixture.identity,
                    status="open",
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            self.thread = thread
            self.own_message = self.insert(
                connection,
                "identity_review_messages",
                dict(
                    thread_id=thread,
                    sender_role="applicant",
                    body="Fictional own message",
                    body_redacted=False,
                    created_at=NOW,
                ),
            )
            self.shared_message = self.insert(
                connection,
                "identity_review_messages",
                dict(
                    thread_id=thread,
                    sender_role="admin",
                    sender_person_id=self.fixture.other_person,
                    body="Fictional other admin reviewed response",
                    body_redacted=False,
                    created_at=NOW,
                ),
            )
            audit = self.insert(
                connection,
                "access_audit",
                dict(
                    action="identity_pending",
                    auth_identity_id=self.fixture.identity,
                    reason="Fictional owned identity history",
                    request_id=str(uuid4()),
                    created_at=NOW,
                ),
            )
            self.review(
                connection,
                "events",
                self.event_id,
                "update",
                {"created_by_person_id": None, "title": "Reviewed shared title"},
            )
            self.review(
                connection,
                "activities",
                self.activity_id,
                "update",
                {"title": "Reviewed shared activity"},
            )
            self.review(
                connection,
                "identity_review_threads",
                thread,
                "update",
                {"auth_identity_id": None},
            )
            self.review(
                connection, "identity_review_messages", self.own_message, "delete", {}
            )
            self.review(
                connection,
                "identity_review_messages",
                self.shared_message,
                "retain",
                {},
            )
            self.review(connection, "access_audit", audit, "delete", {})
            self.shared_manager = self.insert(
                connection,
                "event_managers",
                dict(
                    event_id=self.event_id,
                    person_id=self.fixture.other_person,
                    assigned_by_person_id=self.fixture.person,
                    created_at=NOW,
                ),
            )
            self.review(
                connection,
                "event_managers",
                self.shared_manager,
                "update",
                {"assigned_by_person_id": None},
            )
            self.shared_qualification = self.insert(
                connection,
                "person_qualifications",
                dict(
                    person_id=self.fixture.other_person,
                    qualification="staff",
                    status="active",
                    granted_by_person_id=self.fixture.person,
                    reason="Fictional target mentioned in shared reason",
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            self.review(
                connection,
                "person_qualifications",
                self.shared_qualification,
                "update",
                {
                    "granted_by_person_id": None,
                    "reason": "Reviewed shared qualification",
                },
            )
            self.own_qualification = self.insert(
                connection,
                "person_qualifications",
                dict(
                    person_id=self.fixture.person,
                    qualification="team_player",
                    status="active",
                    granted_by_person_id=self.fixture.other_person,
                    reason="Fictional owned qualification",
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            self.review(
                connection,
                "person_qualifications",
                self.own_qualification,
                "delete",
                {},
            )
            self.insert(
                connection,
                "account_deletion_requests",
                dict(
                    id=str(uuid4()),
                    person_id=self.fixture.person,
                    status="requested",
                    requested_at=NOW,
                ),
            )
            self.unlinked_event = self.insert(
                connection,
                "events",
                dict(
                    title="Fictional target mention without account FK",
                    event_type="practice",
                    status="draft",
                    start_at=NOW,
                    created_by_person_id=self.fixture.other_person,
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            self.review(
                connection,
                "events",
                self.unlinked_event,
                "update",
                {"title": "Reviewed unrelated shared event"},
            )
            self.configure_target(connection)
        self.codec = RestoreBindingCodec(
            namespace=str(uuid4()),
            active_key="fictional",
            keys={"fictional": b"fictional-key-" * 4},
        )
        with Session(self.engine) as session, session.begin():
            self.snapshot = capture_person_snapshot(
                session,
                self.fixture.person,
                reviewed_dispositions=tuple(self.reviews),
                restore_codec=self.codec,
                provider_audiences={
                    "apple": "fictional-apple",
                    "line": "fictional-line",
                },
            )
        self.secret = "f" * 64
        with self.engine.begin() as connection:
            self.fixture.connection = connection
            self.job_id = self.fixture.job(
                expected_generation=self.snapshot.generation,
                scope_hash=self.snapshot.scope_hash,
                receipt_secret_hash=hashlib.sha256(self.secret.encode()).hexdigest(),
            )
            target = connection.execute(
                text(
                    "SELECT provider_subject,account_generation::text FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": self.fixture.identity},
            ).one()
        fresh = proof(
            job_id=self.job_id,
            identity_id=self.fixture.identity,
            provider_subject=target[0],
            identity_generation=target[1],
            person_id=self.fixture.person,
            target_generation=self.snapshot.generation,
        )
        with Session(self.engine) as session, session.begin():
            ErasureVerificationCoordinator(
                verifier=lambda assertion: fresh,
                audience=AUDIENCE,
                max_proof_age=timedelta(minutes=1),
                clock=lambda: NOW,
            ).verify(session, job_id=self.job_id, assertion="fictional-one-proof")
        self.calls = []
        self.provider_result = "succeeded"
        self.store = FictionalRestoreStore()
        self.executor = PersonFulfillment(
            self.engine,
            self.prepare_provider,
            self.store,
            clock=lambda: NOW + timedelta(seconds=1),
        )

    def configure_target(self, connection):
        """Scenario hook runs before the immutable snapshot and request exist."""

    def review(self, connection, table, identifier, action, patch):
        self.reviews.append(
            seal_reviewed_person_disposition(
                connection,
                table=table,
                row_id=identifier,
                action=action,
                patch=patch,
                reviewed_fields=CONTENT_FIELDS[table],
                decision=(
                    "own_content_delete"
                    if action == "delete"
                    else "no_target_content_after_disposition"
                ),
            )
        )

    def prepare_provider(self, connection, job, item, identity):
        def invoke():
            self.calls.append(identity.provider)
            with self.engine.connect() as probe:
                self.assertIsNotNone(
                    probe.scalar(
                        text(
                            "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                        ),
                        {"id": self.job_id},
                    )
                )
            return (
                "credential_missing"
                if identity.provider == "line"
                else self.provider_result
            )

        return PreparedProviderEffect(
            item["binding_hash"],
            job["scope_hash"],
            str(job["expected_generation"]),
            invoke,
        )

    def execute(self):
        return self.executor.execute(job_id=self.job_id, snapshot=self.snapshot)

    def scalar(self, sql, **values):
        with self.engine.connect() as connection:
            return connection.scalar(text(sql), values)

    def cleanup_fixture(self):
        transaction = getattr(self.fixture, "transaction", None)
        connection = getattr(self.fixture, "connection", None)
        try:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
        finally:
            if connection is not None:
                connection.close()
        require_local_database_url(ledger.DATABASE_URL)
        with self.engine.begin() as connection:
            if getattr(self, "saved_authority", None) is not None:
                connection.execute(
                    text(
                        "UPDATE ntubtob.portal_authority_state SET mode=:mode,epoch=:epoch,updated_at=:updated_at WHERE singleton_id=1"
                    ),
                    self.saved_authority,
                )
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.access_audit DISABLE TRIGGER erasure_privacy_guard"
                )
            )
            for table in (
                *structured.DELETE_ORDER,
                "access_audit",
                "identity_review_messages",
                "identity_review_threads",
                "apple_provider_credentials",
                "account_deletion_requests",
                "event_managers",
                "person_qualifications",
                "game_attendance_replies",
                "line_users",
                "members",
                "activities",
                "events",
                "games",
            ):
                ids = self.saved.get(table, [])
                if ids:
                    column = (
                        "id::text" if table == "account_deletion_requests" else "id"
                    )
                    connection.execute(
                        text(f"DELETE FROM ntubtob.{table} WHERE {column}=ANY(:ids)"),
                        {
                            "ids": (
                                [str(identifier) for identifier in ids]
                                if table == "account_deletion_requests"
                                else ids
                            )
                        },
                    )
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER erasure_privacy_guard"
                )
            )
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            for table, identifiers in (
                (
                    "auth_identities",
                    [
                        getattr(self.fixture, "identity", None),
                        getattr(self.fixture, "other_identity", None),
                        *self.saved.get("auth_identities", []),
                    ],
                ),
                (
                    "people",
                    [
                        getattr(self.fixture, "person", None),
                        getattr(self.fixture, "other_person", None),
                    ],
                ),
            ):
                connection.execute(
                    text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                    {"ids": [value for value in identifiers if type(value) is int]},
                )


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class PersonFulfillmentPostgresTests(_PersonFulfillmentFixture, unittest.TestCase):
    def test_two_provider_person_online_completion_preserves_other_person_and_shared_content(
        self,
    ):
        result = self.execute()
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(sorted(self.calls), ["apple", "line"])
        self.assertEqual(self.store.calls, 2)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=ANY(:ids)",
                ids=[self.fixture.identity, self.line],
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.other_person,
            ),
            1,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.own_message,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT body FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.shared_message,
            ),
            "Fictional other admin reviewed response",
        )
        self.assertIsNone(
            self.scalar(
                "SELECT auth_identity_id FROM ntubtob.identity_review_threads WHERE id=:id",
                id=self.thread,
            )
        )
        self.assertEqual(
            self.scalar(
                "SELECT title FROM ntubtob.events WHERE id=:id", id=self.event_id
            ),
            "Reviewed shared title",
        )
        for table, ids in self.owned[1].items():
            self.assertEqual(
                self.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)", ids=ids
                ),
                len(ids),
                table,
            )
        with Session(self.engine) as session, session.begin():
            receipt = load_erasure_receipt(
                session,
                job_id=self.job_id,
                receipt_secret=self.secret,
                clock=lambda: NOW + timedelta(seconds=2),
            )
        self.assertEqual(receipt.status, "online_completed")
        self.assertEqual(self.execute().reason, "receipt_read_required")
        self.assertEqual(len(self.calls), 2)
        self.assertIsNone(
            self.scalar(
                "SELECT assigned_by_person_id FROM ntubtob.event_managers WHERE id=:id",
                id=self.shared_manager,
            )
        )
        self.assertEqual(
            self.scalar(
                "SELECT reason FROM ntubtob.person_qualifications WHERE id=:id",
                id=self.shared_qualification,
            ),
            "Reviewed shared qualification",
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.person_qualifications WHERE id=:id",
                id=self.own_qualification,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_deletion_requests WHERE person_id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT title FROM ntubtob.events WHERE id=:id", id=self.unlinked_event
            ),
            "Reviewed unrelated shared event",
        )
        self.assertEqual(
            self.scalar(
                "SELECT created_by_person_id FROM ntubtob.events WHERE id=:id",
                id=self.unlinked_event,
            ),
            self.fixture.other_person,
        )

    def test_unknown_provider_still_purges_local_but_keeps_target_credentials(self):
        self.provider_result = None
        result = self.execute()
        self.assertEqual(result.classification, "needs_attention", result)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.mobile_sessions WHERE person_id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.members WHERE person_id=:id",
                id=self.fixture.person,
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
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            1,
        )
        self.execute()
        self.assertEqual(len(self.calls), 2)

    def test_provider_credential_or_session_payload_drift_rejects_before_dispatch(self):
        for table, sql, identifier in (
            (
                "mobile_sessions",
                "UPDATE ntubtob.mobile_sessions SET installation_id_hash=:value WHERE id=:id",
                self.active,
            ),
            (
                "mobile_sessions",
                "UPDATE ntubtob.mobile_sessions SET access_epoch=access_epoch+1 WHERE id=:id",
                self.revoked,
            ),
            (
                "mobile_refresh_tokens",
                "UPDATE ntubtob.mobile_refresh_tokens SET token_hash=:value WHERE id=:id",
                self.owned[0]["mobile_refresh_tokens"][0],
            ),
            (
                "apple_provider_credentials",
                "UPDATE ntubtob.apple_provider_credentials SET refresh_token_hash=:value WHERE id=:id",
                self.saved["apple_provider_credentials"][0],
            ),
        ):
            with self.subTest(table=table):
                with self.engine.begin() as connection:
                    original = connection.scalar(
                        text(f"SELECT to_jsonb(t) FROM ntubtob.{table} t WHERE id=:id"),
                        {"id": identifier},
                    )
                    connection.execute(
                        text(sql), {"id": identifier, "value": uuid4().hex * 2}
                    )
                result = self.execute()
                self.assertEqual(result.classification, "not_applied", result)
                self.assertEqual(self.calls, [])
                with self.engine.begin() as connection:
                    fields = {
                        "mobile_sessions": ("installation_id_hash", "access_epoch"),
                        "mobile_refresh_tokens": ("token_hash",),
                        "apple_provider_credentials": ("refresh_token_hash",),
                    }[table]
                    connection.execute(
                        text(
                            f"UPDATE ntubtob.{table} SET "
                            + ",".join(name + "=:" + name for name in fields)
                            + " WHERE id=:id"
                        ),
                        dict(original, id=identifier),
                    )

    def test_missing_review_rejects_without_default_retain(self):
        with Session(self.engine) as session, session.begin():
            with self.assertRaisesRegex(ValueError, "reviewed_dispositions_required"):
                capture_person_snapshot(
                    session,
                    self.fixture.person,
                    reviewed_dispositions=tuple(
                        review
                        for review in self.reviews
                        if review.table != "access_audit"
                    ),
                    restore_codec=self.codec,
                    provider_audiences={
                        "apple": "fictional-apple",
                        "line": "fictional-line",
                    },
                )

    def test_explicit_review_anchor_includes_unlinked_shared_text_without_authority_to_delete(
        self,
    ):
        with self.engine.begin() as connection:
            identifier = self.insert(
                connection,
                "events",
                dict(
                    title="Fictional unrelated target mention",
                    event_type="practice",
                    status="draft",
                    start_at=NOW,
                    created_by_person_id=self.fixture.other_person,
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            extra = seal_reviewed_person_disposition(
                connection,
                table="events",
                row_id=identifier,
                action="update",
                patch={"title": "Reviewed unrelated event"},
                reviewed_fields=CONTENT_FIELDS["events"],
                decision="no_target_content_after_disposition",
            )
            illegal = seal_reviewed_person_disposition(
                connection,
                table="events",
                row_id=identifier,
                action="delete",
                patch={},
                reviewed_fields=CONTENT_FIELDS["events"],
                decision="own_content_delete",
            )
        with Session(self.engine) as session, session.begin():
            captured = capture_person_snapshot(
                session,
                self.fixture.person,
                reviewed_dispositions=(*self.reviews, extra),
                restore_codec=self.codec,
                provider_audiences={
                    "apple": "fictional-apple",
                    "line": "fictional-line",
                },
            )
            self.assertIn(identifier, dict(dict(captured.rows)["events"]))
            self.assertNotEqual(captured.scope_hash, self.snapshot.scope_hash)
        with Session(self.engine) as session, session.begin():
            with self.assertRaisesRegex(ValueError, "content_ownership_changed"):
                capture_person_snapshot(
                    session,
                    self.fixture.person,
                    reviewed_dispositions=(*self.reviews, illegal),
                    restore_codec=self.codec,
                    provider_audiences={
                        "apple": "fictional-apple",
                        "line": "fictional-line",
                    },
                )

    def test_shared_game_exact_patch_completes_without_deleting_or_changing_schedule(
        self,
    ):
        result = self.execute()
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT to_jsonb(t) FROM ntubtob.games t WHERE id=:id", id=self.game
            ),
            dict(self.game_before, **self.game_patch),
        )

    def test_confirmed_game_postimage_drift_never_recaptures_or_redispatches(self):
        self.provider_result = None
        self.assertEqual(self.execute().classification, "needs_attention")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.games SET away_team='Fictional later content' WHERE id=:id"
                ),
                {"id": self.game},
            )
        result = self.execute()
        self.assertEqual(result.reason, "inventory_changed", result)
        self.assertEqual(len(self.calls), 2)

    def test_missing_workset_is_not_filled_in_and_never_dispatches(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'provider_revocation',:binding,:generation,:now)"
                ),
                dict(
                    id=str(uuid4()),
                    job=self.job_id,
                    binding="c" * 64,
                    generation=self.snapshot.generation,
                    now=NOW,
                ),
            )
        result = self.execute()
        self.assertEqual(result.reason, "workset_changed", result)
        self.assertEqual(self.calls, [])
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_items WHERE job_id=:job",
                job=self.job_id,
            ),
            1,
        )

    def test_extra_item_never_counts_as_a_complete_required_workset(self):
        self.assertEqual(
            self.executor.prepare(
                job_id=self.job_id, snapshot=self.snapshot
            ).classification,
            "confirmed",
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'online_erasure',:binding,:generation,:now)"
                ),
                dict(
                    id=str(uuid4()),
                    job=self.job_id,
                    binding="d" * 64,
                    generation=self.snapshot.generation,
                    now=NOW + timedelta(seconds=1),
                ),
            )
        result = self.execute()
        self.assertEqual(result.reason, "workset_changed", result)
        self.assertEqual(self.calls, [])

    def test_restore_wrong_scope_cannot_confirm_or_repeat_custody(self):
        original = self.store.read
        self.store.read = lambda identifier: replace(
            original(identifier), scope_hash="0" * 64
        )
        result = self.execute()
        self.assertEqual(result.classification, "needs_attention", result)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.mobile_sessions WHERE person_id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            1,
        )
        self.execute()
        self.assertEqual(self.store.calls, 2)
        self.assertEqual(len(self.calls), 2)

    def test_retained_postimage_drift_after_local_cleanup_never_expands_scope(self):
        self.provider_result = None
        self.assertEqual(self.execute().classification, "needs_attention")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.identity_review_messages SET body='Fictional late content' WHERE id=:id"
                ),
                {"id": self.shared_message},
            )
        result = self.execute()
        self.assertEqual(result.reason, "inventory_changed", result)
        self.assertEqual(len(self.calls), 2)

    def test_final_commit_unknown_preserves_receipt_without_redispatch(self):
        def fail(session):
            if session.info.get("person_fulfillment_final"):
                raise RuntimeError("fictional lost commit acknowledgement")

        event.listen(Session, "after_commit", fail)
        try:
            result = self.execute()
        finally:
            event.remove(Session, "after_commit", fail)
        self.assertEqual(
            (result.classification, result.reason),
            ("outcome_unknown", "commit_unconfirmed"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            "online_completed",
        )
        self.assertEqual(self.execute().reason, "receipt_read_required")
        self.assertEqual(len(self.calls), 2)

    def test_final_failure_rolls_back_target_and_final_item_but_not_prior_commits(self):
        def fail(connection, cursor, statement, parameters, context, many):
            if statement.startswith("DELETE FROM ntubtob.people"):
                raise RuntimeError("fictional final failure")

        event.listen(self.engine, "before_cursor_execute", fail)
        try:
            result = self.execute()
        finally:
            event.remove(self.engine, "before_cursor_execute", fail)
        self.assertEqual(result.classification, "not_applied", result)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            1,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                id=self.fixture.identity,
            ),
            1,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.mobile_sessions WHERE person_id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertNotEqual(
            self.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            "online_completed",
        )


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class PersonAdminFulfillmentPostgresTests(_PersonFulfillmentFixture, unittest.TestCase):
    def configure_target(self, connection):
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
            text("UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"),
            {"id": self.fixture.person},
        )

    def test_admin_with_other_reachable_admin_completes_without_granting_authority(
        self,
    ):
        before = self.scalar(
            "SELECT to_jsonb(t) FROM ntubtob.people t WHERE id=:id",
            id=self.fixture.other_person,
        )
        result = self.execute()
        self.assertEqual(
            (result.classification, result.reason),
            ("confirmed", "online_completed"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT to_jsonb(t) FROM ntubtob.people t WHERE id=:id",
                id=self.fixture.other_person,
            ),
            before,
        )
        self.assertEqual(sorted(self.calls), ["apple", "line"])

    def test_unreachable_other_admin_requires_recovery_before_any_item_or_dispatch(
        self,
    ):
        for table, field, changed, original, identifier in (
            (
                "people",
                "portal_status",
                "disabled",
                "active",
                self.fixture.other_person,
            ),
            (
                "people",
                "portal_access_level",
                "basic",
                "admin",
                self.fixture.other_person,
            ),
            (
                "auth_identities",
                "status",
                "disabled",
                "linked",
                self.fixture.other_identity,
            ),
        ):
            with self.subTest(table=table, field=field):
                with self.engine.begin() as connection:
                    connection.execute(
                        text(f"UPDATE ntubtob.{table} SET {field}=:value WHERE id=:id"),
                        {"id": identifier, "value": changed},
                    )
                result = self.execute()
                self.assertEqual(result.reason, "admin_recovery_required", result)
                self.assertEqual(self.calls, [])
                self.assertEqual(
                    self.scalar(
                        "SELECT count(*) FROM ntubtob.account_erasure_items WHERE job_id=:id",
                        id=self.job_id,
                    ),
                    0,
                )
                with self.engine.begin() as connection:
                    connection.execute(
                        text(f"UPDATE ntubtob.{table} SET {field}=:value WHERE id=:id"),
                        {"id": identifier, "value": original},
                    )

    def test_requested_other_admin_counts_but_verified_other_admin_does_not(self):
        with self.engine.begin() as connection:
            self.fixture.connection = connection
            generation = connection.scalar(
                text(
                    "SELECT account_generation::text FROM ntubtob.people WHERE id=:id"
                ),
                {"id": self.fixture.other_person},
            )
            other_job = self.fixture.job(
                person_id=self.fixture.other_person, expected_generation=generation
            )
            target = connection.execute(
                text(
                    "SELECT provider_subject,account_generation::text FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": self.fixture.other_identity},
            ).one()
        prepared = self.executor.prepare(job_id=self.job_id, snapshot=self.snapshot)
        self.assertEqual(prepared.classification, "confirmed", prepared)
        fresh = proof(
            job_id=other_job,
            identity_id=self.fixture.other_identity,
            provider_subject=target[0],
            identity_generation=target[1],
            person_id=self.fixture.other_person,
            target_generation=generation,
        )
        with Session(self.engine) as session, session.begin():
            ErasureVerificationCoordinator(
                verifier=lambda assertion: fresh,
                audience=AUDIENCE,
                max_proof_age=timedelta(minutes=1),
                clock=lambda: NOW,
            ).verify(session, job_id=other_job, assertion="fictional-other-admin-proof")
        result = self.execute()
        self.assertEqual(result.reason, "admin_recovery_required", result)
        self.assertEqual(self.calls, [])
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_item_events e JOIN ntubtob.account_erasure_items i ON i.id=e.item_id WHERE i.job_id=:id",
                id=self.job_id,
            ),
            0,
        )

    def test_legacy_mode_cannot_claim_persistent_role_proves_an_admin_survives(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.portal_authority_state SET mode='legacy_allowlist' WHERE singleton_id=1"
                )
            )
        result = self.execute()
        self.assertEqual(result.reason, "admin_authority_unavailable", result)
        self.assertEqual(self.calls, [])

    def test_finalization_rechecks_survivor_after_prior_committed_local_cleanup(self):
        finalize = self.executor._finalize

        def lose_survivor_then_finalize(job_id, snapshot):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ntubtob.people SET portal_status='disabled' WHERE id=:id"
                    ),
                    {"id": self.fixture.other_person},
                )
            return finalize(job_id, snapshot)

        self.executor._finalize = lose_survivor_then_finalize
        result = self.execute()
        self.assertEqual(
            (result.stage, result.reason),
            ("finalization", "admin_recovery_required"),
            result,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.mobile_sessions WHERE person_id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            1,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.apple_provider_credentials WHERE auth_identity_id=:id",
                id=self.fixture.identity,
            ),
            1,
        )
        self.assertNotEqual(
            self.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            "online_completed",
        )
        self.assertEqual(len(self.calls), 2)


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class LastAdminIntakePostgresTests(_PersonFulfillmentFixture, unittest.TestCase):
    def configure_target(self, connection):
        PersonAdminFulfillmentPostgresTests.configure_target(self, connection)
        connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='basic' WHERE id=:id"),
            {"id": self.fixture.other_person},
        )

    def test_last_admin_capture_and_verification_do_not_authorize_dispatch(self):
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            "verified",
        )
        result = self.execute()
        self.assertEqual(result.reason, "admin_recovery_required", result)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.calls, 0)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_items WHERE job_id=:id",
                id=self.job_id,
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT portal_access_level FROM ntubtob.people WHERE id=:id",
                id=self.fixture.other_person,
            ),
            "basic",
        )
