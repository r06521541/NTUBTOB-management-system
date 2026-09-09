"""Fictional public fixtures built in memory; no files or network."""

import contextlib
import io
import socket
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from tools import ios_certificate_pair as pair

NOW = datetime(2026, 9, 9, tzinfo=timezone.utc)
PEM = serialization.Encoding.PEM
DER = serialization.Encoding.DER


class PairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.subject = x509.Name(
            [
                x509.NameAttribute(
                    x509.NameOID.COMMON_NAME, "Fictional Private Subject"
                ),
                x509.NameAttribute(
                    x509.NameOID.EMAIL_ADDRESS, "fictional@example.invalid"
                ),
            ]
        )
        cls.csr = cls.make_csr(cls.key)
        cls.certificate = cls.make_certificate(cls.key)

    @classmethod
    def make_csr(cls, key, algorithm=None):
        return (
            x509.CertificateSigningRequestBuilder()
            .subject_name(cls.subject)
            .sign(key, algorithm or hashes.SHA256())
        )

    @classmethod
    def make_certificate(cls, key, ca=False):
        builder = (
            x509.CertificateBuilder()
            .subject_name(cls.subject)
            .issuer_name(cls.subject)
            .public_key(key.public_key())
            .serial_number(123456789)
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(NOW + timedelta(days=1))
        )
        if ca is not None:
            builder = builder.add_extension(
                x509.BasicConstraints(ca=ca, path_length=None), critical=True
            )
        return builder.sign(key, hashes.SHA256())

    def check(self, certificate=None, csr=None, now=NOW):
        return pair.check_pair(
            self.certificate.public_bytes(PEM) if certificate is None else certificate,
            self.csr.public_bytes(PEM) if csr is None else csr,
            now=now,
        )

    def assert_stop(self, reason=None, **kwargs):
        result = self.check(**kwargs)
        self.assertIn(result["reason"], pair.STOP_REASONS)
        self.assertEqual(result, pair._result(reason=reason or result["reason"]))

    def test_actionable_fixed_reasons(self):
        csr = self.csr.public_bytes(DER)
        cases = (
            ({"certificate": "fictional-path"}, "INVALID_INPUT_TYPE"),
            ({"certificate": b""}, "INVALID_INPUT_SIZE"),
            ({"now": None}, "INVALID_VERIFICATION_TIME"),
            ({"certificate": b"junk"}, "INVALID_CERTIFICATE_ENCODING"),
            ({"csr": b"junk"}, "INVALID_CSR_ENCODING"),
            (
                {"csr": self.make_csr(self.key, hashes.SHA384()).public_bytes(DER)},
                "UNSUPPORTED_CSR_ALGORITHM",
            ),
            ({"csr": csr[:-1] + bytes([csr[-1] ^ 1])}, "INVALID_CSR_SIGNATURE"),
            ({"now": NOW - timedelta(days=2)}, "CERTIFICATE_NOT_YET_VALID"),
            ({"now": NOW + timedelta(days=2)}, "CERTIFICATE_EXPIRED"),
            (
                {"certificate": self.make_certificate(self.other).public_bytes(DER)},
                "PUBLIC_KEY_MISMATCH",
            ),
            (
                {
                    "certificate": self.make_certificate(
                        self.key, ca=True
                    ).public_bytes(DER)
                },
                "CA_CERTIFICATE_REJECTED",
            ),
        )
        for kwargs, reason in cases:
            with self.subTest(reason=reason):
                self.assert_stop(reason=reason, **kwargs)
        with patch.object(pair, "_DEPENDENCY_AVAILABLE", False):
            self.assert_stop(reason="DEPENDENCY_UNAVAILABLE")
        with patch.object(
            pair, "_parse", side_effect=RuntimeError("private-unexpected")
        ):
            self.assert_stop(reason="PAIR_CHECK_REJECTED")

    def test_self_signed_pair_match_only_pem_and_der(self):
        for certificate_encoding in (PEM, DER):
            for csr_encoding in (PEM, DER):
                result = self.check(
                    certificate=self.certificate.public_bytes(certificate_encoding),
                    csr=self.csr.public_bytes(csr_encoding),
                )
                self.assertEqual(result["classification"], "PAIR_MATCH_ONLY")
                self.assertEqual(result["ca_status"], "not_ca")
                self.assertTrue(
                    all(
                        value is False
                        for key, value in result.items()
                        if key.endswith(("_verified", "_authorized"))
                    )
                )
                self.assertFalse(result["certificate_signature_verified"])

    def test_pem_crlf_and_optional_final_newline(self):
        for transform in (
            lambda value: value.replace(b"\n", b"\r\n"),
            lambda value: value[:-1],
        ):
            self.assertEqual(
                self.check(csr=transform(self.csr.public_bytes(PEM)))["classification"],
                "PAIR_MATCH_ONLY",
            )

    def test_time_bounds_inclusive_and_timezone_conversion(self):
        for instant in (
            NOW - timedelta(days=1),
            NOW + timedelta(days=1),
            NOW.astimezone(timezone(timedelta(hours=8))),
        ):
            self.assertEqual(
                self.check(now=instant)["classification"], "PAIR_MATCH_ONLY"
            )
        for instant in (
            NOW - timedelta(days=1, microseconds=1),
            NOW + timedelta(days=1, microseconds=1),
            NOW.replace(tzinfo=None),
            None,
            "now",
        ):
            self.assert_stop(now=instant)

    def test_mismatched_key_and_tampered_csr(self):
        self.assert_stop(
            certificate=self.make_certificate(self.other).public_bytes(DER)
        )
        csr = self.csr.public_bytes(DER)
        self.assert_stop(csr=csr[:-1] + bytes([csr[-1] ^ 1]))

    def test_certificate_signature_deliberately_unverified(self):
        certificate = self.certificate.public_bytes(DER)
        result = self.check(certificate=certificate[:-1] + bytes([certificate[-1] ^ 1]))
        self.assertEqual(result["classification"], "PAIR_MATCH_ONLY")
        self.assertFalse(result["certificate_signature_verified"])
        self.assertFalse(result["certificate_trust_verified"])

    def test_wrong_dependency_stops_before_parsing(self):
        with (
            patch.object(pair.cryptography, "__version__", "unexpected"),
            patch.object(pair, "_parse") as parser,
        ):
            self.assert_stop(reason="DEPENDENCY_UNAVAILABLE")
        parser.assert_not_called()

    def test_wrong_csr_algorithm_and_key_size(self):
        for key, algorithm in (
            (self.key, hashes.SHA384()),
            (
                rsa.generate_private_key(public_exponent=65537, key_size=1024),
                hashes.SHA256(),
            ),
            (ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()),
        ):
            self.assert_stop(csr=self.make_csr(key, algorithm).public_bytes(DER))

    def test_ca_rejected_missing_constraints_unknown(self):
        self.assert_stop(
            certificate=self.make_certificate(self.key, ca=True).public_bytes(PEM)
        )
        result = self.check(
            certificate=self.make_certificate(self.key, ca=None).public_bytes(PEM)
        )
        self.assertEqual(result["classification"], "PAIR_MATCH_ONLY")
        self.assertEqual(result["ca_status"], "unknown")
        self.assertFalse(result["certificate_purpose_verified"])

    def test_types_and_size_rejected_before_parse(self):
        for value in (
            None,
            "private-path.pem",
            bytearray(b"fixture"),
            memoryview(b"fixture"),
            b"",
            b"x" * (pair.MAX_INPUT_BYTES + 1),
        ):
            for field in ("certificate_bytes", "csr_bytes"):
                args = {
                    "certificate_bytes": b"fixture",
                    "csr_bytes": b"fixture",
                    field: value,
                }
                with patch.object(pair, "_parse") as parser:
                    reason = (
                        "INVALID_INPUT_SIZE"
                        if type(value) is bytes
                        else "INVALID_INPUT_TYPE"
                    )
                    self.assertEqual(
                        pair.check_pair(**args, now=NOW), pair._result(reason=reason)
                    )
                    parser.assert_not_called()

    def test_exact_max_size_is_bounded_before_parser(self):
        with patch.object(pair, "_parse", side_effect=ValueError()) as parser:
            self.assert_stop(certificate=b"x" * pair.MAX_INPUT_BYTES)
            parser.assert_called_once()

    def test_single_canonical_object_only(self):
        for encoding in (PEM, DER):
            for field, original in (
                ("certificate", self.certificate.public_bytes(encoding)),
                ("csr", self.csr.public_bytes(encoding)),
            ):
                for value in (
                    original + b"junk",
                    original + original,
                    b"junk" + original,
                    original[:-4],
                    original + b"\n",
                ):
                    self.assert_stop(**{field: value})
        wrong_label = self.csr.public_bytes(PEM).replace(
            b"CERTIFICATE REQUEST", b"NEW CERTIFICATE REQUEST"
        )
        self.assert_stop(csr=wrong_label)
        self.assert_stop(csr=self.certificate.public_bytes(PEM))
        self.assert_stop(certificate=self.csr.public_bytes(PEM))

    def test_no_io_and_fixed_no_disclosure(self):
        output = io.StringIO()
        with (
            patch(
                "builtins.open", side_effect=AssertionError("unexpected I/O")
            ) as files,
            patch.object(
                socket, "socket", side_effect=AssertionError("unexpected network")
            ) as network,
            patch.object(
                subprocess, "run", side_effect=AssertionError("unexpected subprocess")
            ) as process,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            result = self.check()
            with patch.object(
                pair, "_parse", side_effect=RuntimeError("private-parser-cause")
            ):
                rejected = self.check()
        self.assertEqual(result["classification"], "PAIR_MATCH_ONLY")
        self.assertEqual(rejected, pair._result())
        files.assert_not_called()
        network.assert_not_called()
        process.assert_not_called()
        self.assertEqual(output.getvalue(), "")
        rendered = repr((result, rejected))
        for value in (
            "Fictional",
            "example.invalid",
            "123456789",
            "private-parser-cause",
            "BEGIN",
            "fingerprint",
        ):
            self.assertNotIn(value, rendered)


if __name__ == "__main__":
    unittest.main()
