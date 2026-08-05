import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import deploy_scheduled_service as deploy


SHA = "a" * 40


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        dirty=False,
        build_status="SUCCESS",
        ready=True,
        traffic=True,
    ):
        self.root = root
        self.dirty = dirty
        self.build_status = build_status
        self.ready = ready
        self.traffic = traffic
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
        elif arguments[:4] == ["gcloud", "run", "services", "describe"]:
            self.describe_calls += 1
            revision = "game-broadcast-service-00099-abc"
            status = {
                "latestCreatedRevisionName": revision,
                "latestReadyRevisionName": revision if self.ready else "old",
                "traffic": (
                    [{"revisionName": revision, "percent": 100}]
                    if self.traffic
                    else []
                ),
            }
            stdout = json.dumps({"status": status})
        elif arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
            stdout = json.dumps({"status": {"imageDigest": "sha256:" + "b" * 64}})
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
                "SAFE: visible\nCHANNEL_ACCESS_TOKEN: fake-token\n"
                "CHANNEL_SECRET: fake-secret\nWEATHER_API_KEY: fake-weather\n"
                "DSN_PASSWORD: fake-password\n",
                encoding="utf-8",
            )
        (self.root / "shared_lib" / "dist").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

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
                self.root, "game-broadcast-service", SHA,
                "notify-cronjob-service-00010-abc", runner, False,
            )

    def test_dirty_source_and_existing_temporary_env_fail_closed(self):
        with self.assertRaisesRegex(deploy.DeploymentError, "clean"):
            deploy.preflight(
                self.root, "game-broadcast-service", None, None,
                FakeRunner(self.root, dirty=True), False,
            )
        temporary = self.root / "apps" / "game_broadcast_service" / ".env.yaml"
        temporary.write_text("owner: file\n", encoding="utf-8")
        with self.assertRaisesRegex(deploy.DeploymentError, "overwrite"):
            deploy.preflight(
                self.root, "game-broadcast-service", None, None,
                FakeRunner(self.root), False,
            )
        self.assertEqual(temporary.read_text(encoding="utf-8"), "owner: file\n")

    def test_filter_removes_service_secrets_without_logging_values(self):
        source = self.root / "envs" / "game_broadcast_service" / ".env.yaml"
        destination = self.root / "filtered.yaml"
        deploy.write_filtered_env(
            source, destination,
            deploy.SERVICES["game-broadcast-service"].secret_env_keys,
        )
        self.assertEqual(destination.read_text(encoding="utf-8"), "SAFE: visible\n")

    def test_success_uses_sha_tag_and_explicitly_assigns_traffic(self):
        runner = FakeRunner(self.root)
        result = deploy.execute_deployment(
            self.root, "game-broadcast-service", SHA,
            "game-broadcast-service-00030-pgg", runner, False,
        )
        self.assertEqual(result["image_tag"], SHA)
        build = next(
            command
            for command in runner.commands
            if command[:3] == ["gcloud", "builds", "submit"]
        )
        self.assertIn(f"_IMAGE_TAG={SHA}", build[build.index("--substitutions") + 1])
        traffic = [
            command for command in runner.commands if "update-traffic" in command
        ]
        self.assertEqual(len(traffic), 1)
        self.assertIn("game-broadcast-service-00099-abc=100", traffic[0])
        self.assertFalse(
            (self.root / "apps" / "game_broadcast_service" / ".env.yaml").exists()
        )

    def test_not_ready_revision_rolls_back_and_cleans_environment(self):
        runner = FakeRunner(self.root, ready=False)
        with self.assertRaisesRegex(deploy.DeploymentError, "not ready"):
            deploy.execute_deployment(
                self.root, "game-broadcast-service", SHA,
                "game-broadcast-service-00030-pgg", runner, False,
            )
        rollback = [
            command for command in runner.commands if "update-traffic" in command
        ]
        self.assertEqual(len(rollback), 1)
        self.assertIn("game-broadcast-service-00030-pgg=100", rollback[0])
        self.assertFalse(
            (self.root / "apps" / "game_broadcast_service" / ".env.yaml").exists()
        )

    def test_build_failure_cleans_environment_without_traffic_command(self):
        runner = FakeRunner(self.root, build_status="FAILURE")
        with self.assertRaisesRegex(deploy.DeploymentError, "SUCCESS"):
            deploy.execute_deployment(
                self.root, "game-broadcast-service", SHA,
                "game-broadcast-service-00030-pgg", runner, False,
            )
        self.assertFalse(
            any("update-traffic" in command for command in runner.commands)
        )
        self.assertFalse(
            (self.root / "apps" / "game_broadcast_service" / ".env.yaml").exists()
        )


if __name__ == "__main__":
    unittest.main()
