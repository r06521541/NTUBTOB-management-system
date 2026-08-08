import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shared_lib.shared_module.portal_data.runtime import ROLLOUT_SERVICES
from tools import phase_c_transition_controller as controller

SOURCE_COMMIT = "a" * 40
FINGERPRINT = "b" * 64


class PhaseCTransitionControllerTests(unittest.TestCase):
    def plan(self, current, target, **overrides):
        values = {
            "source_commit": SOURCE_COMMIT,
            "expected_source_commit": SOURCE_COMMIT,
            "artifact_fingerprint": FINGERPRINT,
            "expected_artifact_fingerprint": FINGERPRINT,
        }
        values.update(overrides)
        return controller.plan_transition(current, target, **values)

    def test_forward_and_rollback_follow_one_canonical_flag_at_a_time(self):
        path = controller.canonical_transition_path()
        forward = self.plan(path[0], path[-2])
        rollback = self.plan(path[-2], path[0])

        self.assertEqual(forward.direction, "forward")
        self.assertEqual(rollback.direction, "rollback")
        self.assertEqual(len(forward.steps), len(path) - 2)
        self.assertEqual(
            tuple((step.service, step.flag, step.value) for step in rollback.steps),
            tuple(
                (step.service, step.flag, not step.value)
                for step in reversed(forward.steps)
            ),
        )
        self.assertEqual(forward.next_step.flag, "freeze")
        self.assertEqual(forward.next_step.service, "web_portal")
        self.assertTrue(forward.next_step.value)
        self.assertEqual(rollback.next_step.flag, "freeze")
        self.assertEqual(rollback.next_step.service, "notify_cron")
        self.assertTrue(rollback.next_step.value)

    def test_canonical_path_allows_mixed_phase_only_while_all_frozen(self):
        path = controller.canonical_transition_path()
        mixed = [
            vector
            for vector in path
            if 0 < sum(vector.phase_flags().values()) < len(ROLLOUT_SERVICES)
        ]
        self.assertTrue(mixed)
        for vector in mixed:
            self.assertTrue(all(vector.freeze_flags().values()))

        unsafe = controller.rollout_vector(
            {
                "web_portal": "true",
                "line_webhook": "false",
                "notify_cron": "false",
            },
            {
                "web_portal": "true",
                "line_webhook": "true",
                "notify_cron": "false",
            },
            "false",
        )
        with self.assertRaisesRegex(
            controller.TransitionPlanError, "canonical unambiguous"
        ):
            self.plan(path[0], unsafe)

    def test_missing_unknown_and_ambiguous_values_fail_closed(self):
        all_false = {service: "false" for service in ROLLOUT_SERVICES}
        invalid = (
            ({"web_portal": "false"}, all_false, "every exact rollout service"),
            ({**all_false, "unknown": "false"}, all_false, "every exact"),
            ({**all_false, "web_portal": "False"}, all_false, "exactly true"),
        )
        for phase_c, freeze, message in invalid:
            with self.subTest(message=message), self.assertRaisesRegex(
                controller.TransitionPlanError, message
            ):
                controller.rollout_vector(phase_c, freeze, "false")

    def test_stale_commit_or_artifact_fingerprint_stops(self):
        path = controller.canonical_transition_path()
        cases = (
            (
                {"expected_source_commit": "c" * 40},
                "does not match the expected commit",
            ),
            (
                {"expected_artifact_fingerprint": "d" * 64},
                "does not match the expected fingerprint",
            ),
            ({"source_commit": "not-a-commit"}, "invalid format"),
        )
        for overrides, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                controller.TransitionPlanError, message
            ):
                self.plan(path[0], path[-2], **overrides)

    def test_error_messages_do_not_echo_untrusted_values(self):
        sentinel = "credential-like-sentinel"
        all_false = {service: "false" for service in ROLLOUT_SERVICES}
        with self.assertRaises(controller.TransitionPlanError) as raised:
            controller.rollout_vector(
                {**all_false, "web_portal": sentinel}, all_false, "false"
            )
        self.assertNotIn(sentinel, str(raised.exception))

    def test_maintenance_is_only_a_final_separate_step(self):
        path = controller.canonical_transition_path()
        plan = self.plan(path[-2], path[-1])
        self.assertEqual(plan.target_mode, "maintenance_unfrozen")
        self.assertEqual(plan.next_step.flag, "identity_maintenance")
        self.assertEqual(plan.next_step.service, "web_portal")
        self.assertTrue(plan.next_step.value)

    def test_json_cli_is_offline_bounded_and_redacts_invalid_input(self):
        arguments = []
        for prefix in ("current", "target"):
            for service in ROLLOUT_SERVICES:
                option = service.replace("_", "-")
                arguments.extend([f"--{prefix}-{option}-phase-c", "false"])
                arguments.extend([f"--{prefix}-{option}-freeze", "false"])
            arguments.extend([f"--{prefix}-identity-maintenance", "false"])
        arguments.extend(
            [
                "--expected-source-commit",
                SOURCE_COMMIT,
                "--expected-artifact-fingerprint",
                FINGERPRINT,
                "--output",
                "json",
            ]
        )
        output = io.StringIO()
        with patch.object(
            controller.preflight, "verify_environment_examples"
        ), patch.object(controller.preflight, "verify_build_contexts"), patch.object(
            controller.preflight, "verify_service_requirements"
        ), patch.object(
            controller.preflight,
            "verify_artifacts",
            return_value=(FINGERPRINT, ()),
        ), patch.object(
            controller, "repository_head_commit", return_value=SOURCE_COMMIT
        ), redirect_stdout(
            output
        ):
            result = controller.main(arguments)

        self.assertEqual(result, 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "valid")
        self.assertEqual(document["direction"], "complete")
        self.assertIsNone(document["next_step"])

        sentinel = "credential-like-sentinel"
        invalid_output = io.StringIO()
        invalid_arguments = list(arguments)
        invalid_arguments[invalid_arguments.index("--expected-source-commit") + 1] = (
            sentinel
        )
        with patch.object(
            controller.preflight, "verify_environment_examples"
        ), patch.object(controller.preflight, "verify_build_contexts"), patch.object(
            controller.preflight, "verify_service_requirements"
        ), patch.object(
            controller.preflight,
            "verify_artifacts",
            return_value=(FINGERPRINT, ()),
        ), patch.object(
            controller, "repository_head_commit", return_value=SOURCE_COMMIT
        ), redirect_stdout(
            invalid_output
        ):
            result = controller.main(invalid_arguments)
        self.assertEqual(result, 2)
        self.assertNotIn(sentinel, invalid_output.getvalue())

    def test_repository_head_is_read_without_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = root / ".git"
            reference = git / "refs" / "heads" / "task"
            reference.parent.mkdir(parents=True)
            (git / "HEAD").write_text("ref: refs/heads/task\n", encoding="utf-8")
            reference.write_text(SOURCE_COMMIT + "\n", encoding="utf-8")
            self.assertEqual(controller.repository_head_commit(root), SOURCE_COMMIT)


if __name__ == "__main__":
    unittest.main()
