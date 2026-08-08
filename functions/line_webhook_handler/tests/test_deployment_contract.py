import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_MAKEFILE = REPOSITORY_ROOT / "makes" / "deploy_functions.mk"


def extract_make_target(makefile: str, target: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(target)}:\s*$\n(?P<body>.*?)(?=^[^\s#][^\n]*:\s*$|\Z)",
        makefile,
    )
    if not match:
        raise AssertionError(f"Make target not found: {target}")
    return match.group("body")


def make_variables(makefile: str) -> dict:
    return dict(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)\s*=\s*([^\r\n]+?)\s*$", makefile))


class DeploymentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.makefile = DEPLOY_MAKEFILE.read_text(encoding="utf-8")
        cls.target = extract_make_target(cls.makefile, "deploy-line-webhook-handler")
        cls.variables = make_variables(cls.makefile)

    def test_line_webhook_deploy_binds_complete_secret_contract(self):
        option = re.search(r"--set-secrets\s+'(?P<bindings>[^']+)'", self.target)
        self.assertIsNotNone(option, "LINE webhook deploy must set runtime secrets")

        bindings = re.sub(
            r"\$\{([A-Z][A-Z0-9_]*)\}",
            lambda match: self.variables.get(match.group(1), ""),
            option.group("bindings"),
        ).split(",")

        self.assertEqual(
            set(bindings),
            {
                "DSN_PASSWORD=supabase-database-password:latest",
                "WEB_PORTAL_URL=web-portal-url:latest",
                "CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:2",
                "CHANNEL_SECRET=CHANNEL_SECRET:2",
            },
        )

    def test_line_webhook_deploy_rejects_version_one_line_bindings(self):
        self.assertNotIn("CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1", self.makefile)
        self.assertNotIn("CHANNEL_SECRET=CHANNEL_SECRET:1", self.makefile)


if __name__ == "__main__":
    unittest.main()
