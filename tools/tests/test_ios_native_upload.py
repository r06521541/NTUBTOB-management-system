"""Fictional credentials and native help; no signing or Apple request."""

import base64
import json
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tools import ios_native_upload as upload


def fixture():
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return {
        "key_id": "FAKEKEY001",
        "issuer_id": "11111111-2222-4333-8444-555555555555",
        "p8_base64": base64.b64encode(pem).decode("ascii"),
    }


class CredentialTests(unittest.TestCase):
    def test_existing_validated_key_roundtrip(self):
        value = fixture()
        metadata, pem = upload.credential(json.dumps(value).encode())
        self.assertEqual(set(metadata), {"key_id", "issuer_id"})
        self.assertEqual(pem, base64.b64decode(value["p8_base64"]))

    def test_no_private_value_in_errors(self):
        for field in ("key_id", "issuer_id", "p8_base64"):
            value = fixture()
            value[field] = "fictional-sensitive-DO-NOT-ECHO"
            with self.assertRaises(upload.Failure) as caught:
                upload.credential(json.dumps(value).encode())
            self.assertNotIn("sensitive", str(caught.exception.public()))
            self.assertEqual(caught.exception.stage, "asc_input")

    def test_duplicate_extra_fields_bad_key_and_size_rejected(self):
        good = json.dumps(fixture()).encode()
        for raw in (
            b"{}",
            b"x" * 48001,
            good[:-1] + b',"key_id":"FAKEKEY001"}',
            good[:-1] + b',"extra":"x"}',
        ):
            with self.assertRaises(upload.Failure):
                upload.credential(raw)


class ProbeTests(unittest.TestCase):
    def test_fixed_xcode_contents_not_assumed_developer_subtree(self):
        prefix = "/Applications/Xcode_26.3.app/Contents/"
        for path, accepted in (
            (prefix + "SharedFrameworks/Fixture.framework/Support/altool", True),
            (prefix + "Developer/usr/bin/altool", True),
            (prefix + "../elsewhere/altool", False),
            (prefix + "../Contents/Developer/usr/bin/altool", False),
            (prefix.replace("26.3", "26.4") + "Developer/usr/bin/altool", False),
            (prefix.rstrip("/") + "-other/altool", False),
        ):

            def run(stage, *args, **kwargs):
                if stage == "xcode_version":
                    return b"Xcode 26.3\nBuild version 17C529"
                if stage == "altool_location":
                    return path.encode()
                return b"--help"

            with self.subTest(path=path):
                if accepted:
                    self.assertTrue(upload.probe(run=run)["altool_under_pinned_xcode"])
                else:
                    with self.assertRaises(upload.Failure):
                        upload.probe(run=run)

    def test_help_probe_no_key_file_or_upload(self):
        calls = []

        def run(stage, args, cwd, timeout=60):
            calls.append((stage, args))
            if stage == "xcode_version":
                return b"Xcode 26.3\nBuild version 17C529\n"
            if stage == "altool_location":
                return upload.signing.DEVELOPER.encode() + b"/usr/bin/altool"
            return b"--upload-app --upload-package --apiKey --apiIssuer --output-format --help"

        result = upload.probe(run=run)
        self.assertEqual(result["classification"], "TOOL_PROBED")
        self.assertEqual(result["options"]["upload_app"], True)
        self.assertFalse(result["upload_attempted"])
        self.assertEqual(calls[-1][1], ["/usr/bin/xcrun", "altool", "--help"])

    def test_toolchain_drift_precedes_altool(self):
        with self.assertRaises(upload.Failure) as caught:
            upload.probe(run=lambda *a, **k: b"Xcode unexpected")
        self.assertEqual(caught.exception.reason, "TOOLCHAIN_DRIFT")

    def test_unknown_help_is_observation_not_upload_readiness(self):
        def run(stage, *args, **kwargs):
            if stage == "altool_location":
                return upload.signing.DEVELOPER.encode() + b"/usr/bin/altool"
            return (
                b"Xcode 26.3\nBuild version 17C529"
                if stage == "xcode_version"
                else b"new interface"
            )

        result = upload.probe(run=run)
        self.assertFalse(any(result["options"].values()))
        self.assertFalse(result["upload_authorized"])


if __name__ == "__main__":
    unittest.main()
