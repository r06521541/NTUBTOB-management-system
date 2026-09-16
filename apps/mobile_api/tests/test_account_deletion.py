import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from shared_module.account_deletion import (
    AccountDeletionRequest,
    AccountDeletionService,
    AccountDeletionUnavailable,
)
from shared_module.mobile_api import AuthenticationError, MobilePrincipal

from apps.mobile_api.app import Dependencies, create_app


class AccountDeletionRouteTests(unittest.TestCase):
    def setUp(self):
        self.principal = MobilePrincipal("fake-session", 1, 2, "basic", "Fake", 1)
        self.auth = SimpleNamespace(authenticate=Mock(return_value=self.principal))
        self.repository = Mock()
        self.repository.status.return_value = None
        self.repository.request.return_value = AccountDeletionRequest(
            "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            datetime(2035, 1, 1, tzinfo=timezone.utc),
        )
        self.service = AccountDeletionService(self.repository)
        self.headers = {
            "Authorization": "Bearer obvious-fake-access",
            "Idempotency-Key": "11111111-2222-4333-8444-555555555555",
        }
        self.path = "/api/v1/me/account-deletion"
        self.client = self.make_client(self.service)

    def make_client(self, service):
        return create_app(
            Dependencies(
                auth=self.auth,
                basic=Mock(),
                publishing=Mock(),
                revision_check=lambda: True,
                account_deletion=service,
            )
        ).test_client()

    def post(self, **kwargs):
        return self.client.post(self.path, headers=self.headers, **kwargs)

    def test_get_and_post_are_current_principal_only(self):
        self.assertEqual(
            self.client.get(self.path, headers=self.headers).json, {"request": None}
        )
        response = self.post(json={"confirmed": True})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json["request"]["status"], "requested")
        self.repository.request.assert_called_once_with(self.principal)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_default_disabled_is_truthful_nonretryable_unavailable(self):
        dependencies = Dependencies(
            auth=self.auth, basic=Mock(), publishing=Mock(), revision_check=lambda: True
        )
        self.assertIsNone(dependencies.account_deletion)
        client = create_app(dependencies).test_client()
        for method in ("get", "post"):
            response = getattr(client, method)(
                self.path, headers=self.headers, json={"confirmed": True}
            )
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json["error"]["retryable"])
        self.repository.request.assert_not_called()

    def test_duplicate_keys_and_new_keys_return_identical_receipt(self):
        first = self.post(json={"confirmed": True})
        second = self.post(json={"confirmed": True})
        self.headers["Idempotency-Key"] = "66666666-7777-4888-9999-aaaaaaaaaaaa"
        third = self.post(json={"confirmed": True})
        self.assertEqual(
            [first.status_code, second.status_code, third.status_code], [202] * 3
        )
        self.assertEqual(first.json, second.json)
        self.assertEqual(first.json, third.json)

    def test_openapi_describes_exact_bounded_and_disabled_contract(self):
        contract = json.loads(
            (Path(__file__).resolve().parents[1] / "openapi.json").read_text(
                encoding="utf-8"
            )
        )
        path = contract["paths"]["/me/account-deletion"]
        self.assertEqual(set(path), {"get", "post"})
        schema = path["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertIs(schema["properties"]["confirmed"]["const"], True)
        self.assertEqual(set(schema["properties"]), {"confirmed"})
        self.assertIn("202", path["post"]["responses"])
        self.assertNotIn("200", path["post"]["responses"])
        self.assertIn("absent in normal bootstrap", path["get"]["description"])

    def test_requires_bearer_and_propagates_stale_auth(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)
        self.auth.authenticate.side_effect = AuthenticationError("inactive session")
        self.assertEqual(self.post(json={"confirmed": True}).status_code, 401)
        self.repository.request.assert_not_called()

    def test_revision_failure_also_requires_reconciliation_not_post_retry(self):
        client = create_app(
            Dependencies(
                auth=self.auth,
                basic=Mock(),
                publishing=Mock(),
                revision_check=lambda: False,
                account_deletion=self.service,
            )
        ).test_client()
        response = client.post(
            self.path, headers=self.headers, json={"confirmed": True}
        )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["error"]["retryable"])
        self.repository.request.assert_not_called()

    def test_malformed_and_ambiguous_confirmation_is_never_dispatched(self):
        bodies = (
            "[]",
            "null",
            "{",
            '{"confirmed":true,"confirmed":false}',
            '{"confirmed":false,"confirmed":true}',
            '{"confirmed":true,"person_id":9}',
            "{}",
            '{"confirmed":1}',
            '{"confirmed":"true"}',
            " " * 257,
        )
        for body in bodies:
            with self.subTest(body=body):
                self.assertIn(
                    self.post(data=body, content_type="application/json").status_code,
                    (400, 422),
                )
        self.assertEqual(
            self.post(data='{"confirmed":true}', content_type="text/plain").status_code,
            400,
        )
        self.repository.request.assert_not_called()

    def test_rejects_query_and_body_person_override(self):
        for method in ("get", "post"):
            response = getattr(self.client, method)(
                self.path + "?person_id=999",
                headers=self.headers,
                json={"confirmed": True},
            )
            self.assertEqual(response.status_code, 422)
        self.repository.request.assert_not_called()
        self.repository.status.assert_not_called()

    def test_invalid_uuid_key_is_rejected(self):
        self.headers["Idempotency-Key"] = "not-a-uuid"
        self.assertEqual(self.post(json={"confirmed": True}).status_code, 422)
        self.repository.request.assert_not_called()

    def test_persistence_error_does_not_disclose_or_invite_post_retry(self):
        self.repository.request.side_effect = AccountDeletionUnavailable()
        response = self.post(json={"confirmed": True})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"]["code"], "service_unavailable")
        self.assertFalse(response.json["error"]["retryable"])
        self.assertNotIn("obvious-fake-access", json.dumps(response.json))


if __name__ == "__main__":
    unittest.main()
