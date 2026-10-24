"""Fictional fixed retention decisions; never real inventory or purge proof."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from shared_lib.shared_module.portal_data.erasure_retention import (
    BackupObservation,
    RetentionFacts,
    RetentionRejected,
    evaluate_retention,
    retention_failure_reason,
)


class RetentionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.requested = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.now = self.requested + timedelta(days=180)
        self.backup = BackupObservation(
            checked_at=self.now,
            inventory_complete=True,
            last_restorable_until=self.now - timedelta(days=1),
            suppression_verified_at=self.now,
            binding_readable=True,
            key_readable=True,
        )
        self.facts = RetentionFacts(
            requested_at=self.requested,
            status="completed",
            online_completed_at=self.requested + timedelta(days=5),
            receipt_until=self.now,
            evidence_until=self.now,
            unresolved_effects=False,
            executor_needs_plan=False,
            authority_target_detached=True,
            backup=self.backup,
        )

    def evaluate(self, **changes):
        return evaluate_retention(replace(self.facts, **changes), now=self.now)

    def test_complete_boundary_allows_eligibility_not_purge_authority(self):
        result = self.evaluate()
        self.assertTrue(result.private_plan_due)
        self.assertTrue(result.minimal_evidence_eligible)
        self.assertFalse(result.block_new_irreversible)
        self.assertEqual(result.next_action, "authorized_custody_review")
        self.assertNotIn("complete", vars(result))

    def test_online_completion_plus_thirty_not_request_plus_thirty(self):
        self.assertFalse(
            self.evaluate(
                online_completed_at=self.now - timedelta(days=29)
            ).private_plan_due
        )
        self.assertTrue(
            self.evaluate(
                online_completed_at=self.now - timedelta(days=30)
            ).private_plan_due
        )

    def test_plan_does_not_wait_for_backup_expiry_but_requires_custody(self):
        future_copy = replace(
            self.backup,
            last_restorable_until=self.now + timedelta(days=7),
            suppression_verified_at=None,
        )
        result = self.evaluate(backup=future_copy)
        self.assertTrue(result.private_plan_due)
        self.assertFalse(result.minimal_evidence_eligible)
        self.assertFalse(result.block_new_irreversible)

    def test_unknown_horizon_day149_then_day150(self):
        for age, blocked in ((149, False), (150, True)):
            with self.subTest(age=age):
                now = self.requested + timedelta(days=age)
                facts = replace(
                    self.facts,
                    status="needs_attention",
                    online_completed_at=None,
                    backup=None,
                )
                result = evaluate_retention(facts, now=now)
                self.assertEqual(result.block_new_irreversible, blocked)
                self.assertFalse(result.private_plan_due)
                self.assertFalse(result.minimal_evidence_eligible)

    def test_stale_observation_does_not_silently_extend_inventory(self):
        for age, blocked in ((30, False), (31, True)):
            result = self.evaluate(
                backup=replace(
                    self.backup,
                    checked_at=self.now - timedelta(days=age),
                    suppression_verified_at=None,
                )
            )
            self.assertEqual(result.block_new_irreversible, blocked)

    def test_unknown_incomplete_and_missing_keys_do_not_mean_zero_copies(self):
        for backup in (
            None,
            replace(self.backup, inventory_complete=False),
            replace(self.backup, last_restorable_until=None),
            replace(self.backup, binding_readable=False),
            replace(self.backup, key_readable=False),
        ):
            with self.subTest(backup=type(backup).__name__):
                result = self.evaluate(backup=backup)
                self.assertTrue(result.block_new_irreversible)
                self.assertEqual(
                    result.private_plan_due,
                    backup is not None
                    and backup.binding_readable
                    and backup.key_readable,
                )
                self.assertFalse(result.minimal_evidence_eligible)

    def test_unfinished_effects_and_executor_need_preserve_private_plan(self):
        for changes in (
            dict(status="needs_attention"),
            dict(unresolved_effects=True),
            dict(executor_needs_plan=True),
        ):
            result = self.evaluate(**changes)
            self.assertFalse(result.private_plan_due)
            self.assertFalse(result.minimal_evidence_eligible)

    def test_minimal_cleanup_requires_terminal_not_just_online_completion(self):
        result = self.evaluate(status="online_completed")
        self.assertTrue(result.private_plan_due)
        self.assertFalse(result.minimal_evidence_eligible)

    def test_exact_phase_revision_can_release_plan_but_not_unresolved_evidence(self):
        facts = replace(
            self.facts, unresolved_effects=True, nonprovider_work_confirmed=True
        )
        result = evaluate_retention(
            facts, now=self.now, schema_revision="0024_erasure_provider_phases"
        )
        self.assertTrue(result.private_plan_due)
        self.assertFalse(result.minimal_evidence_eligible)
        self.assertFalse(
            evaluate_retention(
                replace(facts, nonprovider_work_confirmed=False),
                now=self.now,
                schema_revision="0024_erasure_provider_phases",
            ).private_plan_due
        )
        for revision in (None, "0023_erasure_minimal_retention", "future"):
            self.assertFalse(
                evaluate_retention(
                    facts, now=self.now, schema_revision=revision
                ).private_plan_due
            )
        self.assertFalse(
            evaluate_retention(
                replace(facts, executor_needs_plan=True),
                now=self.now,
                schema_revision="0024_erasure_provider_phases",
            ).private_plan_due
        )

    def test_day180_is_only_a_check_not_expiry_cleanup(self):
        for changes in (
            dict(
                receipt_until=self.now + timedelta(seconds=1),
                evidence_until=self.now + timedelta(seconds=1),
            ),
            dict(evidence_until=self.now + timedelta(seconds=1)),
            dict(authority_target_detached=False),
            dict(backup=replace(self.backup, suppression_verified_at=None)),
        ):
            self.assertFalse(self.evaluate(**changes).minimal_evidence_eligible)
        before = replace(self.facts, requested_at=self.requested + timedelta(seconds=1))
        self.assertFalse(
            evaluate_retention(before, now=self.now).minimal_evidence_eligible
        )

    def test_suppression_must_follow_last_restorable_copy(self):
        result = self.evaluate(
            backup=replace(
                self.backup, suppression_verified_at=self.now - timedelta(days=2)
            )
        )
        self.assertFalse(result.minimal_evidence_eligible)

    def test_cancelled_is_not_online_completed_or_permission_to_discard_unknowns(self):
        result = self.evaluate(status="cancelled", online_completed_at=None)
        self.assertFalse(result.private_plan_due)
        self.assertTrue(result.minimal_evidence_eligible)

    def test_reject_invalid_typed_or_future_facts_without_private_details(self):
        invalid = (
            replace(self.facts, status="fictional-private-value"),
            replace(self.facts, requested_at=self.now + timedelta(seconds=1)),
            replace(self.facts, requested_at=self.requested.replace(tzinfo=None)),
            replace(self.facts, unresolved_effects=0),
            replace(self.facts, online_completed_at=self.now + timedelta(seconds=1)),
            replace(
                self.facts,
                backup=replace(self.backup, checked_at=self.now + timedelta(seconds=1)),
            ),
            replace(
                self.facts,
                backup=replace(
                    self.backup, suppression_verified_at=self.now + timedelta(seconds=1)
                ),
            ),
            replace(self.facts, backup=replace(self.backup, inventory_complete=1)),
        )
        for facts in invalid:
            with self.subTest():
                with self.assertRaisesRegex(
                    RetentionRejected, "^retention_input_rejected$"
                ):
                    evaluate_retention(facts, now=self.now)

    def test_inputs_and_sensitive_observations_not_printed_or_changed(self):
        original = vars(self.facts).copy()
        self.evaluate()
        self.assertEqual(vars(self.facts), original)
        self.assertNotIn("2035", repr(self.facts))
        self.assertNotIn("2035", repr(self.backup))

    def test_safe_sql_failure_preserves_exact_check_but_never_raw_details(self):
        for message, expected in (
            (
                "retention_backup_horizon_unresolved",
                "retention_backup_horizon_unresolved",
            ),
            ("retention_backup_horizon_unresolved fictional-private-value", None),
            ("fictional-private-value", None),
            (None, None),
        ):
            error = SimpleNamespace(
                orig=SimpleNamespace(diag=SimpleNamespace(message_primary=message))
            )
            self.assertEqual(retention_failure_reason(error), expected)

    def test_inventory_freshness_and_suppression_equality_boundaries(self):
        stale = replace(
            self.backup,
            checked_at=self.now - timedelta(days=30, microseconds=1),
            suppression_verified_at=None,
        )
        self.assertTrue(self.evaluate(backup=stale).block_new_irreversible)
        equal = replace(
            self.backup,
            last_restorable_until=self.now,
            suppression_verified_at=self.now,
        )
        self.assertTrue(self.evaluate(backup=equal).minimal_evidence_eligible)


if __name__ == "__main__":
    unittest.main()
