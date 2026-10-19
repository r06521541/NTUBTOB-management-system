"""Fictional structured-store disposition; PostgreSQL is explicitly opt-in."""

import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine

from shared_lib.shared_module.portal_data import erasure_structured_execution as module
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.runtime import acquire_admin_event_locks
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data import test_erasure_provider_execution as provider_fixture
from tests.portal_data.test_erasure_verification import NOW

JOB = "11111111-1111-4111-8111-111111111111"
ITEM = "22222222-2222-4222-8222-222222222222"
GENERATION = "33333333-3333-4333-8333-333333333333"


def inventory(*, person=7, session="fictional-session"):
    return module.StructuredInventory(
        person,
        ((11, GENERATION),),
        tuple(
            (table, ((session, person, 11),) if table == "mobile_sessions" else ())
            for table in module.DELETE_ORDER
        ),
        (),
    )


class StructuredExecutionTests(unittest.TestCase):
    def test_binding_is_separate_and_binds_job_generation_owner_and_exact_inventory(
        self,
    ):
        baseline = module.structured_item_binding(JOB, GENERATION, inventory())
        self.assertRegex(baseline, r"^[0-9a-f]{64}$")
        for job, generation, scope in (
            (ITEM, GENERATION, inventory()),
            (JOB, ITEM, inventory()),
            (JOB, GENERATION, inventory(person=8)),
            (JOB, GENERATION, inventory(session="another-fictional-session")),
        ):
            self.assertNotEqual(
                baseline, module.structured_item_binding(job, generation, scope)
            )
        self.assertNotIn("fictional-session", repr(inventory()))

    def test_outer_connection_and_non_engine_are_rejected_without_io(self):
        for value in (Mock(spec=Connection), object(), None):
            with (
                self.subTest(kind=type(value).__name__),
                self.assertRaisesRegex(ValueError, "^invalid_executor_configuration$"),
            ):
                module.StructuredErasureExecutor(value)

    def exercise(self, *, failure=None, scope=None, validator=None):
        scope = inventory() if scope is None else scope
        connection = Mock()
        connection.execute.return_value.rowcount = 1
        state = {"committed": False, "rolled_back": False}

        @contextmanager
        def transaction():
            try:
                yield
                if failure == "commit":
                    raise RuntimeError("fictional private storage sentinel")
                state["committed"] = True
            except Exception:
                state["rolled_back"] = True
                raise

        @contextmanager
        def session(engine):
            yield Mock(begin=transaction)

        job = dict(
            person_id=7,
            expected_generation=GENERATION,
            updated_at=NOW,
        )
        item = dict(
            binding_hash=module.structured_item_binding(JOB, GENERATION, scope),
            created_at=NOW,
        )
        delete = Mock()
        if failure == "delete":
            delete.side_effect = module._Rejected("disposition_count_changed")
        with (
            patch.object(module, "Session", session),
            patch.object(module, "_connection", return_value=connection),
            patch.object(module, "_locked_context", return_value=(job, item)),
            patch.object(module, "_locked_inventory", return_value=scope),
            patch.object(module, "_delete_inventory", delete),
        ):
            result = module.StructuredErasureExecutor(
                Mock(spec=Engine),
                clock=lambda: NOW + timedelta(seconds=1),
                scope_validator=validator,
            ).execute(job_id=JOB, item_id=ITEM)
        return result, state, connection, delete

    def test_sealed_scope_validator_uses_locked_connection_before_any_write(self):
        seen = []

        def validate(connection, job, item):
            connection.execute.assert_not_called()
            self.assertEqual(job["person_id"], 7)
            self.assertEqual(
                item["binding_hash"],
                module.structured_item_binding(JOB, GENERATION, inventory()),
            )
            seen.append(connection)

        result, state, connection, delete = self.exercise(validator=validate)
        self.assertEqual(seen, [connection])
        self.assertEqual(result.classification, "confirmed")
        self.assertTrue(state["committed"])
        delete.assert_called_once_with(connection, inventory())

    def test_sealed_scope_rejection_or_non_none_result_never_fences_or_deletes(self):
        for validator in (
            Mock(side_effect=module._Rejected("sealed_inventory_changed")),
            Mock(side_effect=RuntimeError("fictional sensitive detail")),
            Mock(return_value=False),
            Mock(return_value=True),
        ):
            with self.subTest(validator=validator):
                result, state, connection, delete = self.exercise(validator=validator)
                self.assertEqual(result.classification, "not_applied")
                self.assertEqual(result.stage, "sealed_scope")
                self.assertTrue(state["rolled_back"])
                connection.execute.assert_not_called()
                delete.assert_not_called()
                self.assertNotIn("sensitive", repr(result))

    def test_non_callable_scope_validator_rejected_at_configuration(self):
        with self.assertRaisesRegex(ValueError, "^invalid_executor_configuration$"):
            module.StructuredErasureExecutor(Mock(spec=Engine), scope_validator=False)

    def test_local_effect_and_evidence_commit_together_without_job_completion(self):
        result, state, connection, delete = self.exercise()
        self.assertEqual(result.classification, "confirmed")
        self.assertTrue(state["committed"])
        delete.assert_called_once()
        sql = "\n".join(str(call.args[0]) for call in connection.execute.call_args_list)
        self.assertIn("irreversible_started_at", sql)
        self.assertIn("'started'", sql)
        self.assertIn("'confirmed'", sql)
        self.assertNotIn("online_completed", sql)
        self.assertNotIn("person_id=NULL", sql)

    def test_disposition_failure_rolls_back_and_does_not_confirm(self):
        result, state, connection, _ = self.exercise(failure="delete")
        self.assertEqual(result.classification, "not_applied")
        self.assertEqual(result.reason, "disposition_count_changed")
        self.assertTrue(state["rolled_back"])
        self.assertFalse(state["committed"])
        self.assertNotIn(
            "'confirmed'",
            " ".join(str(c.args[0]) for c in connection.execute.call_args_list),
        )

    def test_commit_unknown_is_not_permission_to_retry_and_has_fixed_evidence(self):
        result, _, _, _ = self.exercise(failure="commit")
        self.assertEqual(result.classification, "outcome_unknown")
        self.assertEqual(result.reason, "commit_unconfirmed")
        self.assertEqual(result.next_action, "read_only_review")
        self.assertNotIn("sentinel", repr(result))

    def test_empty_scope_creates_no_fence(self):
        scope = module.StructuredInventory(
            7, (), tuple((table, ()) for table in module.DELETE_ORDER), ()
        )
        result, _, connection, delete = self.exercise(scope=scope)
        self.assertEqual(result.reason, "empty_scope")
        connection.execute.assert_not_called()
        delete.assert_not_called()

    def test_rls_unknown_schema_dirty_and_nontransactional_connections_fail_closed(
        self,
    ):
        for case in ("dirty", "autocommit", "isolation", "schema", "rls"):
            with self.subTest(case=case):
                session = Mock()
                session.in_transaction.return_value = True
                session.new = session.dirty = session.deleted = set()
                connection = session.connection.return_value
                connection.connection.dbapi_connection.autocommit = False
                connection.get_isolation_level.return_value = "READ COMMITTED"
                connection.scalars.return_value = ["0018_erasure_privacy_mutation"]
                connection.scalar.return_value = False
                if case == "dirty":
                    session.dirty = {object()}
                elif case == "autocommit":
                    connection.connection.dbapi_connection.autocommit = True
                elif case == "isolation":
                    connection.get_isolation_level.return_value = "REPEATABLE READ"
                elif case == "schema":
                    connection.scalars.return_value = ["0019_future"]
                else:
                    connection.scalar.return_value = None
                with self.assertRaises(module._Rejected):
                    module._connection(session)
                self.assertFalse(
                    any(
                        str(call.args[0]).startswith(("DELETE", "INSERT", "UPDATE"))
                        for call in connection.execute.call_args_list
                    )
                )


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class StructuredExecutionPostgresTests(unittest.TestCase):
    cleanup_fixture = provider_fixture.ProviderExecutionPostgresTests.cleanup_fixture

    def prepare(self, *args):
        raise AssertionError("provider must not be invoked")

    def setUp(self):
        provider_fixture.ProviderExecutionPostgresTests.setUp(self)
        self.saved = {}
        self.owned = [{table: [] for table in module.DELETE_ORDER} for _ in range(2)]
        self.addCleanup(self.cleanup_structured)
        with self.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_erasure_privacy_mutation")
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                ),
                dict(person=self.fixture.other_person, id=self.fixture.other_identity),
            )
            self.event_id = self.insert(
                connection,
                "events",
                dict(
                    title="Fictional shared event",
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
                    title="Fictional shared activity",
                    activity_type="other",
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
            self.individual_notification, self.individual_delivery = (
                self.seed_notification(
                    connection, (0,), "individual", self.fixture.person
                )
            )
            self.shared_notification, self.shared_delivery = self.seed_notification(
                connection, (0, 1), "team", None
            )
            self.other_notification, self.other_delivery = self.seed_notification(
                connection, (1,), "individual", self.fixture.other_person
            )
            self.owned[0]["mobile_notification_deliveries"].append(
                self.individual_delivery
            )
            self.owned[1]["mobile_notification_deliveries"].extend(
                (self.shared_delivery, self.other_delivery)
            )
            self.structured_item = self.make_item(connection)
        self.executor = module.StructuredErasureExecutor(
            self.engine, clock=lambda: NOW + timedelta(seconds=1)
        )

    def insert(self, connection, table, values, owner=None):
        # Only test-owned literal table/column names are passed here.
        identifier = connection.scalar(
            text(
                f"INSERT INTO ntubtob.{table} ({','.join(values)}) "
                f"VALUES ({','.join(':'+key for key in values)}) RETURNING id"
            ),
            values,
        )
        self.saved.setdefault(table, []).append(identifier)
        if owner is not None:
            self.owned[owner][table].append(identifier)
        return identifier

    def seed_person(self, connection, owner, person, identity):
        session = self.insert(
            connection,
            "mobile_sessions",
            dict(
                id=str(uuid4()),
                person_id=person,
                auth_identity_id=identity,
                installation_id_hash=uuid4().hex * 2,
                platform="ios",
                status="revoked",
                access_epoch=2,
                refresh_family_expires_at=NOW + timedelta(hours=1),
                revoked_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            ),
            owner,
        )
        tokens = []
        for generation in (1, 2):
            tokens.append(
                self.insert(
                    connection,
                    "mobile_refresh_tokens",
                    dict(
                        session_id=session,
                        token_hash=uuid4().hex * 2,
                        generation=generation,
                        status="revoked",
                        issued_at=NOW,
                        expires_at=NOW + timedelta(hours=1),
                        revoked_at=NOW,
                    ),
                    owner,
                )
            )
        connection.execute(
            text(
                "UPDATE ntubtob.mobile_refresh_tokens SET successor_token_id=:successor WHERE id=:id"
            ),
            dict(successor=tokens[1], id=tokens[0]),
        )
        self.insert(
            connection,
            "mobile_refresh_attempts",
            dict(
                session_id=session,
                attempt_id_hash=uuid4().hex * 2,
                request_hash="a" * 64,
                encrypted_successor=b"fictional-secret",
                expires_at=NOW + timedelta(minutes=1),
                created_at=NOW,
            ),
            owner,
        )
        self.insert(
            connection,
            "mobile_auth_exchanges",
            dict(
                session_id=session,
                provider="apple",
                assertion_hash=uuid4().hex * 2,
                login_attempt_hash=uuid4().hex * 2,
                expires_at=NOW + timedelta(minutes=1),
                created_at=NOW,
            ),
            owner,
        )
        self.insert(
            connection,
            "mobile_idempotency_records",
            dict(
                session_id=session,
                person_id=person,
                method="POST",
                route="/fictional",
                key_hash=uuid4().hex * 2,
                request_hash="a" * 64,
                state="completed",
                response_status=200,
                response_body='{"fictional_private":"sentinel"}',
                expires_at=NOW + timedelta(minutes=1),
                created_at=NOW,
                updated_at=NOW,
            ),
            owner,
        )
        self.insert(
            connection,
            "mobile_device_registrations",
            dict(
                session_id=session,
                person_id=person,
                installation_id_hash=uuid4().hex * 2,
                platform="ios",
                provider="fake",
                token_hash=uuid4().hex * 2,
                status="revoked",
                revoked_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            ),
            owner,
        )
        self.insert(
            connection,
            "event_attendance_replies",
            dict(
                event_id=self.event_id,
                person_id=person,
                reply="attending",
                updated_at=NOW,
            ),
            owner,
        )
        self.insert(
            connection,
            "activity_attendance_replies",
            dict(
                activity_id=self.activity_id,
                person_id=person,
                reply="attending",
                updated_at=NOW,
            ),
            owner,
        )
        self.insert(
            connection,
            "apple_provider_credentials",
            dict(
                auth_identity_id=identity,
                encrypted_refresh_token=b"fictional-provider-secret",
                refresh_token_hash=uuid4().hex * 2,
                status="active",
                created_at=NOW,
                updated_at=NOW,
            ),
        )

    def seed_notification(self, connection, owners, audience_type, reference):
        notification = self.insert(
            connection,
            "mobile_notifications",
            dict(
                notification_type=(
                    "officer_personal" if len(owners) == 1 else "officer_team_broadcast"
                ),
                title="Fictional shared title",
                body="Fictional shared body",
                destination_type="notification",
                created_at=NOW,
                visible_until=NOW + timedelta(days=90),
            ),
        )
        self.insert(
            connection,
            "mobile_notification_publish_audits",
            dict(
                notification_id=notification,
                actor_person_id=self.fixture.other_person,
                audience_type=audience_type,
                audience_reference_id=reference,
                preview_revision="a" * 64,
                recipient_count=len(owners),
                request_hash=uuid4().hex * 2,
                created_at=NOW,
            ),
        )
        for owner in owners:
            self.insert(
                connection,
                "mobile_notification_recipients",
                dict(
                    notification_id=notification,
                    person_id=(self.fixture.person, self.fixture.other_person)[owner],
                    created_at=NOW,
                ),
                owner,
            )
        delivery = self.insert(
            connection,
            "mobile_notification_deliveries",
            dict(
                notification_id=notification,
                channel="push",
                status="pending",
                attempt_count=0,
                retryable=True,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        return notification, delivery

    def make_item(self, connection, *, binding=None):
        acquire_admin_event_locks(connection)
        if binding is None:
            scope = module._locked_inventory(connection, self.fixture.person)
            binding = module.structured_item_binding(
                self.job_id, str(self.job["expected_generation"]), scope
            )
        identifier = str(uuid4())
        connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_items "
                "(id,job_id,stage,binding_hash,expected_generation,created_at) "
                "VALUES (:id,:job,'online_erasure',:binding,:generation,:now)"
            ),
            dict(
                id=identifier,
                job=self.job_id,
                binding=binding,
                generation=self.job["expected_generation"],
                now=NOW,
            ),
        )
        return identifier

    def cleanup_structured(self):
        require_local_database_url(
            self.engine.url.render_as_string(hide_password=False)
        )
        if not self.saved:
            return
        with self.engine.begin() as connection:
            # setUp may have rolled back the 0018 upgrade and all seeded rows.
            # Do not assume the named 0018 triggers exist after a partial setup.
            if not any(
                connection.scalar(
                    text(f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                    {"ids": ids},
                )
                for table, ids in self.saved.items()
            ):
                return
            # Only this fictional fixture's exact IDs; the named guards are
            # restored before COMMIT, or both ALTERs and DELETEs roll back.
            for table in ("mobile_notification_publish_audits", "mobile_notifications"):
                connection.execute(
                    text(
                        f"ALTER TABLE ntubtob.{table} DISABLE TRIGGER erasure_privacy_guard"
                    )
                )
            for table in (
                *module.DELETE_ORDER,
                "apple_provider_credentials",
                "mobile_notification_publish_audits",
                "mobile_notifications",
                "activities",
                "events",
            ):
                ids = self.saved.get(table, [])
                if ids:
                    connection.execute(
                        text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                        {"ids": ids},
                    )
            for table in ("mobile_notification_publish_audits", "mobile_notifications"):
                connection.execute(
                    text(
                        f"ALTER TABLE ntubtob.{table} ENABLE TRIGGER erasure_privacy_guard"
                    )
                )

    def execute(self):
        return self.executor.execute(job_id=self.job_id, item_id=self.structured_item)

    def assert_own_intact(self):
        with self.engine.connect() as connection:
            for table, ids in self.owned[0].items():
                self.assertEqual(
                    connection.scalar(
                        text(
                            f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)"
                        ),
                        {"ids": ids},
                    ),
                    len(ids),
                    table,
                )
            state = connection.execute(
                text(
                    "SELECT status,irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job_id},
            ).one()
            self.assertEqual(tuple(state), ("verified", None))
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.structured_item},
                ),
                0,
            )

    def test_exact_ten_stores_deleted_other_person_content_audits_and_credentials_survive(
        self,
    ):
        result = self.execute()
        self.assertEqual(
            (result.classification, result.reason), ("confirmed", "item_completed")
        )
        with self.engine.connect() as connection:
            for owner, expected in ((0, False), (1, True)):
                for table, ids in self.owned[owner].items():
                    self.assertEqual(
                        connection.scalar(
                            text(
                                f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)"
                            ),
                            {"ids": ids},
                        ),
                        len(ids) if expected else 0,
                        (owner, table),
                    )
            for table in (
                "events",
                "activities",
                "mobile_notifications",
                "mobile_notification_publish_audits",
                "apple_provider_credentials",
            ):
                self.assertEqual(
                    connection.scalar(
                        text(
                            f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)"
                        ),
                        {"ids": self.saved[table]},
                    ),
                    len(self.saved[table]),
                    table,
                )
            self.assertEqual(
                connection.scalar(
                    text("SELECT title FROM ntubtob.events WHERE id=:id"),
                    {"id": self.event_id},
                ),
                "Fictional shared event",
            )
            for table, identifier in (
                ("people", self.fixture.person),
                ("auth_identities", self.fixture.identity),
            ):
                self.assertEqual(
                    connection.scalar(
                        text(f"SELECT count(*) FROM ntubtob.{table} WHERE id=:id"),
                        {"id": identifier},
                    ),
                    1,
                )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    {"id": self.job_id},
                ),
                "processing",
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.structured_item},
                ),
                2,
            )
        self.assertEqual(self.execute().reason, "item_already_started")

    def test_person_session_and_dual_owned_children_conflicts_never_delete(self):
        for table, field, value, original in (
            (
                "mobile_sessions",
                "auth_identity_id",
                self.fixture.other_identity,
                self.fixture.identity,
            ),
            (
                "mobile_idempotency_records",
                "person_id",
                self.fixture.other_person,
                self.fixture.person,
            ),
            (
                "mobile_device_registrations",
                "session_id",
                self.owned[1]["mobile_sessions"][0],
                self.owned[0]["mobile_sessions"][0],
            ),
        ):
            identifier = self.owned[0][table][0]
            with self.subTest(table=table):
                with self.engine.begin() as connection:
                    connection.execute(
                        text(f"UPDATE ntubtob.{table} SET {field}=:value WHERE id=:id"),
                        dict(value=value, id=identifier),
                    )
                try:
                    self.assertEqual(self.execute().reason, "ownership_conflict")
                    self.assert_own_intact()
                finally:
                    with self.engine.begin() as connection:
                        connection.execute(
                            text(
                                f"UPDATE ntubtob.{table} SET {field}=:value WHERE id=:id"
                            ),
                            dict(value=original, id=identifier),
                        )

    def test_cross_session_successor_reference_rejects_both_directions(self):
        for source, destination in ((0, 1), (1, 0)):
            identifier = self.owned[source]["mobile_refresh_tokens"][0]
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ntubtob.mobile_refresh_tokens SET successor_token_id=:successor WHERE id=:id"
                    ),
                    dict(
                        id=identifier,
                        successor=self.owned[destination]["mobile_refresh_tokens"][1],
                    ),
                )
            try:
                self.assertEqual(self.execute().reason, "ownership_conflict")
                self.assert_own_intact()
            finally:
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            "UPDATE ntubtob.mobile_refresh_tokens SET successor_token_id=:successor WHERE id=:id"
                        ),
                        dict(
                            id=identifier,
                            successor=self.owned[source]["mobile_refresh_tokens"][1],
                        ),
                    )

    def test_new_row_after_item_plan_rejects_inventory_expansion(self):
        with self.engine.begin() as connection:
            self.insert(
                connection,
                "mobile_refresh_attempts",
                dict(
                    session_id=self.owned[0]["mobile_sessions"][0],
                    attempt_id_hash=uuid4().hex * 2,
                    request_hash="a" * 64,
                    encrypted_successor=b"fictional",
                    created_at=NOW,
                    expires_at=NOW + timedelta(minutes=1),
                ),
                0,
            )
        self.assertEqual(self.execute().reason, "inventory_changed")
        self.assert_own_intact()

    def test_identity_generation_change_invalidates_review_even_with_same_person(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET provider_subject=:subject WHERE id=:id"
                ),
                dict(subject="fictional-new-" + str(uuid4()), id=self.fixture.identity),
            )
        self.assertEqual(self.execute().reason, "inventory_changed")
        self.assert_own_intact()

    def test_stored_person_generation_mismatch_rejects_before_any_delete(self):
        with self.engine.begin() as connection:
            previous = self.fixture.connection
            self.fixture.connection = connection
            try:
                wrong_job = self.fixture.job(
                    person_id=self.fixture.other_person,
                    expected_generation=str(uuid4()),
                )
            finally:
                self.fixture.connection = previous
            connection.execute(
                text(
                    "UPDATE ntubtob.account_erasure_jobs SET status='verified',verified_at=:now,updated_at=:now WHERE id=:id"
                ),
                dict(id=wrong_job, now=NOW),
            )
        result = self.executor.execute(job_id=wrong_job, item_id=self.structured_item)
        self.assertEqual(result.reason, "target_scope_changed")
        self.assert_own_intact()

    def test_last_recipient_is_not_proof_that_shared_delivery_is_owned(self):
        with self.engine.begin() as connection:
            shared_other = connection.scalar(
                text(
                    "SELECT id FROM ntubtob.mobile_notification_recipients WHERE notification_id=:notification AND person_id=:person"
                ),
                dict(
                    notification=self.shared_notification,
                    person=self.fixture.other_person,
                ),
            )
            connection.execute(
                text("DELETE FROM ntubtob.mobile_notification_recipients WHERE id=:id"),
                {"id": shared_other},
            )
        # Target inventory has not expanded; its individual delivery remains
        # deletable, but the shared delivery is not inferred from a sole survivor.
        self.assertEqual(self.execute().classification, "confirmed")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_notification_deliveries WHERE id=:id"
                    ),
                    {"id": self.shared_delivery},
                ),
                1,
            )

    def test_ambiguous_individual_audience_keeps_delivery_after_fresh_review(self):
        with self.engine.begin() as connection:
            self.insert(
                connection,
                "mobile_notification_recipients",
                dict(
                    notification_id=self.individual_notification,
                    person_id=self.fixture.other_person,
                    created_at=NOW,
                ),
                1,
            )
        self.assertEqual(self.execute().reason, "inventory_changed")
        self.assert_own_intact()
        with self.engine.begin() as connection:
            self.structured_item = self.make_item(connection)
        self.assertEqual(self.execute().classification, "confirmed")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_notification_deliveries WHERE id=:id"
                    ),
                    {"id": self.individual_delivery},
                ),
                1,
            )

    def test_skipped_delete_rowcount_does_not_confirm_or_leave_partial_deletes(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION ntubtob.fictional_skip_structured_delete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER fictional_skip_structured_delete BEFORE DELETE ON ntubtob.mobile_sessions FOR EACH ROW EXECUTE FUNCTION ntubtob.fictional_skip_structured_delete()"
                )
            )
        try:
            self.assertEqual(self.execute().reason, "disposition_count_changed")
            self.assert_own_intact()
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "DROP TRIGGER fictional_skip_structured_delete ON ntubtob.mobile_sessions"
                    )
                )
                connection.execute(
                    text("DROP FUNCTION ntubtob.fictional_skip_structured_delete()")
                )

    def test_lost_commit_ack_keeps_durable_deletes_and_does_not_redispatch(self):
        def fail_after_commit(session):
            raise RuntimeError("fictional private commit acknowledgement")

        event.listen(module.Session, "after_commit", fail_after_commit)
        try:
            result = self.execute()
        finally:
            event.remove(module.Session, "after_commit", fail_after_commit)
        self.assertEqual(
            (result.classification, result.reason),
            ("outcome_unknown", "commit_unconfirmed"),
        )
        self.assertEqual(result.next_action, "read_only_review")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_sessions WHERE id=ANY(:ids)"
                    ),
                    {"ids": self.owned[0]["mobile_sessions"]},
                ),
                0,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.structured_item},
                ),
                2,
            )
        self.assertEqual(self.execute().reason, "item_already_started")

    def test_delete_failure_rolls_back_earlier_deletes_and_fence(self):
        def reject_delete(
            connection, cursor, statement, parameters, context, executemany
        ):
            if statement.startswith("DELETE FROM ntubtob.mobile_sessions"):
                raise RuntimeError("fictional private storage sentinel")

        event.listen(self.engine, "before_cursor_execute", reject_delete)
        try:
            result = self.execute()
        finally:
            event.remove(self.engine, "before_cursor_execute", reject_delete)
        self.assertEqual(
            (result.classification, result.reason),
            ("not_applied", "transaction_failed"),
        )
        self.assertNotIn("sentinel", repr(result))
        self.assert_own_intact()

    def test_empty_scope_does_not_fence_or_confirm(self):
        with self.engine.begin() as connection:
            for table, ids in self.owned[0].items():
                connection.execute(
                    text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                    {"ids": ids},
                )
            self.structured_item = self.make_item(connection)
        self.assertEqual(self.execute().reason, "empty_scope")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    {"id": self.job_id},
                ),
                None,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.structured_item},
                ),
                0,
            )

    def test_unreviewed_cascade_never_deletes_new_dependent_store(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE ntubtob.fictional_structured_dependency (session_id varchar(64) REFERENCES ntubtob.mobile_sessions(id) ON DELETE CASCADE)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.fictional_structured_dependency VALUES (:session)"
                ),
                {"session": self.owned[0]["mobile_sessions"][0]},
            )
        try:
            self.assertEqual(self.execute().reason, "unreviewed_cascade")
            self.assert_own_intact()
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text("DROP TABLE ntubtob.fictional_structured_dependency")
                )

    def test_outer_connection_rejected_before_any_disposition(self):
        with self.engine.connect() as connection, connection.begin():
            with self.assertRaises(ValueError):
                module.StructuredErasureExecutor(connection)
        self.assert_own_intact()

    def test_extra_cascade_on_allowed_table_cannot_delete_other_owner(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ntubtob.mobile_refresh_attempts ADD COLUMN "
                    "fictional_shadow_session varchar(64) REFERENCES "
                    "ntubtob.mobile_sessions(id) ON DELETE CASCADE"
                )
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_refresh_attempts SET fictional_shadow_session=:session "
                    "WHERE id=ANY(:ids)"
                ),
                {
                    "session": self.owned[0]["mobile_sessions"][0],
                    "ids": self.owned[1]["mobile_refresh_attempts"],
                },
            )
        try:
            self.assertEqual(self.execute().reason, "unreviewed_cascade")
            self.assert_own_intact()
            with self.engine.connect() as connection:
                self.assertEqual(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM ntubtob.mobile_refresh_attempts WHERE id=ANY(:ids)"
                        ),
                        {"ids": self.owned[1]["mobile_refresh_attempts"]},
                    ),
                    len(self.owned[1]["mobile_refresh_attempts"]),
                )
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE ntubtob.mobile_refresh_attempts DROP COLUMN fictional_shadow_session"
                    )
                )
