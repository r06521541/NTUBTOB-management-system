from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ci_change_classifier import (
    OUTPUTS,
    SCOPES,
    classify_git_diff,
    classify_paths,
    final_gate_failures,
)


def outputs(**enabled):
    return {name: "true" if enabled.get(name, False) else "false" for name in OUTPUTS}


def results(**overrides):
    values = {name: "skipped" for name in SCOPES}
    values.update(classify="success", quick="success")
    values.update(overrides)
    return values


class ChangeClassifierTests(unittest.TestCase):
    def assertScopes(self, paths, *expected):
        observed = classify_paths(paths).outputs()
        self.assertEqual(
            {name for name, value in observed.items() if value == "true"},
            set(expected),
        )

    def test_general_and_coordination_documents_are_docs_only(self):
        self.assertScopes(
            ["README.md", "docs/coordination/HANDOFF.yaml", "docs/planning/PLAN.md"],
            "docs_only",
        )

    def test_approved_repository_bootstrap_wrapper_is_quick_only(self):
        for paths in (
            ["tools/Invoke-FlutterToolchain.ps1"],
            ["tools/tests/test_ci_flutter_toolchain_contract.py"],
            [
                "AGENTS.md",
                "docs/coordination/archive/mobile/CLOSEOUT.md",
                "tools/Invoke-FlutterToolchain.ps1",
            ],
        ):
            with self.subTest(paths=paths):
                self.assertScopes(paths, "quick_only")

    def test_database_artifacts_and_boundaries_are_not_docs_only(self):
        for path, expected in (
            ("docs/operations/sql/inventory.sql", "portal_data"),
            ("docs/operations/data/RUNBOOK.md", "portal_data"),
            ("docs/development/LOCAL_PORTAL_DATA.md", "portal_data"),
            ("migrations/versions/0005.py", "portal_data"),
            ("tests/portal_data/test_contract.py", "portal_data"),
            ("tools/portal_data_phase_c_readiness.py", "portal_data"),
            ("docker-compose.portal-data.yml", "portal_data"),
            (".gitattributes", "full"),
        ):
            with self.subTest(path=path):
                self.assertScopes([path], expected)

    def test_each_application_and_function_selects_its_suite(self):
        cases = (
            ("apps/web_portal/tests/test_route.py", "web_portal"),
            ("apps/game_broadcast_service/main.py", "game_broadcast"),
            ("apps/notify_cronjob_service/tests/test_health.py", "notify_cron"),
            ("functions/update_game_schedule/tests/test_filter.py", "update_schedule"),
            ("functions/line_webhook_handler/main.py", "line_webhook"),
            ("tools/deploy_web_portal.py", "deployment_tools"),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertScopes([path], expected)

    def test_flutter_sources_and_reusable_workflow_select_flutter(self):
        for path in (
            "clients/flutter_app/lib/main.dart",
            "clients/flutter_app/android/app/build.gradle.kts",
            ".github/workflows/flutter-tests.yml",
        ):
            with self.subTest(path=path):
                self.assertScopes([path], "flutter")

    def test_multiple_known_scopes_are_combined(self):
        self.assertScopes(
            [
                "docs/README.md",
                "apps/web_portal/main.py",
                "functions/line_webhook_handler/main.py",
            ],
            "web_portal",
            "line_webhook",
        )

    def test_phase_c_runtime_selects_its_direct_consumer_suites(self):
        self.assertScopes(
            [
                "shared_lib/shared_module/portal_data/runtime.py",
            ],
            "deployment_tools",
            "web_portal",
            "line_webhook",
            "notify_cron",
        )

    def test_phase_c_deployment_boundaries_avoid_database_matrix(self):
        self.assertScopes(
            [
                "tests/portal_data/test_phase_c_rollout_state.py",
                "tools/phase_c_rollout_preflight.py",
                "tools/phase_c_transition_controller.py",
                "docs/operations/data/PORTAL_DATA_PHASE_C_APPLICATION_ROLLOUT.md",
                "envs/web_portal/.env_example.yaml",
                "envs/line_webhook_handler/.env_example.yaml",
                "envs/notify_cronjob_service/.env_example.yaml",
            ],
            "deployment_tools",
        )

    def test_shared_dependencies_workflow_models_and_unknown_paths_are_full(self):
        for path in (
            "shared_lib/shared_module/models/member.py",
            "requirements.txt",
            ".github/workflows/python-tests.yml",
            "tools/ci_change_classifier.py",
            "tools/UnreviewedBootstrap.ps1",
            "unexpected/new-boundary.conf",
        ):
            with self.subTest(path=path):
                self.assertScopes([path], "full")

    def test_path_normalization_deduplicates_without_scope_escape(self):
        self.assertScopes(
            [
                ".\\apps\\web_portal\\main.py",
                "./apps/web_portal/main.py",
                "apps/web_portal/main.py",
            ],
            "web_portal",
        )
        for path in (
            "",
            "../README.md",
            "/README.md",
            "C:\\repo\\README.md",
            "docs/a\nfull=true",
        ):
            with self.subTest(path=path):
                self.assertScopes([path], "full")
        self.assertScopes([], "full")

    def test_git_diff_is_nul_safe_and_fail_conservative(self):
        base = "a" * 40
        head = "b" * 40
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"docs/README.md\0docs/name\nfull=true.md\0"
        )
        with patch(
            "tools.ci_change_classifier.subprocess.run", return_value=completed
        ) as run:
            classification, observed_base, observed_head = classify_git_diff(
                base, head, merge_base=True
            )
        self.assertTrue(classification.full)
        self.assertEqual((observed_base, observed_head), (base, head))
        self.assertIn("--merge-base", run.call_args.args[0])

        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout=b"")
        with patch("tools.ci_change_classifier.subprocess.run", return_value=failed):
            classification, observed_base, observed_head = classify_git_diff(base, head)
        self.assertTrue(classification.full)
        self.assertEqual((observed_base, observed_head), ("", ""))

        classification, observed_base, observed_head = classify_git_diff("0" * 40, head)
        self.assertTrue(classification.full)
        self.assertEqual((observed_base, observed_head), ("", ""))

    def test_cli_emits_only_fixed_github_output_keys(self):
        completed = subprocess.run(
            [sys.executable, "-m", "tools.ci_change_classifier", "classify"],
            cwd=Path(__file__).resolve().parents[2],
            input=b"docs/name\nfull=true.md\0",
            check=True,
            stdout=subprocess.PIPE,
        )
        lines = completed.stdout.decode("utf-8").splitlines()
        self.assertEqual(len(lines), len(OUTPUTS) + 2)
        self.assertEqual(
            {line.partition("=")[0] for line in lines},
            {*OUTPUTS, "base_sha", "head_sha"},
        )
        self.assertIn("full=true", lines)


class FinalGateTests(unittest.TestCase):
    def test_docs_only_allows_only_legitimate_skips(self):
        self.assertEqual(final_gate_failures(outputs(docs_only=True), results()), [])
        self.assertTrue(
            final_gate_failures(outputs(docs_only=True), results(portal_data="failure"))
        )

    def test_quick_only_allows_only_legitimate_skips(self):
        self.assertEqual(final_gate_failures(outputs(quick_only=True), results()), [])
        self.assertTrue(
            final_gate_failures(outputs(quick_only=True), results(flutter="success"))
        )

    def test_selected_jobs_must_succeed(self):
        selected = outputs(web_portal=True, line_webhook=True)
        successful = results(web_portal="success", line_webhook="success")
        self.assertEqual(final_gate_failures(selected, successful), [])
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(result=result):
                changed = dict(successful, web_portal=result)
                self.assertTrue(final_gate_failures(selected, changed))

    def test_full_requires_every_scope(self):
        successful = results(**{scope: "success" for scope in SCOPES})
        self.assertEqual(final_gate_failures(outputs(full=True), successful), [])
        self.assertTrue(
            final_gate_failures(
                outputs(full=True), dict(successful, portal_data="cancelled")
            )
        )

    def test_flutter_is_required_when_selected_or_full(self):
        selected = outputs(flutter=True)
        self.assertEqual(final_gate_failures(selected, results(flutter="success")), [])
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(selected_result=result):
                self.assertTrue(final_gate_failures(selected, results(flutter=result)))

        full_results = results(**{scope: "success" for scope in SCOPES})
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(full_result=result):
                self.assertTrue(
                    final_gate_failures(
                        outputs(full=True), dict(full_results, flutter=result)
                    )
                )

    def test_non_flutter_scope_legitimately_skips_flutter(self):
        self.assertEqual(
            final_gate_failures(
                outputs(web_portal=True),
                results(web_portal="success", flutter="skipped"),
            ),
            [],
        )

    def test_invalid_or_empty_classification_fails(self):
        self.assertTrue(final_gate_failures({}, results()))
        self.assertTrue(final_gate_failures(outputs(), results()))
        self.assertTrue(
            final_gate_failures(outputs(full=True, web_portal=True), results())
        )
        self.assertTrue(
            final_gate_failures(outputs(docs_only=True, web_portal=True), results())
        )
        self.assertTrue(
            final_gate_failures(outputs(quick_only=True, web_portal=True), results())
        )
        self.assertTrue(
            final_gate_failures(outputs(docs_only=True), results(classify="failure"))
        )
