"""Fictional bootstrap configuration and actual intake-only assembly, no I/O."""

import base64
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from shared_module.erasure_restricted_proof import RestrictedErasureProofRejected
from shared_module.mobile_api import VerifiedAssertion
from shared_module.portal_data.erasure_intake import ErasureIntakeRepository
from sqlalchemy import create_engine

from apps.mobile_api import erasure_runtime as runtime
from apps.mobile_api.app import Dependencies, create_app


def encoded(value):
    return base64.urlsafe_b64encode(value).decode("ascii")


class ErasureRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.connect = Mock(side_effect=AssertionError("no database I/O"))
        self.engine = create_engine("postgresql+psycopg2://", creator=self.connect)
        self.addCleanup(self.engine.dispose)
        self.now = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.clock = lambda: self.now
        self.environment = {
            "MOBILE_API_ERASURE_INTAKE_ENABLED": "true",
            "MOBILE_API_ERASURE_RECEIPT_KEY": encoded(b"R" * 32),
            "MOBILE_API_ERASURE_PROOF_KEY": encoded(b"P" * 32),
            "MOBILE_API_ERASURE_GOOGLE_AUDIENCE": "fictional-google-native",
            "MOBILE_API_AUDIENCE": "fictional-line",
            "MOBILE_API_GOOGLE_AUDIENCES": "fictional-google-web,fictional-google-native",
            "MOBILE_API_APPLE_AUDIENCE": "fictional-apple",
            "MOBILE_API_APPLE_CLIENT_SECRET": "fictional-client-secret",
            "MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY": encoded(b"A" * 32),
            "MOBILE_API_APPLE_NOTIFICATION_AUDIENCE": "fictional-apple-notifications",
            "MOBILE_ACCESS_SIGNING_KEY": encoded(b"S" * 32),
            "MOBILE_REFRESH_REPLAY_KEY": encoded(b"F" * 32),
        }

    def build(self, **changes):
        return runtime.build_runtime_erasure_service(
            engine=self.engine,
            checks_enabled=True,
            environment={**self.environment, **changes},
            clock=self.clock,
        )

    def test_flag_is_exact_and_reads_no_other_configuration(self):
        for raw, expected in ((None, False), ("false", False), ("true", True)):
            environment = Mock()
            environment.get.return_value = raw
            self.assertIs(runtime.erasure_intake_enabled(environment), expected)
            environment.get.assert_called_once_with("MOBILE_API_ERASURE_INTAKE_ENABLED")
        for raw in ("", "TRUE", " true", "false ", "1", True, "fictional-private"):
            with (
                self.subTest(raw=raw),
                self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure intake configuration$"
                ),
            ):
                runtime.erasure_intake_enabled(
                    {"MOBILE_API_ERASURE_INTAKE_ENABLED": raw}
                )

    def test_enabled_assembly_has_exact_provider_ports_and_no_external_io(self):
        service = self.build()
        self.assertIsInstance(service.repository, ErasureIntakeRepository)
        self.assertIs(service.repository, service.restricted_repository)
        self.assertIs(service.repository.engine, self.engine)
        self.assertIs(service.repository.clock, self.clock)
        proofs = (
            service.proofs,
            service.cancellation_proofs,
            service.receipt_proofs,
            service.restricted_proofs,
            service.recovery_proofs,
        )
        self.assertEqual(len({proof._key for proof in proofs}), 5)
        for proof in proofs:
            self.assertEqual(set(proof.providers), {"line", "google", "apple"})
            self.assertEqual(proof.lifetime, timedelta(minutes=5))
            self.assertEqual(proof.providers["line"][1], "fictional-line")
            self.assertEqual(proof.providers["apple"][1], "fictional-apple")
            verifier, audience = proof.providers["google"]
            self.assertEqual(audience, "fictional-google-native")
            self.assertEqual(verifier._audiences, frozenset({audience}))
        self.connect.assert_not_called()

    def test_three_nonce_bound_providers_reach_real_route_without_login_or_db(self):
        providers = {name: Mock() for name in ("line", "google", "apple")}
        with (
            patch.object(
                runtime, "LineIdTokenVerifier", return_value=providers["line"]
            ),
            patch.object(
                runtime, "GoogleIdTokenVerifier", return_value=providers["google"]
            ),
            patch.object(
                runtime, "AppleIdTokenVerifier", return_value=providers["apple"]
            ),
        ):
            service = self.build()
        auth = Mock()
        client = create_app(
            Dependencies(
                auth=auth,
                basic=Mock(),
                publishing=Mock(),
                revision_check=lambda: True,
                account_erasure=service,
            )
        ).test_client()
        for name, verifier in providers.items():
            response = client.post(
                "/api/v1/account-erasure/request/challenge", json={"provider": name}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            challenge = response.json
            audience = service.restricted_proofs.providers[name][1]
            verifier.verify.return_value = VerifiedAssertion(
                name,
                "fictional-subject",
                audience,
                challenge["nonce"],
                self.now + timedelta(minutes=3),
            )
            proof = service.restricted_proofs.authenticate(
                challenge["challenge_credential"], "fictional-provider-assertion"
            )
            self.assertEqual(service.restricted_proofs(proof).provider, name)
            verifier.verify.assert_called_once_with(
                "fictional-provider-assertion", audience, challenge["nonce"], self.now
            )
        self.assertEqual(auth.mock_calls, [])
        self.connect.assert_not_called()

    def test_wrong_nonce_and_google_other_allowed_login_audience_are_rejected(self):
        service = self.build()
        google = service.restricted_proofs.providers["google"][0]
        for audience, nonce in (
            ("fictional-google-native", "wrong-nonce"),
            ("fictional-google-web", None),
        ):
            challenge = service.restricted_proofs.begin("google")
            claims = dict(
                iss="https://accounts.google.com",
                aud=audience,
                sub="fictional-subject",
                exp=int((self.now + timedelta(minutes=2)).timestamp()),
                nonce=nonce or challenge["nonce"],
            )
            with patch.object(google, "_verify_token", return_value=claims):
                with self.assertRaises(RestrictedErasureProofRejected):
                    service.restricted_proofs.authenticate(
                        challenge["challenge_credential"], "fictional-id-token"
                    )
        self.connect.assert_not_called()

    def test_guards_are_required_as_exact_true(self):
        for enabled in (False, None, 1, "true"):
            with (
                self.subTest(enabled=enabled),
                self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure intake configuration$"
                ),
            ):
                runtime.build_runtime_erasure_service(
                    engine=self.engine,
                    checks_enabled=enabled,
                    environment=self.environment,
                    clock=self.clock,
                )
        self.connect.assert_not_called()

    def test_missing_or_invalid_provider_configuration_fails_before_assembly(self):
        for changes in (
            {"MOBILE_API_AUDIENCE": ""},
            {"MOBILE_API_AUDIENCE": " padded "},
            {"MOBILE_API_APPLE_AUDIENCE": ""},
            {"MOBILE_API_APPLE_CLIENT_SECRET": ""},
            {"MOBILE_API_APPLE_CLIENT_SECRET": "fictional\u2603"},
            {"MOBILE_API_APPLE_CLIENT_SECRET": "fictional\nsecret"},
            {"MOBILE_API_APPLE_CLIENT_SECRET": "A" * 8193},
            {"MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY": ""},
            {"MOBILE_API_APPLE_NOTIFICATION_AUDIENCE": ""},
            {"MOBILE_API_ERASURE_GOOGLE_AUDIENCE": ""},
            {"MOBILE_API_ERASURE_GOOGLE_AUDIENCE": "not-allowed"},
            {"MOBILE_API_GOOGLE_AUDIENCES": ""},
            {"MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY": encoded(b"F" * 32)},
        ):
            with (
                self.subTest(fields=tuple(changes)),
                patch.object(runtime, "build_erasure_intake_service") as assembly,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure intake configuration$"
                ):
                    self.build(**changes)
                assembly.assert_not_called()
        self.connect.assert_not_called()

    def test_new_keys_are_canonical_bounded_and_at_least_32_bytes(self):
        for name in ("MOBILE_API_ERASURE_RECEIPT_KEY", "MOBILE_API_ERASURE_PROOF_KEY"):
            for value in (
                "",
                encoded(b"short"),
                encoded(b"R" * 32).rstrip("="),
                encoded(b"R" * 32) + "=",
                "private-value\u2603",
                "A" * 4097,
            ):
                with (
                    self.subTest(name=name, length=len(value)),
                    self.assertRaisesRegex(
                        RuntimeError, "^invalid erasure intake configuration$"
                    ),
                ):
                    self.build(**{name: value})
        service = self.build(MOBILE_API_ERASURE_PROOF_KEY=encoded(b"long" * 16))
        self.assertIsInstance(service.repository, ErasureIntakeRepository)
        self.connect.assert_not_called()

    def test_keys_cannot_reuse_each_other_or_login_or_provider_material(self):
        for new_key in (
            "MOBILE_API_ERASURE_RECEIPT_KEY",
            "MOBILE_API_ERASURE_PROOF_KEY",
        ):
            other = (
                "MOBILE_API_ERASURE_PROOF_KEY"
                if new_key.endswith("RECEIPT_KEY")
                else "MOBILE_API_ERASURE_RECEIPT_KEY"
            )
            for old_key in (
                other,
                "MOBILE_ACCESS_SIGNING_KEY",
                "MOBILE_REFRESH_REPLAY_KEY",
                "MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY",
            ):
                with (
                    self.subTest(new=new_key, old=old_key),
                    self.assertRaisesRegex(
                        RuntimeError, "^invalid erasure intake configuration$"
                    ),
                ):
                    self.build(**{new_key: self.environment[old_key]})
        self.connect.assert_not_called()

    def test_constructor_errors_are_fixed_and_hide_underlying_values(self):
        with patch.object(
            runtime,
            "build_erasure_intake_service",
            side_effect=ValueError("fictional-sensitive-diagnostic"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^invalid erasure intake configuration$"
            ) as caught:
                self.build()
        self.assertTrue(caught.exception.__suppress_context__)
        self.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
