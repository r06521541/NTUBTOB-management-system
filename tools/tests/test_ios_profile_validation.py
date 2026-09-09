"""Fictional decoded plist/certificate fixtures only; no real profile intake."""

import contextlib
import copy
import io
import plistlib
import socket
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tools import ios_profile_validation as profile

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)
TEAM = "FICTTEAM01"
BUNDLE = "invalid.fictional.app"


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.key = key
        name = x509.Name(
            [x509.NameAttribute(x509.NameOID.COMMON_NAME, "fictional-private-subject")]
        )
        cls.der = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(123456789)
            .not_valid_before(NOW - timedelta(days=2))
            .not_valid_after(NOW + timedelta(days=2))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .sign(key, hashes.SHA256())
            .public_bytes(serialization.Encoding.DER)
        )

    def fixture(self):
        return {
            "Name": "fictional-private-profile",
            "UUID": "fictional-private-uuid",
            "TeamIdentifier": [TEAM],
            "ApplicationIdentifierPrefix": [TEAM],
            "Platform": ["iOS"],
            "DeveloperCertificates": [self.der],
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

    def check(self, data=None, **overrides):
        values = dict(
            expected_bundle=BUNDLE,
            expected_team=TEAM,
            expected_certificate_der=self.der,
            now=NOW,
        )
        values.update(overrides)
        return profile.validate_profile(
            plistlib.dumps(self.fixture()) if data is None else data, **values
        )

    def assert_stop(self, result, reason=None):
        self.assertEqual(result["classification"], "STOP")
        self.assertIn(result["reason"], profile.STOP_REASONS)
        self.assertEqual(result, profile._result(reason or result["reason"]))

    def test_valid_content_is_not_cms_trust_or_signing(self):
        result = self.check()
        self.assertEqual(result["classification"], "PROFILE_CONTENT_MATCH_ONLY")
        self.assertTrue(
            all(
                value is False
                for key, value in result.items()
                if key.endswith(("_verified", "_authorized"))
            )
        )
        # The certificate is self-signed; neither that nor a tampered signature
        # establishes trust. Only exact supplied public bytes are compared.
        damaged = self.der[:-1] + bytes([self.der[-1] ^ 1])
        fixture = self.fixture()
        fixture["DeveloperCertificates"] = [damaged]
        self.assertEqual(
            self.check(plistlib.dumps(fixture), expected_certificate_der=damaged)[
                "classification"
            ],
            "PROFILE_CONTENT_MATCH_ONLY",
        )

    def test_ca_and_missing_basic_constraints_rejected(self):
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "fictional-ca")])
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(321)
            .not_valid_before(NOW - timedelta(days=2))
            .not_valid_after(NOW + timedelta(days=2))
        )
        for certificate_builder in (
            builder,
            builder.add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            ),
        ):
            der = certificate_builder.sign(self.key, hashes.SHA256()).public_bytes(
                serialization.Encoding.DER
            )
            fixture = self.fixture()
            fixture["DeveloperCertificates"] = [der]
            self.assert_stop(
                self.check(plistlib.dumps(fixture), expected_certificate_der=der),
                "INVALID_CERTIFICATE",
            )

    def test_exact_contract_mismatch_reasons(self):
        mutations = [
            ("TeamIdentifier", ["OTHERTEAM1"], "TEAM_PREFIX_MISMATCH"),
            ("ApplicationIdentifierPrefix", ["LEGACYPREF"], "TEAM_PREFIX_MISMATCH"),
            ("DeveloperCertificates", [self.der, self.der], "CERTIFICATE_MISMATCH"),
            ("DeveloperCertificates", [b"wrong-certificate"], "CERTIFICATE_MISMATCH"),
            ("Platform", ["OSX"], "DISTRIBUTION_PROFILE_REQUIRED"),
            ("ProvisionedDevices", [], "DISTRIBUTION_PROFILE_REQUIRED"),
            ("ProvisionsAllDevices", True, "DISTRIBUTION_PROFILE_REQUIRED"),
            ("ProvisionsAllDevices", 0, "DISTRIBUTION_PROFILE_REQUIRED"),
        ]
        for key, value, reason in mutations:
            fixture = self.fixture()
            fixture[key] = value
            with self.subTest(key=key):
                self.assert_stop(self.check(plistlib.dumps(fixture)), reason)
        for key, value, reason in (
            ("application-identifier", TEAM + ".*", "APPLICATION_MISMATCH"),
            (
                "com.apple.developer.team-identifier",
                "OTHERTEAM1",
                "TEAM_PREFIX_MISMATCH",
            ),
            (
                "com.apple.developer.applesignin",
                "Default",
                "APPLE_ENTITLEMENT_MISMATCH",
            ),
            (
                "com.apple.developer.applesignin",
                ["Default", "Other"],
                "APPLE_ENTITLEMENT_MISMATCH",
            ),
            ("get-task-allow", True, "DISTRIBUTION_PROFILE_REQUIRED"),
            ("get-task-allow", 0, "DISTRIBUTION_PROFILE_REQUIRED"),
            ("beta-reports-active", 1, "DISTRIBUTION_PROFILE_REQUIRED"),
        ):
            fixture = self.fixture()
            fixture["Entitlements"][key] = value
            with self.subTest(key=key):
                self.assert_stop(self.check(plistlib.dumps(fixture)), reason)

    def test_profile_time_boundaries_and_aware_clock(self):
        self.assertEqual(
            self.check(now=NOW - timedelta(days=1))["classification"],
            "PROFILE_CONTENT_MATCH_ONLY",
        )
        self.assertEqual(
            self.check(now=NOW.astimezone(timezone(timedelta(hours=8))))[
                "classification"
            ],
            "PROFILE_CONTENT_MATCH_ONLY",
        )
        for instant in (NOW - timedelta(days=1, seconds=1), NOW + timedelta(days=1)):
            self.assert_stop(self.check(now=instant), "PROFILE_TIME_REJECTED")
        self.assert_stop(
            self.check(now=NOW + timedelta(days=3)), "CERTIFICATE_TIME_REJECTED"
        )
        for value in (None, NOW.replace(tzinfo=None), "now", 1):
            self.assert_stop(self.check(now=value), "INVALID_VERIFICATION_TIME")
        fixture = self.fixture()
        fixture["CreationDate"] = "2026-09-09T00:00:00Z"
        self.assert_stop(self.check(plistlib.dumps(fixture)), "PROFILE_TIME_REJECTED")

    def test_types_and_size_rejected_before_parser(self):
        for field, value in (
            ("decoded_plist", "private-path"),
            ("decoded_plist", b""),
            ("decoded_plist", b"x" * (profile.MAX_PLIST_BYTES + 1)),
            ("expected_certificate_der", b"x" * 65537),
            ("expected_certificate_der", bytearray(self.der)),
            ("expected_team", True),
            ("expected_bundle", "invalid.*"),
        ):
            with patch.object(profile, "_xml_profile") as parser:
                values = dict(
                    expected_bundle=BUNDLE,
                    expected_team=TEAM,
                    expected_certificate_der=self.der,
                    now=NOW,
                    decoded_plist=b"fixture",
                )
                values[field] = value
                self.assert_stop(profile.validate_profile(**values), "INVALID_INPUT")
                parser.assert_not_called()
        self.assert_stop(
            self.check(expected_certificate_der=self.der + b"junk"),
            "INVALID_CERTIFICATE",
        )

    def test_duplicate_keys_and_multiple_values_rejected(self):
        valid = plistlib.dumps(self.fixture())
        for original, changed in (
            (
                b"<key>Name</key>",
                b"<key>Name</key><string>first</string><key>Name</key>",
            ),
            (
                b"<key>get-task-allow</key>",
                b"<key>get-task-allow</key><true/><key>get-task-allow</key>",
            ),
            (b"</plist>", b"<dict/></plist>"),
            (b"<false/>", b"<false>1</false>"),
            (b"<dict>", b"<dict unexpected='yes'>"),
        ):
            self.assert_stop(
                self.check(valid.replace(original, changed, 1)), "INVALID_XML_PLIST"
            )

    def test_entities_dtd_trailing_binary_and_depth_rejected(self):
        valid = plistlib.dumps(self.fixture())
        doctype = valid[
            valid.index(b"<!DOCTYPE") : valid.index(b">", valid.index(b"<!DOCTYPE")) + 1
        ]
        candidates = [
            valid + b"junk",
            valid + valid,
            plistlib.dumps(self.fixture(), fmt=plistlib.FMT_BINARY),
            valid.replace(doctype, b'<!DOCTYPE plist [<!ENTITY private "value">]>'),
            valid.replace(
                doctype, b'<!DOCTYPE plist SYSTEM "https://private.invalid/dtd">'
            ),
            valid.replace(b"<dict>", b"<?private instruction?><dict>", 1),
            valid.replace(
                b"<date>2026-09-09T00:00:00Z</date>",
                b"<date>2026-02-30T00:00:00Z</date>",
            ),
            b'<plist version="1.0"><dict><key>x</key>'
            + b"<array>" * 40
            + b"</array>" * 40
            + b"</dict></plist>",
            b'<plist version="1.0"><dict><key>x</key><unknown/></dict></plist>',
            b'<plist version="1.0"><dict><key>x</key><data>!!!</data></dict></plist>',
        ]
        for candidate in candidates:
            self.assert_stop(self.check(candidate), "INVALID_XML_PLIST")

    def test_no_io_or_private_disclosure(self):
        source = plistlib.dumps(self.fixture())
        original = copy.copy(source)
        output = io.StringIO()
        with (
            patch("builtins.open") as files,
            patch.object(socket, "socket") as network,
            patch.object(subprocess, "run") as process,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            result = self.check(source)
        files.assert_not_called()
        network.assert_not_called()
        process.assert_not_called()
        self.assertEqual(source, original)
        self.assertEqual(output.getvalue(), "")
        for private in (TEAM, BUNDLE, "fictional-private", "123456789", "2026-09"):
            self.assertNotIn(private, repr(result))
        with patch.object(
            profile, "_xml_profile", side_effect=ValueError("private-parser-cause")
        ):
            self.assertNotIn("private-parser-cause", repr(self.check(source)))


if __name__ == "__main__":
    unittest.main()
