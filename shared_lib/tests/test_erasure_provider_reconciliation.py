import unittest
from unittest.mock import Mock

from shared_lib.shared_module.portal_data import (
    erasure_provider_reconciliation as module,
)
from shared_lib.tests import test_erasure_provider_execution as fixture

GENERATION, ITEM, JOB, NOW = fixture.GENERATION, fixture.ITEM, fixture.JOB, fixture.NOW


class ProviderReconciliationTests(unittest.TestCase):
    transaction = fixture.ProviderExecutionTests.transaction
    session = fixture.ProviderExecutionTests.session
    effect = fixture.ProviderExecutionTests.effect

    def setUp(self):
        fixture.ProviderExecutionTests.setUp(self)
        self.connection.execute.return_value.mappings.return_value.all.return_value = [
            dict(event_sequence=1, event_kind="started", result_code="in_progress"),
            dict(
                event_sequence=2, event_kind="unknown", result_code="response_unknown"
            ),
        ]
        self.inspect = Mock(
            return_value=module.ProviderOutcomeEvidence(
                "b" * 64, "a" * 64, GENERATION, "succeeded"
            )
        )
        self.reconciler = module.ProviderErasureReconciler(
            self.executor.engine, self.inspect, clock=lambda: NOW
        )

    def reconcile(self):
        return self.reconciler.reconcile(job_id=JOB, item_id=ITEM)

    def test_reconciliation_records_evidence_without_dispatch(self):
        result = self.reconcile()
        self.assertEqual(result.classification, "confirmed")
        self.assertEqual(result.effect_result, "succeeded")
        self.assertEqual(self.commits, 1)
        self.invoke.assert_not_called()
        self.assertEqual(self.connection.execute.call_args.args[1]["sequence"], 3)

    def test_no_proof_cannot_resolve_unknown(self):
        self.inspect.return_value = None
        result = self.reconcile()
        self.assertEqual(result.reason, "evidence_not_verified")
        self.assertEqual(self.connection.execute.call_count, 1)
        self.invoke.assert_not_called()

    def test_scope_changed_cannot_resolve_unknown(self):
        self.inspect.return_value = module.ProviderOutcomeEvidence(
            "c" * 64, "a" * 64, GENERATION, "succeeded"
        )
        self.assertEqual(self.reconcile().reason, "evidence_not_verified")

    def test_lost_commit_retains_known_result(self):
        self.fail_commit = 1
        result = self.reconcile()
        self.assertEqual(result.classification, "outcome_unknown")
        self.assertEqual(result.effect_result, "succeeded")
        self.assertEqual(result.reason, "evidence_commit_unconfirmed")

    def test_known_terminal_cannot_be_rewritten(self):
        self.connection.execute.return_value.mappings.return_value.all.return_value[
            1
        ].update(event_kind="confirmed", result_code="succeeded")
        self.assertEqual(self.reconcile().reason, "item_not_uncertain")
        self.inspect.assert_not_called()
