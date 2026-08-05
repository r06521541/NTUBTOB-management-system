import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from admin_security import parse_admin_member_ids  # noqa: E402
from line_login import create_oauth_state  # noqa: E402


class AdminAllowlistTest(unittest.TestCase):
    def test_allowlist_parsing(self):
        valid_cases = {
            "1": frozenset({1}),
            "1,2,300": frozenset({1, 2, 300}),
            " 1, 2 ": frozenset({1, 2}),
        }
        for value, expected in valid_cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_admin_member_ids(value), expected)

    def test_invalid_allowlist_fails_closed(self):
        for value in (None, "", "   ", "0", "-1", "1,", ",1", "1,,2", "1,x", "1,1"):
            with self.subTest(value=value):
                self.assertEqual(parse_admin_member_ids(value), frozenset())


class MemberMatchingRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ENV": "production",
                "WEB_PORTAL_DEMO_MODE": "false",
                "SECRET_KEY": "fake-test-session-key",
            },
            clear=False,
        )
        cls.environment.start()

        cls.line_user_model = MagicMock()
        cls.member_model = MagicMock()
        cls.game_model = MagicMock()
        cls.reply_model = MagicMock()
        cls.notifier = MagicMock()

        fake_modules = {
            "shared_module": types.ModuleType("shared_module"),
            "shared_module.models": types.ModuleType("shared_module.models"),
            "shared_module.models.games": cls._module(Game=cls.game_model),
            "shared_module.models.members": cls._module(Member=cls.member_model),
            "shared_module.models.line_users": cls._module(LineUser=cls.line_user_model),
            "shared_module.models.game_attendance_replies": cls._module(
                GameAttendanceReply=cls.reply_model
            ),
            "shared_module.notify": types.ModuleType("shared_module.notify"),
            "shared_module.notify.discord_notify": cls._module(
                DiscordNotifyHelper=lambda: cls.notifier
            ),
            "shared_module.attendance_analyzer": types.ModuleType(
                "shared_module.attendance_analyzer"
            ),
            "shared_module.settings": cls._module(local_timezone=None),
            "shared_module.message_templates": types.ModuleType(
                "shared_module.message_templates"
            ),
            "shared_module.message_templates.general_message": cls._module(
                reply_text_mapping={}
            ),
        }
        cls.modules = patch.dict(sys.modules, fake_modules)
        cls.modules.start()
        sys.modules.pop("app", None)
        cls.app_module = importlib.import_module("app")
        cls.app = cls.app_module.app
        cls.app.config.update(TESTING=True)

    @staticmethod
    def _module(**attributes):
        module = types.ModuleType("fake")
        for name, value in attributes.items():
            setattr(module, name, value)
        return module

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("app", None)
        cls.modules.stop()
        cls.environment.stop()

    def setUp(self):
        self.client = self.app.test_client()
        self.line_user_model.reset_mock()
        self.member_model.reset_mock()
        self.notifier.reset_mock()
        self.line_user_model.search_all_unknowns.return_value = [
            SimpleNamespace(line_user_id="fake-line-user", nickname="Demo User")
        ]
        self.member_model.search_all.return_value = [
            SimpleNamespace(id=8, name="Demo Member")
        ]
        self.line_user_model.search_by_id.return_value = SimpleNamespace(
            nickname="Demo User"
        )
        self.member_model.search_by_id.return_value = SimpleNamespace(
            name="Demo Member"
        )

    def login(self, member_id=7):
        with self.client.session_transaction() as current_session:
            current_session["user_id"] = "fake-authenticated-user"
            current_session["member_id"] = member_id

    def assert_no_management_side_effects(self):
        self.line_user_model.search_all_unknowns.assert_not_called()
        self.member_model.search_all.assert_not_called()
        self.line_user_model.search_by_id.assert_not_called()
        self.member_model.search_by_id.assert_not_called()
        self.line_user_model.update_member_id.assert_not_called()
        self.line_user_model.update_as_ignored.assert_not_called()
        self.notifier.notify_management_message.assert_not_called()

    def get_csrf_token(self):
        self.login()
        with patch.dict(os.environ, {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}):
            response = self.client.get("/match-member")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as current_session:
            return current_session["member_matching_csrf_token"]

    def test_unauthenticated_routes_redirect_before_queries(self):
        for path, method in (
            ("/match-member", self.client.get),
            ("/match-member/match", self.client.post),
            ("/match-member/ignore", self.client.post),
        ):
            with self.subTest(path=path):
                response = method(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/redirect-to-login", response.headers["Location"])
                self.assert_no_management_side_effects()

    def test_non_admin_and_invalid_configuration_return_403_without_queries(self):
        for value in (None, "", "7,invalid", "8"):
            for path, method in (
                ("/match-member", self.client.get),
                ("/match-member/match", self.client.post),
                ("/match-member/ignore", self.client.post),
            ):
                with self.subTest(value=value, path=path):
                    self.login()
                    environment = (
                        {}
                        if value is None
                        else {"WEB_PORTAL_ADMIN_MEMBER_IDS": value}
                    )
                    with patch.dict(os.environ, environment, clear=value is None):
                        response = method(path)
                    self.assertEqual(response.status_code, 403)
                    self.assert_no_management_side_effects()

    def test_admin_get_queries_data_and_creates_reusable_csrf_token(self):
        token = self.get_csrf_token()
        self.assertTrue(token)
        with patch.dict(os.environ, {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}):
            second = self.client.get("/match-member")
        self.assertEqual(second.status_code, 200)
        self.assertIn(token.encode(), second.data)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["member_matching_csrf_token"], token)
        self.line_user_model.search_all_unknowns.assert_called()
        self.member_model.search_all.assert_called()

    def test_both_posts_reject_bad_csrf_without_side_effects(self):
        token = self.get_csrf_token()
        for path, extra_data in (
            ("/match-member/match", {"member_id": "8"}),
            ("/match-member/ignore", {}),
        ):
            for csrf_value in (None, "", "wrong-token"):
                with self.subTest(path=path, csrf=csrf_value):
                    self.line_user_model.reset_mock()
                    self.member_model.reset_mock()
                    self.notifier.reset_mock()
                    data = {"line_user_id": "fake-line-user", **extra_data}
                    if csrf_value is not None:
                        data["csrf_token"] = csrf_value
                    with patch.dict(os.environ, {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}):
                        response = self.client.post(path, data=data)
                    self.assertEqual(response.status_code, 400)
                    self.assertNotEqual(csrf_value, token)
                    self.assert_no_management_side_effects()

    def test_line_callback_records_authenticated_member_id(self):
        class SerializableMember(int):
            @property
            def id(self):
                return int(self)

        self.line_user_model.search_by_id.return_value = SimpleNamespace(member_id=7)
        self.member_model.search_by_id.return_value = SerializableMember(7)
        state = create_oauth_state(
            self.app.secret_key,
            "/attendance",
            "fake-nonce",
        )
        with self.client.session_transaction() as current_session:
            current_session["oauth_state_nonce"] = "fake-nonce"
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "fake-access-token"}
        profile_response = MagicMock()
        profile_response.json.return_value = {
            "userId": "fake-authenticated-user",
            "displayName": "Demo User",
        }
        with patch.object(self.app_module.requests, "post", return_value=token_response), patch.object(
            self.app_module.requests, "get", return_value=profile_response
        ):
            response = self.client.get(
                f"/line/callback?code=fake-code&state={state}"
            )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["member_id"], 7)

    def test_callback_rejects_state_from_a_different_browser_session(self):
        login_client = self.app.test_client()
        callback_client = self.app.test_client()

        login_response = login_client.get("/line/login?next=/future-games")
        state = parse_qs(urlsplit(login_response.headers["Location"]).query)["state"][
            0
        ]
        with callback_client.session_transaction() as callback_session:
            callback_session["user_id"] = "existing-user"
            callback_session["member_id"] = 7
            callback_session["display_name"] = "Existing User"
            callback_session["oauth_state_nonce"] = "other-transaction"
            callback_session["next_url"] = "/future-games"
        with patch.object(
            self.app_module.requests, "post"
        ) as token_request, patch.object(
            self.app_module.requests, "get"
        ) as profile_request:
            response = callback_client.get(
                f"/line/callback?code=fake-code&state={state}"
            )

        self.assertEqual(response.status_code, 400)
        token_request.assert_not_called()
        profile_request.assert_not_called()
        self.line_user_model.search_by_id.assert_not_called()
        with callback_client.session_transaction() as callback_session:
            self.assertEqual(callback_session["user_id"], "existing-user")
            self.assertEqual(callback_session["member_id"], 7)
            self.assertEqual(callback_session["display_name"], "Existing User")
            self.assertNotIn("oauth_state_nonce", callback_session)
            self.assertNotIn("next_url", callback_session)

    def test_line_login_replaces_ambiguous_return_path(self):
        response = self.client.get("/line/login?next=/%255cattacker.example")
        state = parse_qs(urlsplit(response.headers["Location"]).query)["state"][0]
        with self.client.session_transaction() as current_session:
            nonce = current_session["oauth_state_nonce"]
        next_url, state_nonce = self.app_module.load_oauth_state(
            self.app.secret_key,
            state,
            "/attendance",
        )
        self.assertEqual(next_url, "/attendance")
        self.assertEqual(state_nonce, nonce)

    def test_line_login_keeps_authorization_in_initiating_browser(self):
        response = self.client.get("/line/login")
        authorization_query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(authorization_query["disable_auto_login"], ["true"])

    def test_production_session_cookie_has_explicit_security_attributes(self):
        response = self.client.get("/line/login")
        cookies = response.headers.getlist("Set-Cookie")
        session_cookie = next(
            value
            for value in cookies
            if value.startswith("ntubtob_web_session_v2=")
        )
        self.assertIn("Secure", session_cookie)
        self.assertIn("HttpOnly", session_cookie)
        self.assertIn("SameSite=Lax", session_cookie)
        self.assertIn("Path=/", session_cookie)
        self.assertNotIn("Domain=", session_cookie)

    def test_legacy_session_cookie_is_expired_without_reading_its_value(self):
        self.client.set_cookie("session", "opaque-legacy-value")

        response = self.client.get("/line/login")

        cookies = response.headers.getlist("Set-Cookie")
        legacy_cookie = next(
            value for value in cookies if value.startswith("session=;")
        )
        self.assertIn("Expires=", legacy_cookie)
        self.assertIn("Max-Age=0", legacy_cookie)
        self.assertIn("Secure", legacy_cookie)
        self.assertIn("HttpOnly", legacy_cookie)
        self.assertIn("SameSite=Lax", legacy_cookie)
        self.assertIn("Path=/", legacy_cookie)
        self.assertNotIn("Domain=", legacy_cookie)
        self.assertTrue(
            any(
                value.startswith("ntubtob_web_session_v2=") for value in cookies
            )
        )

    def test_invalid_state_rejects_before_line_or_database_calls(self):
        with self.client.session_transaction() as current_session:
            current_session["user_id"] = "stale-user"
            current_session["member_id"] = 7
            current_session["display_name"] = "Existing User"
            current_session["oauth_state_nonce"] = "stale-nonce"
            current_session["next_url"] = "/future-games"
        with patch.object(
            self.app_module.requests, "post"
        ) as token_request, patch.object(
            self.app_module.requests, "get"
        ) as profile_request:
            response = self.client.get(
                "/line/callback?code=fake-code&state=tampered-state"
            )

        self.assertEqual(response.status_code, 400)
        token_request.assert_not_called()
        profile_request.assert_not_called()
        self.line_user_model.search_by_id.assert_not_called()
        self.member_model.search_by_id.assert_not_called()
        self.assertIn("重新開始 LINE 登入".encode(), response.data)
        self.assertNotIn(b"fake-code", response.data)
        self.assertNotIn(b"tampered-state", response.data)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["user_id"], "stale-user")
            self.assertEqual(current_session["member_id"], 7)
            self.assertEqual(current_session["display_name"], "Existing User")
            self.assertNotIn("oauth_state_nonce", current_session)
            self.assertNotIn("next_url", current_session)

        retry = self.client.get("/line/login")
        retry_state = parse_qs(urlsplit(retry.headers["Location"]).query)["state"][0]
        with self.client.session_transaction() as current_session:
            retry_nonce = current_session["oauth_state_nonce"]
        _, state_nonce = self.app_module.load_oauth_state(
            self.app.secret_key,
            retry_state,
            "/attendance",
        )
        self.assertEqual(state_nonce, retry_nonce)
        self.assertNotEqual(retry_nonce, "stale-nonce")

    def test_line_http_failure_is_safe_and_does_not_query_database(self):
        state = create_oauth_state(
            self.app.secret_key,
            "/attendance",
            "fake-nonce",
        )
        with self.client.session_transaction() as current_session:
            current_session["oauth_state_nonce"] = "fake-nonce"
        with patch.object(
            self.app_module.requests,
            "post",
            side_effect=self.app_module.requests.Timeout("fake timeout"),
        ) as token_request, patch.object(
            self.app_module.requests, "get"
        ) as profile_request:
            response = self.client.get(
                f"/line/callback?code=fake-code&state={state}"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(token_request.call_args.kwargs["timeout"], 10)
        profile_request.assert_not_called()
        self.line_user_model.search_by_id.assert_not_called()
        self.member_model.search_by_id.assert_not_called()

    def test_invalid_line_payload_shapes_fail_before_database_lookup(self):
        invalid_token_payloads = ({}, {"access_token": ""}, {"access_token": 7})
        for payload in invalid_token_payloads:
            with self.subTest(payload=payload):
                login_response = self.client.get("/line/login")
                state = parse_qs(urlsplit(login_response.headers["Location"]).query)[
                    "state"
                ][0]
                token_response = MagicMock()
                token_response.json.return_value = payload
                with patch.object(
                    self.app_module.requests, "post", return_value=token_response
                ), patch.object(self.app_module.requests, "get") as profile_request:
                    response = self.client.get(
                        f"/line/callback?code=fake-code&state={state}"
                    )
                self.assertEqual(response.status_code, 502)
                profile_request.assert_not_called()
                self.line_user_model.search_by_id.assert_not_called()

        invalid_profile_payloads = (
            {},
            {"userId": "", "displayName": "Demo"},
            {"userId": 7, "displayName": "Demo"},
            {"userId": "fake-user", "displayName": None},
        )
        for payload in invalid_profile_payloads:
            with self.subTest(payload=payload):
                login_response = self.client.get("/line/login")
                state = parse_qs(urlsplit(login_response.headers["Location"]).query)[
                    "state"
                ][0]
                token_response = MagicMock()
                token_response.json.return_value = {
                    "access_token": "fake-access-token"
                }
                profile_response = MagicMock()
                profile_response.json.return_value = payload
                with patch.object(
                    self.app_module.requests, "post", return_value=token_response
                ), patch.object(
                    self.app_module.requests, "get", return_value=profile_response
                ):
                    response = self.client.get(
                        f"/line/callback?code=fake-code&state={state}"
                    )
                self.assertEqual(response.status_code, 502)
                self.line_user_model.search_by_id.assert_not_called()

    def test_authorized_match_preserves_update_notification_and_redirect(self):
        token = self.get_csrf_token()
        with patch.dict(os.environ, {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}):
            response = self.client.post(
                "/match-member/match",
                data={
                    "csrf_token": token,
                    "line_user_id": "fake-line-user",
                    "member_id": "8",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/match-member"))
        self.line_user_model.update_member_id.assert_called_once_with(
            "fake-line-user", "8"
        )
        self.notifier.notify_management_message.assert_called_once()

    def test_authorized_ignore_preserves_update_and_redirect(self):
        token = self.get_csrf_token()
        with patch.dict(os.environ, {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}):
            response = self.client.post(
                "/match-member/ignore",
                data={"csrf_token": token, "line_user_id": "fake-line-user"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/match-member"))
        self.line_user_model.update_as_ignored.assert_called_once_with(
            "fake-line-user"
        )
        self.notifier.notify_management_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
