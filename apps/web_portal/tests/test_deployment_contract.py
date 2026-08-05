import re
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
                self.assertIn(f'test -n "${{{variable}}}"', command)
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
