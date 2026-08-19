import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

DATABASE_MODULE = (
    Path(__file__).resolve().parents[1] / "shared_module" / "models" / "db.py"
)


def load_database_module(environment):
    spec = importlib.util.spec_from_file_location(
        "test_database_module", DATABASE_MODULE
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, environment, clear=True):
        spec.loader.exec_module(module)
    return module


class DatabaseConfigurationTest(unittest.TestCase):
    def test_portal_data_url_is_used_without_legacy_dsn_parts(self):
        module = load_database_module(
            {
                "PORTAL_DATA_DATABASE_URL": (
                    "postgresql://mobile-user:fake-password@staging.invalid:5432/portal"
                )
            }
        )
        self.addCleanup(module.engine.dispose)

        self.assertEqual(module.engine.url.host, "staging.invalid")
        self.assertEqual(module.engine.url.port, 5432)
        self.assertEqual(module.engine.url.database, "portal")

    def test_legacy_dsn_parts_remain_supported_and_escape_credentials(self):
        module = load_database_module(
            {
                "DSN_DATABASE": "legacy",
                "DSN_HOSTNAME": "legacy.invalid",
                "DSN_PORT": "5432",
                "DSN_UID": "legacy-user",
                "DSN_PASSWORD": "fake:p@ssword",
            }
        )
        self.addCleanup(module.engine.dispose)

        self.assertEqual(module.engine.url.host, "legacy.invalid")
        self.assertEqual(module.engine.url.password, "fake:p@ssword")

    def test_incomplete_or_invalid_legacy_configuration_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "configuration is incomplete"):
            load_database_module({})
        with self.assertRaisesRegex(RuntimeError, "port is invalid"):
            load_database_module(
                {
                    "DSN_DATABASE": "legacy",
                    "DSN_HOSTNAME": "legacy.invalid",
                    "DSN_PORT": "not-a-port",
                    "DSN_UID": "legacy-user",
                    "DSN_PASSWORD": "fake-password",
                }
            )


if __name__ == "__main__":
    unittest.main()
