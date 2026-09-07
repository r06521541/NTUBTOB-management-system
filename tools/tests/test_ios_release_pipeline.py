from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest import mock

from tools import ios_release_pipeline as pipeline

SHA = "a" * 40


class IOSReleasePipelineTests(unittest.TestCase):
    def run_scenario(self, scenario: str = "success") -> dict[str, object]:
        with (
            mock.patch("subprocess.Popen", side_effect=AssertionError("no process")),
            mock.patch("socket.socket", side_effect=AssertionError("no network")),
            mock.patch("builtins.open", side_effect=AssertionError("no files")),
        ):
            return pipeline.rehearse(
                expected_commit=SHA, checkout_commit=SHA, scenario=scenario
            )

    def test_success_never_claims_live_evidence_or_authority(self) -> None:
        result = self.run_scenario()
        self.assertEqual(result["classification"], "REHEARSAL_COMPLETE")
        self.assertEqual(result["evidence_scope"], "fictional_rehearsal")
        self.assertEqual(
            result["simulated_trace"], ["preflight", *pipeline.STAGES, "cleanup"]
        )
        self.assertEqual(result["simulated_upload_attempts"], 1)
        for field in (
            "external_mutation_count",
            "signed_artifact_created",
            "upload_authorized",
            "release_authorized",
            "provider_runtime_verified",
            "real_device_verified",
            "retry_allowed",
        ):
            self.assertFalse(result[field])

    def test_contract_mismatch_stops_before_material_staging(self) -> None:
        for expected, checkout, scenario in (
            (SHA, "b" * 40, "success"),
            ("short", SHA, "success"),
            ("0" * 40, "0" * 40, "success"),
            (SHA, SHA, "live"),
            (SHA, "A" * 40, "success"),
            ("fake-private-value", SHA, "success"),
        ):
            with self.subTest(expected=expected, scenario=scenario):
                result = pipeline.rehearse(
                    expected_commit=expected,
                    checkout_commit=checkout,
                    scenario=scenario,
                )
                self.assertEqual(result["classification"], "STOP")
                self.assertEqual(result["simulated_trace"], [])
                self.assertEqual(result["simulated_cleanup"], "not_needed")
                self.assertNotIn("fake-private-value", json.dumps(result))

    def test_failures_cleanup_and_never_reach_later_stages(self) -> None:
        for scenario, stage in (
            ("stage_failure", "stage_material"),
            ("build_failure", "build"),
            ("inspection_failure", "inspect"),
            ("upload_rejected", "upload"),
            ("upload_uncertain", "upload"),
            ("processing_pending", "processing"),
        ):
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                self.assertEqual(result["classification"], "STOP")
                self.assertEqual(result["simulated_cleanup"], "completed")
                self.assertEqual(
                    result["simulated_trace"],
                    [
                        "preflight",
                        *pipeline.STAGES[: pipeline.STAGES.index(stage) + 1],
                        "cleanup",
                    ],
                )
                self.assertLessEqual(result["simulated_upload_attempts"], 1)
                self.assertFalse(result["retry_allowed"])

    def test_uncertain_and_processing_pending_require_read_only_reconcile(self) -> None:
        for scenario in ("upload_uncertain", "processing_pending"):
            result = self.run_scenario(scenario)
            self.assertEqual(result["next_action"], "read_only_reconcile")
            self.assertEqual(result["simulated_upload_attempts"], 1)

    def test_cleanup_failure_overrides_simulated_success(self) -> None:
        result = self.run_scenario("cleanup_failure")
        self.assertEqual(result["classification"], "STOP")
        self.assertEqual(result["reason"], "CLEANUP_FAILED")
        self.assertEqual(result["simulated_cleanup"], "failed")

    def test_cli_only_emits_fictional_evidence(self) -> None:
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            self.assertEqual(
                pipeline.main(
                    ["rehearse", "--expected-commit", SHA, "--checkout-commit", SHA]
                ),
                0,
            )
        self.assertEqual(
            json.loads(output.getvalue())["evidence_scope"], "fictional_rehearsal"
        )

    def test_live_action_is_not_implemented(self) -> None:
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            pipeline.main(
                ["upload", "--expected-commit", SHA, "--checkout-commit", SHA]
            )

    def test_invalid_arguments_do_not_echo_values(self) -> None:
        output = io.StringIO()
        with mock.patch("sys.stderr", output), self.assertRaises(SystemExit):
            pipeline.main(["fictional-private-value"])
        self.assertEqual(output.getvalue(), "ERROR: rehearsal arguments are invalid\n")

    def test_hosted_rehearsal_has_no_secret_or_upload_step(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / ".github/workflows/flutter-tests.yml"
        ).read_text(encoding="utf-8")
        marker = "      - name: Rehearse iOS release lifecycle without credentials"
        self.assertIn(marker, source)
        step = source.split(marker, 1)[1].split("      - name:", 1)[0]
        self.assertIn("tools.ios_release_pipeline rehearse", step)
        self.assertIn("git rev-parse HEAD", step)
        self.assertIn("github.sha", step)
        for forbidden in (
            "secrets.",
            "upload-artifact",
            "keychain",
            "--execute",
            "security import",
        ):
            self.assertNotIn(forbidden, step)

    def test_hosted_ios_rehydrates_pinned_engine_before_compiling(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / ".github/workflows/flutter-tests.yml"
        ).read_text(encoding="utf-8")
        ios = source.split("    runs-on: macos-latest", 1)[1]
        self.assertIn("flutter precache --ios --force", ios)
        self.assertIn("ios-release/Flutter.xcframework/Info.plist", ios)
        self.assertLess(
            ios.index("flutter precache --ios --force"), ios.index("flutter build ios")
        )


if __name__ == "__main__":
    unittest.main()
