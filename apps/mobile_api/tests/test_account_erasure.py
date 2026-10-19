"""Default-off API contract, fictional dependencies and bounded secret bodies."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shared_module.erasure_recovery_proof import ErasureReceiptRecoveryProofService
from shared_module.mobile_api import MobilePrincipal, VerifiedAssertion
from shared_module.portal_data import erasure_service as service_module
from shared_module.portal_data.erasure_receipt_recovery import (
    ReceiptRecoveryRejected,
    RecoveredErasureReceipt,
)

from apps.mobile_api.app import Dependencies, create_app


class AccountErasureRouteTests(unittest.TestCase):
    def test_recovery_real_codec_service_route_order_and_exact_response(self):
        now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        provider = Mock()
        codec = ErasureReceiptRecoveryProofService(
            b"fictional-api-recovery-master-key-12345",
            audience="fictional-recovery",
            lifetime=timedelta(minutes=5),
            providers={"apple": (provider, "fictional-client")},
            clock=lambda: now,
        )
        reader, ordinary = Mock(), Mock()
        normal_proofs = Mock(
            audience="fictional", lifetime=timedelta(minutes=2), clock=lambda: now
        )
        service = service_module.AccountErasureService(
            ordinary, normal_proofs, recovery_proofs=codec, recovery_repository=reader
        )
        client = self.make_client(service)
        events = []
        with patch.object(service_module, "Session") as session:
            challenge = client.post(
                "/api/v1/account-erasure/recovery/challenge", json={"provider": "apple"}
            )
            self.assertEqual(challenge.status_code, 200)
            self.assertEqual(challenge.headers["Cache-Control"], "no-store")
            self.assertEqual(
                set(challenge.json),
                {"challenge_credential", "nonce", "provider", "expires_in"},
            )
            self.assertEqual(reader.mock_calls, [])

            def verify(*args):
                events.append("provider")
                reader.recover.assert_not_called()
                session.assert_not_called()
                return VerifiedAssertion(
                    "apple",
                    "fictional-subject",
                    "fictional-client",
                    challenge.json["nonce"],
                    now + timedelta(minutes=5),
                )

            provider.verify.side_effect = verify

            def recover(credential):
                events.append("read")
                self.assertEqual(
                    codec(credential).provider_subject, "fictional-subject"
                )
                return RecoveredErasureReceipt(
                    "11111111-1111-4111-8111-111111111111",
                    "f" * 64,
                    "processing",
                    now - timedelta(minutes=1),
                    now,
                    now + timedelta(hours=1),
                )

            reader.recover.side_effect = recover
            response = client.post(
                "/api/v1/account-erasure/recovery",
                json={
                    "challenge_credential": challenge.json["challenge_credential"],
                    "provider_assertion": "fictional-private-assertion",
                    "confirmed": True,
                },
            )
        self.assertEqual(events, ["provider", "read"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json),
            {
                "id",
                "status",
                "receipt_secret",
                "requested_at",
                "updated_at",
                "receipt_expires_at",
            },
        )
        self.assertEqual(response.json["status"], "processing")
        self.assertEqual(
            response.json["receipt_expires_at"], (now + timedelta(hours=1)).isoformat()
        )
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("fictional-subject", response.get_data(as_text=True))
        self.assertNotIn("fictional-private-assertion", response.get_data(as_text=True))
        self.auth.authenticate.assert_not_called()
        ordinary.request.assert_not_called()
        session.assert_not_called()
        provider.verify.assert_called_once()
        reader.recover.assert_called_once()
        provider.verify.reset_mock()
        reader.recover.reset_mock()
        valid = {
            "challenge_credential": challenge.json["challenge_credential"],
            "provider_assertion": "fictional-assertion",
            "confirmed": True,
        }
        for changes in (
            {"challenge_credential": "x" * 4097},
            {"provider_assertion": "x" * 16385},
        ):
            rejected = client.post(
                "/api/v1/account-erasure/recovery", json={**valid, **changes}
            )
            self.assertEqual(rejected.status_code, 401)
            self.assertEqual(rejected.headers["Cache-Control"], "no-store")
        now += timedelta(minutes=5)
        self.assertEqual(
            client.post("/api/v1/account-erasure/recovery", json=valid).status_code, 401
        )
        provider.verify.assert_not_called()
        reader.recover.assert_not_called()

    def test_recovery_http_is_disabled_when_existing_service_lacks_optional_pair(self):
        proofs = Mock(
            audience="fictional", lifetime=timedelta(minutes=2), clock=lambda: None
        )
        ordinary = Mock()
        client = self.make_client(
            service_module.AccountErasureService(ordinary, proofs)
        )
        for suffix, body in (
            ("/challenge", {"provider": "apple"}),
            (
                "",
                {
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": True,
                },
            ),
        ):
            response = client.post(
                "/api/v1/account-erasure/recovery" + suffix, json=body
            )
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json["error"]["retryable"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(ordinary.mock_calls, [])
        proofs.authenticate.assert_not_called()

    def test_recovery_routes_default_off_unready_and_no_client_target(self):
        for suffix, body, method in (
            ("/challenge", {"provider": "apple"}, "recovery_challenge"),
            (
                "",
                {
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": True,
                },
                "recover_receipt",
            ),
        ):
            path = "/api/v1/account-erasure/recovery" + suffix
            for client in (
                self.make_client(None),
                self.make_client(self.service, False),
            ):
                response = client.post(path, json=body)
                self.assertEqual(response.status_code, 503)
                self.assertFalse(response.json["error"]["retryable"])
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            for extra in (
                {"job_id": "fake"},
                {"person_id": 1},
                {"identity_id": 2},
                {"receipt_secret": "fake"},
            ):
                response = self.client.post(path, json={**body, **extra})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(
                self.client.post(path + "?job_id=fake", json=body).status_code, 422
            )
            getattr(self.service, method).assert_not_called()
        self.auth.authenticate.assert_not_called()

    def test_recovery_bounded_unique_exact_json_and_confirmation(self):
        path = "/api/v1/account-erasure/recovery"
        for raw in (
            '{"challenge_credential":"a","challenge_credential":"b","provider_assertion":"c","confirmed":true}',
            "{}",
            "[]",
            "{",
            '"scalar"',
            " " * 24577,
        ):
            response = self.client.post(path, data=raw, content_type="application/json")
            self.assertIn(response.status_code, (400, 422))
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        for value in (False, None, 1, "true"):
            response = self.client.post(
                path,
                json={
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": value,
                },
            )
            self.assertEqual(response.status_code, 422)
        self.service.recover_receipt.assert_not_called()
        self.assertEqual(
            self.client.post(path, data="fake", content_type="text/plain").status_code,
            400,
        )

    def test_recovery_real_service_rejections_hide_existence_and_private_detail(self):
        proofs = Mock(
            audience="fictional", lifetime=timedelta(minutes=2), clock=lambda: None
        )
        recovery_proofs, reader = Mock(), Mock()
        service = service_module.AccountErasureService(
            Mock(), proofs, recovery_proofs=recovery_proofs, recovery_repository=reader
        )
        client = self.make_client(service)
        messages = []
        for error in (
            service_module.RestrictedErasureProofRejected("private-proof"),
            ReceiptRecoveryRejected("missing-person"),
            ReceiptRecoveryRejected("expired-secret"),
        ):
            recovery_proofs.authenticate.side_effect = (
                error
                if type(error) is service_module.RestrictedErasureProofRejected
                else None
            )
            reader.recover.side_effect = (
                error if type(error) is ReceiptRecoveryRejected else None
            )
            response = client.post(
                "/api/v1/account-erasure/recovery",
                json={
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": True,
                },
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertFalse(response.json["error"]["retryable"])
            messages.append(response.json["error"]["message"])
        self.assertEqual(messages, ["account erasure recovery rejected"] * 3)

    def test_receipt_verification_routes_are_exact_no_session_and_default_off(self):
        for suffix, method, body in (
            (
                "receipt/challenge",
                "receipt_challenge",
                {"job_id": "fake", "receipt_secret": "fake", "provider": "apple"},
            ),
            (
                "receipt/verify",
                "verify_receipt",
                {
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": True,
                },
            ),
        ):
            with self.subTest(suffix=suffix):
                path = "/api/v1/account-erasure/" + suffix
                getattr(self.service, method).return_value = {"id": "fake"}
                response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(
                    self.client.post(path, json={**body, "person_id": 7}).status_code,
                    422,
                )
                self.assertEqual(
                    self.client.post(path + "?identity_id=7", json=body).status_code,
                    422,
                )
                for client in (
                    self.make_client(None),
                    self.make_client(self.service, False),
                ):
                    self.assertEqual(client.post(path, json=body).status_code, 503)
        self.auth.authenticate.assert_not_called()
        self.assertEqual(
            self.client.post(
                "/api/v1/account-erasure/receipt/verify",
                json={
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": False,
                },
            ).status_code,
            422,
        )

    def test_pending_challenge_requires_receipt_not_session_or_target_selection(self):
        path = "/api/v1/account-erasure/pending/challenge"
        body = {"job_id": "fake-job", "receipt_secret": "fake-secret"}
        self.service.pending_challenge.return_value = {"challenge_credential": "fake"}
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.auth.authenticate.assert_not_called()
        self.service.pending_challenge.assert_called_once_with(
            "fake-job", "fake-secret"
        )
        for extra in ({"identity_id": 7}, {"provider": "apple"}, {"person_id": 7}):
            self.assertEqual(
                self.client.post(path, json={**body, **extra}).status_code, 422
            )
        self.assertEqual(
            self.client.post(path + "?job_id=fake", json=body).status_code, 422
        )
        for client in (self.make_client(None), self.make_client(self.service, False)):
            result = client.post(path, json=body)
            self.assertEqual(result.status_code, 503)
            self.assertFalse(result.json["error"]["retryable"])

    def test_restricted_intent_requires_proof_not_an_app_session(self):
        self.service.restricted_challenge.return_value = {
            "challenge_credential": "fake"
        }
        self.service.request_restricted.return_value = {
            "id": "fake",
            "status": "requested",
        }
        challenge = self.client.post(
            "/api/v1/account-erasure/request/challenge", json={"provider": "apple"}
        )
        self.assertEqual(challenge.status_code, 200)
        result = self.client.post(
            "/api/v1/account-erasure/request",
            json={
                "challenge_credential": "fake",
                "provider_assertion": "fake",
                "confirmed": True,
            },
        )
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.auth.authenticate.assert_not_called()
        self.service.request_restricted.assert_called_once_with("fake", "fake", True)

    def test_restricted_routes_default_off_and_reject_target_or_query(self):
        for suffix, valid in (
            ("/request/challenge", {"provider": "apple"}),
            (
                "/request",
                {
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": True,
                },
            ),
        ):
            path = "/api/v1/account-erasure" + suffix
            for client in (
                self.make_client(None),
                self.make_client(self.service, False),
            ):
                response = client.post(path, json=valid)
                self.assertEqual(response.status_code, 503)
                self.assertFalse(response.json["error"]["retryable"])
            self.assertEqual(
                self.client.post(path, json={**valid, "person_id": 1}).status_code, 422
            )
            self.assertEqual(
                self.client.post(path + "?provider=apple", json=valid).status_code, 422
            )
        self.service.restricted_challenge.assert_not_called()
        self.service.request_restricted.assert_not_called()

    def test_cancellation_is_receipt_and_fresh_proof_only_no_normal_session(self):
        self.service.cancellation_challenge.return_value = {
            "challenge_credential": "fake"
        }
        self.service.cancel.return_value = {"id": "fake-job", "status": "cancelled"}
        response = self.client.post(
            "/api/v1/account-erasure/cancel/challenge",
            json={
                "job_id": "fake-job",
                "receipt_secret": "fake-secret",
                "provider": "google",
            },
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/v1/account-erasure/cancel",
            json={
                "challenge_credential": "fake",
                "provider_assertion": "fake",
                "confirmed": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "cancelled")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.auth.authenticate.assert_not_called()
        for value in (False, None, 1, "true"):
            response = self.client.post(
                "/api/v1/account-erasure/cancel",
                json={
                    "challenge_credential": "fake",
                    "provider_assertion": "fake",
                    "confirmed": value,
                },
            )
            self.assertEqual(response.status_code, 422)
        self.service.cancel.assert_called_once_with("fake", "fake", True)

    def test_status_default_off_and_unready_are_nonretryable_no_store(self):
        for client in (self.make_client(None), self.make_client(self.service, False)):
            response = client.post(
                "/api/v1/account-erasure/status",
                json={"job_id": "fake", "receipt_secret": "fake"},
            )
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json["error"]["retryable"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.service.status.assert_not_called()

    def test_status_uses_receipt_without_revoked_app_session(self):
        self.service.status.return_value = {"id": "fake-job", "status": "verified"}
        response = self.client.post(
            "/api/v1/account-erasure/status",
            json={"job_id": "fake-job", "receipt_secret": "fake-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"id": "fake-job", "status": "verified"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.auth.authenticate.assert_not_called()
        self.service.status.assert_called_once_with("fake-job", "fake-secret")

    def test_status_rejects_query_duplicate_extra_and_non_string_fields(self):
        path = "/api/v1/account-erasure/status"
        for body in (
            '{"job_id":"a","job_id":"b","receipt_secret":"c"}',
            '{"job_id":"a","receipt_secret":null}',
            '{"job_id":"a","receipt_secret":"c","person_id":1}',
            " " * 25001,
        ):
            self.assertIn(
                self.client.post(
                    path, data=body, content_type="application/json"
                ).status_code,
                (400, 422),
            )
        self.assertEqual(
            self.client.post(path + "?receipt_secret=fake", json={}).status_code, 422
        )
        self.service.status.assert_not_called()

    def setUp(self):
        self.principal = MobilePrincipal("fake-session", 1, 2, "basic", "Fake", 1)
        self.auth = SimpleNamespace(authenticate=Mock(return_value=self.principal))
        self.service = Mock()
        self.service.request.return_value = {
            "id": "fake-job",
            "status": "requested",
            "receipt_secret": "fake-secret",
        }
        self.service.challenge.return_value = {
            "challenge_credential": "fake-challenge",
            "nonce": "fake-nonce",
        }
        self.service.verify.return_value = {"id": "fake-job", "status": "verified"}
        self.client = self.make_client(self.service)
        self.headers = {"Authorization": "Bearer fake-access"}

    def make_client(self, service, ready=True):
        return create_app(
            Dependencies(
                auth=self.auth,
                basic=Mock(),
                publishing=Mock(),
                revision_check=lambda: ready,
                account_erasure=service,
            )
        ).test_client()

    def test_request_challenge_and_verify_are_separate_and_no_store(self):
        response = self.client.post(
            "/api/v1/me/account-erasure", headers=self.headers, json={"confirmed": True}
        )
        self.assertEqual(response.status_code, 202)
        self.service.request.assert_called_once_with(self.principal, True)
        response = self.client.post(
            "/api/v1/me/account-erasure/challenge",
            headers=self.headers,
            json={"job_id": "fake-job", "receipt_secret": "fake-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.service.challenge.assert_called_once_with(
            self.principal, "fake-job", "fake-secret"
        )
        # Session may be revoked by verification; its authority is challenge-bound proof.
        response = self.client.post(
            "/api/v1/account-erasure/verify",
            json={
                "challenge_credential": "fake-challenge",
                "provider_assertion": "fake-id-token",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "verified")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_absent_dependency_and_failed_revision_are_nonretryable(self):
        for client in (self.make_client(None), self.make_client(self.service, False)):
            response = client.post("/api/v1/account-erasure/verify", json={})
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json["error"]["retryable"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.service.verify.assert_not_called()

    def test_linked_steps_require_session_but_cannot_accept_target_from_client(self):
        self.assertEqual(
            self.client.post(
                "/api/v1/me/account-erasure", json={"confirmed": True}
            ).status_code,
            401,
        )
        response = self.client.post(
            "/api/v1/me/account-erasure",
            headers=self.headers,
            json={"confirmed": True, "person_id": 99},
        )
        self.assertEqual(response.status_code, 422)
        self.service.request.assert_not_called()

    def test_duplicate_fields_query_and_oversized_credentials_rejected(self):
        path = "/api/v1/account-erasure/verify"
        for body in (
            '{"challenge_credential":"a","challenge_credential":"b","provider_assertion":"c"}',
            "[]",
            "{",
            "{}",
            " " * 25001,
        ):
            response = self.client.post(
                path, data=body, content_type="application/json"
            )
            self.assertIn(response.status_code, (400, 422))
        self.assertEqual(
            self.client.post(path + "?receipt_secret=fake", json={}).status_code, 422
        )
        self.service.verify.assert_not_called()
