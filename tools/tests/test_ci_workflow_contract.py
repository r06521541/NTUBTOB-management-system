from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "python-tests.yml"
FLUTTER_WORKFLOW = ROOT / ".github" / "workflows" / "flutter-tests.yml"


def job_block(source: str, job: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [a-z][a-z0-9_]*:\n|\Z)", source
    )
    if match is None:
        raise AssertionError(f"missing workflow job: {job}")
    return match.group(1)


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.flutter_source = FLUTTER_WORKFLOW.read_text(encoding="utf-8")

    def test_triggers_concurrency_and_actions_are_fixed(self):
        self.assertRegex(self.source, r"(?m)^  pull_request:$")
        self.assertRegex(self.source, r"(?m)^  push:$")
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertIn("branches:\n      - main", self.source)
        self.assertIn(
            "github.workflow }}-${{ github.event.pull_request.number || github.ref",
            self.source,
        )
        self.assertIn("cancel-in-progress: true", self.source)
        uses = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", self.source)
        self.assertTrue(uses)
        self.assertTrue(
            all(
                action == "./.github/workflows/flutter-tests.yml"
                or re.fullmatch(
                    r"actions/(?:checkout|setup-python)@[0-9a-f]{40}", action
                )
                for action in uses
            )
        )

    def test_classifier_uses_reliable_event_ranges_and_full_fallback(self):
        block = job_block(self.source, "classify")
        self.assertIn("fetch-depth: 0", block)
        self.assertIn(
            "github.event.pull_request.base.sha || github.event.before", block
        )
        self.assertIn("github.event.pull_request.head.sha || github.sha", block)
        self.assertIn('--git-diff "$BASE_SHA" "$HEAD_SHA"', block)
        self.assertIn('--git-diff "$BASE_SHA" "$HEAD_SHA" --merge-base', block)
        self.assertGreaterEqual(block.count("classify --full"), 2)
        self.assertNotIn("pip install", block)
        self.assertNotIn("services:", block)

    def test_quick_gate_has_no_database_or_application_install(self):
        block = job_block(self.source, "quick")
        self.assertIn("test_ci_*.py", block)
        self.assertIn("git diff --check", block)
        self.assertNotIn("pip install", block)
        self.assertNotIn("postgres", block.lower())
        self.assertNotIn("services:", block)

    def test_database_job_retains_dual_version_full_contract(self):
        block = job_block(self.source, "portal_data")
        self.assertIn("needs.classify.outputs.full == 'true'", block)
        self.assertIn("needs.classify.outputs.portal_data == 'true'", block)
        self.assertIn("postgres:15.8-alpine", block)
        self.assertIn("postgres:16.4-alpine", block)
        self.assertIn("requirements-migrations.txt", block)
        self.assertIn("tools/ci_change_classifier.py", block)
        self.assertIn("tools/tests/test_ci_workflow_contract.py", block)
        self.assertIn("portal_data_phase_c_migration verify", block)
        self.assertIn("portal_data_phase_c_evidence verify", block)
        self.assertIn("portal_data_phase_c_readiness verify", block)
        self.assertIn("unittest discover -s tests/portal_data -v", block)

    def test_each_service_job_is_scope_gated(self):
        commands = {
            "web_portal": "apps/web_portal/tests",
            "game_broadcast": "apps/game_broadcast_service/tests",
            "notify_cron": "apps/notify_cronjob_service/tests",
            "deployment_tools": 'tools/tests -p "test_deploy_*.py"',
            "update_schedule": "functions/update_game_schedule/tests",
            "line_webhook": "functions/line_webhook_handler/tests",
        }
        for job, command in commands.items():
            with self.subTest(job=job):
                block = job_block(self.source, job)
                self.assertIn("needs.classify.outputs.full == 'true'", block)
                self.assertIn(f"needs.classify.outputs.{job} == 'true'", block)
                self.assertIn(command, block)
                self.assertNotIn("services:", block)

    def test_flutter_is_reusable_only_exact_and_fake(self):
        self.assertRegex(self.flutter_source, r"(?m)^  workflow_call:$")
        self.assertNotRegex(self.flutter_source, r"(?m)^  (?:push|pull_request):$")
        self.assertIn('flutter-version: "3.47.0"', self.flutter_source)
        self.assertIn("channel: stable", self.flutter_source)
        self.assertIn("permissions:\n  contents: read", self.flutter_source)
        self.assertIn("flutter pub get", self.flutter_source)
        self.assertIn(
            "dart format --output=none --set-exit-if-changed .",
            self.flutter_source,
        )
        self.assertIn("flutter analyze", self.flutter_source)
        self.assertIn("flutter test", self.flutter_source)
        self.assertIn("--dart-define=APP_FLAVOR=development", self.flutter_source)
        self.assertIn("--dart-define=CLIENT_MODE=fake", self.flutter_source)
        uses = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", self.flutter_source)
        self.assertEqual(len(uses), 2)
        self.assertTrue(
            all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action) for action in uses)
        )

    def test_python_workflow_calls_flutter_conditionally(self):
        block = job_block(self.source, "flutter")
        self.assertIn("needs: classify", block)
        self.assertIn("needs.classify.outputs.full == 'true'", block)
        self.assertIn("needs.classify.outputs.flutter == 'true'", block)
        self.assertIn("uses: ./.github/workflows/flutter-tests.yml", block)

    def test_final_gate_is_stable_always_runs_and_observes_every_child(self):
        block = job_block(self.source, "final")
        self.assertIn("name: CI final gate", block)
        self.assertIn("if: always()", block)
        for job in (
            "classify",
            "quick",
            "flutter",
            "portal_data",
            "web_portal",
            "game_broadcast",
            "notify_cron",
            "deployment_tools",
            "update_schedule",
            "line_webhook",
        ):
            self.assertIn(f"- {job}", block)
        self.assertIn("require_success classify", block)
        self.assertIn("classification selected no execution path", block)
        self.assertIn("unselected job was not skipped", block)
        self.assertNotIn("uses:", block)

    def test_final_gate_script_accepts_skips_and_rejects_required_cancel(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            git_bash = (
                Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                / "Git/bin/bash.exe"
            )
            if git_bash.is_file():
                bash = str(git_bash)
        if bash is None:
            self.skipTest("bash is required for the workflow aggregate contract")

        block = job_block(self.source, "final")
        marker = "        run: |\n"
        script = "\n".join(
            line[10:] if line.startswith("          ") else line
            for line in block.partition(marker)[2].splitlines()
        )
        base_environment = dict(os.environ)
        for scope in (
            "DOCS_ONLY",
            "FLUTTER",
            "PORTAL_DATA",
            "WEB_PORTAL",
            "GAME_BROADCAST",
            "NOTIFY_CRON",
            "DEPLOYMENT_TOOLS",
            "UPDATE_SCHEDULE",
            "LINE_WEBHOOK",
            "FULL",
        ):
            base_environment[f"CI_SCOPE_{scope}"] = "false"
        for job in (
            "PORTAL_DATA",
            "WEB_PORTAL",
            "GAME_BROADCAST",
            "NOTIFY_CRON",
            "DEPLOYMENT_TOOLS",
            "UPDATE_SCHEDULE",
            "LINE_WEBHOOK",
        ):
            base_environment[f"CI_RESULT_{job}"] = "skipped"
        base_environment.update(CI_RESULT_CLASSIFY="success", CI_RESULT_QUICK="success")
        base_environment["CI_RESULT_FLUTTER"] = "skipped"

        def run_script(environment):
            return subprocess.run(
                [bash, "-c", script],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        docs_environment = dict(base_environment, CI_SCOPE_DOCS_ONLY="true")
        self.assertEqual(run_script(docs_environment).returncode, 0)

        full_environment = dict(base_environment, CI_SCOPE_FULL="true")
        for job in (
            "PORTAL_DATA",
            "WEB_PORTAL",
            "GAME_BROADCAST",
            "NOTIFY_CRON",
            "DEPLOYMENT_TOOLS",
            "UPDATE_SCHEDULE",
            "LINE_WEBHOOK",
            "FLUTTER",
        ):
            full_environment[f"CI_RESULT_{job}"] = "success"
        self.assertEqual(run_script(full_environment).returncode, 0)
        full_environment["CI_RESULT_PORTAL_DATA"] = "cancelled"
        self.assertNotEqual(run_script(full_environment).returncode, 0)

        flutter_environment = dict(
            base_environment,
            CI_SCOPE_FLUTTER="true",
            CI_RESULT_FLUTTER="success",
        )
        self.assertEqual(run_script(flutter_environment).returncode, 0)
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(result=result):
                flutter_environment["CI_RESULT_FLUTTER"] = result
                self.assertNotEqual(run_script(flutter_environment).returncode, 0)

    def test_no_unreviewed_path_filter_action_is_used(self):
        self.assertNotRegex(self.source.lower(), r"paths?[-_/]filter")


if __name__ == "__main__":
    unittest.main()
