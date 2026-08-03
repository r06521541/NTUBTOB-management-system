import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLOUDBUILD_FILE = (
    REPOSITORY_ROOT / "apps" / "game_broadcast_service" / "cloudbuild.yaml"
)
DOCKERIGNORE_FILE = (
    REPOSITORY_ROOT / "apps" / "game_broadcast_service" / ".dockerignore"
)
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

    def test_cloud_run_deploy_binds_required_secrets(self):
        command = normalize_shell_command(self.cloudbuild)
        self.assertRegex(command, r"\bgcloud\s+run\s+deploy\b")

        option = re.search(r"--update-secrets(?:=|\s+)(?P<bindings>\S+)", command)
        self.assertIsNotNone(option, "Cloud Run deploy must bind runtime secrets")
        bindings = option.group("bindings")

        for variable in (
            "DSN_PASSWORD",
            "WEATHER_API_KEY",
            "CHANNEL_ACCESS_TOKEN",
        ):
            with self.subTest(variable=variable):
                self.assertRegex(
                    bindings,
                    rf"(?:^|,){re.escape(variable)}=[^,\s]+",
                    f"Cloud Run deploy must bind {variable}",
                )

    def test_game_broadcast_service_remains_private(self):
        command = normalize_shell_command(self.cloudbuild)
        self.assertIn("--no-allow-unauthenticated", command)
        self.assertIsNone(
            re.search(r"(?<!no-)--allow-unauthenticated\b", command),
            "game-broadcast-service must not allow unauthenticated access",
        )

    def test_deploy_target_excludes_line_credentials_from_env_file(self):
        target = extract_make_target(
            self.deploy_makefile, "deploy-game-broadcast-service"
        )
        command = normalize_shell_command(target)
        grep_command = re.search(
            r"grep\s+-vE\s+(['\"])(?P<pattern>.*?)\1\s+"
            r"envs/\S+/\.env\.yaml\s*>\s*apps/\S+/\.env\.yaml",
            command,
        )
        self.assertIsNotNone(
            grep_command,
            "deploy target must filter the environment file before Cloud Build",
        )

        excluded_pattern = grep_command.group("pattern")
        for variable in ("CHANNEL_ACCESS_TOKEN", "CHANNEL_SECRET"):
            with self.subTest(variable=variable):
                self.assertIn(
                    variable,
                    excluded_pattern,
                    f"deploy target must exclude {variable}",
                )

    def test_docker_build_context_excludes_environment_file(self):
        ignored_paths = {
            line.strip()
            for line in self.dockerignore.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn(".env.yaml", ignored_paths)


if __name__ == "__main__":
    unittest.main()
