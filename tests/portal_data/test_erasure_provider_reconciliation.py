import unittest

from shared_lib.shared_module.portal_data.erasure_provider_reconciliation import (
    ProviderErasureReconciler,
    ProviderOutcomeEvidence,
)
from tests.portal_data import test_erasure_provider_execution as fixture


@unittest.skipUnless(fixture.ledger.DATABASE_URL, "isolated ledger URL not configured")
class ProviderReconciliationPostgresTests(unittest.TestCase):
    setUp = fixture.ProviderExecutionPostgresTests.setUp
    cleanup_fixture = fixture.ProviderExecutionPostgresTests.cleanup_fixture
    prepare = fixture.ProviderExecutionPostgresTests.prepare
    invoke = fixture.ProviderExecutionPostgresTests.invoke
    events = fixture.ProviderExecutionPostgresTests.events
    execute = fixture.ProviderExecutionPostgresTests.execute

    def reconciler(self, result):
        return ProviderErasureReconciler(
            self.engine,
            lambda connection, job, item: ProviderOutcomeEvidence(
                item["binding_hash"],
                job["scope_hash"],
                str(job["expected_generation"]),
                result,
            ),
            clock=lambda: fixture.NOW + fixture.timedelta(seconds=2),
        )

    def test_unknown_resolves_once_without_repeating_provider(self):
        self.effect = lambda: None
        self.assertEqual(self.execute().classification, "outcome_unknown")
        reconciler = self.reconciler("succeeded")
        self.assertEqual(
            reconciler.reconcile(
                job_id=self.job_id, item_id=self.item_id
            ).classification,
            "confirmed",
        )
        self.assertEqual(self.events()[-1], (3, "confirmed", "succeeded"))
        self.assertEqual(
            reconciler.reconcile(job_id=self.job_id, item_id=self.item_id).reason,
            "item_not_uncertain",
        )
        self.assertEqual(self.calls, 1)

    def test_invalid_evidence_keeps_unknown(self):
        self.effect = lambda: None
        self.execute()
        self.assertEqual(
            self.reconciler("probably_succeeded")
            .reconcile(job_id=self.job_id, item_id=self.item_id)
            .reason,
            "evidence_not_verified",
        )
        self.assertEqual(self.events()[-1], (2, "unknown", "response_unknown"))
        self.assertEqual(self.calls, 1)
