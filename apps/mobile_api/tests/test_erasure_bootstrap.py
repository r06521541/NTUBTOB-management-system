"""Exercise production bootstrap wiring without importing DB/provider runtimes."""

import os
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, sentinel

from shared_module.portal_data.erasure_intake import ErasureIntakeRepository
from sqlalchemy import create_engine

from apps.mobile_api import erasure_runtime
from apps.mobile_api.erasure_runtime import erasure_intake_enabled
from apps.mobile_api.tests.test_erasure_runtime import encoded
from shared_lib.shared_module.portal_data import runtime

BOOTSTRAP = Path(__file__).resolve().parents[1] / "bootstrap.py"


def module(**attributes):
    result = types.ModuleType("fictional_bootstrap_dependency")
    result.__dict__.update(attributes)
    return result


class ErasureBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.mobile = MagicMock(name="MobileRepository")
        self.identity = MagicMock(name="IdentityLifecycleRepository")
        self.fernet = MagicMock(name="Fernet")
        self.codec = MagicMock(name="HmacAccessTokenCodec")
        self.parser = MagicMock(wraps=runtime.erasure_checks_enabled)
        self.basic = MagicMock(name="BasicApiService")
        self.attendance = MagicMock(name="AttendanceReplyService")
        self.create_app = MagicMock(return_value=sentinel.app)
        self.dependencies = MagicMock(name="Dependencies")
        self.intake_parser = MagicMock(wraps=erasure_intake_enabled)
        self.intake_builder = MagicMock(return_value=sentinel.erasure_service)
        self.modules = {
            "app": module(Dependencies=self.dependencies, create_app=self.create_app),
            "apple_verifier": module(AppleIdTokenVerifier=MagicMock()),
            "google_verifier": module(GoogleIdTokenVerifier=MagicMock()),
            "line_verifier": module(LineIdTokenVerifier=MagicMock()),
            "erasure_runtime": module(
                erasure_intake_enabled=self.intake_parser,
                build_runtime_erasure_service=self.intake_builder,
            ),
            "cryptography.fernet": module(Fernet=self.fernet, InvalidToken=ValueError),
            "revision_readiness": module(
                apple_lifecycle_configuration_is_valid=MagicMock(return_value=False),
                database_revision_is_current=MagicMock(),
            ),
            "shared_module.attendance_reply": module(
                AttendanceReplyService=self.attendance
            ),
            "shared_module.identity_linking": module(
                IdentityLinkProofCodec=MagicMock(), IdentityLinkService=MagicMock()
            ),
            "shared_module.mobile_api": module(
                AppleLifecycleAuthService=MagicMock(),
                AppleNotificationService=MagicMock(),
                BasicApiService=self.basic,
                HmacAccessTokenCodec=self.codec,
                MobileApiError=ValueError,
                MobileAuthService=MagicMock(),
                PendingReviewService=MagicMock(),
            ),
            "shared_module.mobile_notifications": module(
                NotificationPublishingService=MagicMock()
            ),
            "shared_module.models.db": module(engine=sentinel.engine),
            "shared_module.portal_data.identity_lifecycle": module(
                IdentityLifecycleRepository=self.identity
            ),
            "shared_module.portal_data.mobile_repository": module(
                MobileRepository=self.mobile
            ),
            "shared_module.portal_data.runtime": module(
                erasure_checks_enabled=self.parser
            ),
            "shared_module.provider_verifiers": module(
                AppleAuthorizationCodeExchanger=MagicMock(),
                AppleServerNotificationVerifier=MagicMock(),
            ),
        }

    def run_bootstrap(self, environment):
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.dict(sys.modules, self.modules),
        ):
            return runpy.run_path(str(BOOTSTRAP))

    def test_one_real_parser_result_reaches_both_repositories_without_phase_c(self):
        for raw, expected in ((None, False), ("false", False), ("true", True)):
            with self.subTest(raw=raw):
                self.setUp()
                environment = {
                    "MOBILE_REFRESH_REPLAY_KEY": "fictional-fernet-key",
                    "MOBILE_ACCESS_SIGNING_KEY": "ZmFrZS1zaWduaW5nLWtleQ==",
                    "MOBILE_API_AUDIENCE": "fictional-line-audience",
                    "MOBILE_API_GOOGLE_AUDIENCES": "fictional-google-audience",
                }
                if raw is not None:
                    environment[runtime.ERASURE_CHECKS_ENV] = raw
                result = self.run_bootstrap(environment)
                self.parser.assert_called_once_with()
                for constructor in (self.mobile, self.identity):
                    constructor.assert_called_once_with(
                        sentinel.engine, erasure_checks_enabled=expected
                    )
                    self.assertIs(
                        constructor.call_args.kwargs["erasure_checks_enabled"], expected
                    )
                self.assertIs(result["app"], sentinel.app)
                self.assertIs(result["repository"], self.mobile.return_value)
                self.assertIs(result["data"], self.identity.return_value)
                self.attendance.assert_called_once_with(
                    self.identity.return_value, result["unavailable_notifier"]
                )
                self.basic.assert_called_once_with(
                    self.identity.return_value,
                    self.attendance.return_value,
                    self.mobile.return_value,
                )
                self.create_app.assert_called_once_with(self.dependencies.return_value)
                self.intake_builder.assert_not_called()
                self.assertIsNone(self.dependencies.call_args.kwargs["account_erasure"])

    def test_invalid_policy_stops_before_repository_or_key_wiring(self):
        for raw in ("", "TRUE", " true", "false ", "1", "fictional-private-value"):
            with self.subTest(raw=raw):
                self.setUp()
                # Missing keys intentionally expose any reordering before validation.
                with self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure checks configuration$"
                ):
                    self.run_bootstrap({runtime.ERASURE_CHECKS_ENV: raw})
                self.parser.assert_called_once_with()
                for dependency in (
                    self.mobile,
                    self.identity,
                    self.fernet,
                    self.codec,
                    self.dependencies,
                    self.create_app,
                ):
                    dependency.assert_not_called()

    def test_intake_enabled_is_actually_injected_by_keyword(self):
        self.run_bootstrap(
            {
                "MOBILE_API_ERASURE_INTAKE_ENABLED": "true",
                runtime.ERASURE_CHECKS_ENV: "true",
                "MOBILE_REFRESH_REPLAY_KEY": "fictional-fernet-key",
                "MOBILE_ACCESS_SIGNING_KEY": "ZmFrZS1zaWduaW5nLWtleQ==",
                "MOBILE_API_AUDIENCE": "fictional-line-audience",
                "MOBILE_API_GOOGLE_AUDIENCES": "fictional-google-audience",
            }
        )
        self.intake_parser.assert_called_once_with()
        self.intake_builder.assert_called_once_with(
            engine=sentinel.engine, checks_enabled=True
        )
        self.assertIs(
            self.dependencies.call_args.kwargs["account_erasure"],
            sentinel.erasure_service,
        )

    def test_explicit_false_does_not_read_invalid_new_keys(self):
        environment = {
            "MOBILE_API_ERASURE_INTAKE_ENABLED": "false",
            "MOBILE_API_ERASURE_RECEIPT_KEY": "invalid-fictional",
            "MOBILE_API_ERASURE_PROOF_KEY": "invalid-fictional",
            "MOBILE_API_ERASURE_GOOGLE_AUDIENCE": "not-allowed",
            "MOBILE_REFRESH_REPLAY_KEY": "fictional-fernet-key",
            "MOBILE_ACCESS_SIGNING_KEY": "ZmFrZS1zaWduaW5nLWtleQ==",
            "MOBILE_API_AUDIENCE": "fictional-line-audience",
            "MOBILE_API_GOOGLE_AUDIENCES": "fictional-google-audience",
        }
        with patch.object(os.environ, "get", wraps=os.environ.get) as read:
            self.run_bootstrap(environment)
        new_settings = {
            "MOBILE_API_ERASURE_RECEIPT_KEY",
            "MOBILE_API_ERASURE_PROOF_KEY",
            "MOBILE_API_ERASURE_GOOGLE_AUDIENCE",
        }
        self.assertFalse(
            new_settings.intersection(call.args[0] for call in read.call_args_list)
        )
        self.intake_builder.assert_not_called()
        self.assertIsNone(self.dependencies.call_args.kwargs["account_erasure"])

    def test_invalid_intake_flag_precedes_normal_repository_and_credential_wiring(self):
        for value in ("", "TRUE", " true", "false ", "1", "fictional-private"):
            with self.subTest(value=value):
                self.setUp()
                with self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure intake configuration$"
                ):
                    self.run_bootstrap({"MOBILE_API_ERASURE_INTAKE_ENABLED": value})
                for dependency in (
                    self.mobile,
                    self.identity,
                    self.fernet,
                    self.codec,
                    self.intake_builder,
                    self.dependencies,
                    self.create_app,
                ):
                    dependency.assert_not_called()

    def test_invalid_enabled_configuration_prevents_app_or_auth_construction(self):
        self.intake_builder.side_effect = RuntimeError(
            "invalid erasure intake configuration"
        )
        with self.assertRaisesRegex(
            RuntimeError, "^invalid erasure intake configuration$"
        ):
            self.run_bootstrap({"MOBILE_API_ERASURE_INTAKE_ENABLED": "true"})
        self.intake_builder.assert_called_once_with(
            engine=sentinel.engine, checks_enabled=False
        )
        for dependency in (
            self.mobile,
            self.identity,
            self.fernet,
            self.codec,
            self.dependencies,
            self.create_app,
        ):
            dependency.assert_not_called()

    def test_bootstrap_reaches_real_intake_factory_without_database_or_execution(self):
        connect = MagicMock(side_effect=AssertionError("no database I/O"))
        engine = create_engine("postgresql+psycopg2://", creator=connect)
        self.addCleanup(engine.dispose)
        self.modules["shared_module.models.db"].engine = engine
        self.intake_builder.side_effect = erasure_runtime.build_runtime_erasure_service
        self.run_bootstrap(
            {
                "MOBILE_API_ERASURE_INTAKE_ENABLED": "true",
                runtime.ERASURE_CHECKS_ENV: "true",
                "MOBILE_API_ERASURE_RECEIPT_KEY": encoded(b"R" * 32),
                "MOBILE_API_ERASURE_PROOF_KEY": encoded(b"P" * 32),
                "MOBILE_API_ERASURE_GOOGLE_AUDIENCE": "fictional-google",
                "MOBILE_REFRESH_REPLAY_KEY": encoded(b"F" * 32),
                "MOBILE_ACCESS_SIGNING_KEY": encoded(b"S" * 32),
                "MOBILE_API_AUDIENCE": "fictional-line",
                "MOBILE_API_GOOGLE_AUDIENCES": "fictional-google",
                "MOBILE_API_APPLE_AUDIENCE": "fictional-apple",
                "MOBILE_API_APPLE_CLIENT_SECRET": "fictional-client-secret",
                "MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY": encoded(b"A" * 32),
                "MOBILE_API_APPLE_NOTIFICATION_AUDIENCE": "fictional-notification",
            }
        )
        service = self.dependencies.call_args.kwargs["account_erasure"]
        self.assertIsInstance(service.repository, ErasureIntakeRepository)
        self.assertIs(service.repository, service.restricted_repository)
        self.assertIs(service.repository.engine, engine)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
