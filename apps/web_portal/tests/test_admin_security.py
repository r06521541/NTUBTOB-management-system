import html
import importlib
import logging
import os
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
from urllib.parse import parse_qs, urlsplit

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from admin_security import parse_admin_member_ids  # noqa: E402
from line_login import create_oauth_state  # noqa: E402
from role_policy import ROLE_ADMIN, Principal  # noqa: E402

from shared_lib.shared_module.portal_data import (  # noqa: E402
    local_database as portal_local_database,
)
from shared_lib.shared_module.portal_data import (  # noqa: E402
    runtime as phase_c_runtime,
)


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
            "shared_module.models.line_users": cls._module(
                LineUser=cls.line_user_model
            ),
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
            "shared_module.portal_data": types.ModuleType("shared_module.portal_data"),
            "shared_module.portal_data.local_database": portal_local_database,
            "shared_module.portal_data.runtime": phase_c_runtime,
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
        self.attendance_analyzer.reset_mock(return_value=True, side_effect=True)
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
                        {} if value is None else {"WEB_PORTAL_ADMIN_MEMBER_IDS": value}
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
        self.assertIn("配對維護暫停中".encode(), second.data)
        self.assertGreaterEqual(second.data.count(b"disabled"), 3)

    def test_identity_maintenance_guard_fails_closed_before_side_effects(self):
        token = self.get_csrf_token()
        for value in (None, "", "false", "False", "TRUE", "1", "unknown", "true"):
            for path, extra_data in (
                ("/match-member/match", {"member_id": "8"}),
                ("/match-member/ignore", {}),
            ):
                with self.subTest(value=value, path=path):
                    self.line_user_model.reset_mock()
                    self.member_model.reset_mock()
                    self.notifier.reset_mock()
                    environment = {"WEB_PORTAL_ADMIN_MEMBER_IDS": "7"}
                    if value is not None:
                        environment["WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED"] = value
                    with patch.dict(os.environ, environment, clear=True):
                        response = self.client.post(
                            path,
                            data={
                                "csrf_token": token,
                                "line_user_id": "fake-line-user",
                                **extra_data,
                            },
                        )
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(
                        response.data,
                        b"Identity maintenance is temporarily unavailable",
                    )
                    self.assert_no_management_side_effects()

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
        with patch.object(
            self.app_module.requests, "post", return_value=token_response
        ), patch.object(self.app_module.requests, "get", return_value=profile_response):
            response = self.client.get(f"/line/callback?code=fake-code&state={state}")
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
        normal_href = choice_page.split('data-login-mode="normal" href="', 1)[1].split(
            '"', 1
        )[0]
        self.assertEqual(normal_href, "/line/login?next=/attendance")

        authorization = self.client.get(normal_href)
        state = parse_qs(urlsplit(authorization.headers["Location"]).query)["state"][0]
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
        ), patch.object(self.app_module.requests, "get", return_value=profile_response):
            callback = self.client.get(f"/line/callback?code=fake-code&state={state}")

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
                normal_href = page.split('data-login-mode="normal" href="', 1)[1].split(
                    '"', 1
                )[0]
                authorization = client.get(normal_href)
                state = parse_qs(urlsplit(authorization.headers["Location"]).query)[
                    "state"
                ][0]
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
        ), self.assertLogs(
            self.app.logger.name, level="INFO"
        ) as captured:
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

    def test_phase_c_callback_persists_person_identity_and_optional_member(self):
        login = self.client.get("/line/login?next=/attendance")
        state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "fake-access-token"}
        profile_response = MagicMock()
        profile_response.json.return_value = {
            "userId": "fake-phase-c-user",
            "displayName": "Phase C User",
        }
        identity = SimpleNamespace(id=81, status="linked")
        principal = SimpleNamespace(
            person=SimpleNamespace(id=80, member_id=None), identity=identity
        )
        repository = MagicMock()
        repository.ensure_pending_line_identity.return_value = SimpleNamespace(
            identity=identity, created=False
        )
        repository.resolve_line_principal.return_value = principal
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
        ), patch.object(
            self.app_module.requests, "post", return_value=token_response
        ), patch.object(
            self.app_module.requests, "get", return_value=profile_response
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            response = self.client.get(f"/line/callback?code=fake-code&state={state}")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["person_id"], 80)
            self.assertEqual(current_session["auth_identity_id"], 81)
            self.assertNotIn("member_id", current_session)

    def test_phase_c_callback_freeze_preserves_oauth_checks_and_has_zero_side_effects(
        self,
    ):
        login = self.client.get("/line/login?next=/attendance")
        state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
        repository = MagicMock()
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true",
            },
            clear=False,
        ), patch.object(
            self.app_module.requests, "post"
        ) as token_request, patch.object(
            self.app_module.requests, "get"
        ) as profile_request, patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            response = self.client.get(f"/line/callback?code=fake-code&state={state}")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.data, self.app_module.ROLLOUT_FREEZE_RESPONSE[0].encode()
        )
        token_request.assert_not_called()
        profile_request.assert_not_called()
        repository.assert_not_called()
        repository.ensure_pending_line_identity.assert_not_called()
        repository.resolve_line_principal.assert_not_called()
        self.line_user_model.search_by_id.assert_not_called()
        self.member_model.search_by_id.assert_not_called()
        self.notifier.notify_management_message.assert_not_called()

        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true",
            },
            clear=False,
        ), patch.object(self.app_module.requests, "post") as invalid_token_request:
            invalid = self.client.get(
                "/line/callback?code=fake-code&state=invalid-state"
            )
        self.assertEqual(invalid.status_code, 400)
        invalid_token_request.assert_not_called()

    def test_phase_c_refresh_fails_closed_without_legacy_fallback(self):
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=80, auth_identity_id=81)
        repository = MagicMock()
        repository.resolve_line_principal.return_value = None
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.get("/account")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/redirect-to-login", response.headers["Location"])
        with self.client.session_transaction() as current_session:
            self.assertNotIn("person_id", current_session)
            self.assertNotIn("member_id", current_session)

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
            self.assertEqual(current_session["demo_member"], {"id": "demo-member-01"})

    def test_callback_rejects_state_from_a_different_browser_session(self):
        login_client = self.app.test_client()
        callback_client = self.app.test_client()

        login_response = login_client.get("/line/login?next=/future-games")
        state = parse_qs(urlsplit(login_response.headers["Location"]).query)["state"][0]
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
        self.assertNotIn('http-equiv="refresh"', page)
        self.assertNotIn("window.location", page)
        self.assertIn('href="/line/login?next=/future-games"', page)
        self.assertIn('href="/line/login?mode=browser&amp;next=/future-games"', page)
        self.assertIn("在 LINE 中登入", page)
        self.assertIn("使用電腦瀏覽器登入", page)
        self.assertIn("請回到 LINE", page)
        self.assertIn("同一支手機也不適合使用 QR Code 登入", page)
        self.assertIn("/static/images/logo_square.png", page)
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
        normal_href = page.split('data-login-mode="normal" href="', 1)[1].split('"', 1)[
            0
        ]
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
            value for value in cookies if value.startswith("ntubtob_web_session_v2=")
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
            any(value.startswith("ntubtob_web_session_v2=") for value in cookies)
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
            response = self.client.get(f"/line/callback?code=old-code&state={state}")

        self.assertEqual(response.status_code, 400)
        token_request.assert_not_called()
        page = html.unescape(response.data.decode())
        options_href = urlsplit(
            page.split('data-login-action="options" href="', 1)[1].split('"', 1)[0]
        )
        self.assertEqual(options_href.path, "/redirect-to-login")
        self.assertEqual(parse_qs(options_href.query), {"next": ["/future-games"]})

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
        response = self.client.get("/line/callback?code=old-code&state=tampered-state")
        page = html.unescape(response.data.decode())
        options_href = urlsplit(
            page.split('data-login-action="options" href="', 1)[1].split('"', 1)[0]
        )
        self.assertEqual(options_href.path, "/redirect-to-login")
        self.assertEqual(parse_qs(options_href.query), {"next": ["/attendance"]})

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
            response = self.client.get(f"/line/callback?code=fake-code&state={state}")

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
                token_response.json.return_value = {"access_token": "fake-access-token"}
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
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.line_identity.return_value = SimpleNamespace(id=72)
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.post(
                "/match-member/match",
                data={
                    "csrf_token": token,
                    "line_user_id": "fake-line-user",
                    "member_id": "8",
                    "request_id": "identity-match-fake-request",
                    "reason": "Verified team membership",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/match-member"))
        repository.approve_member.assert_called_once_with(
            70, 72, 8, "Verified team membership", "identity-match-fake-request"
        )
        self.notifier.notify_management_message.assert_called_once()

    def test_admin_operations_have_separate_people_and_pending_routes(self):
        self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.person_directory.return_value = (
            {
                "person_id": 80,
                "display_name": "?梁迂",
                "formal_name": "甇??憪?",
                "portal_access_level": "basic",
                "portal_status": "active",
                "member_id": 8,
                "qualifications": (),
            },
        )
        repository.admin_dashboard.return_value = {
            "people": (
                {
                    "person_id": 80,
                    "display_name": "暱稱",
                    "formal_name": "正式姓名",
                    "member_id": 8,
                    "status": "active",
                },
            ),
            "identities": (
                {
                    "identity_id": 81,
                    "nickname": "pending",
                    "identity_status": "pending",
                },
            ),
            "available_members": (),
            "audit": (),
        }
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        environment = {
            "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
        }
        with patch.dict(os.environ, environment), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            people = self.client.get("/manage/people?q=正式")
            pending = self.client.get("/manage/pending-identities")
        self.assertEqual(people.status_code, 200)
        self.assertIn("Person 管理".encode(), people.data)
        self.assertIn("暱稱".encode(), people.data)
        self.assertNotIn("顯示名稱".encode(), people.data)
        self.assertEqual(pending.status_code, 200)
        self.assertIn("待配對／待核可身分".encode(), pending.data)
        self.assertNotIn("Person 管理列表".encode(), pending.data)
        self.assertIn("暱稱".encode(), pending.data)
        self.assertNotIn("顯示名稱".encode(), pending.data)
        repository.person_directory.assert_called_once_with(70)
        for item in repository.person_directory.return_value:
            self.assertNotIn("admin_note", item)
            self.assertNotIn("identity_id", item)
            self.assertNotIn("audit", item)
            self.assertNotIn("available_members", item)

    def test_match_rejects_malformed_transport_before_repository_lookup(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        values = (
            {},
            {"member_id": ""},
            {"member_id": "８"},
            {"member_id": "eight"},
            {"member_id": "0"},
            {"member_id": "-1"},
        )
        request_ids = (
            "wrong-prefix-1",
            "identity-match-非ascii",
            "identity-match-" + ("x" * 121),
        )
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            for extra in values:
                with self.subTest(payload=extra):
                    response = self.client.post(
                        "/match-member/match",
                        data={
                            "csrf_token": token,
                            "line_user_id": "fake-line-user",
                            "request_id": "identity-match-valid",
                            "reason": "Verified team membership",
                            **extra,
                        },
                    )
                    self.assertEqual(response.status_code, 400)
            for request_id in request_ids:
                with self.subTest(request_id=request_id):
                    response = self.client.post(
                        "/match-member/match",
                        data={
                            "csrf_token": token,
                            "line_user_id": "fake-line-user",
                            "member_id": "8",
                            "request_id": request_id,
                            "reason": "Verified team membership",
                        },
                    )
                    self.assertEqual(response.status_code, 400)
        repository.line_identity.assert_not_called()
        repository.approve_member.assert_not_called()

    def test_ignore_rejects_malformed_transport_before_repository_lookup(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        payloads = (
            {"line_user_id": ""},
            {"line_user_id": "使用者"},
            {"line_user_id": "x" * 256},
        )
        request_ids = (
            "wrong-prefix-1",
            "identity-ignore-非ascii",
            "identity-ignore-" + ("x" * 121),
        )
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            for extra in payloads:
                with self.subTest(payload=extra):
                    response = self.client.post(
                        "/match-member/ignore",
                        data={
                            "csrf_token": token,
                            "request_id": "identity-ignore-valid",
                            "reason": "Duplicate identity request",
                            **extra,
                        },
                    )
                    self.assertEqual(response.status_code, 400)
            for request_id in request_ids:
                with self.subTest(request_id=request_id):
                    response = self.client.post(
                        "/match-member/ignore",
                        data={
                            "csrf_token": token,
                            "line_user_id": "fake-line-user",
                            "request_id": request_id,
                            "reason": "Duplicate identity request",
                        },
                    )
                    self.assertEqual(response.status_code, 400)
        repository.line_identity.assert_not_called()
        repository.set_ignored.assert_not_called()

    def test_authorized_ignore_preserves_update_and_redirect(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.line_identity.return_value = SimpleNamespace(id=72)
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.post(
                "/match-member/ignore",
                data={
                    "csrf_token": token,
                    "line_user_id": "fake-line-user",
                    "request_id": "identity-ignore-fake-request",
                    "reason": "Duplicate identity request",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/match-member"))
        repository.set_ignored.assert_called_once_with(
            70, 72, True, "Duplicate identity request", "identity-ignore-fake-request"
        )
        self.notifier.notify_management_message.assert_not_called()

    def test_authorized_ignore_replays_exact_same_post_through_all_route_gates(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.line_identity.return_value = SimpleNamespace(id=72)
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        payload = {
            "csrf_token": token,
            "line_user_id": "fake-line-user",
            "request_id": "identity-ignore-fixed-retry",
            "reason": "Bounded closeout retry",
        }
        environment = {
            "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
        }
        with patch.dict(os.environ, environment), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            first = self.client.post("/match-member/ignore", data=payload)
            retry = self.client.post("/match-member/ignore", data=payload)
        self.assertEqual((first.status_code, retry.status_code), (302, 302))
        self.assertEqual(repository.set_ignored.call_count, 2)
        repository.set_ignored.assert_has_calls(
            [
                call(
                    70,
                    72,
                    True,
                    "Bounded closeout retry",
                    "identity-ignore-fixed-retry",
                )
            ]
            * 2
        )

    def test_phase_c_person_can_update_only_own_display_name(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=None),
            identity=SimpleNamespace(id=71),
        )
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.post(
                "/account/profile",
                data={
                    "csrf_token": token,
                    "request_id": "profile-fake-request",
                    "display_name": "Updated Display",
                },
            )
        self.assertEqual(response.status_code, 302)
        repository.update_profile.assert_called_once_with(
            70, 70, "Updated Display", "profile-fake-request"
        )

    def test_freeze_blocks_profile_and_admin_writes_after_auth_and_csrf(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        with self.client.session_transaction() as current_session:
            current_session.update(
                person_id=70,
                auth_identity_id=71,
                pending_identity_id=72,
            )
        environment = {
            "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
            "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true",
        }
        requests_to_test = (
            (
                "/account/profile",
                {
                    "csrf_token": token,
                    "request_id": "profile-frozen-request",
                    "display_name": "Blocked Display",
                },
            ),
            (
                "/identity-review",
                {
                    "csrf_token": token,
                    "request_id": "review-frozen-request",
                    "message": "Blocked review message",
                },
            ),
            (
                "/identity-admin/action",
                {
                    "csrf_token": token,
                    "action": "grant_qualification",
                    "person_id": "80",
                    "qualification": "staff",
                    "reason": "Blocked change",
                    "request_id": "qualification-frozen-request",
                },
            ),
            (
                "/match-member/match",
                {
                    "csrf_token": token,
                    "line_user_id": "fake-line-user",
                    "member_id": "8",
                },
            ),
            (
                "/match-member/ignore",
                {
                    "csrf_token": token,
                    "line_user_id": "fake-line-user",
                },
            ),
        )
        with patch.dict(os.environ, environment, clear=False), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            for path, data in requests_to_test:
                with self.subTest(path=path):
                    response = self.client.post(path, data=data)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(
                        response.data,
                        self.app_module.ROLLOUT_FREEZE_RESPONSE[0].encode(),
                    )

        repository.update_profile.assert_not_called()
        repository.post_review_message.assert_not_called()
        repository.grant_qualification.assert_not_called()
        repository.approve_member.assert_not_called()
        repository.set_ignored.assert_not_called()
        repository.line_identity.assert_not_called()
        self.notifier.notify_management_message.assert_not_called()

    def test_freeze_does_not_bypass_admin_or_csrf_guards(self):
        token = self.get_csrf_token()
        self.login(member_id=8)
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true",
            },
            clear=False,
        ), patch.object(
            self.app_module, "is_rollout_freeze_enabled", return_value=True
        ) as freeze_check:
            unauthorized = self.client.post(
                "/identity-admin/action", data={"csrf_token": token}
            )
        self.assertEqual(unauthorized.status_code, 403)
        freeze_check.assert_not_called()

        self.login()
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true",
            },
            clear=False,
        ), patch.object(
            self.app_module, "is_rollout_freeze_enabled", return_value=True
        ) as freeze_check:
            bad_csrf = self.client.post(
                "/identity-admin/action", data={"csrf_token": "wrong-token"}
            )
        self.assertEqual(bad_csrf.status_code, 400)
        freeze_check.assert_not_called()

    def test_phase_c_admin_qualification_action_uses_transactional_repository(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.post(
                "/identity-admin/action",
                data={
                    "csrf_token": token,
                    "action": "grant_qualification",
                    "person_id": "80",
                    "qualification": "staff",
                    "reason": "Assign event support",
                    "request_id": "qualification-fake-request",
                },
            )
        self.assertEqual(response.status_code, 302)
        repository.grant_qualification.assert_called_once_with(
            70,
            80,
            "staff",
            "Assign event support",
            "qualification-fake-request",
            valid_from=None,
            valid_until=None,
        )

    def test_qualification_management_page_posts_and_reads_back(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.admin_dashboard.side_effect = [
            {
                "people": (
                    {
                        "person_id": 80,
                        "display_name": "Demo Person",
                        "formal_name": "Demo Formal",
                        "member_id": 8,
                        "qualifications": ({"name": "affiliate", "status": "active"},),
                    },
                )
            },
            {
                "people": (
                    {
                        "person_id": 80,
                        "display_name": "Demo Person",
                        "formal_name": "Demo Formal",
                        "member_id": 8,
                        "qualifications": ({"name": "staff", "status": "active"},),
                    },
                )
            },
        ]
        with self.client.session_transaction() as current_session:
            current_session.update(
                person_id=70,
                auth_identity_id=71,
                user_id="line-user",
                member_id=7,
            )
        environment = {
            "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
        }
        with patch.dict(os.environ, environment), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch(
            "admin_security.get_current_principal",
            return_value=Principal(ROLE_ADMIN, 7),
        ):
            page = self.client.get("/manage/people/80/qualifications")
            response = self.client.post(
                "/manage/people/80/qualifications",
                data={
                    "csrf_token": token,
                    "action": "grant",
                    "qualification": "staff",
                    "reason": "Assign staff role",
                    "request_id": "qualification-80-test",
                },
            )
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"affiliate", page.data)
        self.assertNotIn(b'team_player"', page.data)
        self.assertEqual(response.status_code, 302)
        repository.grant_qualification.assert_called_once_with(
            70,
            80,
            "staff",
            "Assign staff role",
            "qualification-80-test",
            valid_from=None,
            valid_until=None,
        )

    def test_phase_c_admin_ui_and_route_require_confirmed_identity_remap(self):
        token = self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.admin_dashboard.return_value = {
            "identities": (
                {
                    "identity_id": 72,
                    "nickname": "Linked Applicant",
                    "identity_status": "linked",
                    "ignored": False,
                    "stale": False,
                    "person_id": 70,
                    "person_name": "Source Member",
                    "person_status": "active",
                    "member_id": 7,
                    "review_status": "closed",
                },
            ),
            "people": (
                {
                    "person_id": 70,
                    "member_id": 7,
                    "display_name": "Source Display",
                    "formal_name": "Source Member",
                    "status": "active",
                    "qualifications": (),
                    "admin_note": None,
                },
                {
                    "person_id": 80,
                    "member_id": 8,
                    "display_name": "Target Display",
                    "formal_name": "Target Member",
                    "status": "inactive",
                    "qualifications": (),
                    "admin_note": None,
                },
            ),
            "audit": (),
        }
        with self.client.session_transaction() as current_session:
            current_session.update(
                user_id="fake-admin-user",
                member_id=7,
                person_id=70,
                auth_identity_id=71,
            )
        environment = {
            "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
        }
        with patch.dict(os.environ, environment), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            page = self.client.get("/match-member")
            missing_confirmation = self.client.post(
                "/identity-admin/action",
                data={
                    "csrf_token": token,
                    "action": "remap",
                    "identity_id": "72",
                    "member_id": "8",
                    "reason": "Correct the verified Member mapping",
                    "request_id": "identity-remap-fake-request",
                },
            )
            remapped = self.client.post(
                "/identity-admin/action",
                data={
                    "csrf_token": token,
                    "action": "remap",
                    "identity_id": "72",
                    "member_id": "8",
                    "reason": "Correct the verified Member mapping",
                    "request_id": "identity-remap-fake-request",
                    "confirm_remap": "yes",
                },
            )

        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="confirm_remap"', page.data)
        self.assertIn(b'value="8"', page.data)
        self.assertIn("inactive 目標會轉為 active".encode(), page.data)
        self.assertEqual(missing_confirmation.status_code, 400)
        self.assertEqual(remapped.status_code, 302)
        repository.remap_member_identity.assert_called_once_with(
            70,
            72,
            8,
            "Correct the verified Member mapping",
            "identity-remap-fake-request",
            current_identity_id=71,
        )

    def test_phase_c_admin_ui_omits_remap_for_current_login_identity(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.admin_dashboard.return_value = {
            "identities": (
                {
                    "identity_id": 71,
                    "nickname": "Current Login",
                    "identity_status": "linked",
                    "ignored": False,
                    "stale": False,
                    "person_id": 70,
                    "person_name": "Admin Member",
                    "person_status": "active",
                    "member_id": 7,
                    "review_status": "closed",
                },
            ),
            "people": (),
            "audit": (),
        }
        with self.client.session_transaction() as current_session:
            current_session.update(
                user_id="fake-admin-user",
                member_id=7,
                person_id=70,
                auth_identity_id=71,
            )
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.get("/match-member")

        self.assertEqual(response.status_code, 200)
        self.assertIn("目前登入使用的 LINE 身分不可重新配對".encode(), response.data)
        self.assertNotIn(b'value="remap"', response.data)

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

    def test_valid_member_session_hides_unanswered_names_on_roster(self):
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
        self.assertNotIn("Waiting Player".encode(), response.data)
        self.assertIn("1 人".encode(), response.data)
        self.assertIn('href="/dashboard"'.encode(), response.data)
        self.assertIn('href="/future-games"'.encode(), response.data)
        self.assertIn('href="/attendance"'.encode(), response.data)
        self.assertIn('href="/account"'.encode(), response.data)
        self.game_model.search_by_id.assert_called_once_with(23)
        self.attendance_analyzer.get_attendance_of_game.assert_called_once_with(23)

    def test_phase_c_roster_hides_unanswered_names_for_all_active_people(self):
        game = SimpleNamespace(
            id=23,
            generate_summary_for_team=lambda: "Fictional game summary",
        )
        self.game_model.search_by_id.return_value = game
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [SimpleNamespace(name="Confirmed Player")],
            5: [
                SimpleNamespace(name="Unanswered Team Player"),
                SimpleNamespace(name="Unanswered Guest Player"),
                SimpleNamespace(name="Unanswered Viewer"),
            ],
        }

        for qualification, member_id in (
            ("team_player", 7),
            ("guest_player", None),
            (None, None),
        ):
            with self.subTest(qualification=qualification):
                repository = MagicMock()
                repository.resolve_line_principal.return_value = SimpleNamespace(
                    person=SimpleNamespace(
                        id=70,
                        member_id=member_id,
                        qualifications=(qualification,) if qualification else (),
                    ),
                    identity=SimpleNamespace(id=71),
                )
                with self.client.session_transaction() as current_session:
                    current_session.clear()
                    current_session.update(
                        user_id="fake-phase-c-user",
                        person_id=70,
                        auth_identity_id=71,
                    )
                    if member_id is not None:
                        current_session["member_id"] = member_id
                with patch.dict(
                    os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ):
                    response = self.client.get("/game-roster/23")

                self.assertEqual(response.status_code, 200)
                self.assertIn("Confirmed Player".encode(), response.data)
                self.assertIn("3 人".encode(), response.data)
                self.assertNotIn("Unanswered Team Player".encode(), response.data)
                self.assertNotIn("Unanswered Guest Player".encode(), response.data)
                self.assertNotIn("Unanswered Viewer".encode(), response.data)

    def test_roster_name_style_is_allowlisted_and_not_stored_in_session(self):
        game = SimpleNamespace(
            id=23,
            generate_summary_for_team=lambda: "Fictional game summary",
        )
        self.game_model.search_by_id.return_value = game

        def attendance_for_name_style(game_id, use_display_name=False):
            self.assertEqual(game_id, 23)
            name = "Display Player" if use_display_name else "Formal Player"
            return {1: [SimpleNamespace(name=name)]}

        self.attendance_analyzer.get_attendance_of_game.side_effect = (
            attendance_for_name_style
        )
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=None),
            identity=SimpleNamespace(id=71),
        )
        with self.client.session_transaction() as current_session:
            current_session.update(
                user_id="fake-active-person",
                person_id=70,
                auth_identity_id=71,
            )
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            formal = self.client.get("/game-roster/23")
            display = self.client.get("/game-roster/23?name_style=display")
            invalid = self.client.get("/game-roster/23?name_style=nickname")
            duplicate = self.client.get(
                "/game-roster/23?name_style=formal&name_style=display"
            )

        self.assertEqual(formal.status_code, 200)
        self.assertIn("Formal Player".encode(), formal.data)
        self.assertNotIn("Display Player".encode(), formal.data)
        self.assertEqual(display.status_code, 200)
        self.assertIn("Display Player".encode(), display.data)
        self.assertNotIn("Formal Player".encode(), display.data)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(
            self.attendance_analyzer.get_attendance_of_game.call_args_list,
            [call(23), call(23, use_display_name=True)],
        )
        with self.client.session_transaction() as current_session:
            self.assertNotIn("name_style", current_session)

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

    def test_attendance_hides_unanswered_names_and_uses_display_name_style(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = SimpleNamespace(
            id=23,
            generate_short_summary_for_team=lambda: "Fictional game summary",
        )
        self.game_model.search_for_invited.return_value = [game]
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [SimpleNamespace(name="Display Attendee")],
            5: [SimpleNamespace(name="Private Unanswered Name")],
        }
        self.login()

        with patch.object(self.app_module, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            response = self.client.get("/attendance?name_style=display")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Display Attendee".encode(), response.data)
        self.assertNotIn("Private Unanswered Name".encode(), response.data)
        self.assertIn("1 人".encode(), response.data)
        self.assertIn(b'href="/games/23?name_style=display"', response.data)
        self.attendance_analyzer.get_attendance_of_game.assert_called_once_with(
            23, use_display_name=True
        )

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

        with patch.object(self.app_module.requests, "get") as http_get, patch.object(
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
        self.assertIn('href="/dashboard"'.encode(), response.data)
        self.assertIn('href="/future-games"'.encode(), response.data)
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
        self.assertIn("前往 Person 管理".encode(), response.data)
        self.assertIn('href="/manage/people"'.encode(), response.data)

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

    @staticmethod
    def portal_game(game_id=23):
        return SimpleNamespace(
            id=game_id,
            start_datetime=SimpleNamespace(day=10, month=8),
            home_team="NTUBTOB",
            away_team="示範隊",
            location="示範球場",
            cancellation_time=None,
            get_game_sign=lambda: "⚾",
            get_formatted_date=lambda: "8/10（一）",
            get_formatted_start_time_with_colon=lambda: "19:00",
            get_formatted_end_time=lambda: "21:00",
            get_is_home_team=lambda: True,
            get_opponent=lambda: "示範隊",
            generate_short_summary_for_team=lambda: "8/10（一） 19:00 vs 示範隊 @示範球場",
            generate_summary_for_team=lambda: "示範賽事摘要",
        )

    def test_dashboard_renders_existing_game_contract(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            name="Fresh Member"
        )
        self.game_model.search_for_invited.return_value = [self.portal_game()]
        self.reply_model.search_by_member_id.return_value = []
        self.login()

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("準備好下一場了嗎".encode(), response.data)
        self.assertIn("示範隊".encode(), response.data)
        self.assertIn('href="/games/23"'.encode(), response.data)

    def test_game_detail_renders_attendance_and_csrf_form(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            name="Fresh Member"
        )
        self.game_model.search_by_id.return_value = self.portal_game()
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [SimpleNamespace(name="出席隊員")],
            5: [SimpleNamespace(name="未回覆隊員")],
        }
        self.reply_model.search_by_member_id.return_value = []
        self.login()

        response = self.client.get("/games/23")

        self.assertEqual(response.status_code, 200)
        self.assertIn("示範球場".encode(), response.data)
        self.assertIn('action="/games/23/attendance"'.encode(), response.data)
        self.assertIn("出席隊員".encode(), response.data)
        with self.client.session_transaction() as current_session:
            self.assertTrue(current_session.get("member_matching_csrf_token"))

    def test_game_reply_requires_csrf_and_uses_phase_c_repository(self):
        self.game_model.search_by_id.return_value = self.portal_game()
        repository = MagicMock()
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(
                person_id=70, member_matching_csrf_token="reply-csrf"
            )

        with patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            missing_csrf = self.client.post("/games/23/attendance", data={"reply": "1"})
            saved = self.client.post(
                "/games/23/attendance",
                data={"reply": "1", "csrf_token": "reply-csrf"},
            )

        self.assertEqual(missing_csrf.status_code, 400)
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(saved.headers["Location"], "/games/23")
        repository.reply_to_game.assert_called_once_with(70, 23, 1)

    def preview_repository(self):
        repository = MagicMock()
        repository.local_preview_identities.return_value = (
            {
                "identity_id": 40,
                "person_id": 10,
                "display_name": "預覽成員 abc123",
                "formal_name": "預覽姓名 abc123",
                "access_level": "officer",
                "member_id": 20,
            },
        )
        repository.local_preview_principal.return_value = SimpleNamespace(
            identity=SimpleNamespace(
                id=40,
                provider_subject="local-preview-identity",
            ),
            person=SimpleNamespace(id=10, member_id=20),
        )
        return repository

    def test_local_preview_identity_login_uses_pseudonymous_projection(self):
        repository = self.preview_repository()
        with (
            patch.object(self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True),
            patch.object(
                self.app_module, "phase_c_repository", return_value=repository
            ),
        ):
            chooser = self.client.get(
                "/local-preview/login", base_url="http://localhost:8080"
            )
            self.assertEqual(chooser.status_code, 200)
            self.assertIn("預覽姓名 abc123".encode(), chooser.data)
            self.assertNotIn(b"local-preview-identity", chooser.data)
            with self.client.session_transaction() as current_session:
                token = current_session["member_matching_csrf_token"]
            response = self.client.post(
                "/local-preview/login",
                data={"identity_id": "40", "csrf_token": token},
                base_url="http://localhost:8080",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard")
        repository.local_preview_principal.assert_called_once_with(40)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["person_id"], 10)
            self.assertEqual(current_session["auth_identity_id"], 40)
            self.assertEqual(current_session["member_id"], 20)
            self.assertEqual(current_session["user_id"], "local-preview-identity")

    def test_preview_rejects_external_routes_and_portal_mutations(self):
        repository = self.preview_repository()
        self.login()
        with self.client.session_transaction() as current_session:
            current_session["person_id"] = 10
            current_session["member_matching_csrf_token"] = "valid-csrf"
        with (
            patch.object(self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True),
            patch.object(
                self.app_module, "phase_c_repository", return_value=repository
            ),
        ):
            non_loopback = self.client.get(
                "/future-games", base_url="http://preview.example:8080"
            )
            line = self.client.get("/line/login", base_url="http://127.0.0.1:8080")
            mutation = self.client.post(
                "/games/23/attendance",
                data={"reply": "1", "csrf_token": "valid-csrf"},
                base_url="http://127.0.0.1:8080",
            )
        self.assertEqual(non_loopback.status_code, 404)
        self.assertEqual(line.status_code, 404)
        self.assertEqual(mutation.status_code, 403)
        repository.reply_to_game.assert_not_called()
        self.notifier.notify_management_message.assert_not_called()

    @staticmethod
    def command_summary():
        return SimpleNamespace(
            participants=(
                {
                    "person_id": 70,
                    "member_id": 7,
                    "name": "虛構隊員",
                    "reply": 1,
                    "qualification": "team_player",
                },
                {
                    "person_id": 80,
                    "member_id": None,
                    "name": "虛構來賓",
                    "reply": 3,
                    "qualification": "guest_player",
                },
            ),
            team_player_total=2,
            team_player_replied=1,
        )

    def command_principal(self, access_level="officer", status="active", member_id=7):
        return SimpleNamespace(
            person=SimpleNamespace(
                id=70,
                member_id=member_id,
                access_level=access_level,
                status=status,
            ),
            identity=SimpleNamespace(id=71),
        )

    def command_game(self, cancelled=False):
        game = self.portal_game()
        game.start_datetime = datetime.now() + timedelta(days=2)
        game.cancellation_time = datetime.now() if cancelled else None
        return game

    def test_bounded_game_routes_allow_officer_and_allowlisted_admin_only(self):
        repository = MagicMock()
        repository.attendance_summary.return_value = self.command_summary()
        self.game_model.search_games.return_value = [self.command_game()]
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        cases = (
            ("officer", "active", "", 200),
            ("basic", "active", "7", 200),
            ("basic", "active", "", 403),
            ("admin", "active", "", 403),
            ("officer", "disabled", "", 403),
        )
        for access, status, allowlist, expected in cases:
            with self.subTest(access=access, status=status, allowlist=allowlist):
                repository.resolve_line_principal.return_value = self.command_principal(
                    access, status
                )
                with patch.dict(
                    os.environ,
                    {
                        "PORTAL_DATA_PHASE_C_ENABLED": "true",
                        "WEB_PORTAL_ADMIN_MEMBER_IDS": allowlist,
                    },
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ):
                    response = self.client.get("/manage/games")
                self.assertEqual(response.status_code, expected)
        self.assertGreaterEqual(repository.resolve_line_principal.call_count, 5)

    def test_unauthenticated_command_routes_redirect_before_read_callers(self):
        for path in (
            "/manage/games",
            "/manage/games/23",
            "/manage/game-insights",
            "/manage/games/23/lineup-lab",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    urlsplit(response.headers["Location"]).path,
                    "/redirect-to-login",
                )
        self.game_model.search_games.assert_not_called()

    def test_person_officer_bridge_does_not_open_non_game_management(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal()
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            game_page = self.client.get("/manage/games")
            pending = self.client.get("/manage/pending-identities")
            qualifications = self.client.get("/manage/people/70/qualifications")
        self.assertIn(game_page.status_code, {200, 503})
        self.assertEqual(pending.status_code, 403)
        self.assertEqual(qualifications.status_code, 403)
        repository.admin_dashboard.assert_not_called()

    def test_command_center_detail_insights_and_lineup_are_read_only(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal()
        repository.attendance_summary.return_value = self.command_summary()
        game = self.command_game()
        self.game_model.search_games.return_value = [game]
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            pages = (
                self.client.get("/manage/games"),
                self.client.get("/manage/games/23"),
                self.client.get("/manage/game-insights"),
                self.client.get("/manage/games/23/lineup-lab"),
            )
        self.assertTrue(all(response.status_code == 200 for response in pages))
        self.assertIn("GAME COMMAND CENTER".encode(), pages[0].data)
        self.assertIn("不是歷史 Roster snapshot".encode(), pages[1].data)
        self.assertIn("不是歷史邀請回覆率".encode(), pages[2].data)
        self.assertIn("sessionStorage".encode(), pages[3].data)
        self.assertIn("虛構隊員".encode(), pages[3].data)
        for mutation in (
            "reply_to_game",
            "update_profile",
            "set_access",
            "grant_qualification",
        ):
            getattr(repository, mutation).assert_not_called()
        self.notifier.notify_management_message.assert_not_called()

    def test_command_routes_fail_closed_for_bad_scope_missing_and_cancelled(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal()
        repository.attendance_summary.return_value = self.command_summary()
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {"PORTAL_DATA_PHASE_C_ENABLED": "true"},
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            self.game_model.search_games.return_value = []
            missing = self.client.get("/manage/games/404")
            malformed = self.client.get("/manage/games/not-a-number")
            bad_scope = self.client.get("/manage/games?scope=future&scope=past")
            self.game_model.search_games.return_value = [
                self.command_game(cancelled=True)
            ]
            cancelled = self.client.get("/manage/games/23/lineup-lab")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(malformed.status_code, 404)
        self.assertEqual(bad_scope.status_code, 400)
        self.assertEqual(cancelled.status_code, 409)
        repository.reply_to_game.assert_not_called()

    def test_local_preview_game_routes_match_roles_and_keep_posts_blocked(self):
        repository = MagicMock()
        repository.attendance_summary.return_value = self.command_summary()
        self.game_model.search_games.return_value = [self.command_game()]
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        for access, expected in (("basic", 403), ("officer", 200), ("admin", 200)):
            with self.subTest(access=access):
                repository.resolve_line_principal.return_value = self.command_principal(
                    access
                )
                with patch.object(
                    self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ):
                    response = self.client.get(
                        "/manage/games", base_url="http://localhost:8080"
                    )
                self.assertEqual(response.status_code, expected)
        with patch.object(
            self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            blocked = self.client.post(
                "/manage/games", base_url="http://localhost:8080"
            )
        self.assertEqual(blocked.status_code, 403)
        repository.reply_to_game.assert_not_called()


if __name__ == "__main__":
    unittest.main()
