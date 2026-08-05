import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))


from demo_portal import is_demo_mode_enabled  # noqa: E402


class DemoGateTest(unittest.TestCase):
    def test_double_gate_truth_table(self):
        self.assertTrue(
            is_demo_mode_enabled(
                {
                    "WEB_PORTAL_ENV": "development",
                    "WEB_PORTAL_DEMO_MODE": "true",
                }
            )
        )
        for values in (
            {},
            {"WEB_PORTAL_ENV": "development"},
            {"WEB_PORTAL_DEMO_MODE": "true"},
            {"WEB_PORTAL_ENV": "production", "WEB_PORTAL_DEMO_MODE": "true"},
            {"WEB_PORTAL_ENV": "development", "WEB_PORTAL_DEMO_MODE": "True"},
        ):
            with self.subTest(values=values):
                self.assertFalse(is_demo_mode_enabled(values))


class DemoPortalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ENV": "development",
                "WEB_PORTAL_DEMO_MODE": "true",
            },
            clear=False,
        )
        cls.environment.start()
        app_module = importlib.import_module("app")
        cls.app = app_module.app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def setUp(self):
        self.client = self.app.test_client()

    def login(self):
        return self.client.post("/demo/login", follow_redirects=False)

    def test_demo_entry_and_protected_redirect(self):
        response = self.client.get("/demo/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/demo/login"))

        login = self.client.get("/demo/login")
        self.assertEqual(login.status_code, 200)
        self.assertIn("進入虛構 Demo".encode(), login.data)
        self.assertIn(b'name="viewport"', login.data)
        self.assertIn(b"Google", login.data)
        self.assertIn(b"disabled", login.data)

    def test_all_main_pages_are_available_after_demo_login(self):
        self.login()
        pages = {
            "/demo/dashboard": "準備好下一場了嗎？",
            "/demo/games": "近期賽事與你的出席狀態",
            "/demo/games/demo-game-01": "已回覆隊員",
            "/demo/games/demo-game-02": "海風原型隊",
            "/demo/profile": "通知設定",
            "/demo/pending": "等待管理員確認",
        }
        for path, expected in pages.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected.encode(), response.data)

    def test_reply_uses_prg_and_is_reflected_across_pages(self):
        self.login()
        response = self.client.post(
            "/demo/games/demo-game-01/reply",
            data={"status": "attending"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(response.headers["Location"])
        dashboard = self.client.get("/demo/dashboard")
        self.assertIn("出席".encode(), detail.data)
        self.assertIn("0".encode(), dashboard.data)
        with self.client.session_transaction() as demo_session:
            self.assertEqual(
                demo_session["demo_replies"]["demo-game-01"], "attending"
            )

    def test_invalid_game_and_reply_fail_safely(self):
        self.login()
        self.assertEqual(self.client.get("/demo/games/unknown").status_code, 404)
        self.assertEqual(
            self.client.post(
                "/demo/games/demo-game-01/reply", data={"status": "maybe"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/demo/games/unknown/reply", data={"status": "attending"}
            ).status_code,
            400,
        )

    def test_logout_clears_demo_session(self):
        self.login()
        response = self.client.post("/demo/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/demo/login"))
        self.assertEqual(self.client.get("/demo/dashboard").status_code, 302)

    def test_navigation_is_offline_and_does_not_call_models_or_http(self):
        self.login()
        app_module = sys.modules["app"]
        forbidden_model = MagicMock()
        failures = [
            patch.object(app_module, "Game", forbidden_model),
            patch.object(app_module, "Member", forbidden_model),
            patch.object(app_module.requests, "get", side_effect=AssertionError),
            patch.object(app_module.requests, "post", side_effect=AssertionError),
        ]
        with failures[0], failures[1], failures[2], failures[3]:
            for path in (
                "/demo/dashboard",
                "/demo/games",
                "/demo/games/demo-game-01",
                "/demo/profile",
                "/demo/pending",
            ):
                self.assertEqual(self.client.get(path).status_code, 200)
        forbidden_model.assert_not_called()

    def test_existing_line_routes_remain_registered(self):
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertIn("/line/login", rules)
        self.assertIn("/line/callback", rules)

    def test_responsive_contract_and_mobile_navigation(self):
        self.login()
        response = self.client.get("/demo/dashboard")
        self.assertIn(b'class="bottom-nav"', response.data)
        self.assertIn(b'class="badge badge-', response.data)
        css = (WEB_PORTAL_DIR / "static" / "portal.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:700px)", css)
        self.assertIn("box-sizing:border-box", css)
        self.assertNotIn("min-width:375px", css)

    def test_demo_routes_fail_closed_when_gate_is_disabled(self):
        with patch.dict(os.environ, {"WEB_PORTAL_DEMO_MODE": "false"}, clear=False):
            for path in (
                "/demo/login",
                "/demo/dashboard",
                "/demo/games",
                "/demo/profile",
                "/demo/pending",
            ):
                self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
