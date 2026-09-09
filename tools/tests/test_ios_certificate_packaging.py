"""Only fictional in-memory certificates and keys; no Apple/Owner inputs."""

import contextlib
import io
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12

from tools import ios_certificate_packaging as packaging

NOW = datetime(2026, 9, 9, tzinfo=timezone.utc)
OLD = b"fictional-old-password"
NEW = b"fictional-new-password"
SHA = "a" * 40
PEM = serialization.Encoding.PEM


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_key, cls.intermediate_key, cls.key = [
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            for _ in range(3)
        ]
        cls.root = cls.certificate("fictional-root", cls.root_key, ca=True, depth=1)
        cls.intermediate = cls.certificate(
            "fictional-intermediate",
            cls.intermediate_key,
            issuer=cls.root,
            signer=cls.root_key,
            ca=True,
            depth=0,
        )
        cls.leaf = cls.leaf_certificate()
        cls.csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(cls.leaf.subject)
            .sign(cls.key, hashes.SHA256())
        )
        cls.encrypted = cls.key.private_bytes(
            PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(OLD),
        )

    @classmethod
    def certificate(
        cls,
        label,
        key,
        *,
        issuer=None,
        signer=None,
        ca=False,
        depth=None,
        missing_marker=False,
        bad_eku=False,
        unknown=False,
        noncritical=False,
        algorithm=None,
        expires=None,
    ):
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, label)])
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(issuer.subject if issuer else name)
            .public_key(key.public_key())
            .serial_number(123)
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(expires or NOW + timedelta(days=1))
            .add_extension(
                x509.BasicConstraints(ca=ca, path_length=depth), critical=True
            )
            .add_extension(
                x509.KeyUsage(not ca, False, False, False, False, ca, ca, False, False),
                critical=True,
            )
        )
        if not ca:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage(
                    [
                        (
                            x509.ExtendedKeyUsageOID.SERVER_AUTH
                            if bad_eku
                            else x509.ExtendedKeyUsageOID.CODE_SIGNING
                        )
                    ]
                ),
                critical=not noncritical,
            )
            for oid in packaging.MARKERS[1:] if missing_marker else packaging.MARKERS:
                builder = builder.add_extension(
                    x509.UnrecognizedExtension(x509.ObjectIdentifier(oid), b"\x05\x00"),
                    critical=True,
                )
        if unknown:
            builder = builder.add_extension(
                x509.UnrecognizedExtension(
                    x509.ObjectIdentifier("1.2.3.4.5"), b"\x05\x00"
                ),
                critical=True,
            )
        return builder.sign(signer or key, algorithm or hashes.SHA256())

    @classmethod
    def leaf_certificate(cls, **kwargs):
        return cls.certificate(
            "fictional-leaf",
            cls.key,
            issuer=cls.intermediate,
            signer=cls.intermediate_key,
            **kwargs,
        )

    def arguments(self):
        return dict(
            certificate_bytes=self.leaf.public_bytes(PEM),
            csr_bytes=self.csr.public_bytes(PEM),
            encrypted_key_bytes=self.encrypted,
            old_password=OLD,
            new_password=NEW,
            root_pem=self.root.public_bytes(PEM),
            intermediate_pem=self.intermediate.public_bytes(PEM),
            now=NOW,
        )

    def test_encrypted_roundtrip_and_originals_unchanged(self):
        args = self.arguments()
        original = dict(args)
        value = packaging.package_material(**args)
        key, leaf, chain = pkcs12.load_key_and_certificates(value, NEW)
        self.assertEqual(key.private_numbers(), self.key.private_numbers())
        self.assertEqual(leaf, self.leaf)
        self.assertEqual(chain, [self.intermediate, self.root])
        self.assertEqual(args, original)
        for password in (None, b"wrong-password"):
            with self.assertRaises(ValueError):
                pkcs12.load_key_and_certificates(value, password)

    def test_core_has_no_file_io(self):
        with patch(
            "builtins.open", side_effect=AssertionError("private-sentinel")
        ) as opened:
            value = packaging.package_material(**self.arguments())
        self.assertIsInstance(value, bytes)
        opened.assert_not_called()

    def test_wrong_password_has_fixed_key_reason(self):
        args = self.arguments()
        args["old_password"] = b"wrong-password"
        with self.assertRaises(packaging.PackagingError) as error:
            packaging.package_material(**args)
        self.assertEqual(str(error.exception), "KEY_REJECTED")

    def test_sha1_leaf_and_expired_anchor_rejected(self):
        der = self.leaf.public_bytes(serialization.Encoding.DER)
        sha256_oid = bytes.fromhex("06092a864886f70d01010b")
        sha1_oid = bytes.fromhex("06092a864886f70d010105")
        self.assertEqual(der.count(sha256_oid), 2)
        expired_root = self.certificate(
            "fictional-root",
            self.root_key,
            ca=True,
            depth=1,
            expires=NOW - timedelta(hours=1),
        )
        for name, value in (
            ("certificate_bytes", der.replace(sha256_oid, sha1_oid)),
            ("root_pem", expired_root.public_bytes(PEM)),
        ):
            args = self.arguments()
            args[name] = value
            with (
                self.subTest(name=name),
                self.assertRaises(packaging.PackagingError) as error,
            ):
                packaging.package_material(**args)
            self.assertEqual(str(error.exception), "CHAIN_REJECTED")

    def test_purpose_and_unknown_critical_fail(self):
        for kwargs in (
            dict(missing_marker=True),
            dict(bad_eku=True),
            dict(unknown=True),
            dict(noncritical=True),
        ):
            args = self.arguments()
            args["certificate_bytes"] = self.leaf_certificate(**kwargs).public_bytes(
                PEM
            )
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaises(packaging.PackagingError),
            ):
                packaging.package_material(**args)

    def test_input_password_key_time_and_signature_failures(self):
        der = self.leaf.public_bytes(serialization.Encoding.DER)
        wrong_key = self.root_key.private_bytes(
            PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(OLD),
        )
        changes = (
            ("old_password", b"wrong-password"),
            ("new_password", b"short"),
            ("encrypted_key_bytes", wrong_key),
            ("encrypted_key_bytes", self.encrypted + self.encrypted),
            (
                "encrypted_key_bytes",
                self.key.private_bytes(
                    PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
                ),
            ),
            ("certificate_bytes", der[:-1] + bytes([der[-1] ^ 1])),
            ("certificate_bytes", b"x" * 65537),
            ("now", NOW + timedelta(days=2)),
            ("now", NOW.replace(tzinfo=None)),
            ("root_pem", self.intermediate.public_bytes(PEM)),
        )
        for name, value in changes:
            args = self.arguments()
            args[name] = value
            with (
                self.subTest(name=name),
                self.assertRaises(packaging.PackagingError) as error,
            ):
                packaging.package_material(**args)
            self.assertIn(str(error.exception), packaging.REASONS)

    def test_public_anchor_pins(self):
        root, intermediate = packaging.pinned_anchors()
        self.assertTrue(root.startswith(b"-----BEGIN CERTIFICATE-----"))
        self.assertTrue(intermediate.startswith(b"-----BEGIN CERTIFICATE-----"))
        from tools import apple_distribution_trust as trust

        with (
            patch.object(trust, "ROOT_SHA256", "0" * 64),
            self.assertRaises(packaging.PackagingError),
        ):
            packaging.pinned_anchors()


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock(output_attempted=False)
        self.session.__enter__ = Mock(return_value=self.session)
        self.session.__exit__ = Mock(return_value=False)
        for target, kwargs in (
            ("repository", {}),
            ("pinned_anchors", {"return_value": (b"root", b"intermediate")}),
            ("package_material", {"return_value": b"fictional-encrypted-p12"}),
        ):
            item = patch.object(packaging, target, **kwargs)
            setattr(self, target, item.start())
            self.addCleanup(item.stop)
        item = patch.object(packaging.custody, "Custody", return_value=self.session)
        item.start()
        self.addCleanup(item.stop)
        item = patch.object(
            packaging.preparation, "local_app_data", return_value=Path("/fictional")
        )
        item.start()
        self.addCleanup(item.stop)

    def test_preflight_never_reads_or_prompts(self):
        with patch.object(packaging.preparation, "hidden") as hidden:
            result = packaging.operate(SHA)
        self.assertEqual(result["classification"], "preflight_passed")
        hidden.assert_not_called()
        self.session.read_input.assert_not_called()
        self.session.write_output.assert_not_called()

    def test_confirmation_and_password_fail_before_file_reads(self):
        for inputs in (
            ("wrong-sha",),
            ("PACKAGE P12 " + SHA, "old", "new", "mismatch"),
            (KeyboardInterrupt(),),
        ):
            with (
                patch.object(packaging.preparation, "hidden", side_effect=inputs),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = packaging.operate(SHA, execute=True)
            self.assertEqual(result["classification"], "pre_execution_rejected")
            self.session.read_input.assert_not_called()
            self.session.write_output.assert_not_called()

    def test_success_false_authorities_and_uncertain_no_retry(self):
        values = ["PACKAGE P12 " + SHA, OLD.decode(), NEW.decode(), NEW.decode()]
        with (
            patch.object(packaging.preparation, "hidden", side_effect=values),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = packaging.operate(SHA, execute=True)
        self.assertEqual(result["classification"], "confirmed_success")
        for name in (
            "revocation_verified",
            "team_verified",
            "app_profile_verified",
            "signing_authorized",
            "upload_authorized",
            "release_authorized",
        ):
            self.assertIs(result[name], False)
        for name in (
            "offline_chain_verified",
            "distribution_purpose_verified",
            "private_key_match_verified",
        ):
            self.assertIs(result[name], True)
        self.session.write_output.assert_called_once()
        self.session.write_output.reset_mock()

        def fail(_):
            self.session.output_attempted = True
            raise ValueError("private-sentinel")

        self.session.write_output.side_effect = fail
        output = io.StringIO()
        with (
            patch.object(packaging.preparation, "hidden", side_effect=values),
            contextlib.redirect_stdout(output),
        ):
            result = packaging.operate(SHA, execute=True)
        self.assertEqual(result["classification"], "uncertain")
        self.session.write_output.assert_called_once()
        self.assertNotIn("private-sentinel", repr(result) + output.getvalue())

    def test_fixed_custody_reason_and_stage(self):
        for reason in ("ACL_REJECTED", "OUTPUT_EXISTS", "private-sentinel"):
            self.session.__enter__.side_effect = packaging.custody.CustodyError(reason)
            result = packaging.operate(SHA)
            self.assertEqual(result["stage"], "metadata")
            self.assertEqual(
                result["reason"],
                "PACKAGING_REJECTED" if reason == "private-sentinel" else reason,
            )
            self.assertNotIn("private-sentinel", repr(result))

    def test_cli_invalid_arguments_do_not_echo(self):
        for args in (
            [],
            ["--private-sentinel"],
            ["--expected-commit"],
            ["--expected-commit", SHA, "--root-pem", "private-sentinel"],
        ):
            output, error = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                self.assertEqual(packaging.main(args), 1)
            self.assertEqual(error.getvalue(), "")
            self.assertNotIn("private-sentinel", output.getvalue())


if __name__ == "__main__":
    unittest.main()
