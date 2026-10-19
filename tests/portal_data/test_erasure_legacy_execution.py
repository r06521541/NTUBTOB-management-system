"""Real isolated PostgreSQL deletion, preserving unrelated fictional members."""

import unittest
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from shared_lib.shared_module.account_erasure_scope import LegacyErasureScope
from shared_lib.shared_module.portal_data.erasure_legacy_execution import (
    LegacyErasureExecutor,
    legacy_item_binding,
)
from shared_lib.shared_module.portal_data.erasure_provider_execution import _Rejected
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data import test_erasure_provider_execution as provider_fixture
from tests.portal_data.test_erasure_verification import NOW


class LegacyConfigurationTests(unittest.TestCase):
    def test_non_callable_scope_validator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "^invalid_executor_configuration$"):
            LegacyErasureExecutor(Mock(spec=Engine), scope_validator=False)


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class LegacyExecutionPostgresTests(unittest.TestCase):
    cleanup_fixture = provider_fixture.ProviderExecutionPostgresTests.cleanup_fixture

    def setUp(self):
        provider_fixture.ProviderExecutionPostgresTests.setUp(self)
        self.addCleanup(self.cleanup_legacy)
        self.members, self.users, self.replies = [], [], []
        with self.engine.begin() as connection:
            self.game = connection.scalar(
                text("INSERT INTO ntubtob.games DEFAULT VALUES RETURNING id")
            )
            reply_type = connection.scalar(
                text(
                    "SELECT id FROM ntubtob.attendance_reply_types ORDER BY id LIMIT 1"
                )
            )
            for person in (self.fixture.person, self.fixture.other_person):
                member = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.members (name,person_id) VALUES ('Fictional erasure',:person) RETURNING id"
                    ),
                    {"person": person},
                )
                user = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.line_users (nickname,line_user_id,member_id,has_replied,ignored) VALUES ('Fictional erasure',:subject,:member,false,false) RETURNING id"
                    ),
                    {"subject": "fictional-erasure-" + str(uuid4()), "member": member},
                )
                reply = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.game_attendance_replies (game_id,person_id,member_id,user_id,reply) VALUES (:game,:person,:member,:user,:reply) RETURNING id"
                    ),
                    dict(
                        game=self.game,
                        person=person,
                        member=member,
                        user=user,
                        reply=reply_type,
                    ),
                )
                self.members.append(member)
                self.users.append(user)
                self.replies.append(reply)
            self.legacy_item = str(uuid4())
            binding = legacy_item_binding(
                self.job_id,
                str(self.job["expected_generation"]),
                LegacyErasureScope(
                    (self.members[0],), (self.users[0],), (self.replies[0],)
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'online_erasure',:binding,:generation,:now)"
                ),
                dict(
                    id=self.legacy_item,
                    job=self.job_id,
                    binding=binding,
                    generation=self.job["expected_generation"],
                    now=NOW,
                ),
            )
        self.legacy_executor = LegacyErasureExecutor(
            self.engine, clock=lambda: NOW + timedelta(seconds=1)
        )

    def prepare(self, *args):
        raise AssertionError("provider must not be invoked")

    def cleanup_legacy(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ntubtob.game_attendance_replies WHERE game_id=:id"),
                {"id": self.game},
            )
            for table, ids in (("line_users", self.users), ("members", self.members)):
                connection.execute(
                    text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                    {"ids": ids},
                )
            connection.execute(
                text("DELETE FROM ntubtob.games WHERE id=:id"), {"id": self.game}
            )

    def execute(self):
        return self.legacy_executor.execute(
            job_id=self.job_id, item_id=self.legacy_item
        )

    def counts(self):
        with self.engine.connect() as connection:
            return tuple(
                connection.scalar(
                    text(f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                    {"ids": ids},
                )
                for table, ids in (
                    ("members", self.members),
                    ("line_users", self.users),
                    ("game_attendance_replies", self.replies),
                )
            )

    def test_exact_own_rows_deleted_other_person_and_shared_game_survive(self):
        self.assertEqual(self.execute().classification, "confirmed")
        self.assertEqual(self.counts(), (1, 1, 1))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT person_id FROM ntubtob.members WHERE id=:id"),
                    {"id": self.members[1]},
                ),
                self.fixture.other_person,
            )
            self.assertEqual(
                connection.scalar(
                    text("SELECT count(*) FROM ntubtob.games WHERE id=:id"),
                    {"id": self.game},
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
        self.assertEqual(self.execute().reason, "item_already_started")

    def test_sealed_scope_check_precedes_fence_and_rejection_preserves_rows(self):
        seen = []

        def validate(connection, job, item):
            self.assertTrue(connection.in_transaction())
            self.assertEqual(job["person_id"], self.fixture.person)
            self.assertEqual(str(item["id"]), self.legacy_item)
            self.assertIsNone(
                connection.scalar(
                    text(
                        "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                    ),
                    {"id": self.job_id},
                )
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.legacy_item},
                ),
                0,
            )
            seen.append(connection)
            raise _Rejected("sealed_inventory_changed")

        self.legacy_executor = LegacyErasureExecutor(
            self.engine,
            clock=lambda: NOW + timedelta(seconds=1),
            scope_validator=validate,
        )
        result = self.execute()
        self.assertEqual(
            (result.classification, result.stage, result.reason),
            ("not_applied", "sealed_scope", "sealed_inventory_changed"),
        )
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.counts(), (2, 2, 2))
        self.legacy_executor.scope_validator = lambda connection, job, item: None
        self.assertEqual(self.execute().classification, "confirmed")
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_non_none_scope_result_never_deletes(self):
        for result in (False, True):
            self.legacy_executor = LegacyErasureExecutor(
                self.engine,
                clock=lambda: NOW + timedelta(seconds=1),
                scope_validator=lambda connection, job, item: result,
            )
            self.assertEqual(self.execute().reason, "scope_validator_rejected")
            self.assertEqual(self.counts(), (2, 2, 2))

    def test_conflicting_ownership_rolls_back_before_deletion(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.game_attendance_replies SET member_id=:member WHERE id=:id"
                ),
                {"member": self.members[1], "id": self.replies[0]},
            )
        self.assertEqual(self.execute().reason, "ownership_conflict")
        self.assertEqual(self.counts(), (2, 2, 2))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.legacy_item},
                ),
                0,
            )

    def test_inventory_drift_is_not_silently_expanded(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies (game_id,person_id,reply) SELECT game_id,person_id,reply FROM ntubtob.game_attendance_replies WHERE id=:id"
                ),
                {"id": self.replies[0]},
            )
        self.assertEqual(self.execute().reason, "inventory_changed")
        self.assertEqual(self.counts(), (2, 2, 2))

    def test_delete_failure_rolls_back_fence_and_prior_deletes(self):
        # A real FK protects a newly introduced dependent store; do not override it.
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE ntubtob.fictional_erasure_dependency (member_id bigint REFERENCES ntubtob.members(id))"
                )
            )
            connection.execute(
                text("INSERT INTO ntubtob.fictional_erasure_dependency VALUES (:id)"),
                {"id": self.members[0]},
            )
        try:
            result = self.execute()
            self.assertEqual(
                (result.classification, result.stage, result.reason),
                ("not_applied", "disposition", "transaction_failed"),
            )
            self.assertEqual(self.counts(), (2, 2, 2))
            with self.engine.connect() as connection:
                self.assertEqual(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                        ),
                        {"id": self.legacy_item},
                    ),
                    0,
                )
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text("DROP TABLE ntubtob.fictional_erasure_dependency")
                )

    def test_cannot_accept_outer_transaction(self):
        with self.engine.connect() as connection, connection.begin():
            with self.assertRaises(ValueError):
                LegacyErasureExecutor(connection)

    def test_empty_scope_does_not_create_irreversible_fence(self):
        with self.engine.begin() as connection:
            for table, identifier in (
                ("game_attendance_replies", self.replies[0]),
                ("line_users", self.users[0]),
                ("members", self.members[0]),
            ):
                connection.execute(
                    text(f"DELETE FROM ntubtob.{table} WHERE id=:id"),
                    {"id": identifier},
                )
            self.legacy_item = str(uuid4())
            binding = legacy_item_binding(
                self.job_id,
                str(self.job["expected_generation"]),
                LegacyErasureScope((), (), ()),
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'online_erasure',:binding,:generation,:now)"
                ),
                dict(
                    id=self.legacy_item,
                    job=self.job_id,
                    binding=binding,
                    generation=self.job["expected_generation"],
                    now=NOW,
                ),
            )
        self.assertEqual(self.execute().reason, "empty_scope")
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT status,irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job_id},
            ).one()
            self.assertEqual(tuple(row), ("verified", None))
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.legacy_item},
                ),
                0,
            )
