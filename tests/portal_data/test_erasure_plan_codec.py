"""Real fictional inventory roundtrip; no durable custody is claimed here."""

import unittest

from shared_lib.shared_module.portal_data.erasure_plan_codec import ErasurePlanCodec
from tests.portal_data.test_erasure_person_fulfillment import (
    _PersonFulfillmentFixture,
    ledger,
)


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class ActualSnapshotCodecTests(_PersonFulfillmentFixture, unittest.TestCase):
    def test_original_snapshot_survives_codec_restart_and_fulfills_exact_scope(self):
        namespace = "00000000-0000-4000-8000-000000000003"
        blob = ErasurePlanCodec(namespace=namespace, key=b"F" * 32).encode(
            self.snapshot, job_id=self.job_id
        )
        restored = ErasurePlanCodec(namespace=namespace, key=b"F" * 32).decode(
            blob,
            job_id=self.job_id,
            target_kind="person",
            generation=self.snapshot.generation,
            scope_hash=self.snapshot.scope_hash,
        )
        self.assertEqual(restored, self.snapshot)
        result = self.executor.execute(job_id=self.job_id, snapshot=restored)
        self.assertEqual(
            (result.classification, result.reason), ("confirmed", "online_completed")
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE id=:id",
                id=self.fixture.person,
            ),
            0,
        )
        self.assertEqual(sorted(self.calls), ["apple", "line"])


if __name__ == "__main__":
    unittest.main()
