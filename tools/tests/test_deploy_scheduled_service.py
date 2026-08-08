import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import deploy_scheduled_service as deploy


SHA = "a" * 40
APPROVED_DIGEST = "sha256:" + "b" * 64
FULL_REVISION_DIGEST = (
    "asia-east1-docker.pkg.dev/fake-project/fake-repo/fake-image@"
    + APPROVED_DIGEST
)
ROLLBACK_REVISION = "game-broadcast-service-00030-pgg"
BASELINE_REVISION = "game-broadcast-service-00031-s65"
NEW_REVISION = "game-broadcast-service-00099-abc"


class CommandResolutionTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows batch execution contract")
    def test_run_command_executes_resolved_windows_batch_file_without_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            batch_file = Path(directory) / "fixture-gcloud.cmd"
            batch_file.write_text("@echo fixture-gcloud-ok\r\n", encoding="utf-8")
            with patch(
                "tools.deploy_scheduled_service.shutil.which",
                return_value=str(batch_file),
            ):
                result = deploy.run_command(["gcloud"], Path(directory))

        self.assertEqual(result.stdout.strip(), "fixture-gcloud-ok")

    @patch("tools.deploy_scheduled_service.subprocess.run")
    @patch("tools.deploy_scheduled_service.shutil.which")
    def test_run_command_uses_resolved_windows_batch_file(self, which, run):
        which.return_value = r"C:\Program Files\Google\Cloud SDK\bin\gcloud.cmd"
        run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        deploy.run_command(["gcloud", "version"], Path("fixture"))

        run.assert_called_once_with(
            [r"C:\Program Files\Google\Cloud SDK\bin\gcloud.cmd", "version"],
            cwd=Path("fixture"),
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )

    @patch("tools.deploy_scheduled_service.subprocess.run")
    @patch("tools.deploy_scheduled_service.shutil.which")
    def test_run_command_uses_resolved_posix_executable(self, which, run):
        which.return_value = "/usr/bin/gcloud"
        run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        deploy.run_command(["gcloud", "version"], Path("fixture"))

        self.assertEqual(run.call_args.args[0], ["/usr/bin/gcloud", "version"])
        self.assertFalse(run.call_args.kwargs["shell"])

    @patch("tools.deploy_scheduled_service.shutil.which", return_value=None)
    def test_run_command_fails_closed_when_executable_is_missing(self, _which):
        with self.assertRaisesRegex(deploy.DeploymentError, "unavailable: gcloud"):
            deploy.run_command(["gcloud", "version"], Path("fixture"))


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        dirty=False,
        build_status="SUCCESS",
        revision_ready=True,
        no_op=False,
        revision_digest=FULL_REVISION_DIGEST,
        traffic=True,
        traffic_command_failure=False,
        interrupt_traffic=False,
    ):
        self.root = root
        self.dirty = dirty
        self.build_status = build_status
        self.revision_ready = revision_ready
        self.no_op = no_op
        self.revision_digest = revision_digest
        self.traffic = traffic
        self.traffic_command_failure = traffic_command_failure
        self.interrupt_traffic = interrupt_traffic
        self.commands = []
        self.describe_calls = 0

    def __call__(self, arguments, cwd):
        arguments = list(arguments)
        self.commands.append(arguments)
        stdout = ""
        if arguments[:2] == ["git", "status"]:
            stdout = " M user-file\n" if self.dirty else ""
        elif arguments[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = SHA + "\n"
        elif "setup.py" in arguments:
            artifact = self.root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"fake sdist")
        elif arguments[:3] == ["gcloud", "builds", "submit"]:
            stdout = json.dumps({"id": "fake-build", "status": self.build_status})
        elif arguments[:5] == [
            "gcloud", "artifacts", "docker", "images", "describe",
        ]:
            stdout = APPROVED_DIGEST + "\n"
        elif arguments[:4] == ["gcloud", "run", "services", "describe"]:
            self.describe_calls += 1
            if self.describe_calls == 1 or self.no_op:
                revision = BASELINE_REVISION
            else:
                revision = NEW_REVISION
            latest_ready = (
                NEW_REVISION
                if self.describe_calls >= 3 and self.traffic
                else BASELINE_REVISION
            )
            status = {
                "latestCreatedRevisionName": revision,
                "latestReadyRevisionName": latest_ready,
                "traffic": (
                    [{"revisionName": revision, "percent": 100}]
                    if self.describe_calls >= 3 and self.traffic
                    else []
                ),
            }
            stdout = json.dumps({"status": status})
        elif arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
            stdout = json.dumps(
                {
                    "status": {
                        "imageDigest": self.revision_digest,
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "True" if self.revision_ready else "False",
                            }
                        ],
                    }
                }
            )
        elif "update-traffic" in arguments:
            destination = arguments[arguments.index("--to-revisions") + 1]
            if self.interrupt_traffic and destination.startswith(NEW_REVISION):
                raise KeyboardInterrupt()
            if self.traffic_command_failure and destination.startswith(NEW_REVISION):
                raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout=stdout, stderr="")


class DeploymentWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for service in deploy.SERVICES.values():
            service_root = self.root / "apps" / service.directory
            service_root.mkdir(parents=True)
            (service_root / "cloudbuild.yaml").write_text(
                "steps: []\n", encoding="utf-8"
            )
            env_root = self.root / "envs" / service.directory
            env_root.mkdir(parents=True)
            (env_root / ".env.yaml").write_text(
                "SAFE: visible\n"
                "PORTAL_DATA_PHASE_C_ENABLED: false\n"
                "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED: false\n"
                "  CHANNEL_ACCESS_TOKEN: fixture-access\n"
                "\tCHANNEL_SECRET: fixture-secret\n WEATHER_API_KEY: fixture-weather\n"
                "  DSN_PASSWORD: fixture-password\n",
                encoding="utf-8",
            )

    def tearDown(self):
        self.temp.cleanup()

    def temporary_env(self):
        return self.root / "apps" / "game_broadcast_service" / ".env.yaml"

    @staticmethod
    def traffic_commands(runner):
        return [
            command for command in runner.commands if "update-traffic" in command
        ]

    def execute(self, runner):
        return deploy.execute_deployment(
            self.root,
            "game-broadcast-service",
            SHA,
            ROLLBACK_REVISION,
            runner,
            False,
        )

    def assert_only_exact_rollback(self, runner):
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 1)
        self.assertEqual(
            traffic[0][traffic[0].index("--to-revisions") + 1],
            f"{ROLLBACK_REVISION}=100",
        )

    def test_default_preflight_runs_only_git_read_commands(self):
        runner = FakeRunner(self.root)
        deploy.preflight(
            self.root, "game-broadcast-service", None, None, runner, check_tools=False
        )
        self.assertEqual(
            runner.commands,
            [["git", "status", "--porcelain"], ["git", "rev-parse", "HEAD"]],
        )

    def test_execute_requires_full_sha_and_matching_revision(self):
        runner = FakeRunner(self.root)
        with self.assertRaisesRegex(deploy.DeploymentError, "40-character"):
            deploy.preflight(
                self.root, "game-broadcast-service", "abc", None, runner, False
            )
        with self.assertRaisesRegex(deploy.DeploymentError, "target service"):
            deploy.preflight(
                self.root,
                "game-broadcast-service",
                SHA,
                "notify-cronjob-service-00010-abc",
                runner,
                False,
            )

    def test_dirty_source_and_existing_temporary_env_fail_closed(self):
        with self.assertRaisesRegex(deploy.DeploymentError, "clean"):
            deploy.preflight(
                self.root,
                "game-broadcast-service",
                None,
                None,
                FakeRunner(self.root, dirty=True),
                False,
            )
        temporary = self.temporary_env()
        temporary.write_text("owner: file\n", encoding="utf-8")
        with self.assertRaisesRegex(deploy.DeploymentError, "overwrite"):
            deploy.preflight(
                self.root,
                "game-broadcast-service",
                None,
                None,
                FakeRunner(self.root),
                False,
            )
        self.assertEqual(temporary.read_text(encoding="utf-8"), "owner: file\n")

    def test_filter_removes_indented_service_secrets_without_leaking_values(self):
        source = self.root / "envs" / "game_broadcast_service" / ".env.yaml"
        destination = self.root / "filtered.yaml"
        deploy.write_filtered_env(
            source,
            destination,
            deploy.SERVICES["game-broadcast-service"].secret_env_keys,
        )
        output = destination.read_text(encoding="utf-8")
        self.assertEqual(
            output,
            "SAFE: visible\n"
            "PORTAL_DATA_PHASE_C_ENABLED: false\n"
            "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED: false\n",
        )
        for fixture_value in (
            "fixture-access",
            "fixture-secret",
            "fixture-weather",
            "fixture-password",
        ):
            self.assertNotIn(fixture_value, output)

    def test_clean_checkout_without_dist_builds_artifact_and_deploys(self):
        self.assertFalse((self.root / "shared_lib" / "dist").exists())
        runner = FakeRunner(self.root)
        result = self.execute(runner)
        self.assertTrue(
            (self.root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz").is_file()
        )
        self.assertEqual(result["image_tag"], SHA)
        self.assertEqual(result["image_digest"], APPROVED_DIGEST)
        build = next(
            command
            for command in runner.commands
            if command[:3] == ["gcloud", "builds", "submit"]
        )
        self.assertIn(f"_IMAGE_TAG={SHA}", build[build.index("--substitutions") + 1])
        self.assertEqual(build[build.index("--region") + 1], deploy.REGION)
        self.assertIn("--suppress-logs", build)
        self.assertIn("--format=json", build)
        artifact_lookup = next(
            command
            for command in runner.commands
            if command[:3] == ["gcloud", "artifacts", "docker"]
        )
        self.assertTrue(
            any(argument.endswith(f":{SHA}") for argument in artifact_lookup)
        )
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 1)
        self.assertIn(f"{NEW_REVISION}=100", traffic[0])
        self.assertFalse(self.temporary_env().exists())
        command_text = repr(runner.commands)
        self.assertNotIn("fixture-access", command_text)
        self.assertNotIn("fixture-secret", command_text)

    def test_stale_latest_revision_no_op_never_receives_traffic(self):
        runner = FakeRunner(self.root, no_op=True)
        with self.assertRaisesRegex(deploy.DeploymentError, "new revision"):
            self.execute(runner)
        self.assertEqual(self.traffic_commands(runner), [])
        self.assertNotIn(f"{BASELINE_REVISION}=100", repr(runner.commands))
        self.assertFalse(self.temporary_env().exists())

    def test_digest_mismatch_stops_before_new_revision_traffic(self):
        runner = FakeRunner(
            self.root,
            revision_digest="registry.example/fake-image@sha256:" + "c" * 64,
        )
        with self.assertRaisesRegex(deploy.DeploymentError, "approved image tag"):
            self.execute(runner)
        self.assertEqual(self.traffic_commands(runner), [])
        self.assertNotIn(f"{NEW_REVISION}=100", repr(runner.commands))
        self.assertFalse(self.temporary_env().exists())

    def test_not_ready_revision_rolls_back_and_cleans_environment(self):
        runner = FakeRunner(self.root, revision_ready=False)
        with self.assertRaisesRegex(deploy.DeploymentError, "not ready"):
            self.execute(runner)
        self.assertEqual(self.traffic_commands(runner), [])
        self.assertFalse(self.temporary_env().exists())

    def test_build_failure_cleans_environment_without_traffic_command(self):
        runner = FakeRunner(self.root, build_status="FAILURE")
        with self.assertRaisesRegex(deploy.DeploymentError, "SUCCESS"):
            self.execute(runner)
        self.assertEqual(self.traffic_commands(runner), [])
        self.assertFalse(self.temporary_env().exists())

    def test_traffic_command_failure_rolls_back_exact_revision_and_cleans(self):
        runner = FakeRunner(self.root, traffic_command_failure=True)
        with self.assertRaisesRegex(deploy.DeploymentError, "Command failed") as caught:
            self.execute(runner)
        self.assertNotIn("fixture-access", str(caught.exception))
        self.assertNotIn("fixture-secret", str(caught.exception))
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 2)
        self.assertEqual(
            traffic[-1][traffic[-1].index("--to-revisions") + 1],
            f"{ROLLBACK_REVISION}=100",
        )
        self.assertFalse(self.temporary_env().exists())

    def test_interrupted_traffic_promotion_rolls_back_and_cleans_environment(self):
        runner = FakeRunner(self.root, interrupt_traffic=True)
        with self.assertRaises(KeyboardInterrupt):
            self.execute(runner)
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 2)
        self.assertEqual(
            traffic[-1][traffic[-1].index("--to-revisions") + 1],
            f"{ROLLBACK_REVISION}=100",
        )
        self.assertFalse(self.temporary_env().exists())

    def test_traffic_verification_failure_rolls_back_exact_revision_and_cleans(self):
        runner = FakeRunner(self.root, traffic=False)
        with self.assertRaisesRegex(
            deploy.DeploymentError, "latest ready revision|100% traffic"
        ):
            self.execute(runner)
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 2)
        self.assertEqual(
            traffic[-1][traffic[-1].index("--to-revisions") + 1],
            f"{ROLLBACK_REVISION}=100",
        )
        self.assertFalse(self.temporary_env().exists())

    def test_resume_verify_only_promotes_exact_successful_candidate(self):
        commands = []

        def runner(arguments, _cwd):
            commands.append(list(arguments))
            if arguments[:2] == ["git", "status"]:
                output = ""
            elif arguments[:3] == ["git", "rev-parse", "HEAD"]:
                output = SHA
            elif arguments[:3] == ["gcloud", "builds", "describe"]:
                output = json.dumps({"status": "SUCCESS", "substitutions": {"_SERVICE_NAME": "game-broadcast-service", "_IMAGE_TAG": SHA}})
            elif arguments[:3] == ["gcloud", "artifacts", "docker"]:
                output = APPROVED_DIGEST
            elif arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
                output = json.dumps({"status": {"imageDigest": FULL_REVISION_DIGEST, "conditions": [{"type": "Ready", "status": "True"}]}})
            elif arguments[:4] == ["gcloud", "run", "services", "describe"]:
                output = json.dumps({"status": {"latestCreatedRevisionName": NEW_REVISION, "latestReadyRevisionName": NEW_REVISION, "traffic": [{"revisionName": NEW_REVISION, "percent": 100}] if len([item for item in commands if "update-traffic" in item]) else [{"revisionName": ROLLBACK_REVISION, "percent": 100}]}})
            else:
                output = ""
            return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")

        result = deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        self.assertFalse(result["already_promoted"])
        self.assertEqual(len([item for item in commands if "update-traffic" in item]), 1)
        build_describe = next(
            command
            for command in commands
            if command[:3] == ["gcloud", "builds", "describe"]
        )
        self.assertEqual(
            build_describe[build_describe.index("--region") + 1], deploy.REGION
        )

    def make_resume_runner(
        self,
        *,
        latest_created=NEW_REVISION,
        initial_traffic=None,
        post_traffic=None,
        build_status="SUCCESS",
        substitutions=None,
        interrupt=False,
        rollback_failure=False,
    ):
        commands = []
        service_describes = 0
        initial_traffic = initial_traffic or [{"revisionName": ROLLBACK_REVISION, "percent": 100}]
        post_traffic = post_traffic or [{"revisionName": NEW_REVISION, "percent": 100}]
        substitutions = substitutions or {
            "_SERVICE_NAME": "game-broadcast-service",
            "_IMAGE_TAG": SHA,
        }

        def runner(arguments, _cwd):
            nonlocal service_describes
            commands.append(list(arguments))
            if arguments[:2] == ["git", "status"]:
                output = ""
            elif arguments[:3] == ["git", "rev-parse", "HEAD"]:
                output = SHA
            elif arguments[:3] == ["gcloud", "builds", "describe"]:
                output = json.dumps(
                    {"status": build_status, "substitutions": substitutions}
                )
            elif arguments[:3] == ["gcloud", "artifacts", "docker"]:
                output = APPROVED_DIGEST
            elif arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
                output = json.dumps({"status": {"imageDigest": FULL_REVISION_DIGEST, "conditions": [{"type": "Ready", "status": "True"}]}})
            elif arguments[:4] == ["gcloud", "run", "services", "describe"]:
                service_describes += 1
                output = json.dumps({"status": {"latestCreatedRevisionName": latest_created, "latestReadyRevisionName": ROLLBACK_REVISION, "traffic": initial_traffic if service_describes == 1 else post_traffic}})
            elif "update-traffic" in arguments:
                destination = arguments[arguments.index("--to-revisions") + 1].split("=", 1)[0]
                if destination == NEW_REVISION and interrupt:
                    raise KeyboardInterrupt()
                if destination == ROLLBACK_REVISION and rollback_failure:
                    raise deploy.DeploymentError("rollback unavailable")
                output = ""
            else:
                output = ""
            return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")

        runner.commands = commands
        return runner

    def test_resume_rejects_unknown_baseline_without_promotion(self):
        runner = self.make_resume_runner(initial_traffic=[{"revisionName": "unknown-baseline", "percent": 100}])
        with self.assertRaisesRegex(deploy.DeploymentError, "traffic state is ambiguous"):
            deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        self.assertEqual(self.traffic_commands(runner), [])

    def test_resume_rejects_candidate_that_is_not_latest_created(self):
        runner = self.make_resume_runner(latest_created=BASELINE_REVISION)
        with self.assertRaisesRegex(deploy.DeploymentError, "latest created"):
            deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        self.assertEqual(self.traffic_commands(runner), [])

    def test_resume_interruption_rolls_back_exact_revision(self):
        runner = self.make_resume_runner(interrupt=True)
        with self.assertRaises(KeyboardInterrupt):
            deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 2)
        self.assertEqual(traffic[-1][traffic[-1].index("--to-revisions") + 1], f"{ROLLBACK_REVISION}=100")

    def test_resume_post_promotion_verification_failure_rolls_back_exact_revision(self):
        runner = self.make_resume_runner(post_traffic=[{"revisionName": NEW_REVISION, "percent": 99}])
        with self.assertRaisesRegex(deploy.DeploymentError, "exact 100% traffic"):
            deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 2)
        self.assertEqual(traffic[-1][traffic[-1].index("--to-revisions") + 1], f"{ROLLBACK_REVISION}=100")

    def test_resume_already_promoted_candidate_performs_no_mutation(self):
        runner = self.make_resume_runner(initial_traffic=[{"revisionName": NEW_REVISION, "percent": 100}])
        result = deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        self.assertTrue(result["already_promoted"])
        self.assertEqual(self.traffic_commands(runner), [])

    def test_resume_reports_combined_failure_when_rollback_fails(self):
        runner = self.make_resume_runner(interrupt=True, rollback_failure=True)
        with self.assertRaisesRegex(deploy.DeploymentError, "rollback also failed"):
            deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        self.assertEqual(len(self.traffic_commands(runner)), 2)

    def test_resume_rejects_failed_or_ambiguous_state_without_promotion(self):
        runner = FakeRunner(self.root)
        with self.assertRaisesRegex(deploy.DeploymentError, "Cloud Build resume"):
            deploy.resume_verify_only(self.root, "game-broadcast-service", SHA, "build-12345678", NEW_REVISION, ROLLBACK_REVISION, runner, False)
        self.assertEqual(self.traffic_commands(runner), [])

    def test_resume_rejects_non_resumable_builds_without_promotion(self):
        cases = (
            ("FAILURE", None, "not a successful resumable build"),
            ("WORKING", None, "not a successful resumable build"),
            (
                "SUCCESS",
                {"_SERVICE_NAME": "wrong-service", "_IMAGE_TAG": SHA},
                "substitutions do not match",
            ),
            (
                "SUCCESS",
                {"_SERVICE_NAME": "game-broadcast-service", "_IMAGE_TAG": "c" * 40},
                "substitutions do not match",
            ),
        )
        for status, substitutions, error in cases:
            with self.subTest(status=status, substitutions=substitutions):
                runner = self.make_resume_runner(
                    build_status=status, substitutions=substitutions
                )
                with self.assertRaisesRegex(deploy.DeploymentError, error):
                    deploy.resume_verify_only(
                        self.root,
                        "game-broadcast-service",
                        SHA,
                        "build-12345678",
                        NEW_REVISION,
                        ROLLBACK_REVISION,
                        runner,
                        False,
                    )
                self.assertEqual(self.traffic_commands(runner), [])

    def test_resume_cli_rejects_mixed_or_incomplete_execution_inputs(self):
        combinations = (
            ["game-broadcast-service", "--execute", "--resume-verify-only"],
            ["game-broadcast-service", "--build-id", "build-12345678"],
            ["game-broadcast-service", "--resume-verify-only", "--approved-commit", SHA],
        )
        for arguments in combinations:
            with self.subTest(arguments=arguments), patch.object(
                deploy, "repository_root", return_value=self.root
            ):
                self.assertEqual(deploy.main(arguments), 2)


if __name__ == "__main__":
    unittest.main()
