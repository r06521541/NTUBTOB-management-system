"""Real local PostgreSQL coordinator with fictional object-storage transport."""

import unittest
from unittest.mock import Mock

import httplib2
from googleapiclient.errors import HttpError
from sqlalchemy import text

from shared_lib.shared_module.portal_data.erasure_fulfillment import (
    PendingRestoreRecord,
)
from shared_lib.shared_module.portal_data.erasure_restore_store import (
    GcsErasureRestorePurger,
    GcsErasureRestoreStore,
)
from shared_lib.tests.test_erasure_restore_store import (
    BUCKET,
    NAMESPACE,
    FakePurgeObjects,
)
from tests.portal_data import test_erasure_fulfillment as fulfillment


@unittest.skipUnless(
    fulfillment.ledger.DATABASE_URL, "isolated ledger URL not configured"
)
class RestoreStorePostgresTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fulfillment.PendingFulfillmentPostgresTests("runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.objects = FakePurgeObjects()
        self.client = Mock()
        self.client.objects.return_value = self.objects
        self.fixture.executor.restore_store = self.new_store()

    def new_store(self):
        return GcsErasureRestoreStore(
            client=self.client, bucket=BUCKET, namespace=NAMESPACE
        )

    def restore_events(self):
        with self.fixture.engine.connect() as connection:
            return tuple(
                connection.execute(
                    text(
                        "SELECT e.event_kind,e.result_code FROM "
                        "ntubtob.account_erasure_item_events e JOIN "
                        "ntubtob.account_erasure_items i ON i.id=e.item_id "
                        "WHERE i.job_id=:job AND i.stage='restore_suppression' "
                        "ORDER BY e.event_sequence"
                    ),
                    {"job": self.fixture.job_id},
                ).all()
            )

    def observe_upload(self, *, lose_response=False):
        original = self.objects.insert

        def insert(**kwargs):
            request = original(**kwargs)
            upload = request.callback

            def checked_upload():
                # Independent connection proves the started event was committed.
                self.assertEqual(self.restore_events(), (("started", "in_progress"),))
                self.assertIsNotNone(
                    self.fixture.scalar(
                        "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                        id=self.fixture.job_id,
                    )
                )
                result = upload()
                if lose_response:
                    raise TimeoutError("fictional response lost after storage")
                return result

            request.callback = checked_upload
            return request

        self.objects.insert = insert

    def test_committed_fence_exact_readback_then_confirmed(self):
        self.observe_upload()
        result = self.fixture.execute()
        self.assertEqual(result.classification, "confirmed", result)
        self.assertEqual(
            self.restore_events(),
            (("started", "in_progress"), ("confirmed", "succeeded")),
        )
        self.assertEqual(len(self.objects.inserts), 1)
        self.assertEqual(len(self.objects.http_calls), 1)
        item_id = self.objects.metadata["name"].rsplit("/", 1)[1][:-5]
        restored = self.new_store().read(item_id)
        self.assertEqual(
            restored,
            PendingRestoreRecord(
                self.fixture.job_id,
                item_id,
                self.fixture.snapshot.scope_hash,
                self.fixture.snapshot.generation,
                self.fixture.snapshot.restore_binding,
            ),
        )

    def test_lost_insert_response_is_unknown_and_never_repeated(self):
        self.observe_upload(lose_response=True)
        self.assertEqual(self.fixture.execute().classification, "needs_attention")
        self.assertEqual(
            self.restore_events(),
            (("started", "in_progress"), ("unknown", "response_unknown")),
        )
        self.assertTrue(self.objects.blob)
        self.assertEqual(self.objects.gets, [])
        self.assertEqual(self.fixture.execute().classification, "needs_attention")
        self.assertEqual(len(self.objects.inserts), 1)
        self.assertEqual(self.fixture.calls, 1)
        for table, column in (
            ("auth_identities", "id"),
            ("apple_provider_credentials", "auth_identity_id"),
        ):
            self.assertEqual(
                self.fixture.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE {column}=:id",
                    id=self.fixture.fixture.identity,
                ),
                1,
            )
        self.assertIsNone(
            self.fixture.scalar(
                "SELECT online_completed_at FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.fixture.job_id,
            )
        )
        # Read-only investigation can find the record, but cannot rewrite evidence
        # or silently authorize another upload/finalization.
        item_id = self.objects.metadata["name"].rsplit("/", 1)[1][:-5]
        self.assertEqual(self.new_store().read(item_id).job_id, self.fixture.job_id)
        self.assertEqual(self.restore_events()[-1], ("unknown", "response_unknown"))

    def test_versioned_custody_purge_ack_does_not_change_ledger_or_claim_policy_completion(
        self,
    ):
        self.assertEqual(self.fixture.execute().classification, "confirmed")
        events = self.restore_events()
        item_id = self.objects.metadata["name"].rsplit("/", 1)[1][:-5]
        versioned = self.new_store().read_versioned(item_id)
        self.assertEqual(versioned.record.job_id, self.fixture.job_id)
        # A separately supplied private client is not the custody writer's client.
        private_client = Mock()
        private_client.objects.return_value = self.objects
        purger = GcsErasureRestorePurger(
            client=private_client, bucket=BUCKET, namespace=NAMESPACE
        )
        result = purger.purge(versioned.version)
        self.assertEqual(result.classification, "active_version_removed")
        self.assertEqual(result.next_action, "read_only_version_review")
        self.assertEqual(self.objects.deletes[0]["ifGenerationMatch"], "7")
        self.assertNotIn("generation", self.objects.deletes[0])
        self.assertEqual(self.restore_events(), events)
        self.assertEqual(purger.purge(versioned.version), result)
        self.assertEqual(len(self.objects.deletes), 1)

    def test_purge_lost_ack_readonly_version_missing_preserves_unknown_and_ledger(self):
        self.assertEqual(self.fixture.execute().classification, "confirmed")
        events = self.restore_events()
        item_id = self.objects.metadata["name"].rsplit("/", 1)[1][:-5]
        version = self.new_store().read_versioned(item_id).version
        private_client = Mock()
        private_client.objects.return_value = self.objects
        purger = GcsErasureRestorePurger(
            client=private_client, bucket=BUCKET, namespace=NAMESPACE
        )
        self.objects.after_delete = lambda: setattr(
            self.objects,
            "metadata_error",
            HttpError(
                httplib2.Response({"status": "404"}), b"fictional missing version"
            ),
        )
        self.objects.delete_error = TimeoutError("fictional lost delete response")
        unknown = purger.purge(version)
        self.assertEqual(unknown.classification, "delete_outcome_unknown")
        self.assertTrue(unknown.delete_dispatched)
        self.assertEqual(
            purger.read_version_presence(version).classification, "version_not_found"
        )
        self.assertEqual(purger.purge(version), unknown)
        self.assertEqual(len(self.objects.deletes), 1)
        self.assertEqual(self.restore_events(), events)
