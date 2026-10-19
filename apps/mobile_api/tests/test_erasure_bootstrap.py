"""Exercise production bootstrap wiring without importing DB/provider runtimes."""

import os
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, sentinel

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
        self.modules = {
            "app": module(Dependencies=self.dependencies, create_app=self.create_app),
            "apple_verifier": module(AppleIdTokenVerifier=MagicMock()),
            "google_verifier": module(GoogleIdTokenVerifier=MagicMock()),
            "line_verifier": module(LineIdTokenVerifier=MagicMock()),
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


if __name__ == "__main__":
    unittest.main()
