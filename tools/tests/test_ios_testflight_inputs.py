"""Fictional in-memory material only; no native custody or Apple calls."""

import base64
import json
import plistlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, utils
from cryptography.hazmat.primitives.serialization import pkcs12

from tools import ios_testflight_inputs as inputs

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
TEAM = "FICTTEAM01"
BUNDLE = "invalid.fictional.app"
PASSWORD = b"fictional-password"


class InputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name(
            [x509.NameAttribute(x509.NameOID.ORGANIZATIONAL_UNIT_NAME, TEAM)]
        )
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(cls.key.public_key())
            .serial_number(123)
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(NOW + timedelta(days=2))
            .add_extension(x509.BasicConstraints(False, None), True)
            .add_extension(
                x509.KeyUsage(
                    True, False, False, False, False, False, False, False, False
                ),
                True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CODE_SIGNING]), True
            )
        )
        for oid in ("1.2.840.113635.100.6.1.4", "1.2.840.113635.100.6.1.7"):
            builder = builder.add_extension(
                x509.UnrecognizedExtension(x509.ObjectIdentifier(oid), b"\x05\x00"),
                True,
            )
        cls.cert = builder.sign(cls.key, hashes.SHA256())
        cls.der = cls.cert.public_bytes(serialization.Encoding.DER)
        cls.p12 = pkcs12.serialize_key_and_certificates(
            b"fictional",
            cls.key,
            cls.cert,
            None,
            serialization.BestAvailableEncryption(PASSWORD),
        )
        cls.asc_key = ec.generate_private_key(ec.SECP256R1())
        cls.login_key = ec.generate_private_key(ec.SECP256R1())

    def profile(self):
        return plistlib.dumps(
            {
                "DeveloperCertificates": [self.der],
                "TeamIdentifier": [TEAM],
                "ApplicationIdentifierPrefix": [TEAM],
                "Platform": ["iOS"],
                "CreationDate": (NOW - timedelta(days=1)).replace(tzinfo=None),
                "ExpirationDate": (NOW + timedelta(days=1)).replace(tzinfo=None),
                "Entitlements": {
                    "application-identifier": TEAM + "." + BUNDLE,
                    "com.apple.developer.team-identifier": TEAM,
                    "com.apple.developer.applesignin": ["Default"],
                    "get-task-allow": False,
                    "beta-reports-active": True,
                },
            }
        )

    def pem(self, key):
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def asc(self, key=None):
        return inputs.load_asc_key(
            self.pem(key or self.asc_key),
            key_id="FICTKEY001",
            issuer_id="11111111-1111-4111-8111-111111111111",
        )

    def login(self, key=None):
        return inputs.load_apple_login_key(
            self.pem(key or self.login_key),
            key_id="FICTKEY002",
            team=TEAM,
            bundle=BUNDLE,
        )

    def test_signing_structural_only(self):
        value = inputs.validate_signing(
            self.p12, PASSWORD, self.profile(), team=TEAM, bundle=BUNDLE, now=NOW
        )
        self.assertEqual(value.certificate_der, self.der)
        self.assertNotIn(TEAM, repr(value))
        self.assertFalse(value.apple_trust_verified)
        self.assertFalse(value.signing_authorized)

    def test_signing_rejections(self):
        for p12, password, profile, team, now in (
            (self.p12, b"wrong", self.profile(), TEAM, NOW),
            (self.p12, PASSWORD, b"private-sentinel", TEAM, NOW),
            (self.p12, PASSWORD, self.profile(), "WRONGTEAM1", NOW),
            (self.p12, PASSWORD, self.profile(), TEAM, NOW + timedelta(days=3)),
            (self.p12, PASSWORD, self.profile(), TEAM, NOW.replace(tzinfo=None)),
            (b"x" * 65537, PASSWORD, self.profile(), TEAM, NOW),
        ):
            with (
                self.subTest(team=team),
                self.assertRaises(inputs.InputError) as caught,
            ):
                inputs.validate_signing(
                    p12, password, profile, team=team, bundle=BUNDLE, now=now
                )
            self.assertIn(str(caught.exception), inputs.REASONS)

    def test_key_separation_and_strict_encoding(self):
        inputs.validate_distinct_keys(self.asc(), self.login())
        with self.assertRaises(inputs.InputError):
            inputs.validate_distinct_keys(self.asc(), self.login(self.asc_key))
        for pem in (
            b"private-sentinel",
            self.pem(self.asc_key) + b"junk",
            self.pem(self.key),
            self.pem(ec.generate_private_key(ec.SECP384R1())),
        ):
            with self.assertRaises(inputs.InputError):
                inputs.load_asc_key(
                    pem,
                    key_id="FICTKEY001",
                    issuer_id="11111111-1111-4111-8111-111111111111",
                )

    def test_jwt_signature_claims_and_types(self):
        for material, function, key, ttl, audience in (
            (self.asc(), inputs.asc_jwt, self.asc_key, 600, "appstoreconnect-v1"),
            (
                self.login(),
                inputs.apple_login_jwt,
                self.login_key,
                604800,
                "https://appleid.apple.com",
            ),
        ):
            token = function(material, now=NOW)
            header, payload, sig = token.value.split(".")
            decode = lambda v: base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))
            claims = json.loads(decode(payload))
            self.assertEqual(claims["aud"], audience)
            self.assertEqual(claims["exp"] - claims["iat"], ttl)
            self.assertEqual(token.expires_at, NOW + timedelta(seconds=ttl))
            signature = decode(sig)
            der = utils.encode_dss_signature(
                int.from_bytes(signature[:32], "big"),
                int.from_bytes(signature[32:], "big"),
            )
            key.public_key().verify(
                der, (header + "." + payload).encode(), ec.ECDSA(hashes.SHA256())
            )
            with self.assertRaises(Exception):
                key.public_key().verify(
                    der,
                    (header + "." + payload + "x").encode(),
                    ec.ECDSA(hashes.SHA256()),
                )
            self.assertNotIn(token.value, repr(token))
        with self.assertRaises(inputs.InputError):
            inputs.asc_jwt(self.login(), now=NOW)

    def test_no_io_or_private_error(self):
        with (
            patch("builtins.open", side_effect=AssertionError),
            patch("socket.socket", side_effect=AssertionError),
        ):
            self.asc()
            self.login()
        with self.assertRaises(inputs.InputError) as caught:
            inputs.load_apple_login_key(
                b"private-sentinel", key_id="private-sentinel", team=TEAM, bundle=BUNDLE
            )
        self.assertNotIn("private-sentinel", repr(caught.exception))

    def test_unencrypted_trailing_and_missing_private_key(self):
        plain = pkcs12.serialize_key_and_certificates(
            b"fictional", self.key, self.cert, None, serialization.NoEncryption()
        )
        cert_only = pkcs12.serialize_key_and_certificates(
            b"fictional",
            None,
            self.cert,
            None,
            serialization.BestAvailableEncryption(PASSWORD),
        )
        for data in (plain, cert_only, self.p12 + b"tail", self.p12 + self.p12):
            with self.assertRaises(inputs.InputError):
                inputs.validate_signing(
                    data, PASSWORD, self.profile(), team=TEAM, bundle=BUNDLE, now=NOW
                )

    def test_profile_negative_bindings(self):
        for field, value in (
            ("DeveloperCertificates", [b"wrong"]),
            ("TeamIdentifier", ["WRONGTEAM1"]),
            ("ProvisionedDevices", ["fictional"]),
            ("Platform", ["macOS"]),
        ):
            profile = plistlib.loads(self.profile())
            profile[field] = value
            with self.assertRaises(inputs.InputError) as caught:
                inputs.validate_signing(
                    self.p12,
                    PASSWORD,
                    plistlib.dumps(profile),
                    team=TEAM,
                    bundle=BUNDLE,
                    now=NOW,
                )
            self.assertEqual(str(caught.exception), "PROFILE_REJECTED")

    def test_crypto_mismatch_and_purpose(self):
        from cryptography.hazmat.primitives.serialization import pkcs12 as parser

        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        def mismatched(data, password):
            if password is None:
                raise ValueError("private-sentinel")
            return other, self.cert, []

        with (
            patch.object(parser, "load_key_and_certificates", side_effect=mismatched),
            self.assertRaises(inputs.InputError) as caught,
        ):
            inputs.validate_signing(
                self.p12, PASSWORD, self.profile(), team=TEAM, bundle=BUNDLE, now=NOW
            )
        self.assertEqual(str(caught.exception), "CERTIFICATE_REJECTED")
        missing = (
            x509.CertificateBuilder()
            .subject_name(self.cert.subject)
            .issuer_name(self.cert.subject)
            .public_key(self.key.public_key())
            .serial_number(2)
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(NOW + timedelta(days=1))
            .sign(self.key, hashes.SHA256())
        )
        encoded = pkcs12.serialize_key_and_certificates(
            b"fictional",
            self.key,
            missing,
            None,
            serialization.BestAvailableEncryption(PASSWORD),
        )
        with self.assertRaises(inputs.InputError) as caught:
            inputs.validate_signing(
                encoded, PASSWORD, self.profile(), team=TEAM, bundle=BUNDLE, now=NOW
            )
        self.assertEqual(str(caught.exception), "CERTIFICATE_REJECTED")

    def test_jwt_time_and_constructor_validation(self):
        for now in (
            None,
            NOW.replace(tzinfo=None),
            NOW.astimezone(timezone(timedelta(hours=8))),
        ):
            with self.assertRaises(inputs.InputError) as caught:
                inputs.asc_jwt(self.asc(), now=now)
            self.assertEqual(str(caught.exception), "TIME_REJECTED")
        forged = inputs.AscMaterial(self.asc_key, "FICTKEY001", "private-sentinel")
        with self.assertRaises(inputs.InputError):
            inputs.asc_jwt(forged, now=NOW)
        self.assertEqual(
            inputs.asc_jwt(self.asc(), now=NOW.replace(microsecond=123)).expires_at,
            NOW + timedelta(seconds=600),
        )
        with (
            patch.object(
                inputs.preparation,
                "dependencies",
                side_effect=RuntimeError("private-sentinel"),
            ),
            self.assertRaises(inputs.InputError) as caught,
        ):
            self.asc()
        self.assertEqual(str(caught.exception), "DEPENDENCY_REJECTED")


if __name__ == "__main__":
    unittest.main()
