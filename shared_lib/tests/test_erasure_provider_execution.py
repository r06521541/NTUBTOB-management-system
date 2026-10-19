import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from sqlalchemy import create_engine

from shared_lib.shared_module.portal_data import erasure_provider_execution as module

JOB = "11111111-1111-4111-8111-111111111111"
ITEM = "22222222-2222-4222-8222-222222222222"
GENERATION = "33333333-3333-4333-8333-333333333333"
NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)


class ProviderExecutionTests(unittest.TestCase):
    def setUp(self):
        self.live = 0
        self.commits = 0
        self.fail_commit = None
        self.connection = Mock()
        self.connection.scalar.return_value = False
        self.job = dict(
            expected_generation=GENERATION,
            scope_hash="a" * 64,
            updated_at=NOW,
            irreversible_started_at=NOW,
        )
        self.item = dict(binding_hash="b" * 64, created_at=NOW)
        self.invoke = Mock(side_effect=self.effect)
        self.prepared = module.PreparedProviderEffect(
            "b" * 64, "a" * 64, GENERATION, self.invoke
        )
        self.prepare = Mock(return_value=self.prepared)
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.executor = module.ProviderErasureExecutor(
            self.engine, self.prepare, clock=lambda: NOW
        )
        for name, replacement in (
            ("Session", lambda engine: self.session()),
            ("_connection", Mock(return_value=self.connection)),
            ("_locked", Mock(return_value=(self.job, self.item))),
            ("_target", Mock()),
        ):
            patcher = patch.object(module, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextmanager
    def transaction(self):
        self.live += 1
        try:
            yield
            if self.fail_commit == self.commits + 1:
                raise RuntimeError("private storage sentinel")
            self.commits += 1
        finally:
            self.live -= 1

    @contextmanager
    def session(self):
        yield Mock(begin=self.transaction)

    def effect(self):
        self.assertEqual(self.live, 0)
        self.assertEqual(self.commits, 1)
        return "succeeded"

    def execute(self):
        return self.executor.execute(job_id=JOB, item_id=ITEM)

    def test_existing_connection_is_not_an_independent_commit_boundary(self):
        with self.engine.connect() as connection, connection.begin():
            with self.assertRaises(ValueError):
                module.ProviderErasureExecutor(connection, self.prepare)
        self.prepare.assert_not_called()
        self.invoke.assert_not_called()

    def test_provider_only_after_commit_and_result_after_second_commit(self):
        result = self.execute()
        self.assertEqual(result.classification, "confirmed")
        self.assertEqual(result.effect_result, "succeeded")
        self.assertEqual(self.commits, 2)
        self.invoke.assert_called_once_with()

    def test_lost_fence_commit_ack_never_calls_provider(self):
        self.fail_commit = 1
        result = self.execute()
        self.assertEqual(result.stage, "fence_commit")
        self.assertEqual(result.reason, "fence_unconfirmed")
        self.assertEqual(result.next_action, "read_only_review")
        self.invoke.assert_not_called()
        self.assertNotIn("private", repr(result))

    def test_lost_result_commit_keeps_known_provider_result(self):
        self.fail_commit = 2
        result = self.execute()
        self.assertEqual(result.classification, "outcome_unknown")
        self.assertEqual(result.stage, "result_commit")
        self.assertEqual(result.effect_result, "succeeded")
        self.assertEqual(result.reason, "evidence_unconfirmed")
        self.invoke.assert_called_once_with()

    def test_provider_exception_is_unknown_not_missing_credential(self):
        self.invoke.side_effect = RuntimeError("private provider sentinel")
        result = self.execute()
        self.assertEqual(result.classification, "outcome_unknown")
        self.assertEqual(result.effect_result, None)
        self.assertEqual(result.reason, "response_unknown")
        self.assertEqual(self.commits, 2)
        values = [call.args[1] for call in self.connection.execute.call_args_list]
        self.assertTrue(
            any(value.get("result") == "response_unknown" for value in values)
        )
        self.assertNotIn("private", repr(result))

    def test_invalid_provider_result_is_unknown(self):
        self.invoke.side_effect = None
        for value in (None, {"raw": "private"}, "retry", True):
            with self.subTest(kind=type(value).__name__):
                self.invoke.return_value = value
                self.assertEqual(self.execute().classification, "outcome_unknown")

    def test_existing_attempt_and_scope_mismatch_never_dispatch(self):
        self.connection.scalar.return_value = True
        self.assertEqual(self.execute().reason, "item_already_started")
        self.prepare.assert_not_called()
        self.connection.scalar.return_value = False
        self.prepare.return_value = module.PreparedProviderEffect(
            "c" * 64, "a" * 64, GENERATION, self.invoke
        )
        self.assertEqual(self.execute().reason, "prepared_scope_changed")
        self.invoke.assert_not_called()

    def test_invalid_identifier_no_prepare_or_dispatch(self):
        result = self.executor.execute(job_id="private", item_id=ITEM)
        self.assertEqual(result.stage, "input")
        self.assertEqual(result.reason, "invalid_identifier")
        self.prepare.assert_not_called()
        self.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
