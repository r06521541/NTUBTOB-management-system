import os
import subprocess
import sys
import unittest
from pathlib import Path

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from local_preview import is_local_preview_enabled  # noqa: E402
from local_preview import require_local_preview_startup, require_loopback_request

LOCAL_DATABASE_URL = (
    "postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/"
    "ntubtob_portal_local"
)


def preview_environment(**changes):
    values = {
        "WEB_PORTAL_ENV": "development",
        "WEB_PORTAL_LOCAL_PREVIEW_MODE": "true",
        "WEB_PORTAL_DEMO_MODE": "false",
        "WEB_PORTAL_BIND_HOST": "127.0.0.1",
        "PORTAL_DATA_DATABASE_URL": LOCAL_DATABASE_URL,
        "DSN_HOSTNAME": "127.0.0.1",
        "DSN_PORT": "55432",
        "DSN_DATABASE": "ntubtob_portal_local",
    }
    values.update(changes)
    return values


class LocalPreviewGateTest(unittest.TestCase):
    def test_exact_dual_gate_and_startup_contract(self):
        values = preview_environment()
        self.assertTrue(is_local_preview_enabled(values))
        self.assertTrue(require_local_preview_startup(values))
        self.assertFalse(is_local_preview_enabled({}))
        self.assertFalse(require_local_preview_startup({}))

    def test_production_remote_database_wrong_name_and_non_loopback_fail_closed(self):
        cases = (
            {"WEB_PORTAL_ENV": "production"},
            {"WEB_PORTAL_LOCAL_PREVIEW_MODE": "TRUE"},
            {"WEB_PORTAL_BIND_HOST": "0.0.0.0"},
            {"DSN_HOSTNAME": "db.example"},
            {"DSN_DATABASE": "postgres"},
            {
                "PORTAL_DATA_DATABASE_URL": (
                    "postgresql://user:password@db.example/ntubtob_portal_local"
                )
            },
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError):
                    require_local_preview_startup(preview_environment(**changes))

    def test_request_host_must_be_loopback(self):
        for host in ("localhost:8080", "127.0.0.1:8080", "[::1]:8080"):
            require_loopback_request(host)
        for host in ("0.0.0.0:8080", "preview.example:8080", "127.0.0.1.example"):
            with self.subTest(host=host), self.assertRaises(RuntimeError):
                require_loopback_request(host)

    def test_preview_app_import_uses_local_session_and_no_notifier(self):
        script = """
import os
import sys
sys.path.insert(0, os.environ["WEB_PORTAL_TEST_ROOT"])
import app
assert app.LOCAL_PREVIEW_MODE_ENABLED
assert app.discord_notify_helper is None
assert app.app.config["SESSION_COOKIE_SECURE"] is False
assert app.app.secret_key == "development-local-session-key-not-for-production"
"""
        environment = {
            name: os.environ[name]
            for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")
            if name in os.environ
        }
        environment.update(preview_environment())
        environment.update(
            {
                "WEB_PORTAL_TEST_ROOT": str(WEB_PORTAL_DIR),
                "DSN_UID": "portal_local",
                "DSN_PASSWORD": "local-only-password",
            }
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=WEB_PORTAL_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
