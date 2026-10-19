"""Same-transaction real capture/custody using only fictional local PostgreSQL."""

import json
import unittest

from shared_lib.shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_lib.shared_module.portal_data.erasure_composition import (
    ErasurePlanPolicy,
    TrustedErasurePlanBuilder,
)
from shared_lib.shared_module.portal_data.erasure_request import (
    ErasureRequestUnavailable,
)
from tests.portal_data import test_erasure_request as linked
from tests.portal_data import test_erasure_restricted_request as pending


def builder(test, *, missing=False):
    metadata = linked.plan()

    def review(**values):
        test.assertIs(values["connection"], test.connection)
        test.review_calls += 1
        if missing:
            return None
        if values["person_id"] is None:
            return ()  # Explicit fictional approval; capture still checks required rows.
        return json.dumps(
            {
                "version": 1,
                "person_id": values["person_id"],
                "generation": values["target_generation"],
                "dispositions": [],
            }
        ).encode()

    return TrustedErasurePlanBuilder(
        review_source=review,
        policy_source=lambda **values: ErasurePlanPolicy(
            metadata.retention_policy_version,
            metadata.fulfillment_due_at,
            metadata.receipt_expires_at,
            metadata.evidence_expires_at,
        ),
        restore_codec=RestoreBindingCodec(
            namespace="00000000-0000-4000-8000-000000000003",
            active_key="fictional",
            keys={"fictional": b"F" * 32},
        ),
        provider_audiences={"apple": "fictional-apple"},
    )


@unittest.skipUnless(
    pending.fixture.DATABASE_URL, "isolated erasure URL not configured"
)
class LinkedCompositionPostgresTests(unittest.TestCase):
    setUpClass = linked.RequestCustodyPostgresTests.__dict__["setUpClass"]
    tearDownClass = linked.RequestCustodyPostgresTests.__dict__["tearDownClass"]
    capture = linked.RequestCustodyPostgresTests.capture
    count = linked.RequestCustodyPostgresTests.count

    def setUp(self):
        linked.RequestCustodyPostgresTests.setUp(self)
        self.review_calls = 0
        self.repo.plan_builder = builder(self)

    def test_real_builder_capture_and_custody_duplicate_load_only(self):
        receipt = self.repo.request(self.principal)
        snapshot = self.store.load(self.connection, receipt.job_id)
        self.assertEqual(snapshot.person_id, self.principal.person_id)
        self.assertEqual(self.repo.request(self.principal), receipt)
        self.assertEqual(self.review_calls, 1)
        self.assertEqual(self.count("account_erasure_jobs"), 1)
        self.assertEqual(self.count("account_erasure_sealed_plans"), 1)

    def test_missing_review_never_creates_job_or_plan(self):
        self.repo.plan_builder = builder(self, missing=True)
        with self.assertRaises(ErasureRequestUnavailable):
            self.repo.request(self.principal)
        self.assertEqual(self.count("account_erasure_jobs"), 0)
        self.assertEqual(self.count("account_erasure_sealed_plans"), 0)


@unittest.skipUnless(
    pending.fixture.DATABASE_URL, "isolated erasure URL not configured"
)
class PendingCompositionPostgresTests(unittest.TestCase):
    setUpClass = pending.RestrictedCustodyPostgresTests.__dict__["setUpClass"]
    tearDownClass = pending.RestrictedCustodyPostgresTests.__dict__["tearDownClass"]
    upgrade = pending.RestrictedCustodyPostgresTests.upgrade
    capture = pending.RestrictedCustodyPostgresTests.capture
    count = pending.RestrictedCustodyPostgresTests.count

    def setUp(self):
        pending.RestrictedCustodyPostgresTests.setUp(self)
        self.review_calls = 0
        self.repo.plan_builder = builder(self)

    def test_real_pending_builder_and_attempt_share_original_transaction(self):
        receipt = self.repo.request_restricted("fictional-proof")
        snapshot = self.store.load(self.connection, receipt.job_id)
        self.assertIsNotNone(snapshot.identity_id)
        self.assertEqual(self.repo.request_restricted("fictional-proof"), receipt)
        self.assertEqual(self.review_calls, 1)
        self.assertEqual(
            [
                self.count(table)
                for table in (
                    "account_erasure_jobs",
                    "account_erasure_sealed_plans",
                    "account_erasure_request_attempts",
                )
            ],
            [1, 1, 1],
        )


if __name__ == "__main__":
    unittest.main()
