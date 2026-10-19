"""Local-verifier fixtures only; no genuine provider proof or runtime enablement."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    require_account_not_erasing,
)
from shared_lib.shared_module.portal_data.erasure_verification import (
    ERASURE_VERIFICATION_PURPOSE,
    ErasureVerificationCoordinator,
    ErasureVerificationRejected,
    ErasureVerificationUnavailable,
    FreshErasureProof,
)
from shared_lib.shared_module.portal_data.runtime import (
    ADMIN_LOCK_KEY,
    EVENT_SNAPSHOT_LOCK_KEY,
)
from tests.portal_data import test_erasure_ledger as ledger_fixture

NOW = datetime(2035, 1, 1, 0, 1, tzinfo=timezone.utc)
JOB = "11111111-1111-4111-8111-111111111111"
PERSON_GENERATION = "22222222-2222-4222-8222-222222222222"
IDENTITY_GENERATION = "33333333-3333-4333-8333-333333333333"
AUDIENCE = "fictional-erasure-verifier"


def proof(**changes):
    values = dict(
        job_id=JOB,
        purpose=ERASURE_VERIFICATION_PURPOSE,
        audience=AUDIENCE,
        identity_id=11,
        provider="apple",
        provider_subject="fictional-private-subject",
        identity_generation=IDENTITY_GENERATION,
        target_kind="person",
        person_id=7,
        target_generation=PERSON_GENERATION,
        authenticated_at=NOW - timedelta(seconds=20),
        expires_at=NOW + timedelta(seconds=20),
    )
    values.update(changes)
    return FreshErasureProof(**values)


class ErasureVerificationTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.in_transaction.return_value = True
        self.session.new = self.session.dirty = self.session.deleted = set()
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.scalars.return_value.all.return_value = [
            "0015_account_generations"
        ]
        self.connection.scalar.return_value = False
        self.job = dict(
            id=JOB,
            status="requested",
            target_kind="person",
            person_id=7,
            auth_identity_id=None,
            expected_generation=PERSON_GENERATION,
            requested_at=NOW - timedelta(seconds=30),
            updated_at=NOW - timedelta(seconds=30),
        )
        self.identity = dict(
            id=11,
            provider="apple",
            provider_subject="fictional-private-subject",
            person_id=7,
            status="linked",
            account_generation=IDENTITY_GENERATION,
        )
        self.person = dict(id=7, account_generation=PERSON_GENERATION)
        self.connection.execute.side_effect = self.execute
        self.verifier = MagicMock(return_value=proof())
        self.coordinator = ErasureVerificationCoordinator(
            verifier=self.verifier,
            audience=AUDIENCE,
            max_proof_age=timedelta(minutes=1),
            clock=lambda: NOW,
        )

    def execute(self, statement, parameters=None):
        sql = str(statement)
        for table, row in (
            ("account_erasure_jobs", self.job),
            ("auth_identities", self.identity),
            ("people", self.person),
        ):
            if "SELECT " in sql and f"FROM ntubtob.{table}" in sql:
                return SimpleNamespace(
                    mappings=lambda row=row: SimpleNamespace(first=lambda: row)
                )
        return SimpleNamespace(rowcount=1)

    def verify(self, **changes):
        values = dict(job_id=JOB, assertion="fictional-proof")
        values.update(changes)
        return self.coordinator.verify(self.session, **values)

    def mutations(self):
        return [
            call
            for call in self.connection.execute.call_args_list
            if str(call.args[0]).lstrip().startswith(("UPDATE", "INSERT"))
        ]

    def test_person_verification_fences_rows_and_revokes_sessions_in_same_savepoint(
        self,
    ):
        result = self.verify()
        self.assertEqual(result.job_id, JOB)
        self.assertEqual(result.verified_at, NOW)
        calls = self.connection.execute.call_args_list
        self.assertEqual(calls[0].args[1], {"key": ADMIN_LOCK_KEY})
        self.assertEqual(calls[1].args[1], {"key": EVENT_SNAPSHOT_LOCK_KEY})
        self.assertTrue(all("FOR UPDATE" in str(c.args[0]) for c in calls[2:5]))
        sql = "\n".join(str(call.args[0]) for call in self.mutations())
        self.assertIn("access_epoch=access_epoch+1", sql)
        self.assertIn("status='active'", sql)
        self.assertIn("'verification'", sql)
        self.assertNotIn("'access_block'", sql)
        self.assertNotIn("fictional-private-subject", sql)
        self.connection.begin_nested.assert_called_once()
        self.session.execute.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()

    def test_pending_identity_does_not_revoke_other_person_sessions(self):
        self.job.update(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=11,
            expected_generation=IDENTITY_GENERATION,
        )
        self.identity.update(person_id=None, status="pending")
        self.verifier.return_value = proof(
            target_kind="pending_identity",
            person_id=None,
            target_generation=IDENTITY_GENERATION,
        )
        self.verify()
        self.assertFalse(
            any(
                "UPDATE ntubtob.mobile_sessions" in str(c.args[0])
                for c in self.mutations()
            )
        )

    def test_proof_binding_and_freshness_matrix_fails_before_mutation(self):
        for change in (
            {"job_id": str(uuid4())},
            {"purpose": "login"},
            {"audience": "other-audience"},
            {"identity_id": 12},
            {"identity_id": True},
            {"provider": "line"},
            {"provider_subject": "other-fictional-subject"},
            {"identity_generation": str(uuid4())},
            {"target_generation": str(uuid4())},
            {"person_id": 8},
            {"target_kind": "pending_identity", "person_id": None},
            {"target_kind": []},
            {"person_id": True},
            {"identity_generation": "not-a-uuid"},
            {"provider_subject": ""},
            {"expires_at": NOW},
            {"authenticated_at": NOW + timedelta(seconds=1)},
            {"authenticated_at": NOW - timedelta(minutes=2)},
            {"authenticated_at": NOW.replace(tzinfo=None)},
        ):
            with self.subTest(change=change):
                self.setUp()
                self.verifier.return_value = proof(**change)
                with self.assertRaises(ErasureVerificationRejected):
                    self.verify()
                self.assertEqual(self.mutations(), [])

    def test_client_boolean_dict_and_verifier_exception_are_not_proof(self):
        for value in (True, {}, None):
            self.verifier.return_value = value
            with self.assertRaises(ErasureVerificationRejected):
                self.verify()
        self.verifier.side_effect = RuntimeError("fictional-private-provider-token")
        with self.assertRaises(ErasureVerificationRejected) as error:
            self.verify()
        self.assertNotIn("fictional-private", str(error.exception))
        self.assertEqual(self.mutations(), [])

    def test_current_generation_mapping_and_replay_are_rechecked(self):
        for attribute, change in (
            ("job", {"status": "verified"}),
            ("job", {"expected_generation": str(uuid4())}),
            ("identity", {"person_id": 8}),
            ("identity", {"account_generation": str(uuid4())}),
            ("identity", {"provider_subject": "changed-subject"}),
            ("person", {"account_generation": str(uuid4())}),
        ):
            with self.subTest(attribute=attribute, change=change):
                self.setUp()
                getattr(self, attribute).update(change)
                with self.assertRaises(ErasureVerificationRejected):
                    self.verify()
                self.assertEqual(self.mutations(), [])

    def test_missing_job_identity_or_person_fails_closed(self):
        for attribute in ("job", "identity", "person"):
            with self.subTest(attribute=attribute):
                self.setUp()
                setattr(self, attribute, None)
                with self.assertRaises(ErasureVerificationRejected):
                    self.verify()
                self.assertEqual(self.mutations(), [])

    def test_invalid_job_assertion_or_session_rejected_before_connection(self):
        for values in (
            {"job_id": "not-a-uuid"},
            {"assertion": True},
            {"assertion": ""},
        ):
            with self.assertRaises(ErasureVerificationRejected):
                self.verify(**values)
        self.session.in_transaction.return_value = False
        with self.assertRaises(ErasureVerificationUnavailable):
            self.verify()
        self.session.in_transaction.return_value = True
        self.session.dirty = {object()}
        with self.assertRaises(ErasureVerificationUnavailable):
            self.verify()
        self.session.connection.assert_not_called()

    def test_wrong_schema_driver_or_isolation_rejected_without_mutation(self):
        for revisions in (
            [],
            ["0014_account_erasure_ledger"],
            ["0015_account_generations", "branch"],
        ):
            self.connection.scalars.return_value.all.return_value = revisions
            with self.assertRaises(ErasureVerificationUnavailable):
                self.verify()
        for autocommit in (True, None):
            self.connection.connection.dbapi_connection.autocommit = autocommit
            with self.assertRaises(ErasureVerificationUnavailable):
                self.verify()
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaises(ErasureVerificationUnavailable):
            self.verify()
        self.assertEqual(self.mutations(), [])

    def test_every_required_table_requires_unfiltered_rls_visibility(self):
        for index in range(5):
            for invisible in (True, None):
                self.setUp()
                self.connection.scalar.side_effect = [False] * index + [invisible]
                with self.assertRaises(ErasureVerificationUnavailable):
                    self.verify()
                self.assertEqual(self.mutations(), [])

    def test_clock_is_read_after_canonical_and_target_locks(self):
        def clock():
            calls = self.connection.execute.call_args_list
            self.assertEqual(len(calls), 5)
            self.assertIn("FROM ntubtob.people", str(calls[-1].args[0]))
            return NOW

        self.coordinator.clock = clock
        self.verify()

    def test_storage_failure_is_sanitized_and_nested_mutations_roll_back(self):
        def fail_on_step(statement, parameters=None):
            if "INSERT INTO ntubtob.account_erasure_steps" in str(statement):
                raise SQLAlchemyError("fictional-private-SQL")
            return self.execute(statement, parameters)

        self.connection.execute.side_effect = fail_on_step
        with self.assertRaises(ErasureVerificationUnavailable) as error:
            self.verify()
        self.assertNotIn("fictional-private", str(error.exception))
        self.connection.begin_nested.return_value.__exit__.assert_called_once()
        self.session.commit.assert_not_called()

    def test_proof_repr_does_not_include_subject(self):
        self.assertNotIn("fictional-private-subject", repr(proof()))

    def test_configuration_has_no_implicit_freshness_policy_or_verifier(self):
        for change in (
            {"verifier": None},
            {"audience": ""},
            {"max_proof_age": None},
            {"max_proof_age": timedelta(0)},
            {"max_proof_age": timedelta(seconds=-1)},
        ):
            with self.subTest(change=change):
                values = dict(
                    verifier=self.verifier,
                    audience=AUDIENCE,
                    max_proof_age=timedelta(minutes=1),
                )
                values.update(change)
                with self.assertRaises(ErasureVerificationUnavailable):
                    ErasureVerificationCoordinator(**values)

    def test_conditional_update_failure_rolls_back_without_step_or_revocation(self):
        def no_change(statement, parameters=None):
            if str(statement).startswith("UPDATE ntubtob.account_erasure_jobs"):
                return SimpleNamespace(rowcount=0)
            return self.execute(statement, parameters)

        self.connection.execute.side_effect = no_change
        with self.assertRaises(ErasureVerificationRejected):
            self.verify()
        self.assertEqual(len(self.mutations()), 1)
        self.connection.begin_nested.return_value.__exit__.assert_called_once()


@unittest.skipUnless(ledger_fixture.DATABASE_URL, "isolated ledger URL not configured")
class ErasureVerificationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ledger_fixture.ErasureLedgerPostgresTests.setUpClass.__func__(cls)
        with cls.engine.begin() as connection:
            config = Config(str(ledger_fixture.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0015_account_generations")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger_fixture.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.connection = self.fixture.connection

    def tearDown(self):
        if self.fixture.transaction.is_active:
            self.fixture.transaction.rollback()
        self.connection.close()

    def prepare(self, *, pending=False, generation_override=None):
        if not pending:
            self.connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                ),
                {"person": self.fixture.person, "id": self.fixture.identity},
            )
        identity = self.connection.execute(
            text(
                "SELECT provider_subject,account_generation FROM ntubtob.auth_identities WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        ).one()
        generation = (
            str(identity.account_generation)
            if pending
            else str(
                self.connection.scalar(
                    text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                    {"id": self.fixture.person},
                )
            )
        )
        self.job_id = self.fixture.job(
            expected_generation=generation_override or generation,
            target_kind="pending_identity" if pending else "person",
            person_id=None if pending else self.fixture.person,
            auth_identity_id=self.fixture.identity if pending else None,
        )
        self.fresh = proof(
            job_id=self.job_id,
            identity_id=self.fixture.identity,
            provider_subject=identity.provider_subject,
            identity_generation=str(identity.account_generation),
            target_kind="pending_identity" if pending else "person",
            person_id=None if pending else self.fixture.person,
            target_generation=generation_override or generation,
        )
        self.coordinator = ErasureVerificationCoordinator(
            verifier=lambda assertion: self.fresh,
            audience=AUDIENCE,
            max_proof_age=timedelta(minutes=1),
            clock=lambda: NOW,
        )
        self.session_id = str(uuid4())
        if not pending:
            self.other_session_id = str(uuid4())
            self.second_session_id = str(uuid4())
            self.connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                ),
                {
                    "person": self.fixture.other_person,
                    "id": self.fixture.other_identity,
                },
            )
            self.connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions "
                    "(id,auth_identity_id,person_id,installation_id_hash,platform,status,access_epoch,refresh_family_expires_at,created_at,updated_at) "
                    "VALUES (:id,:identity,:person,:hash,'ios','active',1,:expiry,:now,:now)"
                ),
                [
                    dict(
                        id=session_id,
                        identity=identity,
                        person=person,
                        hash="a" * 64,
                        expiry=NOW + timedelta(hours=1),
                        now=ledger_fixture.NOW,
                    )
                    for session_id, identity, person in (
                        (self.session_id, self.fixture.identity, self.fixture.person),
                        (
                            self.second_session_id,
                            self.fixture.identity,
                            self.fixture.person,
                        ),
                        (
                            self.other_session_id,
                            self.fixture.other_identity,
                            self.fixture.other_person,
                        ),
                    )
                ],
            )

    def session(self):
        return Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def verify(self):
        with self.session() as session, session.begin():
            return self.coordinator.verify(
                session, job_id=self.job_id, assertion="fictional-proof"
            )

    def guard(self, *, pending=False):
        with self.session() as session, session.begin():
            require_account_not_erasing(
                session,
                person_id=None if pending else self.fixture.person,
                identity_id=self.fixture.identity,
            )

    def assert_requested(self):
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job_id},
            ),
            "requested",
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": self.job_id},
            ),
            0,
        )

    def test_person_actual_generation_verified_and_sessions_revoked_with_guard(self):
        self.prepare()
        self.guard()
        self.verify()
        with self.assertRaises(ErasureAccessBlocked):
            self.guard()
        with self.assertRaises(ErasureVerificationRejected):
            self.verify()
        row = self.connection.execute(
            text(
                "SELECT status,access_epoch FROM ntubtob.mobile_sessions WHERE id=:id"
            ),
            {"id": self.session_id},
        ).one()
        self.assertEqual(tuple(row), ("revoked", 2))
        for session_id, expected in (
            (self.second_session_id, ("revoked", 2)),
            (self.other_session_id, ("active", 1)),
        ):
            row = self.connection.execute(
                text(
                    "SELECT status,access_epoch FROM ntubtob.mobile_sessions WHERE id=:id"
                ),
                {"id": session_id},
            ).one()
            self.assertEqual(tuple(row), expected)
        self.assertEqual(
            self.connection.execute(
                text(
                    "SELECT stage,result_code FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": self.job_id},
            ).all(),
            [("verification", "succeeded")],
        )

    def test_pending_actual_generation_verified_and_guard_blocks(self):
        self.prepare(pending=True)
        self.guard(pending=True)
        self.verify()
        with self.assertRaises(ErasureAccessBlocked):
            self.guard(pending=True)

    def test_pending_becoming_linked_invalidates_proof_without_mutation(self):
        self.prepare(pending=True)
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.person, "id": self.fixture.identity},
        )
        with self.assertRaises(ErasureVerificationRejected):
            self.verify()
        self.assert_requested()

    def test_equal_asserted_generations_cannot_override_actual_stored_generation(self):
        self.prepare(generation_override=str(uuid4()))
        with self.assertRaises(ErasureVerificationRejected):
            self.verify()
        self.assert_requested()
        self.guard()

    def test_disabled_person_and_blocked_bound_identity_can_verify_ownership(self):
        self.prepare()
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_status='disabled' WHERE id=:id"),
            {"id": self.fixture.person},
        )
        self.connection.execute(
            text("UPDATE ntubtob.auth_identities SET status='blocked' WHERE id=:id"),
            {"id": self.fixture.identity},
        )
        self.verify()
        with self.assertRaises(ErasureAccessBlocked):
            self.guard()

    def test_other_provider_proof_cannot_verify_same_subject(self):
        self.prepare()
        self.fresh = replace(self.fresh, provider="line")
        with self.assertRaises(ErasureVerificationRejected):
            self.verify()
        self.assert_requested()

    def test_caller_rollback_restores_requested_session_and_guard(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, "fictional rollback"):
            with self.session() as session, session.begin():
                self.coordinator.verify(
                    session, job_id=self.job_id, assertion="fictional-proof"
                )
                raise RuntimeError("fictional rollback")
        self.assert_requested()
        self.guard()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.mobile_sessions WHERE id=:id"),
                {"id": self.session_id},
            ),
            "active",
        )

    def test_failed_step_insert_cannot_commit_partial_job_or_revocation(self):
        self.prepare()

        def reject_step(connection, cursor, statement, parameters, context, many):
            if "INSERT INTO ntubtob.account_erasure_steps" in statement:
                raise SQLAlchemyError("fictional step failure")

        event.listen(self.connection, "before_cursor_execute", reject_step)
        try:
            with self.session() as session, session.begin():
                with self.assertRaises(ErasureVerificationUnavailable):
                    self.coordinator.verify(
                        session, job_id=self.job_id, assertion="fictional-proof"
                    )
        finally:
            event.remove(self.connection, "before_cursor_execute", reject_step)
        self.assert_requested()
        self.guard()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.mobile_sessions WHERE id=:id"),
                {"id": self.session_id},
            ),
            "active",
        )
