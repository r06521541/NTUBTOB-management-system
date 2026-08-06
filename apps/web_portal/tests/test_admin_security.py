import importlib
import html
import logging
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, call, patch


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

        cls.attendance_analyzer = MagicMock()
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
            "shared_module.attendance_analyzer": cls.attendance_analyzer,
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
        self.game_model.reset_mock()
        self.attendance_analyzer.reset_mock()
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
            self.assertEqual(current_session["user_id"], "fake-authenticated-user")
            self.assertEqual(current_session["member_id"], 7)
            self.assertNotIn("member", current_session)
            self.assertNotIn("display_name", current_session)

    def test_protected_attendance_round_trip_preserves_destination(self):
        class SerializableMember(int):
            @property
            def id(self):
                return int(self)

        protected = self.client.get("/attendance")
        self.assertEqual(protected.status_code, 302)
        choice_url = protected.headers["Location"]
        self.assertEqual(
            parse_qs(urlsplit(choice_url).query), {"next": ["/attendance"]}
        )

        choice = self.client.get(choice_url)
        choice_page = html.unescape(choice.data.decode())
        normal_href = choice_page.split(
            'data-login-mode="normal" href="', 1
        )[1].split('"', 1)[0]
        self.assertEqual(normal_href, "/line/login?next=/attendance")

        authorization = self.client.get(normal_href)
        state = parse_qs(urlsplit(authorization.headers["Location"]).query)[
            "state"
        ][0]
        self.line_user_model.search_by_id.return_value = SimpleNamespace(member_id=7)
        self.member_model.search_by_id.return_value = SerializableMember(7)
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "fake-access-token"}
        profile_response = MagicMock()
        profile_response.json.return_value = {
            "userId": "fake-authenticated-user",
            "displayName": "Demo User",
        }
        with patch.object(
            self.app_module.requests, "post", return_value=token_response
        ), patch.object(
            self.app_module.requests, "get", return_value=profile_response
        ):
            callback = self.client.get(
                f"/line/callback?code=fake-code&state={state}"
            )

        self.assertEqual(callback.status_code, 302)
        self.assertEqual(callback.headers["Location"], "/attendance")

        self.game_model.search_for_invited.return_value = []
        with patch.object(self.app_module, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            attendance = self.client.get(callback.headers["Location"])
        self.assertEqual(attendance.status_code, 200)
        self.assertNotEqual(attendance.request.path, "/")

    def test_protected_member_destinations_survive_signed_state_round_trip(self):
        for path in ("/account", "/game-roster/23"):
            with self.subTest(path=path):
                client = self.app.test_client()
                protected = client.get(path)
                choice = client.get(protected.headers["Location"])
                page = html.unescape(choice.data.decode())
                normal_href = page.split(
                    'data-login-mode="normal" href="', 1
                )[1].split('"', 1)[0]
                authorization = client.get(normal_href)
                state = parse_qs(
                    urlsplit(authorization.headers["Location"]).query
                )["state"][0]
                with client.session_transaction() as current_session:
                    nonce = current_session["oauth_state_nonce"]
                return_path, state_nonce = self.app_module.load_oauth_state(
                    self.app.secret_key, state, "/attendance"
                )
                self.assertEqual(return_path, path)
                self.assertEqual(state_nonce, nonce)

    def test_successful_callback_logs_only_allowlisted_destination_category(self):
        class SerializableMember(int):
            @property
            def id(self):
                return int(self)

        sentinels = (
            "sentinel-code",
            "sentinel-state",
            "sentinel-nonce",
            "sentinel-access-token",
            "sentinel-line-user",
            "sentinel-display-name",
            "sentinel-cookie",
            "member_id=7",
            "/attendance?private=sentinel-query",
        )
        login = self.client.get(
            "/line/login?next=/attendance%3Fprivate%3Dsentinel-query"
        )
        state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
        self.assertNotEqual(state, "sentinel-state")
        self.line_user_model.search_by_id.return_value = SimpleNamespace(member_id=7)
        self.member_model.search_by_id.return_value = SerializableMember(7)
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "sentinel-access-token"}
        profile_response = MagicMock()
        profile_response.json.return_value = {
            "userId": "sentinel-line-user",
            "displayName": "sentinel-display-name",
        }
        with patch.object(
            self.app_module.requests, "post", return_value=token_response
        ), patch.object(
            self.app_module.requests, "get", return_value=profile_response
        ), self.assertLogs(self.app.logger.name, level="INFO") as captured:
            response = self.client.get(
                f"/line/callback?code=sentinel-code&state={state}",
                headers={"Cookie": "sentinel-cookie"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            captured.output,
            ["INFO:app:line_login_callback destination=attendance"],
        )
        diagnostic = "\n".join(captured.output)
        for sentinel in sentinels:
            with self.subTest(sentinel=sentinel):
                self.assertNotIn(sentinel, diagnostic)

    def test_logging_failure_does_not_block_successful_callback(self):
        class SerializableMember(int):
            @property
            def id(self):
                return int(self)

        class FailingHandler(logging.Handler):
            def emit(self, record):
                raise RuntimeError("sentinel logging failure")

        login = self.client.get("/line/login?next=/attendance")
        state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
        self.line_user_model.search_by_id.return_value = SimpleNamespace(member_id=7)
        self.member_model.search_by_id.return_value = SerializableMember(7)
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "fake-access-token"}
        profile_response = MagicMock()
        profile_response.json.return_value = {
            "userId": "fake-authenticated-user",
            "displayName": "Demo User",
        }
        failing_handler = FailingHandler()
        self.app.logger.addHandler(failing_handler)
        try:
            with patch.object(
                self.app_module.requests, "post", return_value=token_response
            ), patch.object(
                self.app_module.requests, "get", return_value=profile_response
            ):
                response = self.client.get(
                    f"/line/callback?code=fake-code&state={state}"
                )
        finally:
            self.app.logger.removeHandler(failing_handler)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/attendance")
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["user_id"], "fake-authenticated-user")
            self.assertEqual(current_session["member_id"], 7)

    def test_legacy_identity_payload_is_minimized_without_losing_other_state(self):
        legacy_member = {"id": 7, "name": "Legacy Member"}
        with self.client.session_transaction() as current_session:
            current_session.update(
                {
                    "user_id": "existing-user",
                    "member_id": 7,
                    "member": legacy_member,
                    "display_name": "Legacy Display Name",
                    "oauth_state_nonce": "active-nonce",
                    "next_url": "/future-games",
                    "member_matching_csrf_token": "csrf-token",
                    "demo_member": {"id": "demo-member-01"},
                }
            )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["user_id"], "existing-user")
            self.assertEqual(current_session["member_id"], 7)
            self.assertNotIn("member", current_session)
            self.assertNotIn("display_name", current_session)
            self.assertEqual(current_session["oauth_state_nonce"], "active-nonce")
            self.assertEqual(current_session["next_url"], "/future-games")
            self.assertEqual(
                current_session["member_matching_csrf_token"], "csrf-token"
            )
            self.assertEqual(
                current_session["demo_member"], {"id": "demo-member-01"}
            )

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
            self.assertNotIn("display_name", callback_session)
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

    def test_login_choice_page_has_explicit_normal_and_browser_actions(self):
        response = self.client.get("/redirect-to-login?next=/future-games")

        self.assertEqual(response.status_code, 200)
        page = response.data.decode()
        self.assertNotIn("http-equiv=\"refresh\"", page)
        self.assertNotIn("window.location", page)
        self.assertIn('href="/line/login?next=/future-games"', page)
        self.assertIn(
            'href="/line/login?mode=browser&amp;next=/future-games"', page
        )
        self.assertIn("在 LINE 中登入", page)
        self.assertIn("使用電腦瀏覽器登入", page)
        self.assertIn("請回到 LINE", page)
        self.assertIn("同一支手機也不適合使用 QR Code 登入", page)
        self.assertIn('/static/images/logo_square.png', page)
        self.assertNotIn("https://storage.googleapis.com", page)

    def test_login_choice_page_fails_closed_for_ambiguous_next(self):
        response = self.client.get(
            "/redirect-to-login?next=/attendance&next=/future-games"
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b"/line/login", response.data)

    def test_login_choices_preserve_safe_return_path_in_fresh_transactions(self):
        choice_page = self.client.get("/redirect-to-login?next=/future-games")
        page = html.unescape(choice_page.data.decode())
        normal_href = page.split('data-login-mode="normal" href="', 1)[1].split(
            '"', 1
        )[0]
        browser_href = page.split('data-login-mode="browser" href="', 1)[1].split(
            '"', 1
        )[0]

        normal = self.client.get(normal_href)
        normal_query = parse_qs(urlsplit(normal.headers["Location"]).query)
        normal_return, normal_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, normal_query["state"][0], "/attendance"
        )

        browser = self.client.get(browser_href)
        browser_query = parse_qs(urlsplit(browser.headers["Location"]).query)
        browser_return, browser_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, browser_query["state"][0], "/attendance"
        )

        self.assertEqual(normal_return, "/future-games")
        self.assertEqual(browser_return, "/future-games")
        self.assertNotEqual(normal_nonce, browser_nonce)
        self.assertNotEqual(normal_query["state"], browser_query["state"])
        self.assertNotIn("disable_auto_login", normal_query)
        self.assertEqual(browser_query["disable_auto_login"], ["true"])

    def test_login_choice_page_uses_safe_default_for_external_next(self):
        response = self.client.get(
            "/redirect-to-login?next=https://attacker.example/path"
        )
        page = html.unescape(response.data.decode())

        self.assertIn('href="/line/login?next=/"', page)
        self.assertIn('href="/line/login?mode=browser&next=/"', page)

    def test_normal_line_login_allows_auto_login(self):
        response = self.client.get("/line/login")
        authorization_query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertNotIn("disable_auto_login", authorization_query)

    def test_explicit_browser_fallback_disables_auto_login(self):
        response = self.client.get("/line/login?mode=browser&next=/future-games")
        authorization_query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(authorization_query["disable_auto_login"], ["true"])

    def test_browser_fallback_starts_a_fresh_bound_transaction(self):
        normal = self.client.get("/line/login?next=/future-games")
        normal_state = parse_qs(urlsplit(normal.headers["Location"]).query)["state"][0]
        with self.client.session_transaction() as current_session:
            normal_nonce = current_session["oauth_state_nonce"]

        fallback = self.client.get("/line/login?mode=browser&next=/future-games")
        fallback_state = parse_qs(urlsplit(fallback.headers["Location"]).query)[
            "state"
        ][0]
        with self.client.session_transaction() as current_session:
            fallback_nonce = current_session["oauth_state_nonce"]

        self.assertNotEqual(normal_nonce, fallback_nonce)
        self.assertNotEqual(normal_state, fallback_state)
        next_url, state_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, fallback_state, "/attendance"
        )
        self.assertEqual(next_url, "/future-games")
        self.assertEqual(state_nonce, fallback_nonce)

    def test_unknown_or_ambiguous_login_mode_fails_closed(self):
        for query in (
            "mode=automatic",
            "mode=browser&mode=automatic",
            "next=/attendance&next=/future-games",
        ):
            with self.subTest(query=query):
                response = self.client.get(f"/line/login?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("Location", response.headers)

    def test_browser_fallback_replaces_external_return_path(self):
        response = self.client.get(
            "/line/login?mode=browser&next=https://attacker.example/path"
        )
        state = parse_qs(urlsplit(response.headers["Location"]).query)["state"][0]
        next_url, _ = self.app_module.load_oauth_state(
            self.app.secret_key, state, "/attendance"
        )
        self.assertEqual(next_url, "/attendance")

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
            current_session["member"] = {"id": 7, "name": "Stale Member"}
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
        self.assertIn("返回登入說明".encode(), response.data)
        self.assertNotIn(b"fake-code", response.data)
        self.assertNotIn(b"tampered-state", response.data)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["user_id"], "stale-user")
            self.assertEqual(current_session["member_id"], 7)
            self.assertNotIn("member", current_session)
            self.assertNotIn("display_name", current_session)
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

    def test_nonce_mismatch_returns_to_login_options_with_safe_return_path(self):
        state = create_oauth_state(
            self.app.secret_key,
            "/future-games",
            "original-nonce",
        )
        with self.client.session_transaction() as current_session:
            current_session["oauth_state_nonce"] = "different-nonce"

        with patch.object(self.app_module.requests, "post") as token_request:
            response = self.client.get(
                f"/line/callback?code=old-code&state={state}"
            )

        self.assertEqual(response.status_code, 400)
        token_request.assert_not_called()
        page = html.unescape(response.data.decode())
        options_href = urlsplit(
            page.split('data-login-action="options" href="', 1)[1].split('"', 1)[0]
        )
        self.assertEqual(options_href.path, "/redirect-to-login")
        self.assertEqual(
            parse_qs(options_href.query), {"next": ["/future-games"]}
        )

        options = self.client.get(options_href.geturl())
        self.assertEqual(options.status_code, 200)
        options_page = html.unescape(options.data.decode())
        self.assertIn('href="/line/login?next=/future-games"', options_page)
        self.assertIn(
            'href="/line/login?mode=browser&next=/future-games"', options_page
        )
        self.assertNotIn("old-code", options_page)
        self.assertNotIn(state, options_page)
        with self.client.session_transaction() as current_session:
            self.assertNotIn("oauth_state_nonce", current_session)

    def test_tampered_state_fallback_uses_fixed_safe_default(self):
        response = self.client.get(
            "/line/callback?code=old-code&state=tampered-state"
        )
        page = html.unescape(response.data.decode())
        options_href = urlsplit(
            page.split('data-login-action="options" href="', 1)[1].split('"', 1)[0]
        )
        self.assertEqual(options_href.path, "/redirect-to-login")
        self.assertEqual(
            parse_qs(options_href.query), {"next": ["/attendance"]}
        )

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

    def test_roster_rejects_missing_or_invalid_member_session_before_queries(self):
        invalid_sessions = (
            {},
            {"user_id": "fake-user"},
            {"member_id": 7},
            {"user_id": "", "member_id": 7},
            {"user_id": "   ", "member_id": 7},
            {"user_id": 7, "member_id": 7},
            {"user_id": "fake-user", "member_id": True},
            {"user_id": "fake-user", "member_id": 0},
            {"user_id": "fake-user", "member_id": -1},
            {"user_id": "fake-user", "member_id": "7"},
        )
        for session_values in invalid_sessions:
            with self.subTest(session_values=session_values):
                with self.client.session_transaction() as current_session:
                    current_session.clear()
                    current_session.update(session_values)
                with patch.object(
                    self.app_module.requests, "get"
                ) as http_get, patch.object(
                    self.app_module.requests, "post"
                ) as http_post:
                    response = self.client.get("/game-roster/23")

                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    urlsplit(response.headers["Location"]).path,
                    "/redirect-to-login",
                )
                self.assertEqual(
                    parse_qs(urlsplit(response.headers["Location"]).query)["next"],
                    ["/game-roster/23"],
                )
                self.game_model.search_by_id.assert_not_called()
                self.attendance_analyzer.get_attendance_of_game.assert_not_called()
                self.member_model.search_by_id.assert_not_called()
                http_get.assert_not_called()
                http_post.assert_not_called()

    def test_valid_member_session_preserves_roster_response(self):
        game = SimpleNamespace(
            id=23,
            generate_summary_for_team=lambda: "Fictional game summary",
        )
        attending = SimpleNamespace(name="Demo Player")
        waiting = SimpleNamespace(name="Waiting Player")
        self.game_model.search_by_id.return_value = game
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [attending],
            5: [waiting],
        }
        self.login()

        response = self.client.get("/game-roster/23")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Demo Player".encode(), response.data)
        self.assertIn("Waiting Player".encode(), response.data)
        self.assertIn('href="/"'.encode(), response.data)
        self.assertIn('href="/attendance"'.encode(), response.data)
        self.assertIn('href="/account"'.encode(), response.data)
        self.game_model.search_by_id.assert_called_once_with(23)
        self.attendance_analyzer.get_attendance_of_game.assert_called_once_with(23)

    def test_attendance_loads_fresh_member_from_member_id(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = SimpleNamespace(
            id=23,
            generate_short_summary_for_team=lambda: "Fictional game summary",
        )
        self.game_model.search_for_invited.return_value = [game]
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [fresh_member]
        }
        self.login()

        with patch.object(self.app_module, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            response = self.client.get("/attendance")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Fresh Member".encode(), response.data)
        self.member_model.search_by_id.assert_called_once_with(7)
        self.game_model.search_for_invited.assert_called_once_with()
        self.attendance_analyzer.get_attendance_of_game.assert_called_once_with(23)

    def test_attendance_reloads_games_and_replies_on_every_request(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = SimpleNamespace(
            id=23,
            generate_short_summary_for_team=lambda: "Fictional game summary",
        )
        self.game_model.search_for_invited.return_value = [game]
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [fresh_member]
        }
        self.login()

        with patch.object(self.app_module, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            first = self.client.get("/attendance")
            second = self.client.get("/attendance")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.member_model.search_by_id.call_count, 2)
        self.assertEqual(self.game_model.search_for_invited.call_count, 2)
        self.assertEqual(
            self.attendance_analyzer.get_attendance_of_game.call_args_list,
            [call(23), call(23)],
        )

    def test_successful_attendance_logs_one_bounded_timing_event(self):
        fresh_member = SimpleNamespace(id=7, name="member-name-sentinel")
        self.member_model.search_by_id.return_value = fresh_member
        game = SimpleNamespace(
            id=23,
            generate_short_summary_for_team=lambda: "game-summary-sentinel",
        )
        self.game_model.search_for_invited.return_value = [game]
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [fresh_member]
        }
        self.login()
        clock_values = iter((10.000, 10.003, 10.008, 10.021, 10.023, 10.030))
        timing_type = self.app_module.AttendanceTiming

        with patch.object(
            self.app_module,
            "AttendanceTiming",
            side_effect=lambda: timing_type(clock=lambda: next(clock_values)),
        ), patch.object(self.app.logger, "info") as log_info, patch.object(
            self.app_module, "datetime"
        ) as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            response = self.client.get("/attendance?query=query-sentinel")

        self.assertEqual(response.status_code, 200)
        log_info.assert_called_once_with(
            "attendance_timing member_lookup_ms=%d games_query_ms=%d "
            "attendance_analysis_ms=%d render_ms=%d total_ms=%d",
            3,
            5,
            13,
            2,
            30,
        )
        log_text = " ".join(str(value) for value in log_info.call_args.args)
        for sentinel in (
            "member-name-sentinel",
            "game-summary-sentinel",
            "query-sentinel",
            "cookie",
            "oauth",
            "secret",
            "dsn",
        ):
            self.assertNotIn(sentinel, log_text.lower())
        self.member_model.search_by_id.assert_called_once_with(7)
        self.game_model.search_for_invited.assert_called_once_with()
        self.attendance_analyzer.get_attendance_of_game.assert_called_once_with(23)

    def test_attendance_logging_failure_preserves_success_response(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        self.game_model.search_for_invited.return_value = []
        self.login()

        with patch.object(
            self.app.logger,
            "info",
            side_effect=RuntimeError("logging unavailable"),
        ), patch.object(self.app_module, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            response = self.client.get("/attendance")

        self.assertEqual(response.status_code, 200)
        self.member_model.search_by_id.assert_called_once_with(7)
        self.game_model.search_for_invited.assert_called_once_with()
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()

    def test_attendance_has_no_cache_invalidation_route(self):
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}

        self.assertNotIn("/clear-cache/attendance", rules)

    def test_attendance_missing_member_clears_identity_before_other_queries(self):
        self.member_model.search_by_id.return_value = None
        self.login()

        with patch.object(
            self.app_module.requests, "get"
        ) as http_get, patch.object(
            self.app_module.requests, "post"
        ) as http_post:
            response = self.client.get("/attendance")

        self.assertEqual(response.status_code, 403)
        self.member_model.search_by_id.assert_called_once_with(7)
        self.game_model.search_for_invited.assert_not_called()
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()
        http_get.assert_not_called()
        http_post.assert_not_called()
        with self.client.session_transaction() as current_session:
            self.assertNotIn("user_id", current_session)
            self.assertNotIn("member_id", current_session)

    def test_account_loads_fresh_member_and_shows_member_role(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            id=7, name="Fresh Member"
        )
        self.login()

        response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Fresh Member".encode(), response.data)
        self.assertIn('href="/"'.encode(), response.data)
        self.assertIn('href="/account"'.encode(), response.data)
        self.assertIn("一般隊員".encode(), response.data)
        self.assertIn("LINE".encode(), response.data)
        self.assertNotIn("前往 Member 配對".encode(), response.data)
        self.member_model.search_by_id.assert_called_once_with(7)

    def test_admin_account_uses_policy_for_role_and_management_entry(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            id=7, name="Admin Member"
        )
        self.login()

        with patch.dict(os.environ, {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}):
            response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn("系統管理者".encode(), response.data)
        self.assertIn("前往 Member 配對".encode(), response.data)
        self.assertIn('href="/match-member"'.encode(), response.data)

    def test_account_missing_member_clears_identity_without_other_queries(self):
        self.member_model.search_by_id.return_value = None
        self.login()

        with patch.object(self.app_module.requests, "get") as http_get, patch.object(
            self.app_module.requests, "post"
        ) as http_post:
            response = self.client.get("/account")

        self.assertEqual(response.status_code, 403)
        self.member_model.search_by_id.assert_called_once_with(7)
        self.game_model.search_for_invited.assert_not_called()
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()
        http_get.assert_not_called()
        http_post.assert_not_called()
        with self.client.session_transaction() as current_session:
            self.assertNotIn("user_id", current_session)
            self.assertNotIn("member_id", current_session)

    def test_account_malformed_identity_fails_before_member_lookup(self):
        with self.client.session_transaction() as current_session:
            current_session["user_id"] = "fake-user"
            current_session["member_id"] = "7"

        response = self.client.get("/account")

        self.assertEqual(response.status_code, 302)
        self.member_model.search_by_id.assert_not_called()

    def test_logout_is_post_only_and_bad_csrf_preserves_complete_session(self):
        self.login()
        with self.client.session_transaction() as current_session:
            current_session["logout_csrf_token"] = "correct-logout-token"
            current_session["oauth_state_nonce"] = "active-oauth"
            current_session["member_matching_csrf_token"] = "admin-token"

        self.assertEqual(self.client.get("/logout").status_code, 405)
        for csrf_value in (None, "", "wrong-token"):
            data = {} if csrf_value is None else {"csrf_token": csrf_value}
            response = self.client.post("/logout", data=data)
            self.assertEqual(response.status_code, 400)
            with self.client.session_transaction() as current_session:
                self.assertEqual(current_session["member_id"], 7)
                self.assertEqual(current_session["oauth_state_nonce"], "active-oauth")
                self.assertEqual(
                    current_session["member_matching_csrf_token"], "admin-token"
                )

    def test_valid_logout_clears_entire_session_and_protected_routes_relogin(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            id=7, name="Fresh Member"
        )
        self.login()
        account = self.client.get("/account")
        self.assertEqual(account.status_code, 200)
        with self.client.session_transaction() as current_session:
            token = current_session["logout_csrf_token"]
            current_session["oauth_state_nonce"] = "active-oauth"
            current_session["member_matching_csrf_token"] = "admin-token"
            current_session["demo_member"] = {"id": "fictional"}

        response = self.client.post("/logout", data={"csrf_token": token})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/redirect-to-login?next=/account",
        )
        with self.client.session_transaction() as current_session:
            self.assertEqual(dict(current_session), {})
        for path in ("/account", "/attendance", "/game-roster/23"):
            with self.subTest(path=path):
                protected = self.client.get(path)
                self.assertEqual(protected.status_code, 302)
                self.assertEqual(
                    urlsplit(protected.headers["Location"]).path,
                    "/redirect-to-login",
                )

    def test_logout_csrf_is_separate_from_member_matching_csrf(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            id=7, name="Fresh Member"
        )
        self.login()
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "admin-token"

        response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as current_session:
            self.assertNotEqual(
                current_session["logout_csrf_token"],
                current_session["member_matching_csrf_token"],
            )

    def test_attendance_malformed_identity_fails_before_member_lookup(self):
        for session_values in (
            {},
            {"user_id": "fake-user", "member_id": "7"},
            {"user_id": "", "member_id": 7},
            {"user_id": "fake-user", "member_id": True},
        ):
            with self.subTest(session_values=session_values):
                self.member_model.reset_mock()
                self.game_model.reset_mock()
                self.attendance_analyzer.reset_mock()
                with self.client.session_transaction() as current_session:
                    current_session.clear()
                    current_session.update(session_values)

                response = self.client.get("/attendance")

                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    urlsplit(response.headers["Location"]).path,
                    "/redirect-to-login",
                )
                self.member_model.search_by_id.assert_not_called()
                self.game_model.search_for_invited.assert_not_called()
                self.attendance_analyzer.get_attendance_of_game.assert_not_called()

    def test_missing_game_returns_404_without_attendance_query(self):
        self.game_model.search_by_id.return_value = None
        self.login()

        response = self.client.get("/game-roster/404")

        self.assertEqual(response.status_code, 404)
        self.game_model.search_by_id.assert_called_once_with(404)
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()


if __name__ == "__main__":
    unittest.main()
