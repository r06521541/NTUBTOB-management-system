import html
import importlib
import logging
import os
import re
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
from urllib.parse import parse_qs, urlencode, urlsplit

from flask import Blueprint, Flask, session

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from admin_security import parse_admin_member_ids  # noqa: E402
from line_login import create_oauth_state  # noqa: E402
from role_policy import ROLE_ADMIN, Principal  # noqa: E402

from shared_lib.shared_module import (
    attendance_reply as attendance_reply_service,
)  # noqa: E402
from shared_lib.shared_module import event_read as event_read_contract  # noqa: E402
from shared_lib.shared_module.portal_data import (
    local_database as portal_local_database,
)  # noqa: E402
from shared_lib.shared_module.portal_data import (
    runtime as phase_c_runtime,
)  # noqa: E402


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
        cls.ballpark_model = MagicMock()
        cls.reply_model = MagicMock()
        cls.notifier = MagicMock()

        cls.attendance_analyzer = MagicMock()
        fake_modules = {
            "shared_module": types.ModuleType("shared_module"),
            "shared_module.models": types.ModuleType("shared_module.models"),
            "shared_module.models.games": cls._module(Game=cls.game_model),
            "shared_module.models.ballparks": cls._module(Ballpark=cls.ballpark_model),
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
            "shared_module.attendance_reply": attendance_reply_service,
            "shared_module.event_read": event_read_contract,
            "shared_module.settings": cls._module(
                local_timezone=timezone(timedelta(hours=8))
            ),
            "shared_module.message_templates": types.ModuleType(
                "shared_module.message_templates"
            ),
            "shared_module.message_templates.general_message": cls._module(
                reply_text_mapping={
                    1: "會出席",
                    2: "不出席",
                    3: "晚到",
                    4: "早退",
                    5: "未定",
                }
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
        self.ballpark_model.reset_mock()
        self.attendance_analyzer.reset_mock(return_value=True, side_effect=True)
        self.notifier.reset_mock()
        self.notifier.notify_management_message.side_effect = None
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

    def login_link(self, page, attribute, value):
        match = re.search(
            rf'<a\s+[^>]*{re.escape(attribute)}="{re.escape(value)}"[^>]*'
            r'href="([^"]+)"',
            page,
        )
        self.assertIsNotNone(match)
        return html.unescape(match.group(1))

    def commit_browser_login_bootstrap(self, client, response):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        bootstrap_location = response.headers["Location"]
        self.assertEqual(
            urlsplit(bootstrap_location).path, "/line/login/browser/bootstrap"
        )
        self.assertEqual(
            f"{urlsplit(bootstrap_location).scheme}://"
            f"{urlsplit(bootstrap_location).netloc}",
            canonical_origin,
        )
        return client.get(bootstrap_location)

    def browser_bootstrap_envelope(self, response):
        query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(set(query), {"initiation"})
        return query["initiation"][0]

    def complete_browser_login_bootstrap(self, client, response):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        bootstrap = self.commit_browser_login_bootstrap(client, response)
        authorization_location = bootstrap.headers["Location"]
        self.assertEqual(
            urlsplit(authorization_location).path, "/line/login/browser/authorize"
        )
        self.assertEqual(
            f"{urlsplit(authorization_location).scheme}://"
            f"{urlsplit(authorization_location).netloc}",
            canonical_origin,
        )
        return client.get(authorization_location)

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
        normal_href = self.login_link(choice_page, "data-login-mode", "normal")
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
                normal_href = self.login_link(page, "data-login-mode", "normal")
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

    def test_phase_c_subjectless_session_revalidates_internal_ids(self):
        principal = SimpleNamespace(
            person=SimpleNamespace(id=80, member_id=7, access_level="basic"),
            identity=SimpleNamespace(id=81),
        )
        repository = MagicMock()
        repository.resolve_principal_by_ids.return_value = principal
        with self.app.test_request_context("/account"):
            session.update(person_id=80, auth_identity_id=81)
            with patch.dict(
                os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
            ), patch.object(
                self.app_module, "phase_c_repository", return_value=repository
            ):
                loaded = self.app_module.load_phase_c_web_principal(session)
            self.assertIsNotNone(loaded)
            self.assertNotIn("user_id", session)
        repository.resolve_principal_by_ids.assert_called_once_with(81, 80)

    def test_phase_c_subjectless_account_lists_only_redacted_login_methods(self):
        principal = SimpleNamespace(
            person=SimpleNamespace(
                id=80,
                member_id=7,
                access_level="basic",
                display_name="Safe Member",
            ),
            identity=SimpleNamespace(id=81),
        )
        repository = MagicMock(engine=object())
        repository.resolve_principal_by_ids.return_value = principal
        mobile_repository = MagicMock()
        mobile_repository.linked_identity_labels.return_value = [
            {
                "provider": "line",
                "label": "LINE",
                "linked_at": datetime(2026, 8, 24, tzinfo=timezone.utc),
            }
        ]
        mobile_module = self._module(
            MobileRepository=MagicMock(return_value=mobile_repository)
        )
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=80, auth_identity_id=81, member_id=7)
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.dict(
            sys.modules,
            {"shared_module.portal_data.mobile_repository": mobile_module},
        ):
            response = self.client.get("/account")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("LINE", page)
        self.assertNotIn("provider_subject", page)
        self.assertNotIn("fake-authenticated-user", page)
        mobile_repository.linked_identity_labels.assert_called_once_with(80)

    def test_identity_link_blueprint_config_missing_fails_closed_before_repository(
        self,
    ):
        repository = MagicMock()
        names = {
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID": "",
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET": "",
            "WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI": "",
            "WEB_IDENTITY_LINK_LINE_CLIENT_ID": "",
            "WEB_IDENTITY_LINK_LINE_CLIENT_SECRET": "",
            "WEB_IDENTITY_LINK_LINE_REDIRECT_URI": "",
        }
        with patch.dict(os.environ, names, clear=False), patch.object(
            self.app_module, "phase_c_repository", repository
        ):
            self.assertFalse(self.app_module.register_identity_link_routes())
        repository.assert_not_called()

    def test_identity_link_blueprint_registers_only_with_complete_named_config(self):
        fresh_app = Flask("identity-link-production-composition")
        fresh_app.secret_key = "s" * 32
        repository = MagicMock(engine=object())
        blueprint = Blueprint("identity_link_composition_test", __name__)
        provider_port = MagicMock()
        service = MagicMock()
        modules = {
            "identity_link_provider": self._module(
                WebIdentityProviderPort=MagicMock(return_value=provider_port)
            ),
            "identity_link_web": self._module(
                create_identity_link_blueprint=MagicMock(return_value=blueprint)
            ),
            "shared_module.identity_linking": self._module(
                IdentityLinkProofCodec=MagicMock(),
                IdentityLinkService=MagicMock(return_value=service),
            ),
            "shared_module.portal_data.mobile_repository": self._module(
                MobileRepository=MagicMock()
            ),
            "shared_module.provider_verifiers": self._module(
                GoogleIdTokenVerifier=MagicMock(),
                LineIdTokenVerifier=MagicMock(),
            ),
        }
        config = {
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID": "fake-google-client",
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET": "fake-google-secret",
            "WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI": (
                "https://portal.example/api/v1/auth/identity-link/web/callback/google"
            ),
            "WEB_IDENTITY_LINK_LINE_CLIENT_ID": "fake-line-client",
            "WEB_IDENTITY_LINK_LINE_CLIENT_SECRET": "fake-line-secret",
            "WEB_IDENTITY_LINK_LINE_REDIRECT_URI": (
                "https://portal.example/api/v1/auth/identity-link/web/callback/line"
            ),
        }
        with patch.dict(os.environ, config, clear=False), patch.object(
            self.app_module, "app", fresh_app
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.dict(
            sys.modules, modules
        ):
            self.assertTrue(self.app_module.register_identity_link_routes())
        self.assertIn("identity_link_composition_test", fresh_app.blueprints)

    def test_phase_c_subjectless_disabled_unlinked_or_inactive_fails_closed(self):
        repository = MagicMock()
        repository.resolve_principal_by_ids.return_value = None
        with self.app.test_request_context("/account"):
            session.update(person_id=80, auth_identity_id=81, member_id=7)
            with patch.dict(
                os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
            ), patch.object(
                self.app_module, "phase_c_repository", return_value=repository
            ):
                self.assertIsNone(self.app_module.load_phase_c_web_principal(session))
            for key in ("person_id", "auth_identity_id", "member_id", "user_id"):
                self.assertNotIn(key, session)

    def test_phase_c_existing_line_session_keeps_legacy_loader_compatibility(self):
        principal = SimpleNamespace(
            person=SimpleNamespace(id=80, member_id=7, access_level="basic"),
            identity=SimpleNamespace(id=81),
        )
        repository = MagicMock()
        repository.resolve_line_principal.return_value = principal
        with self.app.test_request_context("/account"):
            session.update(
                user_id="existing-line-subject",
                person_id=80,
                auth_identity_id=81,
                member_id=7,
            )
            with patch.dict(
                os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
            ), patch.object(
                self.app_module, "phase_c_repository", return_value=repository
            ):
                self.assertIsNotNone(
                    self.app_module.load_phase_c_web_principal(session)
                )
        repository.resolve_line_principal.assert_called_once_with(
            "existing-line-subject"
        )
        repository.resolve_principal_by_ids.assert_not_called()

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

    def test_callback_rejection_logs_only_fixed_reason_categories(self):
        state = create_oauth_state(
            self.app.secret_key,
            "/attendance",
            "sentinel-state-nonce",
        )
        cases = (
            ("tampered-sentinel-state", None, "state_invalid_or_expired"),
            (state, None, "session_nonce_missing"),
            (state, "sentinel-other-nonce", "session_nonce_mismatch"),
        )
        for callback_state, session_nonce, expected_category in cases:
            with self.subTest(expected_category=expected_category):
                client = self.app.test_client()
                if session_nonce is not None:
                    with client.session_transaction() as current_session:
                        current_session["oauth_state_nonce"] = session_nonce
                with patch.object(
                    self.app_module.requests, "post"
                ) as token_request, self.assertLogs("app", level="WARNING") as captured:
                    response = client.get(
                        f"/line/callback?code=sentinel-code&state={callback_state}"
                    )

                self.assertEqual(response.status_code, 400)
                token_request.assert_not_called()
                self.assertEqual(
                    captured.output,
                    [
                        "WARNING:app:line_login_rejected "
                        f"category={expected_category}"
                    ],
                )
                diagnostic = "\n".join(captured.output)
                for sentinel in (
                    "sentinel-code",
                    "sentinel-state-nonce",
                    "sentinel-other-nonce",
                    "tampered-sentinel-state",
                ):
                    self.assertNotIn(sentinel, diagnostic)

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
        normal_href = self.login_link(page, "data-login-mode", "normal")
        browser_href = self.login_link(page, "data-login-mode", "browser")

        normal = self.client.get(normal_href)
        normal_query = parse_qs(urlsplit(normal.headers["Location"]).query)
        normal_return, normal_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, normal_query["state"][0], "/attendance"
        )

        browser_bootstrap = self.client.get(browser_href)
        browser = self.complete_browser_login_bootstrap(self.client, browser_bootstrap)
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
        bootstrap = self.client.get("/line/login?mode=browser&next=/future-games")
        response = self.complete_browser_login_bootstrap(self.client, bootstrap)
        authorization_query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(authorization_query["disable_auto_login"], ["true"])

    def test_browser_fallback_starts_a_fresh_bound_transaction(self):
        normal = self.client.get("/line/login?next=/future-games")
        normal_state = parse_qs(urlsplit(normal.headers["Location"]).query)["state"][0]
        with self.client.session_transaction() as current_session:
            normal_nonce = current_session["oauth_state_nonce"]

        bootstrap = self.client.get("/line/login?mode=browser&next=/future-games")
        committed = self.commit_browser_login_bootstrap(self.client, bootstrap)
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            fallback_nonce = current_session["oauth_state_nonce"]
            self.assertEqual(current_session["next_url"], "/future-games")
            self.assertIs(current_session["oauth_browser_bootstrap_pending"], True)
        fallback = self.client.get(committed.headers["Location"])
        fallback_state = parse_qs(urlsplit(fallback.headers["Location"]).query)[
            "state"
        ][0]

        self.assertNotEqual(normal_nonce, fallback_nonce)
        self.assertNotEqual(normal_state, fallback_state)
        next_url, state_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, fallback_state, "/attendance"
        )
        self.assertEqual(next_url, "/future-games")
        self.assertEqual(state_nonce, fallback_nonce)

    def test_browser_fallback_clears_existing_portal_session_before_new_transaction(
        self,
    ):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            current_session.update(
                user_id="existing-user",
                member_id=7,
                person_id=70,
                auth_identity_id=71,
                member_matching_csrf_token="old-csrf",
                oauth_state_nonce="old-nonce",
                next_url="/account",
            )

        bootstrap = self.client.get("/line/login?mode=browser&next=/future-games")
        committed = self.commit_browser_login_bootstrap(self.client, bootstrap)
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            self.assertEqual(
                set(current_session),
                {
                    "oauth_browser_bootstrap_consumed",
                    "oauth_browser_bootstrap_pending",
                    "oauth_state_nonce",
                    "next_url",
                },
            )
            fresh_nonce = current_session["oauth_state_nonce"]
        response = self.client.get(committed.headers["Location"])
        state = parse_qs(urlsplit(response.headers["Location"]).query)["state"][0]

        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            self.assertEqual(
                set(current_session),
                {"oauth_browser_bootstrap_consumed", "oauth_state_nonce"},
            )
        next_url, state_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, state, "/attendance"
        )
        self.assertEqual(next_url, "/future-games")
        self.assertEqual(state_nonce, fresh_nonce)
        self.assertNotEqual(fresh_nonce, "old-nonce")

    def test_normal_login_does_not_clear_existing_portal_session(self):
        with self.client.session_transaction() as current_session:
            current_session.update(
                user_id="existing-user",
                member_id=7,
                member_matching_csrf_token="existing-csrf",
            )

        self.client.get("/line/login?next=/future-games")

        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["user_id"], "existing-user")
            self.assertEqual(current_session["member_id"], 7)
            self.assertEqual(
                current_session["member_matching_csrf_token"], "existing-csrf"
            )

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
        bootstrap = self.client.get(
            "/line/login?mode=browser&next=https://attacker.example/path"
        )
        response = self.complete_browser_login_bootstrap(self.client, bootstrap)
        state = parse_qs(urlsplit(response.headers["Location"]).query)["state"][0]
        next_url, _ = self.app_module.load_oauth_state(
            self.app.secret_key, state, "/attendance"
        )
        self.assertEqual(next_url, "/attendance")

    def test_desktop_login_canonicalizes_host_before_callback_bound_session(self):
        class SerializableMember(int):
            @property
            def id(self):
                return int(self)

        client = self.app.test_client()
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        first = client.get(
            "/line/login?mode=browser&next=/attendance",
            base_url="https://alternate.example",
        )
        self.assertEqual(
            f"{urlsplit(first.headers['Location']).scheme}://"
            f"{urlsplit(first.headers['Location']).netloc}",
            canonical_origin,
        )
        self.assertNotIn("access.line.me", first.headers["Location"])

        bootstrap = self.commit_browser_login_bootstrap(client, first)
        with client.session_transaction(base_url=canonical_origin) as current_session:
            nonce = current_session["oauth_state_nonce"]
        authorization = client.get(bootstrap.headers["Location"])
        authorization_query = parse_qs(
            urlsplit(authorization.headers["Location"]).query
        )
        state = authorization_query["state"][0]
        return_path, state_nonce = self.app_module.load_oauth_state(
            self.app.secret_key, state, "/attendance"
        )
        self.assertEqual((return_path, state_nonce), ("/attendance", nonce))

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
            callback = client.get(
                f"/line/callback?code=fake-code&state={state}",
                base_url=canonical_origin,
            )

        self.assertEqual(callback.status_code, 302)
        self.assertEqual(callback.headers["Location"], "/attendance")
        with client.session_transaction(base_url=canonical_origin) as current_session:
            self.assertEqual(current_session["user_id"], "fake-authenticated-user")
            self.assertEqual(current_session["member_id"], 7)

    def test_browser_authorization_rejects_direct_or_invalid_bootstrap_safely(self):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        sentinels = (
            "sentinel-state",
            "sentinel-nonce",
            "sentinel-code",
            "sentinel-cookie",
            "https://attacker.example/private",
            "sentinel-identity",
        )
        cases = (
            {},
            {
                "oauth_browser_bootstrap_pending": True,
                "oauth_state_nonce": "sentinel-nonce",
                "next_url": "https://attacker.example/private",
            },
        )
        for session_values in cases:
            with self.subTest(session_values=bool(session_values)):
                client = self.app.test_client()
                with client.session_transaction(
                    base_url=canonical_origin
                ) as current_session:
                    current_session.update(session_values)
                with patch.object(
                    self.app_module, "create_oauth_state"
                ) as create_state, self.assertLogs("app", level="WARNING") as captured:
                    response = client.get(
                        "/line/login/browser/authorize?state=sentinel-state"
                        "&code=sentinel-code&cookie=sentinel-cookie",
                        base_url=canonical_origin,
                    )

                self.assertEqual(response.status_code, 400)
                self.assertNotIn("Location", response.headers)
                create_state.assert_not_called()
                self.assertEqual(
                    captured.output,
                    [
                        "WARNING:app:line_login_rejected "
                        "category=browser_bootstrap_invalid"
                    ],
                )
                diagnostic = "\n".join(captured.output)
                for sentinel in sentinels:
                    self.assertNotIn(sentinel, diagnostic)

    def test_canonical_bootstrap_host_check_does_not_depend_on_wsgi_scheme(self):
        canonical_host = urlsplit(self.app_module.LINE_REDIRECT_URI).netloc
        with self.app.test_request_context(
            "/line/login/browser/bootstrap?next=/attendance",
            base_url=f"http://{canonical_host}",
        ):
            self.assertTrue(self.app_module.is_canonical_line_callback_origin())

        generated = self.client.get(
            "/line/login?mode=browser&next=/attendance",
            base_url="http://alternate.example",
        )
        self.assertEqual(urlsplit(generated.headers["Location"]).scheme, "https")

    def test_browser_bootstrap_rejects_wrong_origin_before_state_creation(self):
        canonical_start = self.client.get("/line/login?mode=browser&next=/attendance")
        bootstrap_parts = urlsplit(canonical_start.headers["Location"])
        with self.client.session_transaction(
            base_url="https://alternate.example"
        ) as current_session:
            current_session["sentinel"] = "preserved"
        with patch.object(
            self.app_module, "create_oauth_state"
        ) as create_state, self.assertLogs("app", level="WARNING") as captured:
            response = self.client.get(
                f"{bootstrap_parts.path}?{bootstrap_parts.query}",
                base_url="https://alternate.example",
            )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Location", response.headers)
        create_state.assert_not_called()
        self.assertEqual(
            captured.output,
            ["WARNING:app:line_login_rejected " "category=browser_bootstrap_invalid"],
        )
        with self.client.session_transaction(
            base_url="https://alternate.example"
        ) as current_session:
            self.assertEqual(current_session["sentinel"], "preserved")

    def test_browser_bootstrap_requires_valid_signed_initiation_before_session_clear(
        self,
    ):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        valid_start = self.client.get(
            "/line/login?mode=browser&next=/future-games",
            base_url="https://alternate.example",
        )
        valid_envelope = self.browser_bootstrap_envelope(valid_start)
        serializer = self.app_module.URLSafeTimedSerializer(
            self.app.secret_key,
            salt=self.app_module.BROWSER_BOOTSTRAP_INITIATION_SALT,
        )
        wrong_purpose = serializer.dumps(
            {
                "purpose": "oauth-callback",
                "next": "/future-games",
                "nonce": "fake-initiation-nonce",
            }
        )
        malformed_payload = serializer.dumps(
            {"purpose": "line-browser-bootstrap", "next": "/future-games"}
        )
        cases = (
            "",
            "unsigned-value",
            f"{valid_envelope}tampered",
            wrong_purpose,
            malformed_payload,
        )
        for initiation in cases:
            with self.subTest(initiation=bool(initiation)):
                client = self.app.test_client()
                with client.session_transaction(
                    base_url=canonical_origin
                ) as current_session:
                    current_session["sentinel"] = "preserved"
                    current_session["oauth_state_nonce"] = "old-nonce"
                query = f"?initiation={initiation}" if initiation else ""
                with patch.object(
                    self.app_module, "create_oauth_state"
                ) as create_state:
                    response = client.get(
                        f"/line/login/browser/bootstrap{query}",
                        base_url=canonical_origin,
                    )

                self.assertEqual(response.status_code, 400)
                self.assertNotIn("Location", response.headers)
                create_state.assert_not_called()
                with client.session_transaction(
                    base_url=canonical_origin
                ) as current_session:
                    self.assertEqual(current_session["sentinel"], "preserved")
                    self.assertEqual(current_session["oauth_state_nonce"], "old-nonce")

    def test_browser_bootstrap_rejects_expired_initiation_before_session_clear(self):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        with patch("itsdangerous.timed.time.time", return_value=2_000_000_000):
            initiation = self.app_module.create_browser_bootstrap_initiation(
                "/attendance"
            )
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            current_session["sentinel"] = "preserved"
        with patch(
            "itsdangerous.timed.time.time",
            return_value=(
                2_000_000_000
                + self.app_module.BROWSER_BOOTSTRAP_INITIATION_MAX_AGE_SECONDS
                + 1
            ),
        ), patch.object(self.app_module, "create_oauth_state") as create_state:
            response = self.client.get(
                "/line/login/browser/bootstrap?"
                + urlencode({"initiation": initiation}),
                base_url=canonical_origin,
            )

        self.assertEqual(response.status_code, 400)
        create_state.assert_not_called()
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            self.assertEqual(current_session["sentinel"], "preserved")

    def test_browser_bootstrap_rejects_same_browser_replay_before_session_clear(self):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        start = self.client.get("/line/login?mode=browser&next=/attendance")
        bootstrap_url = start.headers["Location"]
        first = self.client.get(bootstrap_url)
        self.assertEqual(first.status_code, 302)
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            current_session["sentinel"] = "preserved"
            nonce = current_session["oauth_state_nonce"]

        with patch.object(self.app_module, "create_oauth_state") as create_state:
            replay = self.client.get(bootstrap_url)

        self.assertEqual(replay.status_code, 400)
        self.assertNotIn("Location", replay.headers)
        create_state.assert_not_called()
        with self.client.session_transaction(
            base_url=canonical_origin
        ) as current_session:
            self.assertEqual(current_session["sentinel"], "preserved")
            self.assertEqual(current_session["oauth_state_nonce"], nonce)

    def test_browser_bootstrap_initiation_cannot_be_loaded_as_callback_state(self):
        initiation = self.app_module.create_browser_bootstrap_initiation("/attendance")

        with self.assertRaises(self.app_module.InvalidOAuthState):
            self.app_module.load_oauth_state(
                self.app.secret_key, initiation, "/attendance"
            )

    def test_rejection_logging_failure_does_not_change_fail_closed_response(self):
        canonical_origin = self.app_module.LINE_REDIRECT_URI.rsplit("/", 2)[0]
        with patch.object(
            self.app_module.logger,
            "warning",
            side_effect=RuntimeError("fake logging failure"),
        ):
            response = self.client.get(
                "/line/login/browser/authorize",
                base_url=canonical_origin,
            )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Location", response.headers)

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
        options_href = urlsplit(self.login_link(page, "data-login-action", "options"))
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
        options_href = urlsplit(self.login_link(page, "data-login-action", "options"))
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
            {
                "person_id": 81,
                "display_name": "停用暱稱",
                "formal_name": "停用人員",
                "portal_access_level": "basic",
                "portal_status": "disabled",
                "status": "disabled",
                "member_id": None,
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
            active_only = self.client.get("/manage/people")
            all_people = self.client.get("/manage/people?show_inactive=1")
            pending = self.client.get("/manage/pending-identities")
        self.assertEqual(people.status_code, 200)
        self.assertIn("Person 管理".encode(), people.data)
        self.assertIn("暱稱".encode(), people.data)
        self.assertNotIn("顯示名稱".encode(), people.data)
        self.assertIn(b'href="/manage/people/80"', active_only.data)
        self.assertNotIn("停用人員".encode(), active_only.data)
        self.assertIn("停用人員".encode(), all_people.data)
        self.assertIn(b'name="show_inactive" value="1" checked', all_people.data)
        self.assertEqual(pending.status_code, 200)
        self.assertIn("待配對／待核可身分".encode(), pending.data)
        self.assertNotIn("Person 管理列表".encode(), pending.data)
        self.assertIn("暱稱".encode(), pending.data)
        self.assertNotIn("顯示名稱".encode(), pending.data)
        self.assertEqual(repository.person_directory.call_count, 3)
        repository.person_directory.assert_called_with(70)
        for item in repository.person_directory.return_value:
            self.assertNotIn("admin_note", item)
            self.assertNotIn("identity_id", item)
            self.assertNotIn("audit", item)
            self.assertNotIn("available_members", item)

    def test_people_filter_preserves_explicit_inactive_view_across_pagination(self):
        self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.person_directory.return_value = tuple(
            {
                "person_id": person_id,
                "display_name": f"Member {person_id}",
                "formal_name": f"Member {person_id}",
                "member_id": person_id,
                "portal_status": "inactive" if person_id == 99 else "active",
                "status": "inactive" if person_id == 99 else "active",
            }
            for person_id in range(73, 100)
        )
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            active_only = self.client.get("/manage/people?q=Member")
            second_page = self.client.get(
                "/manage/people?q=Member&show_inactive=1&page=2"
            )

        self.assertNotIn(b"Member 99", active_only.data)
        self.assertIn(b"Member 99", second_page.data)
        self.assertIn(
            b'href="/manage/people?q=Member&amp;show_inactive=1&amp;page=1"',
            second_page.data,
        )

    def test_pending_identity_chooser_lists_only_eligible_member_targets(self):
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
                    "nickname": "New LINE User",
                    "identity_status": "pending",
                    "ignored": False,
                    "stale": False,
                    "person_id": None,
                    "review_status": "open",
                },
            ),
            "people": (
                {
                    "person_id": 80,
                    "member_id": 8,
                    "display_name": "Active Target",
                    "formal_name": "Active Target",
                    "status": "active",
                },
                {
                    "person_id": 81,
                    "member_id": 9,
                    "display_name": "Inactive Target",
                    "formal_name": "Inactive Target",
                    "status": "inactive",
                },
                {
                    "person_id": 82,
                    "member_id": 10,
                    "display_name": "Disabled Target",
                    "formal_name": "Disabled Target",
                    "status": "disabled",
                },
                {
                    "person_id": 83,
                    "member_id": None,
                    "display_name": "No Member Link",
                    "formal_name": "No Member Link",
                    "status": "active",
                },
            ),
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
            page = self.client.get("/manage/pending-identities")
            forged = self.client.post(
                "/identity-admin/action",
                data={
                    "csrf_token": token,
                    "identity_id": "72",
                    "member_id": "10",
                    "action": "approve_member",
                    "reason": "Verified existing membership",
                    "request_id": "identity-action-72-test",
                },
            )

        html_page = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("請選擇既有成員", html_page)
        self.assertIn('value="8"', html_page)
        self.assertIn('value="9"', html_page)
        self.assertIn("Inactive Target（非活躍，配對後會啟用）", html_page)
        self.assertNotIn("Disabled Target", html_page)
        self.assertNotIn("No Member Link", html_page)
        rendered_forms = re.findall(r"<form\b.*?</form>", html_page, re.DOTALL)
        member_form = next(
            form for form in rendered_forms if 'value="approve_member"' in form
        )
        non_member_form = next(
            form for form in rendered_forms if 'value="approve_non_member"' in form
        )
        self.assertIn('name="member_id" required', member_form)
        self.assertNotIn('name="member_id"', non_member_form)
        for independent_action in ("approve_non_member", "ignore", "reject"):
            self.assertIn(f'value="{independent_action}"', non_member_form)
        self.assertEqual(forged.status_code, 400)
        repository.approve_member.assert_not_called()

    def test_pending_identity_chooser_has_disabled_empty_state(self):
        self.get_csrf_token()
        repository = MagicMock()
        repository.resolve_line_principal.return_value = SimpleNamespace(
            person=SimpleNamespace(id=70, member_id=7),
            identity=SimpleNamespace(id=71),
        )
        repository.admin_dashboard.return_value = {
            "identities": (
                {
                    "identity_id": 72,
                    "nickname": "New LINE User",
                    "identity_status": "pending",
                    "ignored": False,
                    "stale": False,
                    "person_id": None,
                    "review_status": "open",
                },
            ),
            "people": (),
            "audit": (),
        }
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
            response = self.client.get("/manage/pending-identities")

        page = response.get_data(as_text=True)
        self.assertIn("目前沒有可配對的既有成員", page)
        self.assertRegex(page, r'<select name="member_id"[^>]*disabled')
        self.assertRegex(page, r'value="approve_member"[^>]*disabled')

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

    def test_qualification_management_page_hides_maintenance_when_team_player_present(
        self,
    ):
        repository = MagicMock()
        repository.admin_dashboard.return_value = {
            "people": (
                {
                    "person_id": 80,
                    "display_name": "Demo Person",
                    "formal_name": "Demo Formal",
                    "member_id": 8,
                    "qualifications": ({"name": "team_player", "status": "active"},),
                },
            )
        }
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
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"team_player", page.data)
        self.assertNotIn("資格異動".encode(), page.data)

    def test_person_detail_hides_manage_button_when_team_player_present(self):
        repository = MagicMock()
        repository.admin_dashboard.return_value = {
            "people": (
                {
                    "person_id": 80,
                    "display_name": "Demo Person",
                    "formal_name": "Demo Formal",
                    "member_id": 8,
                    "status": "active",
                    "qualifications": ({"name": "team_player", "status": "active"},),
                },
            )
        }
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
            page = self.client.get("/manage/people/80")
        self.assertEqual(page.status_code, 200)
        self.assertIn("參與資格".encode(), page.data)
        self.assertNotIn("查看與管理".encode(), page.data)

    def test_person_detail_displays_localized_access_level(self):
        repository = MagicMock()
        repository.admin_dashboard.return_value = {
            "people": (
                {
                    "person_id": 80,
                    "display_name": "Demo Person",
                    "formal_name": "Demo Formal",
                    "member_id": 8,
                    "status": "active",
                    "access_level": "admin",
                    "qualifications": (),
                },
            )
        }
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
            page = self.client.get("/manage/people/80")
        self.assertEqual(page.status_code, 200)
        self.assertIn("管理員".encode(), page.data)
        self.assertNotIn(b">admin<", page.data)

    def test_person_detail_recent_attendance_shows_only_replied_games(self):
        repository = MagicMock()
        repository.admin_dashboard.return_value = {
            "people": (
                {
                    "person_id": 80,
                    "display_name": "Demo Person",
                    "formal_name": "Demo Formal",
                    "member_id": 8,
                    "status": "active",
                    "qualifications": (),
                },
            )
        }
        repository.person_attendance_insight.return_value = {
            "periods": (),
            "recent": (
                {
                    "game_id": 91,
                    "home_team": "已回覆主隊",
                    "away_team": "已回覆客隊",
                    "start_datetime": datetime(2026, 8, 1, tzinfo=timezone.utc),
                    "location": "球場 A",
                    "reply": 1,
                },
                {
                    "game_id": 92,
                    "home_team": "未回覆主隊",
                    "away_team": "未回覆客隊",
                    "start_datetime": datetime(2026, 8, 2, tzinfo=timezone.utc),
                    "location": "球場 B",
                    "reply": None,
                },
            ),
        }
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
            page = self.client.get("/manage/people/80?tab=attendance")
        self.assertEqual(page.status_code, 200)
        self.assertIn("已回覆主隊".encode(), page.data)
        self.assertNotIn("未回覆主隊".encode(), page.data)

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
        self.assertRegex(
            page.get_data(as_text=True),
            r"inactive\s+目標會轉為 active",
        )
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
        self.login()

        response = self.client.get("/game-roster/23")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/games/23/lineup-lab")
        self.game_model.search_by_id.assert_not_called()
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()

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

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/games/23/lineup-lab")
                repository.attendance_summary.assert_not_called()

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

        self.assertEqual(formal.status_code, 302)
        self.assertEqual(formal.headers["Location"], "/games/23/lineup-lab")
        self.assertEqual(display.status_code, 302)
        self.assertEqual(
            display.headers["Location"],
            "/games/23/lineup-lab?name_style=display",
        )
        self.assertEqual(invalid.status_code, 302)
        self.assertEqual(duplicate.status_code, 302)
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()
        with self.client.session_transaction() as current_session:
            self.assertNotIn("name_style", current_session)

    def test_attendance_loads_fresh_member_from_member_id(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = self.portal_game()
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

    def test_attendance_shows_uncertain_names_and_uses_display_name_style(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = self.portal_game()
        self.game_model.search_for_invited.return_value = [game]
        self.attendance_analyzer.get_attendance_of_game.return_value = {
            1: [SimpleNamespace(name="Display Attendee")],
            5: [SimpleNamespace(name="Uncertain Player")],
        }
        self.login()

        with patch.object(self.app_module, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "fake update time"
            response = self.client.get("/attendance?name_style=display")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Display Attendee".encode(), response.data)
        self.assertIn("Uncertain Player".encode(), response.data)
        self.assertIn("1 人".encode(), response.data)
        self.assertIn(b'href="/games/23?name_style=display"', response.data)
        self.attendance_analyzer.get_attendance_of_game.assert_called_once_with(
            23, use_display_name=True
        )

    def test_attendance_renders_future_games_style_card_summary(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = SimpleNamespace(
            id=23,
            home_team="NTUBTOB",
            away_team="Opponent",
            location="A球場",
            get_game_sign=lambda: "⚾",
            get_formatted_date=lambda: "8/10（六）",
            get_is_home_team=lambda: True,
            get_opponent=lambda: "Opponent",
            get_formatted_start_time_with_colon=lambda: "17:00",
            generate_short_summary_for_team=lambda: "legacy summary",
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
        html = response.get_data(as_text=True)
        self.assertIn("⚾", html)
        self.assertIn("8/10（六）", html)
        self.assertIn("NTUBTOB", html)
        self.assertIn("17:00", html)
        self.assertIn("A球場", html)
        self.assertNotIn("legacy summary", html)

    def test_attendance_reloads_games_and_replies_on_every_request(self):
        fresh_member = SimpleNamespace(id=7, name="Fresh Member")
        self.member_model.search_by_id.return_value = fresh_member
        game = self.portal_game()
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

    def test_phase_c_attendance_batches_all_games_in_one_repository_call(self):
        games = (SimpleNamespace(id=23), SimpleNamespace(id=24))
        repository = MagicMock()
        repository.attendance_summaries.return_value = {
            23: SimpleNamespace(
                participants=({"person_id": 70, "name": "甲", "reply": 1},)
            ),
            24: SimpleNamespace(
                participants=({"person_id": 71, "name": "乙", "reply": 5},)
            ),
        }

        with patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            result = self.app_module.attendance_for_games(games, "display")

        self.assertEqual(result[23][1][0]["name"], "甲")
        self.assertEqual(result[24][5][0]["name"], "乙")
        repository.attendance_summaries.assert_called_once()
        requested_ids = tuple(repository.attendance_summaries.call_args.args[0])
        self.assertEqual(requested_ids, (23, 24))
        self.assertTrue(
            repository.attendance_summaries.call_args.kwargs["use_display_name"]
        )
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()

    def test_successful_attendance_logs_one_bounded_timing_event(self):
        fresh_member = SimpleNamespace(id=7, name="member-name-sentinel")
        self.member_model.search_by_id.return_value = fresh_member
        game = self.portal_game()
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
        self.assertIn('href="/attendance"'.encode(), response.data)
        self.assertIn('href="/account"'.encode(), response.data)
        self.assertIn("一般使用者".encode(), response.data)
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
        self.assertIn("前往人員管理".encode(), response.data)
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

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/games/404/lineup-lab")
        self.game_model.search_by_id.assert_not_called()
        self.attendance_analyzer.get_attendance_of_game.assert_not_called()

    @staticmethod
    def portal_game(game_id=23):
        return SimpleNamespace(
            id=game_id,
            start_datetime=datetime(
                2026, 8, 10, 19, tzinfo=timezone(timedelta(hours=8))
            ),
            duration=120,
            home_team="NTUBTOB",
            away_team="示範隊",
            location="示範球場",
            cancellation_time=None,
            get_game_sign=lambda: "⚾",
            get_formatted_date=lambda: "8/10（一）",
            get_formatted_short_date=lambda: "8/10",
            get_formatted_start_time_with_colon=lambda: "19:00",
            get_formatted_end_time=lambda: "21:00",
            get_status_label=lambda now=None: "即將開打",
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
        self.assertIn("下一場準備好了嗎".encode(), response.data)
        self.assertIn("示範隊".encode(), response.data)
        self.assertIn('href="/games/23"'.encode(), response.data)
        with self.client.session_transaction() as current_session:
            csrf_token = current_session["member_matching_csrf_token"]
        self.assertIn(f'name="csrf_token" value="{csrf_token}"'.encode(), response.data)

    def test_dashboard_groups_all_games_on_first_calendar_day_before_later_games(self):
        first = self.portal_game(23)
        first.away_team = "第一場對手"
        first.get_opponent = lambda: "第一場對手"
        same_day = self.portal_game(24)
        same_day.start_datetime = first.start_datetime + timedelta(hours=3)
        same_day.away_team = "同日第二場對手"
        same_day.get_opponent = lambda: "同日第二場對手"
        same_day.get_formatted_start_time_with_colon = lambda: "22:00"
        later = self.portal_game(25)
        later.start_datetime = first.start_datetime + timedelta(days=1)
        later.away_team = "隔日對手"
        later.get_opponent = lambda: "隔日對手"
        later.get_formatted_date = lambda: "8/11（二）"
        self.member_model.search_by_id.return_value = SimpleNamespace(
            name="Fresh Member"
        )
        self.game_model.search_for_invited.return_value = [first, same_day, later]
        self.reply_model.search_by_member_id.return_value = [
            SimpleNamespace(
                id=1,
                game_id=24,
                reply=3,
                updated_at=datetime.now(timezone.utc),
            )
        ]
        self.login()

        response = self.client.get("/dashboard")

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        next_day = page.index('data-dashboard-group="next-game-day"')
        upcoming = page.index('data-dashboard-group="upcoming"')
        self.assertLess(next_day, page.index("第一場對手"))
        self.assertLess(page.index("第一場對手"), page.index("同日第二場對手"))
        self.assertLess(page.index("同日第二場對手"), upcoming)
        self.assertLess(upcoming, page.index("隔日對手"))
        for game_id in (23, 24, 25):
            self.assertIn(f'action="/games/{game_id}/attendance"', page)
        featured_cards = re.findall(
            r'<article class="portal-card portal-featured-game".*?</article>',
            page,
            re.DOTALL,
        )
        self.assertEqual(len(featured_cards), 2)
        for game_id, card in zip((23, 24), featured_cards):
            with self.subTest(game_id=game_id):
                self.assertIn("portal-date-tile", card)
                self.assertIn("portal-featured-game-hit-area", card)
                self.assertIn(f'action="/games/{game_id}/attendance"', card)
                self.assertIn("data-dashboard-reply-form", card)
                self.assertEqual(card.count('name="reply"'), 5)
                self.assertIn("先守（三壘側）", card)
        self.assertIn("晚到", featured_cards[1])
        self.assertEqual(page.count("data-dashboard-reply-dialog"), 1)
        reply_buttons = re.findall(
            r'<button class="portal-reply-button".*?</button>', page, re.DOTALL
        )
        self.assertEqual(len(reply_buttons), 15)
        self.assertTrue(all(" disabled" in button for button in reply_buttons))

    def test_dashboard_renders_weather_inside_calendar_day_window(self):
        self.member_model.search_by_id.return_value = SimpleNamespace(
            name="Fresh Member"
        )
        game = self.portal_game()
        game.start_datetime = datetime.now(timezone(timedelta(hours=8))) + timedelta(
            days=1
        )
        self.game_model.search_for_invited.return_value = [game]
        self.reply_model.search_by_member_id.return_value = []
        self.ballpark_model.search_by_name.return_value = SimpleNamespace()
        forecast = SimpleNamespace(
            location_label="臺北中正",
            rain_warning=False,
            points=(SimpleNamespace(hour=6, weather="☀️", rainfall=10, temperature=25),),
        )
        self.login()

        with patch.object(
            self.app_module, "load_dashboard_forecast", return_value=forecast
        ):
            response = self.client.get("/dashboard")
            weather_response = self.client.get("/dashboard/weather/23")

        self.assertEqual(response.status_code, 200)
        self.assertIn("天氣載入中".encode(), response.data)
        self.assertNotIn("臺北中正天氣預報".encode(), response.data)
        self.assertEqual(weather_response.status_code, 200)
        self.assertIn("臺北中正天氣預報".encode(), weather_response.data)
        self.assertIn("降雨 10%".encode(), weather_response.data)
        self.ballpark_model.search_by_name.assert_called_once_with("示範球場")

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

    def _event_repository(self, *, events=()):
        repository = MagicMock()
        principal = SimpleNamespace(
            person=SimpleNamespace(
                id=80,
                member_id=7,
                access_level="basic",
                portal_status="active",
            ),
            identity=SimpleNamespace(id=81, status="linked"),
        )
        repository.resolve_line_principal.return_value = principal
        repository.scoped_events.return_value = events
        return repository, principal

    @staticmethod
    def _event_fixture(*, status="published"):
        attendance = (
            {
                "own_reply": "maybe",
                "counts": {
                    "attending": 1,
                    "not_attending": 0,
                    "maybe": 1,
                    "unanswered": 2,
                },
                "activities": {
                    70: {
                        "own_reply": None,
                        "counts": {
                            "attending": 0,
                            "not_attending": 0,
                            "maybe": 0,
                            "unanswered": 4,
                        },
                    },
                    71: None,
                },
            }
            if status == "published"
            else None
        )
        return {
            "id": 7,
            "title": "校友盃台中行",
            "type": "trip",
            "status": status,
            "start_at": datetime(2026, 9, 12, 1, 30, tzinfo=timezone.utc),
            "end_at": datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc),
            "participation_category": "team_player",
            "attendance": attendance,
            "activities": (
                {
                    "id": 70,
                    "title": "集合出發",
                    "type": "gathering",
                    "position": 1,
                    "start_at": datetime(2026, 9, 12, 1, 30, tzinfo=timezone.utc),
                    "end_at": None,
                    "linked_game_id": None,
                },
                {
                    "id": 71,
                    "title": "校友盃第一戰",
                    "type": "game",
                    "position": 2,
                    "start_at": datetime(2026, 9, 12, 4, 0, tzinfo=timezone.utc),
                    "end_at": datetime(2026, 9, 12, 6, 0, tzinfo=timezone.utc),
                    "linked_game_id": 23,
                },
            ),
        }

    def _login_for_events(self):
        with self.client.session_transaction() as current_session:
            current_session.update(
                user_id="fake-authenticated-user",
                member_id=7,
                person_id=80,
                auth_identity_id=81,
            )

    def test_event_list_requires_authenticated_active_principal(self):
        response = self.client.get("/events")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            parse_qs(urlsplit(response.headers["Location"]).query),
            {"next": ["/events"]},
        )

    def test_event_list_renders_only_repository_scoped_public_projection(self):
        self._login_for_events()
        events = (
            self._event_fixture(),
            {**self._event_fixture(status="cancelled"), "id": 8, "title": "雨備聚餐"},
        )
        repository, _ = self._event_repository(events=events)
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.get("/events")

        self.assertEqual(response.status_code, 200)
        page = response.data.decode()
        self.assertIn("校友盃台中行", page)
        self.assertIn("雨備聚餐", page)
        self.assertIn("活動已取消", page)
        self.assertIn("/events/event_7", page)
        repository.scoped_events.assert_called_once_with(80)
        for private_value in (
            "invitee",
            "eligibility",
            "manager",
            "override reason",
            "provider_subject",
        ):
            self.assertNotIn(private_value, page)

    def test_event_list_has_explicit_empty_and_safe_error_states(self):
        self._login_for_events()
        repository, _ = self._event_repository()
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            empty = self.client.get("/events")
            repository.scoped_events.side_effect = RuntimeError(
                "sentinel database address and private row"
            )
            failed = self.client.get("/events")

        self.assertEqual(empty.status_code, 200)
        self.assertIn("目前沒有近期活動".encode(), empty.data)
        self.assertEqual(failed.status_code, 503)
        self.assertIn("活動暫時無法載入".encode(), failed.data)
        self.assertNotIn(b"sentinel", failed.data)

    def test_event_detail_renders_ordered_timeline_and_visible_game_link(self):
        self._login_for_events()
        repository, _ = self._event_repository()
        repository.scoped_event.return_value = self._event_fixture()
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.get("/events/event_7")

        self.assertEqual(response.status_code, 200)
        page = response.data.decode()
        self.assertLess(page.index("集合出發"), page.index("校友盃第一戰"))
        self.assertIn('href="/games/23"', page)
        self.assertIn("09:30", page)
        self.assertIn('action="/events/event_7/attendance"', page)
        self.assertIn(
            'action="/events/event_7/activities/activity_70/attendance"', page
        )
        self.assertIn('name="return_event" value="event_7"', page)
        self.assertIn("linked Game", page)
        repository.scoped_event.assert_called_once_with(80, 7)

    def test_event_attendance_posts_require_csrf_and_use_prg(self):
        self._login_for_events()
        repository, _ = self._event_repository()
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "event-reply-csrf"
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            missing = self.client.post(
                "/events/event_7/attendance", data={"reply": "attending"}
            )
            event = self.client.post(
                "/events/event_7/attendance",
                data={
                    "csrf_token": "event-reply-csrf",
                    "reply": "maybe",
                    "apply_all": "true",
                },
            )
            activity = self.client.post(
                "/events/event_7/activities/activity_70/attendance",
                data={
                    "csrf_token": "event-reply-csrf",
                    "reply": "not_attending",
                },
            )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(event.status_code, 302)
        self.assertEqual(event.headers["Location"], "/events/event_7")
        self.assertEqual(activity.status_code, 302)
        repository.reply_to_event_attendance.assert_called_once_with(
            80, 7, "maybe", True
        )
        repository.reply_to_activity_attendance.assert_called_once_with(
            80, 7, 70, "not_attending"
        )

    def test_event_detail_rejects_noncanonical_or_unscoped_keys(self):
        self._login_for_events()
        repository, _ = self._event_repository()
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            for key in (
                "event_0",
                "event_07",
                "event_-1",
                "event_9223372036854775808",
                "activity_7",
            ):
                with self.subTest(key=key):
                    self.assertEqual(self.client.get(f"/events/{key}").status_code, 404)
            repository.scoped_event.return_value = None
            self.assertEqual(self.client.get("/events/event_9").status_code, 404)

        repository.scoped_event.assert_called_once_with(80, 9)

    def test_event_detail_returns_safe_unavailable_state_on_read_failure(self):
        self._login_for_events()
        repository, _ = self._event_repository()
        repository.scoped_event.side_effect = RuntimeError(
            "sentinel database address and private row"
        )
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.get("/events/event_7")

        self.assertEqual(response.status_code, 503)
        self.assertIn("活動暫時無法載入".encode(), response.data)
        self.assertNotIn(b"sentinel", response.data)
        repository.scoped_event.assert_called_once_with(80, 7)

    def _event_management_service(self, *, status="draft"):
        service = MagicMock()
        service.managed_events.return_value = ()
        service.managed_event.return_value = {
            "id": 7,
            "title": "虛構管理活動",
            "event_type": "trip",
            "status": status,
            "start_at": datetime(2026, 9, 12, 1, 0, tzinfo=timezone.utc),
            "end_at": datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc),
            "version": 2,
            "eligibility": ("team_player",),
            "activities": (),
        }
        service.eligibility_preview.return_value = {
            "qualification_counts": {"team_player": 3},
            "candidate_count": 3,
            "candidates": ({"person_id": 10, "display_name": "虛構人工邀請對象"},),
            "overrides": (),
        }
        service.preview_event_notification.return_value = {
            "notification_type": "event_published",
            "recipient_count": 3,
            "revision": "a" * 64,
            "confirmation_text": "NOTIFY 3",
        }
        service.managed_guests.return_value = ()
        service.guest_candidates.return_value = ()
        return service

    def test_event_management_create_requires_csrf_and_uses_server_actor(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        principal.person.access_level = "officer"
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "event-csrf"
        payload = {
            "title": "台中移地活動",
            "event_type": "trip",
            "start_at": "2026-09-12T09:00",
            "eligibility": "team_player",
        }
        service.create_event.return_value = 7
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            missing = self.client.post("/manage/events/new", data=payload)
            saved = self.client.post(
                "/manage/events/new", data={**payload, "csrf_token": "event-csrf"}
            )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(saved.headers["Location"], "/manage/events/event_7")
        args = service.create_event.call_args.args
        self.assertEqual(args[:3], (80, "台中移地活動", "trip"))
        self.assertEqual(args[3].utcoffset(), timedelta(hours=8))

    def test_event_management_basic_and_unknown_roles_fail_before_service(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}, clear=False
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            for access_level in ("basic", "owner", ""):
                with self.subTest(access_level=access_level):
                    principal.person.access_level = access_level
                    self.assertEqual(self.client.get("/manage/events").status_code, 403)

        service.managed_events.assert_not_called()

    def test_event_management_production_uses_allowlist_not_persisted_role(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        cases = (
            ("basic", "7", 200),
            ("officer", "", 403),
            ("admin", "", 403),
        )
        for access_level, allowlist, expected in cases:
            with self.subTest(access_level=access_level, allowlist=allowlist):
                principal.person.access_level = access_level
                with patch.dict(
                    os.environ,
                    {
                        "PORTAL_DATA_PHASE_C_ENABLED": "true",
                        "WEB_PORTAL_ADMIN_MEMBER_IDS": allowlist,
                    },
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ), patch.object(
                    self.app_module,
                    "_event_management_service",
                    return_value=service,
                ):
                    response = self.client.get("/manage/events")
                self.assertEqual(response.status_code, expected)

        self.assertEqual(service.managed_events.call_count, 1)

    def test_event_management_local_preview_keeps_persisted_event_roles(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        for access_level, expected in (
            ("officer", 200),
            ("admin", 200),
            ("basic", 403),
        ):
            with self.subTest(access_level=access_level):
                principal.person.access_level = access_level
                with patch.dict(
                    os.environ,
                    {
                        "PORTAL_DATA_PHASE_C_ENABLED": "true",
                        "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
                    },
                ), patch.object(
                    self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ), patch.object(
                    self.app_module,
                    "_event_management_service",
                    return_value=service,
                ):
                    response = self.client.get("/manage/events")
                self.assertEqual(response.status_code, expected)

        self.assertEqual(service.managed_events.call_count, 2)

    def test_event_management_service_wires_runtime_authority_policy(self):
        cases = (
            (False, "basic", "7", frozenset({7}), False),
            (True, "officer", "", frozenset(), True),
        )
        for (
            local_preview,
            access_level,
            allowlist,
            expected_ids,
            expected_mode,
        ) in cases:
            with self.subTest(local_preview=local_preview):
                self._login_for_events()
                repository, principal = self._event_repository()
                principal.person.access_level = access_level
                adapter = MagicMock()
                service = MagicMock()
                service.managed_events.return_value = ()
                repository_constructor = MagicMock(return_value=adapter)
                service_constructor = MagicMock(return_value=service)
                repository_module = self._module(
                    PostgresTeamPortalRepository=repository_constructor
                )
                services_module = self._module(PortalDataService=service_constructor)
                with patch.dict(
                    os.environ,
                    {
                        "PORTAL_DATA_PHASE_C_ENABLED": "true",
                        "WEB_PORTAL_ADMIN_MEMBER_IDS": allowlist,
                    },
                ), patch.object(
                    self.app_module,
                    "LOCAL_PREVIEW_MODE_ENABLED",
                    local_preview,
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ), patch.dict(
                    sys.modules,
                    {
                        "shared_module.portal_data.repository": repository_module,
                        "shared_module.portal_data.services": services_module,
                    },
                ):
                    response = self.client.get("/manage/events")

                self.assertEqual(response.status_code, 200)
                repository_constructor.assert_called_once_with(
                    repository.engine,
                    expected_ids,
                    allow_persisted_event_managers=expected_mode,
                )
                service_constructor.assert_called_once_with(adapter)
                service.managed_events.assert_called_once_with(80)

    def test_event_management_keeps_lifecycle_and_identity_checks_fail_closed(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            principal.person.portal_status = "inactive"
            self.assertEqual(self.client.get("/manage/events").status_code, 403)

            principal.person.portal_status = "active"
            principal.identity.id = 999
            self.assertEqual(self.client.get("/manage/events").status_code, 302)

        service.managed_events.assert_not_called()
        with self.client.session_transaction() as current_session:
            self.assertNotIn("person_id", current_session)
            self.assertNotIn("auth_identity_id", current_session)

    def test_portal_navigation_uses_canonical_event_capability_in_production(self):
        cases = (
            ("basic", "7", "active", True),
            ("officer", "", "active", False),
            ("admin", "", "active", False),
            ("basic", "7", "inactive", False),
        )
        for access_level, allowlist, status, expected in cases:
            with self.subTest(
                access_level=access_level,
                allowlist=allowlist,
                status=status,
            ):
                repository, principal = self._event_repository()
                principal.person.access_level = access_level
                principal.person.portal_status = status
                with self.app.test_request_context("/events"):
                    session.update(
                        user_id="fake-authenticated-user",
                        member_id=7,
                        person_id=80,
                        auth_identity_id=81,
                    )
                    with patch.dict(
                        os.environ,
                        {
                            "PORTAL_DATA_PHASE_C_ENABLED": "true",
                            "WEB_PORTAL_ADMIN_MEMBER_IDS": allowlist,
                        },
                    ), patch.object(
                        self.app_module,
                        "phase_c_repository",
                        return_value=repository,
                    ):
                        self.assertIsNotNone(self.app_module.get_current_principal())
                        portal_context = self.app_module.inject_portal_copy()

                self.assertEqual(portal_context["can_manage_events"], expected)

    def test_portal_navigation_keeps_local_preview_event_roles(self):
        for access_level, expected in (
            ("officer", True),
            ("admin", True),
            ("basic", False),
        ):
            with self.subTest(access_level=access_level):
                repository, principal = self._event_repository()
                principal.person.access_level = access_level
                with self.app.test_request_context("/events"):
                    session.update(
                        user_id="fake-authenticated-user",
                        member_id=7,
                        person_id=80,
                        auth_identity_id=81,
                    )
                    with patch.dict(
                        os.environ,
                        {
                            "PORTAL_DATA_PHASE_C_ENABLED": "true",
                            "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
                        },
                    ), patch.object(
                        self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True
                    ), patch.object(
                        self.app_module,
                        "phase_c_repository",
                        return_value=repository,
                    ):
                        self.assertIsNotNone(self.app_module.get_current_principal())
                        portal_context = self.app_module.inject_portal_copy()

                self.assertEqual(portal_context["can_manage_events"], expected)

    def test_event_management_rejects_noncanonical_keys_before_repository_call(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        principal.person.access_level = "admin"
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            for key in ("event_0", "event_07", "7", "event_-1"):
                self.assertEqual(
                    self.client.get(f"/manage/events/{key}").status_code, 404
                )
        service.managed_event.assert_not_called()

    def test_event_management_post_keys_require_exact_prefix_and_canonical_range(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        principal.person.access_level = "admin"
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "event-csrf"
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            for key in (
                "activity_7",
                "event_0",
                "event_07",
                "event_9223372036854775808",
            ):
                with self.subTest(event_key=key):
                    response = self.client.post(
                        f"/manage/events/{key}/publish",
                        data={"csrf_token": "event-csrf", "request_id": "invalid"},
                    )
                    self.assertEqual(response.status_code, 404)
            for key in (
                "event_7",
                "person_7",
                "activity_0",
                "activity_07",
                "activity_9223372036854775808",
            ):
                with self.subTest(activity_key=key):
                    response = self.client.post(
                        f"/manage/events/event_7/activities/{key}/action",
                        data={
                            "csrf_token": "event-csrf",
                            "action": "delete",
                        },
                    )
                    self.assertEqual(response.status_code, 404)
            for key in (
                "event_7",
                "activity_7",
                "person_0",
                "person_07",
                "person_9223372036854775808",
            ):
                with self.subTest(person_key=key):
                    response = self.client.post(
                        "/manage/events/event_7/overrides",
                        data={"csrf_token": "event-csrf", "person_key": key},
                    )
                    self.assertEqual(response.status_code, 404)
        service.publish_event.assert_not_called()
        service.delete_activity.assert_not_called()
        service.set_invitee_override.assert_not_called()

    def test_event_management_renders_preview_and_explicit_publish_confirmation(self):
        self._login_for_events()
        service = self._event_management_service()
        repository, principal = self._event_repository()
        principal.person.access_level = "officer"
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            response = self.client.get("/manage/events/event_7")

        page = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("資格池預覽", page)
        self.assertIn("符合 3 人", page)
        self.assertIn("虛構人工邀請對象（人員 #10）", page)
        self.assertIn('action="/manage/events/event_7/publish"', page)
        self.assertIn("發布時固定邀請快照", page)
        self.assertNotIn("不得出現在預覽的姓名", page)

    def test_event_publish_and_cancel_are_csrf_post_redirect_get_without_notification(
        self,
    ):
        self._login_for_events()
        service = self._event_management_service(status="published")
        repository, principal = self._event_repository()
        principal.person.access_level = "admin"
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "event-csrf"
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            published = self.client.post(
                "/manage/events/event_7/publish",
                data={"csrf_token": "event-csrf", "request_id": "publish-web-1"},
            )
            cancelled = self.client.post(
                "/manage/events/event_7/cancel",
                data={"csrf_token": "event-csrf", "request_id": "cancel-web-1"},
            )

        self.assertEqual(published.status_code, 302)
        self.assertEqual(cancelled.status_code, 302)
        service.publish_event.assert_called_once_with(80, 7, "publish-web-1")
        service.cancel_event.assert_called_once_with(80, 7, "cancel-web-1")
        self.notifier.notify_management_message.assert_not_called()

    def test_event_notification_is_separate_server_scoped_and_csrf_guarded(self):
        self._login_for_events()
        service = self._event_management_service(status="published")
        repository, principal = self._event_repository()
        principal.person.access_level = "admin"
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "event-csrf"
        payload = {
            "notification_type": "event_published",
            "preview_revision": "a" * 64,
            "typed_confirmation": "NOTIFY 3",
            "request_id": "notify-web-fictional",
        }
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            page = self.client.get("/manage/events/event_7")
            rejected = self.client.post(
                "/manage/events/event_7/notification", data=payload
            )
            saved = self.client.post(
                "/manage/events/event_7/notification",
                data={**payload, "csrf_token": "event-csrf"},
            )

        self.assertEqual(page.status_code, 200)
        self.assertIn("收件者固定來自已發布快照，目前共 3 人", page.data.decode())
        self.assertNotIn('name="recipient', page.data.decode())
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(saved.status_code, 302)
        service.confirm_event_notification.assert_called_once_with(
            80,
            7,
            notification_type="event_published",
            preview_revision="a" * 64,
            typed_confirmation="NOTIFY 3",
            request_id="notify-web-fictional",
        )
        service.publish_event.assert_not_called()
        self.notifier.notify_management_message.assert_not_called()

    def test_guest_manager_defaults_active_and_posts_versioned_server_target(self):
        self._login_for_events()
        service = self._event_management_service()
        service.managed_guests.return_value = (
            {
                "person_id": 91,
                "display_name": "虛構客座",
                "state": "active",
                "valid_from": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 9, 10, tzinfo=timezone.utc),
                "version": 4,
                "member": False,
                "team_player_active": False,
            },
        )
        service.guest_candidates.return_value = (
            {"person_id": 92, "display_name": "虛構候選人"},
        )
        repository, principal = self._event_repository()
        principal.person.access_level = "admin"
        with self.client.session_transaction() as current_session:
            current_session["member_matching_csrf_token"] = "event-csrf"
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
            clear=False,
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ), patch.object(
            self.app_module, "_event_management_service", return_value=service
        ):
            page = self.client.get("/manage/guests")
            bad_state = self.client.get("/manage/guests?state=unknown")
            saved = self.client.post(
                "/manage/guests/person_91",
                data={
                    "csrf_token": "event-csrf",
                    "action": "revoke",
                    "expected_version": "4",
                    "reason": "虛構客座期結束",
                    "request_id": "guest-web-fictional",
                },
            )

        self.assertEqual(page.status_code, 200)
        rendered = page.data.decode()
        self.assertIn("虛構客座", rendered)
        self.assertIn("虛構候選人", rendered)
        self.assertNotIn("provider_subject", rendered)
        self.assertEqual(bad_state.status_code, 400)
        self.assertEqual(saved.status_code, 302)
        service.managed_guests.assert_called_once_with(80, "active")
        service.mutate_guest_qualification.assert_called_once_with(
            80,
            91,
            "revoke",
            expected_version=4,
            reason="虛構客座期結束",
            request_id="guest-web-fictional",
            valid_from=None,
            valid_until=None,
        )

    def test_game_reply_requires_csrf_and_uses_phase_c_repository(self):
        game = self.portal_game()
        game.start_datetime = datetime.now(timezone.utc) + timedelta(hours=6)
        self.game_model.search_by_id.return_value = game
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
        self.notifier.notify_management_message.assert_called_once_with(
            f"緊急！Demo Member臨時回覆{game.generate_short_summary_for_team()}這場：\n會出席"
        )

    def test_linked_game_reply_validates_event_scope_and_returns_with_prg(self):
        game = self.portal_game()
        game.start_datetime = datetime.now(timezone.utc) + timedelta(hours=6)
        self.game_model.search_by_id.return_value = game
        repository = MagicMock()
        repository.scoped_event.return_value = self._event_fixture()
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(
                person_id=70, member_matching_csrf_token="reply-csrf"
            )

        with patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            response = self.client.post(
                "/games/23/attendance",
                data={
                    "reply": "3",
                    "csrf_token": "reply-csrf",
                    "return_event": "event_7",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/events/event_7")
        repository.scoped_event.assert_called_once_with(70, 7)
        repository.reply_to_game.assert_called_once_with(70, 23, 3)

    def test_unchanged_game_reply_does_not_notify(self):
        game = self.portal_game()
        game.start_datetime = datetime.now(timezone.utc) + timedelta(hours=6)
        self.game_model.search_by_id.return_value = game
        repository = MagicMock()
        repository.reply_to_game.return_value = False
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(
                person_id=70, member_matching_csrf_token="reply-csrf"
            )

        with patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            response = self.client.post(
                "/games/23/attendance",
                data={"reply": "1", "csrf_token": "reply-csrf"},
            )

        self.assertEqual(response.status_code, 302)
        self.notifier.notify_management_message.assert_not_called()

    def test_notification_failure_does_not_turn_saved_reply_into_failure(self):
        game = self.portal_game()
        game.start_datetime = datetime.now(timezone.utc) + timedelta(hours=6)
        self.game_model.search_by_id.return_value = game
        repository = MagicMock()
        repository.reply_to_game.return_value = True
        self.notifier.notify_management_message.side_effect = RuntimeError(
            "fake notifier failure"
        )
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(
                person_id=70, member_matching_csrf_token="reply-csrf"
            )

        with patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            response = self.client.post(
                "/games/23/attendance",
                data={"reply": "1", "csrf_token": "reply-csrf"},
            )

        self.assertEqual(response.status_code, 302)
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
        now = datetime.now(timezone(timedelta(hours=8)))
        game.start_datetime = now + timedelta(days=2)
        game.cancellation_time = now if cancelled else None
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
            "/people/70/game-insights",
            "/games/23/attendance-report",
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

    def test_preview_admin_keeps_existing_read_only_management_surface(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        repository.admin_dashboard.return_value = {
            "identities": (),
            "people": (),
            "available_members": (),
            "audit": (),
        }
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
            },
        ), patch.object(
            self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            response = self.client.get(
                "/manage/pending-identities", base_url="http://localhost:8080"
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("待配對／待核可身分".encode(), response.data)
        repository.admin_dashboard.assert_called_once_with(70)

    def test_game_bridge_rejects_session_principal_mismatch_before_reads(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal()
        mismatch_cases = (
            {"person_id": 999, "auth_identity_id": 71},
            {"person_id": 70, "auth_identity_id": 999},
        )
        for session_values in mismatch_cases:
            with self.subTest(session_values=session_values):
                self.game_model.search_games.reset_mock()
                repository.attendance_summary.reset_mock()
                with self.client.session_transaction() as current_session:
                    current_session.clear()
                    current_session.update(
                        user_id="fake-authenticated-user",
                        member_id=7,
                        **session_values,
                    )
                with patch.dict(
                    os.environ,
                    {
                        "PORTAL_DATA_PHASE_C_ENABLED": "true",
                        "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
                    },
                ), patch.object(
                    self.app_module, "phase_c_repository", return_value=repository
                ):
                    response = self.client.get("/manage/games")
                self.assertEqual(response.status_code, 403)
                self.game_model.search_games.assert_not_called()
                repository.attendance_summary.assert_not_called()
                with self.client.session_transaction() as current_session:
                    for key in self.app_module.PHASE_C_SESSION_KEYS:
                        self.assertNotIn(key, current_session)

    def test_command_center_detail_insights_and_lineup_are_read_only(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal()
        repository.attendance_summary.return_value = self.command_summary()
        repository.person_attendance_insight.return_value = {
            "person_id": 70,
            "name": "虛構隊員",
            "periods": ({"label": "近 30 天", "rate": 80, "replied": 4, "total": 5},),
            "recent": (),
        }
        repository.game_attendance_report.return_value = {
            "game_id": 23,
            "home_team": "臺大",
            "away_team": "虛構隊",
            "start_datetime": datetime.now(timezone.utc),
            "attending": ({"person_id": 70, "name": "虛構隊員", "reply": 1},),
            "not_attending": (),
            "unanswered": (),
            "history_limit": 12,
            "minimum_rate": 0,
        }
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
                self.client.get("/games/23/lineup-lab"),
                self.client.get("/people/70/game-insights"),
                self.client.get("/games/23/attendance-report"),
            )
        self.assertTrue(all(response.status_code == 200 for response in pages))
        self.assertIn("GAME COMMAND CENTER".encode(), pages[0].data)
        self.assertIn("人數摘要".encode(), pages[1].data)
        self.assertIn("不是歷史邀請回覆率".encode(), pages[2].data)
        self.assertIn(b'id="lineup-lab"', pages[3].data)
        self.assertIn("虛構隊員".encode(), pages[3].data)
        self.assertIn("參賽回覆概況".encode(), pages[4].data)
        self.assertIn("尚未回覆".encode(), pages[5].data)
        self.assertIn("目前不參加／未定".encode(), pages[5].data)
        repository.game_attendance_report.assert_called_once_with(
            23, history_limit=12, minimum_rate=0
        )
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
            cancelled = self.client.get("/games/23/lineup-lab")
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

    def test_allowlisted_admin_can_assign_and_remove_officer(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        token = self.get_csrf_token()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            promoted = self.client.post(
                "/manage/people/80/access",
                data={
                    "csrf_token": token,
                    "action": "promote_officer",
                    "reason": "Assign game operations",
                    "request_id": "person-access-promote-80",
                },
            )
            demoted = self.client.post(
                "/manage/people/80/access",
                data={
                    "csrf_token": token,
                    "action": "demote_basic",
                    "reason": "Close game operations",
                    "request_id": "person-access-demote-80",
                },
            )
        self.assertEqual(promoted.status_code, 302)
        self.assertEqual(demoted.status_code, 302)
        self.assertEqual(
            repository.change_access.call_args_list,
            [
                call(
                    70,
                    80,
                    "officer",
                    "Assign game operations",
                    "person-access-promote-80",
                ),
                call(
                    70, 80, "basic", "Close game operations", "person-access-demote-80"
                ),
            ],
        )

    def test_admin_member_create_uses_formal_name_as_initial_display_name(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        repository.create_member.return_value = SimpleNamespace(id=80)
        token = self.get_csrf_token()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.post(
                "/manage/people/new",
                data={
                    "csrf_token": token,
                    "name": "林柏安",
                    "display_name": "Admin must not set this",
                    "reason": "Create a fictional member",
                    "request_id": "member-create-test-80",
                    "number": "18",
                },
            )
        self.assertEqual(response.status_code, 302)
        repository.create_member.assert_called_once_with(
            70,
            "林柏安",
            "林柏安",
            "Create a fictional member",
            "member-create-test-80",
            enroll_year=None,
            major=None,
            number=18,
            positions=None,
        )

    def test_admin_member_create_rejects_malformed_request_id(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        token = self.get_csrf_token()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            response = self.client.post(
                "/manage/people/new",
                data={
                    "csrf_token": token,
                    "name": "林柏安",
                    "reason": "Create a fictional member",
                    "request_id": "bad-request-id",
                },
            )
        self.assertEqual(response.status_code, 400)
        repository.create_member.assert_not_called()

    def test_access_route_rejects_officer_bad_action_and_csrf(self):
        repository = MagicMock()
        token = self.get_csrf_token()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        environment = {
            "PORTAL_DATA_PHASE_C_ENABLED": "true",
            "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
        }
        with patch.dict(os.environ, environment), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            bad_csrf = self.client.post(
                "/manage/people/80/access",
                data={"action": "promote_officer"},
            )
            bad_action = self.client.post(
                "/manage/people/80/access",
                data={
                    "csrf_token": token,
                    "action": "admin",
                    "reason": "Invalid role request",
                    "request_id": "person-access-invalid-80",
                },
            )
        self.assertEqual(bad_csrf.status_code, 400)
        self.assertEqual(bad_action.status_code, 400)
        repository.change_access.assert_not_called()

        repository.resolve_line_principal.return_value = self.command_principal(
            "officer"
        )
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            denied = self.client.post(
                "/manage/people/80/access",
                data={
                    "csrf_token": token,
                    "action": "promote_officer",
                    "reason": "Officer may not assign roles",
                    "request_id": "person-access-officer-80",
                },
            )
        self.assertEqual(denied.status_code, 403)
        repository.change_access.assert_not_called()

    def test_access_route_rejects_malformed_request_id_before_repository(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        token = self.get_csrf_token()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        cases = (
            None,
            "",
            "access-80",
            "person-access-測試",
            "person-access-" + "x" * 108,
        )
        with patch.dict(
            os.environ,
            {
                "PORTAL_DATA_PHASE_C_ENABLED": "true",
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
            },
        ), patch.object(self.app_module, "phase_c_repository", return_value=repository):
            for request_id in cases:
                with self.subTest(request_id=request_id):
                    data = {
                        "csrf_token": token,
                        "action": "promote_officer",
                        "reason": "Assign game operations",
                    }
                    if request_id is not None:
                        data["request_id"] = request_id
                    response = self.client.post("/manage/people/80/access", data=data)
                    self.assertEqual(response.status_code, 400)
        repository.change_access.assert_not_called()

    def test_management_hub_and_schedule_navigation_are_role_aware(self):
        repository = MagicMock()
        repository.attendance_summary.return_value = self.command_summary()
        self.game_model.search_games.return_value = [self.command_game()]
        self.login()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        cases = (
            ("basic", "", 403, False, False),
            ("officer", "", 200, False, False),
            ("basic", "7", 200, True, True),
        )
        for access, allowlist, expected, people_visible, events_visible in cases:
            with self.subTest(access=access, allowlist=allowlist):
                repository.resolve_line_principal.return_value = self.command_principal(
                    access
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
                    response = self.client.get("/manage")
                self.assertEqual(response.status_code, expected)
                if expected == 200:
                    self.assertIn("賽務管理".encode(), response.data)
                    self.assertEqual(
                        "人員管理".encode() in response.data, people_visible
                    )
                    self.assertEqual(
                        "活動管理".encode() in response.data, events_visible
                    )
                    self.assertIn('href="/manage/games"'.encode(), response.data)

    def test_role_aware_template_context_reuses_request_principal_resolution(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal(
            "officer"
        )
        repository.attendance_summary.return_value = self.command_summary()
        self.game_model.search_games.return_value = [self.command_game()]
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
            response = self.client.get("/manage")
        self.assertEqual(response.status_code, 200)
        repository.resolve_line_principal.assert_called_once_with(
            "fake-authenticated-user"
        )

    def test_fictional_demo_allows_only_access_post_on_exact_fixture(self):
        repository = MagicMock()
        repository.resolve_line_principal.return_value = self.command_principal("admin")
        repository.is_fictional_demo_fixture.return_value = True
        token = self.get_csrf_token()
        with self.client.session_transaction() as current_session:
            current_session.update(person_id=70, auth_identity_id=71)
        with patch.dict(
            os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}
        ), patch.object(
            self.app_module, "LOCAL_PREVIEW_MODE_ENABLED", True
        ), patch.object(
            self.app_module, "FICTIONAL_DEMO_MODE_ENABLED", True
        ), patch.object(
            self.app_module, "phase_c_repository", return_value=repository
        ):
            allowed = self.client.post(
                "/manage/people/80/access",
                data={
                    "csrf_token": token,
                    "action": "promote_officer",
                    "reason": "TASK-099 fictional access rehearsal",
                    "request_id": "person-access-80-officer",
                },
            )
            blocked = self.client.post(
                "/games/23/attendance",
                data={"csrf_token": token, "reply": "1"},
            )
        self.assertEqual(allowed.status_code, 302)
        self.assertEqual(blocked.status_code, 403)
        repository.change_access.assert_called_once()
        repository.reply_to_game.assert_not_called()

    def test_attendance_windows_safe_timestamp_uses_real_strftime(self):
        self.login()
        self.member_model.search_by_id.return_value = SimpleNamespace(
            id=7, name="Demo Member"
        )
        self.game_model.search_for_invited.return_value = []
        response = self.client.get("/attendance")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.get_data(as_text=True), r"更新於 \d{4}年\d{2}月\d{2}日"
        )


if __name__ == "__main__":
    unittest.main()
