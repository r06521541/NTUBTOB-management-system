import unittest
from unittest.mock import Mock

from apps.mobile_api.app import Dependencies, create_app
from shared_lib.tests import test_apple_onboarding as fixture


class AppleOnboardingRouteTest(unittest.TestCase):
    def test_storage_failure_crosses_real_service_and_route_safely(self):
        service, repository = fixture.AppleFirstLoginTest().service()
        repository.complete_apple_code_for_pending = Mock(
            side_effect=RuntimeError("fictional-private-driver-detail")
        )
        client = create_app(
            Dependencies(
                auth=Mock(),
                basic=Mock(),
                publishing=Mock(),
                revision_check=lambda: True,
                apple_auth=service,
                apple_lifecycle_ready=lambda: True,
            )
        ).test_client()
        response = client.post(
            "/api/v1/auth/apple/exchange",
            json={
                "id_token": "fictional.assertion.signature",
                "authorization_code": "fictional-single-use-code",
                "nonce": "fictional-raw-nonce-123456",
                "login_attempt_id": "fictional-login-attempt",
                "installation_id": "fictional-installation",
                "platform": "ios",
            },
        )
        self.assertEqual(response.status_code, 503)
        body = response.get_json()
        self.assertEqual(body["error"]["code"], "service_unavailable")
        self.assertFalse(body["error"]["retryable"])
        self.assertIn("provider_exchange=completed", body["error"]["message"])
        self.assertIn("app_outcome=unconfirmed", body["error"]["message"])
        self.assertNotIn("fictional-private", response.get_data(as_text=True))
        self.assertNotIn("review_credential", body)
        self.assertEqual(len(service.exchanger.calls), 1)
