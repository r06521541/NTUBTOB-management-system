import re
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLOUDBUILD_FILE = REPOSITORY_ROOT / "apps" / "web_portal" / "cloudbuild.yaml"
DOCKERIGNORE_FILE = REPOSITORY_ROOT / "apps" / "web_portal" / ".dockerignore"
DEPLOY_MAKEFILE = REPOSITORY_ROOT / "makes" / "deploy_apps.mk"


def read_repository_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_shell_command(text: str) -> str:
    return " ".join(text.replace("\\\n", " ").split())


def extract_make_target(makefile: str, target: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(target)}:\s*$\n(?P<body>.*?)(?=^[^\s#][^\n]*:\s*$|\Z)",
        makefile,
    )
    if not match:
        raise AssertionError(f"Make target not found: {target}")
    return match.group("body")


class DeploymentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cloudbuild = read_repository_file(CLOUDBUILD_FILE)
        cls.dockerignore = read_repository_file(DOCKERIGNORE_FILE)
        cls.deploy_makefile = read_repository_file(DEPLOY_MAKEFILE)
        cls.target = extract_make_target(cls.deploy_makefile, "deploy-web-portal")

    def test_docker_context_excludes_sensitive_and_local_files(self):
        ignored = {
            line.strip()
            for line in self.dockerignore.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for path in (
            ".env.yaml",
            ".env*",
            "tests/",
            "__pycache__/",
            ".venv/",
            ".coverage",
        ):
            with self.subTest(path=path):
                self.assertIn(path, ignored)
        self.assertNotIn("dist/", ignored)
        self.assertNotIn("dist/shared_lib-0.0.1.tar.gz", ignored)

    def test_make_target_filters_all_runtime_secrets(self):
        command = normalize_shell_command(self.target)
        self.assertNotIn("cp envs/${DIR_WEB_PORTAL}/.env.yaml", command)
        match = re.search(
            r"grep\s+-vE\s+(['\"])(?P<pattern>.*?)\1\s+"
            r"envs/\S+/\.env\.yaml\s*>\s*apps/\S+/\.env\.yaml",
            command,
        )
        self.assertIsNotNone(match)
        pattern = match.group("pattern")
        self.assertIn("^[[:space:]]*", pattern)
        for variable in (
            "DSN_PASSWORD",
            "LINE_LOGIN_CHANNEL_SECRET",
            "SECRET_KEY",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, pattern)
        self.assertIn("WEB_PORTAL_ADMIN_MEMBER_IDS", read_repository_file(
            REPOSITORY_ROOT / "apps" / "web_portal" / "README.md"
        ))

    def test_unknown_secret_references_are_required_not_hard_coded(self):
        command = normalize_shell_command(self.target)
        for variable in (
            "WEB_PORTAL_LINE_LOGIN_SECRET_REF",
            "WEB_PORTAL_SESSION_SECRET_REF",
        ):
            with self.subTest(variable=variable):
                self.assertIn(f'"${{{variable}}}" | grep -Eq', command)
                self.assertIn(f'_{variable}="${{{variable}}}"', command)

        cloudbuild = normalize_shell_command(self.cloudbuild)
        self.assertIn("${_WEB_PORTAL_LINE_LOGIN_SECRET_REF}", cloudbuild)
        self.assertIn("${_WEB_PORTAL_SESSION_SECRET_REF}", cloudbuild)
        self.assertNotRegex(
            self.cloudbuild,
            r"LINE_LOGIN_CHANNEL_SECRET=[a-z][a-z0-9_-]*:(?:latest|\d+)",
        )
        self.assertNotRegex(
            self.cloudbuild, r"SECRET_KEY=[a-z][a-z0-9_-]*:(?:latest|\d+)"
        )

    def test_invalid_secret_references_stop_before_build_or_gcloud(self):
        make = shutil.which("make")
        if make is None:
            self.skipTest("make is required for executable Make preflight coverage")

        invalid_references = (
            "",
            " ",
            "${_PLACEHOLDER}",
            ":latest",
            "secret:",
            "secret:latest:extra",
            "secret:latest version",
            "secret=other:latest",
        )
        for variable in (
            "WEB_PORTAL_LINE_LOGIN_SECRET_REF",
            "WEB_PORTAL_SESSION_SECRET_REF",
        ):
            for invalid in invalid_references:
                values = {
                    "WEB_PORTAL_LINE_LOGIN_SECRET_REF": "line-login-secret:1",
                    "WEB_PORTAL_SESSION_SECRET_REF": "session-secret:1",
                }
                values[variable] = invalid
                result = subprocess.run(
                    [
                        make,
                        "-f",
                        str(DEPLOY_MAKEFILE),
                        "deploy-web-portal",
                        f"IMAGE_TAG={'a' * 40}",
                        *(f"{key}={value}" for key, value in values.items()),
                    ],
                    cwd=REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                output = result.stdout + result.stderr
                with self.subTest(variable=variable, invalid=invalid):
                    self.assertNotEqual(0, result.returncode)
                    self.assertNotIn("build-shared-lib", output)
                    self.assertNotIn("gcloud builds submit", output)

    def test_temporary_env_cleanup_is_cwd_stable_on_success_and_failure(self):
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("sh is required for executable cleanup coverage")

        block_match = re.search(
            r"(?ms)^\s*@trap '(?P<body>.*?)\Z", self.target
        )
        self.assertIsNotNone(block_match)
        command = "trap '" + block_match.group("body")
        command = command.replace("${DIR_WEB_PORTAL}", "web_portal")
        command = command.replace("${REGION}", "test-region")
        command = command.replace("${WEB_PORTAL_NAME}", "web-portal")
        command = command.replace("${IMAGE_TAG}", "a" * 40)
        command = command.replace(
            "${WEB_PORTAL_LINE_LOGIN_SECRET_REF}", "line-login-secret:1"
        )
        command = command.replace(
            "${WEB_PORTAL_SESSION_SECRET_REF}", "session-secret:1"
        )

        for gcloud_exit in (0, 9):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "envs" / "web_portal" / ".env.yaml"
                target = root / "apps" / "web_portal" / ".env.yaml"
                source.parent.mkdir(parents=True)
                target.parent.mkdir(parents=True)
                source.write_text("SAFE_SETTING: value\n", encoding="utf-8")
                bin_dir = root / "bin"
                bin_dir.mkdir()
                fake_gcloud = bin_dir / "gcloud"
                fake_gcloud.write_text(
                    f"#!/bin/sh\nexit {gcloud_exit}\n", encoding="utf-8"
                )
                fake_gcloud.chmod(0o755)
                environment = os.environ.copy()
                environment["PATH"] = str(bin_dir) + os.pathsep + environment["PATH"]

                result = subprocess.run(
                    [shell, "-c", command],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                with self.subTest(gcloud_exit=gcloud_exit):
                    self.assertEqual(gcloud_exit, result.returncode)
                    self.assertFalse(target.exists())

    def test_cloud_build_fails_closed_and_binds_three_runtime_secrets(self):
        command = normalize_shell_command(self.cloudbuild)
        self.assertIn("Validate deployment inputs", self.cloudbuild)
        self.assertIn("invalid or missing Secret reference", self.cloudbuild)
        bindings = re.search(
            r"--update-secrets(?:=|\s+)(?P<bindings>\S+)", command
        )
        self.assertIsNotNone(bindings)
        value = bindings.group("bindings")
        for binding in (
            "DSN_PASSWORD=supabase-database-password:latest",
            "LINE_LOGIN_CHANNEL_SECRET=${_WEB_PORTAL_LINE_LOGIN_SECRET_REF}",
            "SECRET_KEY=${_WEB_PORTAL_SESSION_SECRET_REF}",
        ):
            with self.subTest(binding=binding):
                self.assertIn(binding, value)

    def test_build_push_deploy_share_immutable_commit_tag(self):
        self.assertGreaterEqual(self.cloudbuild.count("${_IMAGE_TAG}"), 3)
        self.assertNotIn(":tag1", self.cloudbuild)
        self.assertNotRegex(self.cloudbuild, r"-image:latest\b")
        command = normalize_shell_command(self.target)
        self.assertIn('_IMAGE_TAG="${IMAGE_TAG}"', command)
        self.assertIn("40-character Git commit SHA", command)

    def test_service_remains_public_and_demo_is_not_enabled(self):
        command = normalize_shell_command(self.cloudbuild)
        self.assertIn("--allow-unauthenticated", command)
        self.assertNotIn("--no-allow-unauthenticated", command)
        combined = self.cloudbuild + self.target
        self.assertNotRegex(combined, r"WEB_PORTAL_DEMO_MODE\s*[=:]\s*(true|1)")
        self.assertNotRegex(combined, r"WEB_PORTAL_ENV\s*[=:]\s*development")


if __name__ == "__main__":
    unittest.main()
