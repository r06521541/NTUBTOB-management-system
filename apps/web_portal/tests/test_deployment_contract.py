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

    def test_make_target_delegates_to_canonical_wrapper_only(self):
        command = normalize_shell_command(self.target)
        self.assertIn("python tools/deploy_web_portal.py", command)
        for argument in (
            "--execute",
            "--approved-commit",
            "--rollback-revision",
            "--line-login-secret-ref",
            "--session-secret-ref",
            "--weather-secret-ref",
            "--phase-c-enabled",
            "--rollout-freeze-enabled",
            "--identity-maintenance-enabled",
            "--identity-link-mode",
        ):
            with self.subTest(argument=argument):
                self.assertIn(argument, command)
        for forbidden in (
            "gcloud builds submit",
            "build-shared-lib",
            "grep -vE",
            ".env.yaml",
            "trap '",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, command)

    def test_make_target_passes_identity_inputs_only_when_supplied(self):
        command = normalize_shell_command(self.target)
        self.assertIn('if [ -n "${WEB_IDENTITY_LINK_GOOGLE_SECRET_REF}', command)
        for variable, argument in (
            ("WEB_IDENTITY_LINK_GOOGLE_SECRET_REF", "--google-identity-secret-ref"),
            ("WEB_IDENTITY_LINK_LINE_SECRET_REF", "--line-identity-secret-ref"),
            ("WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID", "--google-client-id"),
            ("WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI", "--google-redirect-uri"),
            ("WEB_IDENTITY_LINK_LINE_CLIENT_ID", "--line-client-id"),
            ("WEB_IDENTITY_LINK_LINE_REDIRECT_URI", "--line-redirect-uri"),
        ):
            with self.subTest(variable=variable):
                self.assertIn(f'{argument} "${{{variable}}}"', command)

    def test_cloud_build_fails_closed_for_both_identity_modes(self):
        command = normalize_shell_command(self.cloudbuild)
        self.assertIn("Validate deployment inputs", self.cloudbuild)
        self.assertIn("invalid or missing Secret reference", self.cloudbuild)
        for binding in (
            "DSN_PASSWORD=supabase-database-password:latest",
            "LINE_LOGIN_CHANNEL_SECRET=${_WEB_PORTAL_LINE_LOGIN_SECRET_REF}",
            "SECRET_KEY=${_WEB_PORTAL_SESSION_SECRET_REF}",
            "WEATHER_API_KEY=${_WEB_PORTAL_WEATHER_SECRET_REF}",
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET=${_WEB_IDENTITY_LINK_GOOGLE_SECRET_REF}",
            "WEB_IDENTITY_LINK_LINE_CLIENT_SECRET=${_WEB_IDENTITY_LINK_LINE_SECRET_REF}",
        ):
            with self.subTest(binding=binding):
                self.assertIn(binding, command)
        self.assertIn("case '${_WEB_IDENTITY_LINK_MODE}' in", self.cloudbuild)
        self.assertIn("enabled)", self.cloudbuild)
        self.assertIn("disabled)", self.cloudbuild)
        self.assertIn(
            "--remove-secrets=WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET,WEB_IDENTITY_LINK_LINE_CLIENT_SECRET",
            self.cloudbuild,
        )

    def test_cloud_build_disabled_mode_rejects_all_six_identity_keys(self):
        for name in (
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID",
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET",
            "WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI",
            "WEB_IDENTITY_LINK_LINE_CLIENT_ID",
            "WEB_IDENTITY_LINK_LINE_CLIENT_SECRET",
            "WEB_IDENTITY_LINK_LINE_REDIRECT_URI",
        ):
            with self.subTest(name=name):
                self.assertIn(name, self.cloudbuild)
        self.assertIn("identity-link runtime keys must be absent", self.cloudbuild)

    def test_build_push_deploy_share_immutable_commit_tag(self):
        self.assertGreaterEqual(self.cloudbuild.count("${_IMAGE_TAG}"), 3)
        self.assertNotIn(":tag1", self.cloudbuild)
        self.assertNotRegex(self.cloudbuild, r"-image:latest\b")
        command = normalize_shell_command(self.target)
        self.assertIn('--approved-commit "${IMAGE_TAG}"', command)

    def test_secret_references_are_not_hard_coded(self):
        command = normalize_shell_command(self.cloudbuild)
        for substitution in (
            "${_WEB_PORTAL_LINE_LOGIN_SECRET_REF}",
            "${_WEB_PORTAL_SESSION_SECRET_REF}",
            "${_WEB_PORTAL_WEATHER_SECRET_REF}",
        ):
            self.assertIn(substitution, command)
        self.assertNotRegex(
            self.cloudbuild,
            r"LINE_LOGIN_CHANNEL_SECRET=[a-z][a-z0-9_-]*:(?:latest|\d+)",
        )
        self.assertNotRegex(
            self.cloudbuild, r"SECRET_KEY=[a-z][a-z0-9_-]*:(?:latest|\d+)"
        )

    def test_service_remains_public_and_demo_is_not_enabled(self):
        command = normalize_shell_command(self.cloudbuild)
        self.assertIn("--allow-unauthenticated", command)
        self.assertNotIn("--no-allow-unauthenticated", command)
        combined = self.cloudbuild + self.target
        self.assertNotRegex(combined, r"WEB_PORTAL_DEMO_MODE\s*[=:]\s*(true|1)")
        self.assertNotRegex(combined, r"WEB_PORTAL_ENV\s*[=:]\s*development")


if __name__ == "__main__":
    unittest.main()
