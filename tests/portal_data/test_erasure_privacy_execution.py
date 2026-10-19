"""Exact reviewed shared-content patch and evidence commit in real transactions."""

import json
import unittest
from datetime import timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from shared_lib.shared_module.portal_data.erasure_privacy_execution import (
    PrivacyDispositionExecutor,
)
from shared_lib.shared_module.portal_data.erasure_provider_execution import _Rejected
from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data import test_erasure_provider_execution as provider_fixture
from tests.portal_data.test_erasure_verification import NOW


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class PrivacyExecutionPostgresTests(unittest.TestCase):
    cleanup_fixture = provider_fixture.ProviderExecutionPostgresTests.cleanup_fixture

    def prepare(self, *args):
        raise AssertionError("provider must not be invoked")

    def setUp(self):
        provider_fixture.ProviderExecutionPostgresTests.setUp(self)
        self.patch = {"title": "Team practice", "created_by_person_id": None}
        self.privacy_item = str(uuid4())
        with self.engine.begin() as connection:
            config = Config(str(ledger.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_erasure_privacy_mutation")
            self.event = connection.scalar(
                text(
                    "INSERT INTO ntubtob.events (title,event_type,status,start_at,created_by_person_id,version,created_at,updated_at) VALUES ('Fictional owner practice','practice','draft',:now,:person,1,:now,:now) RETURNING id"
                ),
                {"now": NOW, "person": self.fixture.person},
            )
            self.digest = connection.scalar(
                text(
                    "SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM ntubtob.events t WHERE id=:id"
                ),
                {"id": self.event},
            )
            binding = connection.scalar(
                text(
                    "SELECT encode(sha256(convert_to(jsonb_build_array('privacy_mutation_v1',CAST(:job AS uuid),CAST(:generation AS uuid),'events'::text,CAST(:row AS bigint),CAST(:old AS text),CAST(:patch AS jsonb),'update'::text)::text,'UTF8')),'hex')"
                ),
                dict(
                    job=self.job_id,
                    generation=self.job["expected_generation"],
                    row=self.event,
                    old=self.digest,
                    patch=json.dumps(self.patch),
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,'manual_redaction',:binding,:generation,:now)"
                ),
                dict(
                    id=self.privacy_item,
                    job=self.job_id,
                    binding=binding,
                    generation=self.job["expected_generation"],
                    now=NOW,
                ),
            )
        self.addCleanup(self.cleanup_event)
        self.privacy_executor = PrivacyDispositionExecutor(
            self.engine, clock=lambda: NOW + timedelta(seconds=1)
        )

    def cleanup_event(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ntubtob.events WHERE id=:id"), {"id": self.event}
            )

    def execute(self, **changes):
        args = dict(
            job_id=self.job_id,
            item_id=self.privacy_item,
            table="events",
            row_id=self.event,
            old_digest=self.digest,
            patch=self.patch,
        )
        args.update(changes)
        return self.privacy_executor.execute(**args)

    def test_shared_event_survives_with_actual_text_redacted_and_item_evidence(self):
        self.assertEqual(self.execute().classification, "confirmed")
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT title,created_by_person_id,status FROM ntubtob.events WHERE id=:id"
                ),
                {"id": self.event},
            ).one()
            self.assertEqual(tuple(row), ("Team practice", None, "draft"))
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.privacy_item},
                ),
                2,
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

    def test_replacement_must_match_immutable_reviewed_item(self):
        result = self.execute(patch={"title": "Unreviewed private sentinel"})
        self.assertEqual(result.reason, "privacy_item_binding_rejected")
        self.assertNotIn("sentinel", repr(result))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.privacy_item},
                ),
                0,
            )

    def test_same_transaction_scope_rejection_precedes_fence_and_redaction(self):
        seen = []

        def validate(connection, job, item):
            self.assertTrue(connection.in_transaction())
            self.assertEqual(str(item["id"]), self.privacy_item)
            self.assertIsNone(job["irreversible_started_at"])
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.account_erasure_item_events WHERE item_id=:id"
                    ),
                    {"id": self.privacy_item},
                ),
                0,
            )
            seen.append(connection)
            raise _Rejected("sealed_inventory_changed")

        self.privacy_executor = PrivacyDispositionExecutor(
            self.engine,
            clock=lambda: NOW + timedelta(seconds=1),
            scope_validator=validate,
        )
        self.assertEqual(self.execute().reason, "sealed_inventory_changed")
        self.assertEqual(len(seen), 1)
        for answer in (False, True):
            self.privacy_executor.scope_validator = lambda connection, job, item: answer
            self.assertEqual(self.execute().reason, "scope_validator_rejected")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT title FROM ntubtob.events WHERE id=:id"),
                    {"id": self.event},
                ),
                "Fictional owner practice",
            )
        self.privacy_executor.scope_validator = lambda connection, job, item: None
        self.assertEqual(self.execute().classification, "confirmed")

    def test_edit_after_review_rejects_without_overwriting_new_content(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.events SET title='New team content' WHERE id=:id"),
                {"id": self.event},
            )
        self.assertEqual(self.execute().reason, "privacy_row_version_rejected")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT title FROM ntubtob.events WHERE id=:id"),
                    {"id": self.event},
                ),
                "New team content",
            )

    def test_outer_transaction_is_not_a_commit_boundary(self):
        with self.engine.connect() as connection, connection.begin():
            with self.assertRaises(ValueError):
                PrivacyDispositionExecutor(connection)
