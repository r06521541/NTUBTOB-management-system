"""HTTP fail-closed checks and nested repository policy wiring, with fake I/O."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import test_admin_security as admin_fixture
from flask import Blueprint, Flask

KEY = "PORTAL_DATA_ERASURE_CHECKS_ENABLED"
UNAVAILABLE = "服務暫時無法使用，請稍後再試。"


class ErasureRuntimeTests(unittest.TestCase):
    _module = staticmethod(admin_fixture.MemberMatchingRouteTest._module)
    login = admin_fixture.MemberMatchingRouteTest.login

    @classmethod
    def setUpClass(cls):
        # The existing harness supplies fictional models; discard all ambient config.
        cls.isolated_environment = patch.dict(os.environ, {}, clear=True)
        cls.isolated_environment.start()
        cls.addClassCleanup(cls.isolated_environment.stop)
        # Other demo suites may have cached envs with no session key. Never reuse
        # their module (or read real credentials) when composing this fixture.
        cls.fictional_envs = patch.dict(
            sys.modules,
            {
                "envs": cls._module(
                    secret_key="fictional-erasure-runtime-session-key",
                    login_channel_id="fictional-channel",
                    login_channel_secret="fictional-channel-secret",
                )
            },
        )
        cls.fictional_envs.start()
        cls.addClassCleanup(cls.fictional_envs.stop)
        admin_fixture.MemberMatchingRouteTest.setUpClass.__func__(cls)
        cls.addClassCleanup(
            admin_fixture.MemberMatchingRouteTest.tearDownClass.__func__, cls
        )

    def setUp(self):
        admin_fixture.MemberMatchingRouteTest.setUp(self)

    def test_invalid_or_phase_c_mismatch_returns_fixed_503_before_legacy_queries(self):
        cases = [{KEY: value} for value in ("", "TRUE", "false ", "fictional-private")]
        cases.extend(
            {KEY: "true", "PORTAL_DATA_PHASE_C_ENABLED": value}
            for value in ("false", "TRUE", " true")
        )
        cases.append({KEY: "true"})
        for environment in cases:
            for path in ("/account", "/match-member"):
                with self.subTest(environment=environment, path=path):
                    self.login()
                    with (
                        patch.dict(os.environ, environment, clear=True),
                        patch.object(self.app_module, "phase_c_repository") as factory,
                        self.assertLogs(self.app.logger, level="ERROR") as logs,
                    ):
                        response = self.client.get(path)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.get_data(as_text=True), UNAVAILABLE)
                    self.assertEqual(
                        [record.getMessage() for record in logs.records],
                        ["erasure_runtime_configuration_unavailable"],
                    )
                    factory.assert_not_called()
                    self.member_model.search_by_id.assert_not_called()
                    self.member_model.search_all.assert_not_called()
                    self.line_user_model.search_all_unknowns.assert_not_called()
                    self.notifier.notify_management_message.assert_not_called()

    def test_absent_and_false_keep_explicit_legacy_behavior(self):
        for raw in (None, "false"):
            environment = {
                "WEB_PORTAL_ADMIN_MEMBER_IDS": "7",
                "WEB_PORTAL_ADMIN_AUTHORITY_MODE": "legacy_allowlist",
            }
            if raw is not None:
                environment[KEY] = raw
            with self.subTest(raw=raw):
                self.login()
                self.line_user_model.search_all_unknowns.reset_mock()
                with patch.dict(os.environ, environment, clear=True):
                    response = self.client.get("/match-member")
                self.assertEqual(response.status_code, 200)
                self.line_user_model.search_all_unknowns.assert_called_once_with()

    def test_demo_validation_does_not_require_shared_runtime_or_allow_true(self):
        for raw, expected in ((None, 404), ("false", 404), ("true", 503), ("", 503)):
            environment = {} if raw is None else {KEY: raw}
            with (
                self.subTest(raw=raw),
                patch.dict(os.environ, environment, clear=True),
                patch.object(self.app_module, "DEMO_MODE_ENABLED", True),
                patch.dict(sys.modules, {"shared_module.portal_data.runtime": None}),
            ):
                response = self.client.get("/account")
            self.assertEqual(response.status_code, expected)
            if expected == 503:
                self.assertEqual(response.get_data(as_text=True), UNAVAILABLE)
            self.member_model.search_by_id.assert_not_called()

    def test_account_labels_pass_exact_policy_and_preserve_person_binding(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                principal = SimpleNamespace(
                    person=SimpleNamespace(
                        id=80,
                        member_id=7,
                        access_level="basic",
                        display_name="Fictional",
                    ),
                    identity=SimpleNamespace(id=81),
                )
                repository = MagicMock(engine=object(), erasure_checks_enabled=enabled)
                repository.resolve_principal_by_ids.return_value = principal
                adapter = MagicMock()
                adapter.linked_identity_labels.return_value = ()
                constructor = MagicMock(return_value=adapter)
                with self.client.session_transaction() as values:
                    values.update(person_id=80, auth_identity_id=81, member_id=7)
                with (
                    patch.dict(
                        os.environ,
                        {
                            # The nested adapter must copy the existing policy,
                            # not independently reparse the environment.
                            KEY: str(not enabled).lower(),
                            "PORTAL_DATA_PHASE_C_ENABLED": "true",
                            "WEB_PORTAL_ADMIN_AUTHORITY_MODE": "legacy_allowlist",
                        },
                        clear=True,
                    ),
                    patch.object(
                        self.app_module, "phase_c_repository", return_value=repository
                    ),
                    patch.dict(
                        sys.modules,
                        {
                            "shared_module.portal_data.mobile_repository": self._module(
                                MobileRepository=constructor
                            )
                        },
                    ),
                ):
                    response = self.client.get("/account")
                self.assertEqual(response.status_code, 200)
                constructor.assert_called_once_with(
                    repository.engine, erasure_checks_enabled=enabled
                )
                self.assertIs(
                    constructor.call_args.kwargs["erasure_checks_enabled"], enabled
                )
                adapter.linked_identity_labels.assert_called_once_with(80)
                self.member_model.search_by_id.assert_not_called()

    def test_identity_link_composition_passes_exact_policy_and_keeps_service_wiring(
        self,
    ):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                repository = SimpleNamespace(
                    engine=object(), erasure_checks_enabled=enabled
                )
                constructor = MagicMock()
                codec = MagicMock()
                service = MagicMock()
                blueprint_factory = MagicMock(
                    return_value=Blueprint("fictional_link", __name__)
                )
                modules = {
                    "shared_module.portal_data.mobile_repository": self._module(
                        MobileRepository=constructor
                    ),
                    "shared_module.identity_linking": self._module(
                        IdentityLinkProofCodec=codec, IdentityLinkService=service
                    ),
                    "shared_module.provider_verifiers": self._module(
                        GoogleIdTokenVerifier=MagicMock(),
                        LineIdTokenVerifier=MagicMock(),
                    ),
                    "identity_link_provider": self._module(
                        WebIdentityProviderPort=MagicMock()
                    ),
                    "identity_link_web": self._module(
                        create_identity_link_blueprint=blueprint_factory
                    ),
                }
                config = {
                    f"WEB_IDENTITY_LINK_{provider}_{suffix}": f"fictional-{provider}-{suffix}"
                    for provider in ("GOOGLE", "LINE")
                    for suffix in ("CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI")
                }
                fresh_app = Flask("fictional-erasure-link-composition")
                fresh_app.secret_key = "fictional-session-key"
                with (
                    patch.dict(os.environ, config, clear=True),
                    patch.dict(sys.modules, modules),
                    patch.object(self.app_module, "app", fresh_app),
                    patch.object(
                        self.app_module, "phase_c_repository", return_value=repository
                    ),
                ):
                    self.assertTrue(self.app_module.register_identity_link_routes())
                constructor.assert_called_once_with(
                    repository.engine, erasure_checks_enabled=enabled
                )
                self.assertIs(
                    constructor.call_args.kwargs["erasure_checks_enabled"], enabled
                )
                self.assertEqual(
                    service.call_args.args,
                    (constructor.return_value, codec.return_value),
                )
                self.assertEqual(set(service.call_args.kwargs), {"clock"})
                self.assertTrue(callable(service.call_args.kwargs["clock"]))
                self.assertIs(
                    blueprint_factory.call_args.kwargs["service"], service.return_value
                )
                self.assertIn("fictional_link", fresh_app.blueprints)

    def test_event_composition_passes_exact_policy_and_preserves_authority_arguments(
        self,
    ):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                repository = SimpleNamespace(
                    engine=object(), erasure_checks_enabled=enabled
                )
                constructor = MagicMock()
                service = MagicMock()
                with (
                    patch.object(
                        self.app_module,
                        "_event_management_context",
                        return_value=(repository, object()),
                    ),
                    patch.object(
                        self.app_module,
                        "_game_authority_inputs",
                        return_value=(frozenset({7}), False),
                    ),
                    patch.dict(
                        sys.modules,
                        {
                            "shared_module.portal_data.repository": self._module(
                                PostgresTeamPortalRepository=constructor
                            ),
                            "shared_module.portal_data.services": self._module(
                                PortalDataService=service
                            ),
                        },
                    ),
                ):
                    result = self.app_module._event_management_service()
                constructor.assert_called_once_with(
                    repository.engine,
                    frozenset({7}),
                    allow_persisted_event_managers=True,
                    erasure_checks_enabled=enabled,
                )
                self.assertIs(
                    constructor.call_args.kwargs["erasure_checks_enabled"], enabled
                )
                service.assert_called_once_with(constructor.return_value)
                self.assertIs(result, service.return_value)


if __name__ == "__main__":
    unittest.main()
