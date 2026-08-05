import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import deploy_scheduled_service as deploy


SHA = "a" * 40
APPROVED_DIGEST = "sha256:" + "b" * 64
ROLLBACK_REVISION = "game-broadcast-service-00030-pgg"
BASELINE_REVISION = "game-broadcast-service-00031-s65"
NEW_REVISION = "game-broadcast-service-00099-abc"


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        dirty=False,
        build_status="SUCCESS",
        ready=True,
        no_op=False,
        revision_digest=APPROVED_DIGEST,
        traffic=True,
        traffic_command_failure=False,
    ):
        self.root = root
        self.dirty = dirty
        self.build_status = build_status
        self.ready = ready
        self.no_op = no_op
        self.revision_digest = revision_digest
        self.traffic = traffic
        self.traffic_command_failure = traffic_command_failure
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
            status = {
                "latestCreatedRevisionName": revision,
                "latestReadyRevisionName": (
                    revision if self.ready else BASELINE_REVISION
                ),
                "traffic": (
                    [{"revisionName": revision, "percent": 100}]
                    if self.describe_calls >= 3 and self.traffic
                    else []
                ),
            }
            stdout = json.dumps({"status": status})
        elif arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
            stdout = json.dumps({"status": {"imageDigest": self.revision_digest}})
        elif "update-traffic" in arguments:
            destination = arguments[arguments.index("--to-revisions") + 1]
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
                "SAFE: visible\n  CHANNEL_ACCESS_TOKEN: fixture-access\n"
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
        self.assertEqual(output, "SAFE: visible\n")
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
        self.assert_only_exact_rollback(runner)
        self.assertNotIn(f"{BASELINE_REVISION}=100", repr(runner.commands))
        self.assertFalse(self.temporary_env().exists())

    def test_digest_mismatch_stops_before_new_revision_traffic(self):
        runner = FakeRunner(self.root, revision_digest="sha256:" + "c" * 64)
        with self.assertRaisesRegex(deploy.DeploymentError, "approved image tag"):
            self.execute(runner)
        self.assert_only_exact_rollback(runner)
        self.assertNotIn(f"{NEW_REVISION}=100", repr(runner.commands))
        self.assertFalse(self.temporary_env().exists())

    def test_not_ready_revision_rolls_back_and_cleans_environment(self):
        runner = FakeRunner(self.root, ready=False)
        with self.assertRaisesRegex(deploy.DeploymentError, "not ready"):
            self.execute(runner)
        self.assert_only_exact_rollback(runner)
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

    def test_traffic_verification_failure_rolls_back_exact_revision_and_cleans(self):
        runner = FakeRunner(self.root, traffic=False)
        with self.assertRaisesRegex(deploy.DeploymentError, "100% traffic"):
            self.execute(runner)
        traffic = self.traffic_commands(runner)
        self.assertEqual(len(traffic), 2)
        self.assertEqual(
            traffic[-1][traffic[-1].index("--to-revisions") + 1],
            f"{ROLLBACK_REVISION}=100",
        )
        self.assertFalse(self.temporary_env().exists())


if __name__ == "__main__":
    unittest.main()
