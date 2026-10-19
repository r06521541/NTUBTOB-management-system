"""No-DB regressions for ledger-aware legacy fixture ordering and target binding."""

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from tests.portal_data import test_candidate_diagnostic as candidate
from tests.portal_data import test_phase_c_cross_service_rollout as rollout
from tests.portal_data import test_postgres_constraints as constraints
from tests.portal_data import test_repository_contract as repository


class ErasureFixtureCallerTests(unittest.TestCase):
    def test_retained_native_history_prevents_upgrade_or_legacy_truncation(self):
        for module, cls in (
            (candidate, candidate.CandidateDiagnosticPostgresTests),
            (rollout, rollout.PhaseCCrossServiceRolloutTests),
            (constraints, constraints.PostgresConstraintTests),
            (repository, repository.PostgresRepositoryContractTests),
        ):
            with self.subTest(module=module.__name__), ExitStack() as stack:
                case = cls("runTest")
                case.engine = MagicMock()
                if hasattr(module, "setup_legacy_fixture"):
                    stack.enter_context(patch.object(module, "setup_legacy_fixture"))
                stack.enter_context(
                    patch.object(
                        module,
                        "remove_retained_erasure_ledger_from_isolated_test_database",
                        side_effect=RuntimeError("intake_history_retained"),
                    )
                )
                upgrade = stack.enter_context(patch.object(module.command, "upgrade"))
                with self.assertRaisesRegex(RuntimeError, "intake_history_retained"):
                    case.setUp()
                upgrade.assert_not_called()
                case.engine.begin.assert_not_called()

    def test_restore_uses_fixture_engine_and_runs_after_cleanup(self):
        for module, cls in (
            (candidate, candidate.CandidateDiagnosticPostgresTests),
            (rollout, rollout.PhaseCCrossServiceRolloutTests),
            (constraints, constraints.PostgresConstraintTests),
            (repository, repository.PostgresRepositoryContractTests),
        ):
            with self.subTest(module=module.__name__), ExitStack() as stack:
                case = cls("runTest")
                case.engine = MagicMock()
                connection = case.engine.begin.return_value.__enter__.return_value
                events = []
                stack.enter_context(
                    patch.object(
                        module,
                        "remove_retained_erasure_ledger_from_isolated_test_database",
                        side_effect=lambda engine: events.append("cleanup"),
                    )
                )
                if hasattr(module, "setup_legacy_fixture"):
                    stack.enter_context(patch.object(module, "setup_legacy_fixture"))

                def upgrade(config, revision):
                    self.assertIs(config.attributes.get("connection"), connection)
                    self.assertIn("cleanup", events)
                    events.append(revision)

                stack.enter_context(
                    patch.object(module.command, "upgrade", side_effect=upgrade)
                )
                case.setUp()
                self.assertEqual(events[0], "cleanup")
                self.assertEqual(events[-1], "0014_account_erasure_ledger")

    def test_rollout_class_cleans_retained_schema_before_initial_upgrade(self):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        events = []

        def upgrade(config, revision):
            self.assertIs(config.attributes.get("connection"), connection)
            self.assertEqual(events, ["cleanup"])
            self.assertEqual(revision, "0013_account_deletion_requests")

        with (
            patch.object(
                rollout,
                "DATABASE_URL",
                "postgresql://fake@127.0.0.1/ntubtob_portal_local",
            ),
            patch.object(rollout, "create_engine", return_value=engine),
            patch.object(
                rollout,
                "remove_retained_erasure_ledger_from_isolated_test_database",
                side_effect=lambda engine: events.append("cleanup"),
            ),
            patch.object(rollout.command, "upgrade", side_effect=upgrade),
            patch.object(
                rollout.PhaseCCrossServiceRolloutTests, "engine", engine, create=True
            ),
        ):
            rollout.PhaseCCrossServiceRolloutTests.setUpClass()
