import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from flask import Flask


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from health import create_health_blueprint


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(create_health_blueprint())
        self.client = app.test_client()
        self.dependencies = {
            name: Mock(side_effect=AssertionError(f"{name} must not be called"))
            for name in ("database", "line", "discord", "crawler", "weather")
        }

    def test_get_healthz_is_a_side_effect_free_process_check(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"service": "notify-cronjob-service", "status": "ok"},
        )
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for dependency in self.dependencies.values():
            dependency.assert_not_called()

    def test_post_healthz_is_not_allowed(self):
        self.assertEqual(self.client.post("/healthz").status_code, 405)

    def test_service_app_registers_health_blueprint(self):
        app_source = (SERVICE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn("app.register_blueprint(create_health_blueprint())", app_source)


if __name__ == "__main__":
    unittest.main()
