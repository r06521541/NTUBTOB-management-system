import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import deploy_web_portal as deploy


SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
ROLLBACK = "web-portal-00026-rtc"
BASELINE = "web-portal-00027-fwf"
REVISION = "web-portal-00028-new"
IDENTITY = "123456-compute@developer.gserviceaccount.com"
LINE_REF = "fixture-line-login-secret:1"
SESSION_REF = "fixture-session-secret:2"


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class FakeRunner:
    def __init__(
        self,
        root,
        *,
        dirty=False,
        head=SHA,
        build_statuses=("WORKING", "SUCCESS"),
        revision_ready=True,
        revision_digest=DIGEST,
        traffic=True,
        public=True,
        identity=IDENTITY,
        secret_override=None,
        rollback_failure=False,
    ):
        self.root = root
        self.dirty = dirty
        self.head = head
        self.build_statuses = iter(build_statuses)
        self.last_build_status = None
        self.revision_ready = revision_ready
        self.revision_digest = revision_digest
        self.traffic = traffic
        self.public = public
        self.identity = identity
        self.secret_override = secret_override
        self.rollback_failure = rollback_failure
        self.commands = []
        self.service_describes = 0

    def env_entries(self):
        entries = [
            {"name": name, "value": "fixture-plain-value"}
            for name in deploy.REQUIRED_PLAIN_KEYS
        ]
        references = {
            "DSN_PASSWORD": "supabase-database-password:latest",
            "LINE_LOGIN_CHANNEL_SECRET": LINE_REF,
            "SECRET_KEY": SESSION_REF,
        }
        if self.secret_override:
            references.update(self.secret_override)
        for name, reference in references.items():
            resource, version = reference.rsplit(":", 1)
            entries.append(
                {
                    "name": name,
                    "valueFrom": {
                        "secretKeyRef": {"name": resource, "key": version}
                    },
                }
            )
        return entries

    def __call__(self, arguments, cwd):
        arguments = list(arguments)
        self.commands.append((arguments, Path(cwd)))
        stdout = ""
        if arguments[:2] == ["git", "status"]:
            stdout = " M fixture-file\n" if self.dirty else ""
        elif arguments[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = self.head + "\n"
        elif "setup.py" in arguments:
            artifact = self.root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"fixture sdist")
        elif arguments[:3] == ["gcloud", "builds", "submit"]:
            stdout = "fixture-build-id\n"
        elif arguments[:3] == ["gcloud", "builds", "describe"]:
            try:
                self.last_build_status = next(self.build_statuses)
            except StopIteration:
                pass
            stdout = json.dumps({"status": self.last_build_status})
        elif arguments[:5] == ["gcloud", "artifacts", "docker", "images", "describe"]:
            stdout = DIGEST + "\n"
        elif arguments[:4] == ["gcloud", "run", "services", "describe"]:
            self.service_describes += 1
            revision = BASELINE if self.service_describes == 1 else REVISION
            stdout = json.dumps(
                {
                    "spec": {"template": {"spec": {"serviceAccountName": IDENTITY}}},
                    "status": {
                        "latestCreatedRevisionName": revision,
                        "url": "https://fixture-web-portal.example",
                        "traffic": (
                            [{"revisionName": revision, "percent": 100}]
                            if self.service_describes > 1 and self.traffic
                            else []
                        ),
                    },
                }
            )
        elif arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
            stdout = json.dumps(
                {
                    "spec": {
                        "serviceAccountName": self.identity,
                        "containers": [{"env": self.env_entries()}],
                    },
                    "status": {
                        "imageDigest": self.revision_digest,
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "True" if self.revision_ready else "False",
                            }
                        ],
                    },
                }
            )
        elif arguments[:4] == ["gcloud", "run", "services", "get-iam-policy"]:
            bindings = (
                [{"role": "roles/run.invoker", "members": ["allUsers"]}]
                if self.public
                else []
            )
            stdout = json.dumps({"bindings": bindings})
        elif "update-traffic" in arguments and self.rollback_failure:
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout=stdout, stderr="")


class WebPortalDeploymentWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        service = self.root / "apps" / "web_portal"
        service.mkdir(parents=True)
        (service / "cloudbuild.yaml").write_text("steps: []\n", encoding="utf-8")
        (service / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        shared = self.root / "shared_lib"
        shared.mkdir()
        (shared / "setup.py").write_text("# fixture\n", encoding="utf-8")
        env = self.root / "envs" / "web_portal" / ".env.yaml"
        env.parent.mkdir(parents=True)
        env.write_text(
            "SAFE_SETTING: kept\n"
            "DSN_PASSWORD: fixture-password\n"
            "LINE_LOGIN_CHANNEL_SECRET: fixture-line-value\n"
            "SECRET_KEY: fixture-session-value\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    @property
    def temporary_env(self):
        return self.root / "apps" / "web_portal" / ".env.yaml"

    def execute(self, runner, http_get=None, **kwargs):
        return deploy.execute_deployment(
            self.root,
            SHA,
            ROLLBACK,
            LINE_REF,
            SESSION_REF,
            runner=runner,
            http_get=http_get or (lambda url, timeout: 404 if url.endswith("/demo/") else 200),
            clock=kwargs.pop("clock", FakeClock([0, 1, 2, 3])),
            sleeper=kwargs.pop("sleeper", lambda seconds: None),
            check_tools=False,
            **kwargs,
        )

    def test_dry_run_preflight_uses_only_git_and_local_files(self):
        runner = FakeRunner(self.root)
        deploy.preflight(self.root, runner=runner, check_tools=False)
        self.assertEqual(
            [command for command, _ in runner.commands],
            [["git", "status", "--porcelain"], ["git", "rev-parse", "HEAD"]],
        )

    def test_main_rejects_execution_arguments_without_execute(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = deploy.main(["--approved-commit", SHA])
        self.assertEqual(result, 2)
        self.assertIn("require --execute", stderr.getvalue())

    def test_execute_requires_every_exact_input(self):
        with patch.object(deploy, "execute_deployment") as execute:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = deploy.main(["--execute", "--approved-commit", SHA])
        self.assertEqual(result, 2)
        execute.assert_not_called()

    def test_invalid_inputs_and_dirty_source_fail_closed(self):
        cases = (
            ("abc", ROLLBACK, LINE_REF, SESSION_REF, "40-character"),
            (SHA, "other-service-00001-bad", LINE_REF, SESSION_REF, "web-portal"),
            (SHA, ROLLBACK, "bad value", SESSION_REF, "resource:version"),
            (SHA, ROLLBACK, LINE_REF, "secret:", "resource:version"),
        )
        for commit, revision, line_ref, session_ref, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(deploy.DeploymentError, message):
                    deploy.preflight(
                        self.root, commit, revision, line_ref, session_ref,
                        FakeRunner(self.root), False,
                    )
        with self.assertRaisesRegex(deploy.DeploymentError, "clean"):
            deploy.preflight(
                self.root, runner=FakeRunner(self.root, dirty=True), check_tools=False
            )

    def test_missing_git_tool_fails_before_preflight_commands(self):
        runner = FakeRunner(self.root)
        with patch.object(deploy.shutil, "which", return_value=None):
            with self.assertRaisesRegex(deploy.DeploymentError, "git"):
                deploy.preflight(self.root, runner=runner, check_tools=True)
        self.assertEqual(runner.commands, [])

    def test_head_mismatch_missing_source_and_existing_temp_fail_closed(self):
        with self.assertRaisesRegex(deploy.DeploymentError, "HEAD"):
            deploy.preflight(
                self.root, SHA, runner=FakeRunner(self.root, head="b" * 40), check_tools=False
            )
        (self.root / "apps" / "web_portal" / "Dockerfile").unlink()
        with self.assertRaisesRegex(deploy.DeploymentError, "source"):
            deploy.preflight(self.root, runner=FakeRunner(self.root), check_tools=False)
        (self.root / "apps" / "web_portal" / "Dockerfile").write_text("FROM scratch\n")
        self.temporary_env.write_text("owner file\n", encoding="utf-8")
        with self.assertRaisesRegex(deploy.DeploymentError, "overwrite"):
            deploy.preflight(self.root, runner=FakeRunner(self.root), check_tools=False)
        self.assertEqual(self.temporary_env.read_text(), "owner file\n")

    def test_filtered_env_keeps_safe_key_without_disclosing_fixture_secrets(self):
        source = self.root / "envs" / "web_portal" / ".env.yaml"
        deploy.write_filtered_env(source, self.temporary_env)
        self.assertEqual(self.temporary_env.read_text(), "SAFE_SETTING: kept\n")

    def test_success_uses_fixed_context_single_substitution_argument_and_http_once(self):
        runner = FakeRunner(self.root)
        http_calls = []

        def fake_http(url, timeout):
            http_calls.append((url, timeout))
            return 404 if url.endswith("/demo/") else 200

        result = self.execute(runner, fake_http)
        build, cwd = next(item for item in runner.commands if item[0][:3] == ["gcloud", "builds", "submit"])
        self.assertEqual(cwd, self.root / "apps" / "web_portal")
        self.assertIn("--async", build)
        substitutions = build[build.index("--substitutions") + 1]
        self.assertEqual(build.count(substitutions), 1)
        self.assertIn(f"_IMAGE_TAG={SHA}", substitutions)
        self.assertIn(f"_WEB_PORTAL_LINE_LOGIN_SECRET_REF={LINE_REF}", substitutions)
        self.assertEqual(len(http_calls), 2)
        self.assertEqual(result["http_status"], {"/": 200, "/demo/": 404})
        self.assertNotIn("fixture-password", json.dumps(result))
        self.assertFalse(self.temporary_env.exists())
        self.assertTrue((self.root / "apps" / "web_portal" / "dist" / "shared_lib-0.0.1.tar.gz").is_file())

    def test_polling_handles_failure_malformed_and_timeout(self):
        with self.assertRaisesRegex(deploy.DeploymentError, "FAILURE"):
            deploy.poll_build(
                self.root, "build", FakeRunner(self.root, build_statuses=("FAILURE",)),
                5, 1, FakeClock([0]), lambda seconds: None,
            )
        with self.assertRaisesRegex(deploy.DeploymentError, "malformed"):
            deploy.poll_build(
                self.root, "build", FakeRunner(self.root, build_statuses=(None,)),
                5, 1, FakeClock([0]), lambda seconds: None,
            )
        with self.assertRaisesRegex(deploy.DeploymentError, "timed out"):
            deploy.poll_build(
                self.root, "build", FakeRunner(self.root, build_statuses=("WORKING",)),
                1, 1, FakeClock([0, 1]), lambda seconds: None,
            )

    def test_build_failure_cleans_temp_without_rollback(self):
        runner = FakeRunner(self.root, build_statuses=("FAILURE",))
        with self.assertRaisesRegex(deploy.DeploymentError, "FAILURE"):
            self.execute(runner)
        self.assertFalse(self.temporary_env.exists())
        self.assertFalse(
            any("update-traffic" in command for command, _ in runner.commands)
        )

    def test_http_helper_disables_redirects_and_never_reads_body(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                raise AssertionError("response body must not be read")

        class FakeOpener:
            def __init__(self):
                self.request = None
                self.timeout = None

            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        opener = FakeOpener()
        with patch.object(deploy.urllib.request, "build_opener", return_value=opener) as build:
            status = deploy.http_status("https://fixture.example/", 7.5)
        self.assertEqual(status, 200)
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertEqual(opener.timeout, 7.5)
        self.assertIsInstance(build.call_args.args[0], deploy.NoRedirectHandler)
        self.assertIsNone(
            deploy.NoRedirectHandler().redirect_request(
                None, None, 302, "redirect", {}, "https://other.example/"
            )
        )

    def test_revision_contract_rejects_digest_identity_secret_and_public_drift(self):
        scenarios = (
            (dict(revision_digest="sha256:" + "c" * 64), "digest"),
            (dict(identity="different@example.com"), "identity"),
            (dict(secret_override={"SECRET_KEY": "wrong:1"}), "SECRET_KEY"),
            (dict(public=False), "Public"),
            (dict(traffic=False), "traffic"),
        )
        for options, message in scenarios:
            with self.subTest(message=message):
                runner = FakeRunner(self.root, **options)
                with self.assertRaisesRegex(deploy.DeploymentError, "rollback succeeded"):
                    self.execute(runner)
                rollback = [command for command, _ in runner.commands if "update-traffic" in command]
                self.assertEqual(len(rollback), 1)
                self.assertIn(f"{ROLLBACK}=100", rollback[0])
                self.assertFalse(self.temporary_env.exists())

    def test_http_failure_rolls_back_and_never_reads_response_body(self):
        runner = FakeRunner(self.root)
        calls = []

        def failing_http(url, timeout):
            calls.append(url)
            return 500 if url.endswith("/") and not url.endswith("/demo/") else 404

        with self.assertRaisesRegex(deploy.DeploymentError, "rollback succeeded"):
            self.execute(runner, failing_http)
        self.assertEqual(len(calls), 2)
        self.assertFalse(self.temporary_env.exists())

    def test_http_transport_error_rolls_back_and_cleans_environment(self):
        runner = FakeRunner(self.root)

        def unavailable_http(url, timeout):
            raise deploy.DeploymentError(
                "Web Portal HTTP verification could not complete"
            )

        with self.assertRaisesRegex(deploy.DeploymentError, "rollback succeeded"):
            self.execute(runner, unavailable_http)
        rollback = [command for command, _ in runner.commands if "update-traffic" in command]
        self.assertEqual(len(rollback), 1)
        self.assertIn(f"{ROLLBACK}=100", rollback[0])
        self.assertFalse(self.temporary_env.exists())

    def test_rollback_failure_is_distinct_and_cleanup_still_runs(self):
        runner = FakeRunner(self.root, traffic=False, rollback_failure=True)
        with self.assertRaisesRegex(deploy.DeploymentError, "rollback failed"):
            self.execute(runner)
        self.assertFalse(self.temporary_env.exists())


if __name__ == "__main__":
    unittest.main()
