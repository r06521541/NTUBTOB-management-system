"""Fictional memory-only CMS boundary tests; native evidence requires macOS."""

import base64
import contextlib
import io
import json
import platform
import socket
import subprocess
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from asn1crypto import cms, core

from tools import ios_profile_cms_rehearsal as rehearsal
from tools import ios_profile_cms_verification as verify


class CMSTests(unittest.TestCase):
    def test_diagnostic_stage_preserves_original_exception_args(self):
        for data, stage in [
            (b"", "CMS_SIZE_REJECTED"),
            (b"private-string", "CMS_DECODE_REJECTED"),
            (
                cms.ContentInfo(
                    {"content_type": "data", "content": b"private-string"}
                ).dump(),
                "CMS_CONTAINER_REJECTED",
            ),
        ]:
            with self.assertRaises(verify.Rejected) as caught:
                verify.preflight(data)
            self.assertEqual(caught.exception.args, ("CMS_STRUCTURE_REJECTED",))
            self.assertEqual(caught.exception.diagnostic_stage, stage)

    def test_diagnostic_attribute_algorithm_and_unknown_remain_rejections(self):
        for mutation, stage in [
            ("attributes", "CMS_ATTRIBUTES_REJECTED"),
            ("algorithm", "CMS_ALGORITHM_REJECTED"),
        ]:
            document = self.document()
            signer = document["content"]["signer_infos"][0]
            if mutation == "attributes":
                signer["signed_attrs"] = []
            else:
                signer["digest_algorithm"]["algorithm"] = "sha1"
            with self.assertRaises(verify.Rejected) as caught:
                verify.preflight(document.dump(force=True))
            self.assertEqual(caught.exception.args, ("CMS_STRUCTURE_REJECTED",))
            self.assertEqual(caught.exception.diagnostic_stage, stage)
        with (
            patch.object(
                verify, "_materialize", side_effect=RuntimeError("private-error")
            ),
            self.assertRaises(verify.Rejected) as caught,
        ):
            verify.preflight(self.fixture["cms"])
        self.assertEqual(caught.exception.args, ("CMS_STRUCTURE_REJECTED",))
        self.assertEqual(caught.exception.diagnostic_stage, "CMS_UNKNOWN_REJECTED")

    @classmethod
    def setUpClass(cls):
        cls.fixture = rehearsal.fixture()
        cls.parsed = verify.preflight(cls.fixture["cms"])

    def document(self):
        return cms.ContentInfo.load(self.fixture["cms"])

    def check(self, data, **kwargs):
        values = dict(
            expected_bundle=rehearsal.BUNDLE,
            expected_team=rehearsal.TEAM,
            expected_certificate_der=self.fixture["der"],
            now=rehearsal.NOW,
        )
        values.update(kwargs)
        return verify.verify_profile_cms(data, **values)

    def encoded_output(self, **changes):
        leaf = self.parsed["signer"]
        root = self.fixture["root"]
        intermediate = next(
            cert for cert in self.parsed["certificates"] if cert not in {leaf, root}
        )
        result = {
            "marker": "FICTIONAL_ONLY",
            "reason": "VERIFIED",
            "payload": base64.b64encode(self.fixture["payload"]).decode(),
            "signer": base64.b64encode(leaf).decode(),
            "chain": [
                base64.b64encode(cert).decode() for cert in [leaf, intermediate, root]
            ],
        }
        result.update(changes)
        return json.dumps(result).encode()

    def test_fixture_complete_parse_and_optional_root(self):
        self.assertEqual(self.parsed["payload"], self.fixture["payload"])
        self.assertEqual(len(self.parsed["certificates"]), 3)
        self.assertEqual(
            len(verify.preflight(self.fixture["without_root"])["certificates"]), 2
        )
        with patch.object(verify, "_pipe", return_value=self.encoded_output()):
            for data in [self.fixture["cms"], self.fixture["without_root"]]:
                self.assertEqual(
                    verify._native_verified(
                        verify.preflight(data),
                        rehearsal.NOW,
                        "unused",
                        _test_root=self.fixture["root"],
                    ),
                    self.fixture["payload"],
                )
            with self.assertRaisesRegex(verify.Rejected, "CMS_BINDING_REJECTED"):
                verify._native_verified(
                    verify.preflight(self.fixture["without_intermediate"]),
                    rehearsal.NOW,
                    "unused",
                    _test_root=self.fixture["root"],
                )

    def test_fixture_and_preflight_no_io_and_tamper_requires_native(self):
        with (
            patch("builtins.open", side_effect=AssertionError("private-file")),
            patch.object(
                socket, "create_connection", side_effect=AssertionError("network")
            ),
            patch.object(subprocess, "Popen", side_effect=AssertionError("native")),
        ):
            values = rehearsal.fixture()
            for field in ["signature", "content"]:
                parsed = verify.preflight(rehearsal.tampered(values["cms"], field))
                self.assertIn("payload", parsed)

    def test_compiled_public_anchor_and_test_marker_are_separate(self):
        with (
            patch.object(verify.platform, "system", return_value="Darwin"),
            patch.object(verify.platform, "mac_ver", return_value=("15.0", (), "")),
            patch.object(
                verify.subprocess, "run", return_value=Mock(returncode=0)
            ) as run,
        ):
            for root, marker in [
                (None, "PRODUCTION"),
                (self.fixture["root"], "FICTIONAL_ONLY"),
            ]:
                with verify._compile_native(_fictional_root=root) as binary:
                    public_code = (
                        Path(binary).with_name("main.swift").read_text(encoding="utf-8")
                    )
                    self.assertIn('let buildMarker = "' + marker + '"', public_code)
                    self.assertIn(
                        base64.b64encode(
                            verify._production_root() if root is None else root
                        ).decode(),
                        public_code,
                    )
                    self.assertNotIn("BEGIN PRIVATE", public_code)
                    self.assertNotIn(
                        base64.b64encode(self.fixture["cms"]).decode(), public_code
                    )
                    directory = Path(binary).parent
                self.assertFalse(directory.exists())
            self.assertEqual(run.call_args.kwargs["timeout"], 60)
            self.assertNotIn("shell", run.call_args.kwargs)
        with (
            patch.object(verify.platform, "system", return_value="Windows"),
            patch.object(verify.subprocess, "run") as run,
            self.assertRaisesRegex(verify.Rejected, "PLATFORM_UNSUPPORTED"),
        ):
            with verify._compile_native():
                self.fail("unsupported platform")
        run.assert_not_called()

    def test_structure_never_invokes_native(self):
        invalid = [
            b"",
            b"x" * (verify.MAX_CMS + 1),
            "fictional-private-string",
            self.fixture["cms"] + b"junk",
            self.fixture["detached"],
            self.fixture["multiple"],
            cms.ContentInfo({"content_type": "data", "content": b"unsigned"}).dump(),
        ]
        for kind in ["enveloped_data", "encrypted_data", "signed_and_enveloped_data"]:
            document = self.document()
            # Replace only OID using library encoding; payload cannot reach decoder.
            data = document.dump().replace(
                cms.ContentType("signed_data").dump(), cms.ContentType(kind).dump(), 1
            )
            invalid.append(data)
        for mutation in [
            "nested",
            "no_signer",
            "unsigned",
            "crls",
            "digest",
            "signature_algorithm",
            "duplicate_attrs",
            "missing_attrs",
            "unsupported_attrs",
            "extra_sequence",
            "duplicate_cert",
            "missing_cert",
            "certificate_choice",
        ]:
            document = self.document()
            signed = document["content"]
            signer = signed["signer_infos"][0]
            if mutation == "nested":
                signed["encap_content_info"]["content_type"] = "signed_data"
            elif mutation == "no_signer":
                signed["signer_infos"] = []
            elif mutation == "unsigned":
                signer["unsigned_attrs"] = [
                    {"type": "content_type", "values": ["data"]}
                ]
            elif mutation == "crls":
                signed["crls"] = []
            elif mutation == "digest":
                signer["digest_algorithm"]["algorithm"] = "sha1"
            elif mutation == "signature_algorithm":
                signer["signature_algorithm"]["algorithm"] = "sha1_rsa"
            elif mutation == "duplicate_attrs":
                signer["signed_attrs"].append(signer["signed_attrs"][0])
            elif mutation == "missing_attrs":
                signer["signed_attrs"] = []
            elif mutation == "unsupported_attrs":
                signer["signed_attrs"].append(
                    cms.CMSAttribute({"type": "1.2.3.4", "values": [core.Null()]})
                )
            elif mutation == "extra_sequence":
                raw = document.dump()
                body = raw[4:] + b"\x05\x00"
                invalid.append(b"\x30\x82" + len(body).to_bytes(2, "big") + body)
                continue
            elif mutation == "duplicate_cert":
                signed["certificates"][1] = signed["certificates"][0]
            elif mutation == "missing_cert":
                signed["certificates"] = [signed["certificates"][0]]
            elif mutation == "certificate_choice":
                signed["certificates"][0] = cms.CertificateChoices(
                    name="other",
                    value={"other_cert_format": "1.2.3", "other_cert": core.Null()},
                )
            invalid.append(document.dump(force=True))
        original = self.fixture["cms"]
        self.assertEqual(original[:2], b"\x30\x82")
        invalid += [
            b"\x30\x83\x00" + original[2:],
            b"\x30\x80" + original[4:] + b"\x00\x00",
        ]
        for index, data in enumerate(invalid):
            with (
                self.subTest(case=index),
                patch.object(verify, "_compile_native") as native,
            ):
                result = self.check(data)
                self.assertEqual(result["reason"], "CMS_STRUCTURE_REJECTED")
                native.assert_not_called()
                self.assertTrue(
                    all(
                        value is False
                        for key, value in result.items()
                        if key.endswith(("_verified", "_authorized"))
                    )
                )

    def test_library_tree_depth_node_and_extra_field_limits(self):
        extra = core.Sequence.load(b"\x30\x02\x05\x00")
        with self.assertRaises(ValueError):
            verify._materialize(extra)

        class Nested(core.SequenceOf):
            _child_spec = core.Any

        nested = core.Null().dump()
        for _ in range(34):
            nested = b"\x30" + bytes([len(nested)]) + nested
        with self.assertRaises(ValueError):
            verify._materialize(Nested.load(nested))
        with self.assertRaises(ValueError):
            verify._materialize(Nested([core.Null()] * 129))

    def test_native_payload_chain_marker_and_output_binding(self):
        with (
            patch.object(verify, "_pipe") as pipe,
            self.assertRaisesRegex(verify.Rejected, "CMS_STRUCTURE_REJECTED"),
        ):
            verify._native_verified(
                {"cms": b"fictional-encrypted-input"}, rehearsal.NOW, "unused"
            )
        pipe.assert_not_called()
        for changes, reason in [
            ({"marker": "PRODUCTION"}, "TEST_BUILD_REJECTED"),
            ({"payload": base64.b64encode(b"wrong").decode()}, "CMS_BINDING_REJECTED"),
            ({"signer": base64.b64encode(b"wrong").decode()}, "CMS_BINDING_REJECTED"),
            ({"chain": []}, "NATIVE_OUTPUT_REJECTED"),
            ({"extra": "private-string"}, "NATIVE_OUTPUT_REJECTED"),
            ({"payload": "!"}, "NATIVE_OUTPUT_REJECTED"),
        ]:
            with (
                self.subTest(reason=reason),
                patch.object(
                    verify, "_pipe", return_value=self.encoded_output(**changes)
                ),
                self.assertRaisesRegex(verify.Rejected, reason),
            ):
                verify._native_verified(
                    self.parsed,
                    rehearsal.NOW,
                    "unused",
                    _test_root=self.fixture["root"],
                )
        with (
            patch.object(verify, "_pipe", return_value=self.encoded_output()),
            self.assertRaisesRegex(verify.Rejected, "TEST_BUILD_REJECTED"),
        ):
            verify._native_verified(self.parsed, rehearsal.NOW, "unused")
        for raw in [
            b'{"marker":"PRODUCTION","marker":"PRODUCTION"}',
            b"private-string",
            b"[]",
        ]:
            with (
                patch.object(verify, "_pipe", return_value=raw),
                self.assertRaises(verify.Rejected),
            ):
                verify._native_verified(self.parsed, rehearsal.NOW, "unused")

    def test_invalid_time_and_no_caller_trust_flag(self):
        for now in [None, rehearsal.NOW.replace(tzinfo=None), "private-date"]:
            with patch.object(verify, "_compile_native") as native:
                self.assertEqual(
                    self.check(self.fixture["cms"], now=now)["reason"], "TIME_REJECTED"
                )
                native.assert_not_called()
        with self.assertRaises(TypeError):
            self.check(self.fixture["cms"], trusted=True)

    def test_fixed_public_results_and_content_only_after_native(self):
        with (
            patch.object(verify, "_compile_native") as compile_native,
            patch.object(
                verify,
                "_native_verified",
                side_effect=verify.Rejected("CMS_SIGNATURE_REJECTED"),
            ),
            patch.object(verify.ios_profile_validation, "validate_profile") as content,
        ):
            self.assertEqual(
                self.check(self.fixture["cms"])["reason"], "CMS_SIGNATURE_REJECTED"
            )
            content.assert_not_called()
        with (
            patch.object(verify, "_compile_native"),
            patch.object(
                verify, "_native_verified", return_value=self.fixture["payload"]
            ),
        ):
            result = self.check(self.fixture["cms"])
            self.assertEqual(
                result["classification"], "CMS_PROFILE_VERIFIED_RESTRICTED"
            )
            for key in [
                "revocation_verified",
                "apple_private_policy_verified",
                "private_key_possession_verified",
                "signing_authorized",
                "upload_authorized",
                "release_authorized",
            ]:
                self.assertIs(result[key], False)
        for error in [
            RuntimeError("private-string"),
            verify.Rejected("private-string"),
        ]:
            with (
                patch.object(verify, "preflight", side_effect=error),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                result = self.check(b"private-string")
            self.assertEqual(output.getvalue(), "")
            self.assertNotIn("private-string", repr(result))
        with (
            patch.object(rehearsal, "run") as run,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(rehearsal.main(["private-string"]), 1)
        run.assert_not_called()
        self.assertNotIn("private-string", output.getvalue())

    def test_pipe_bound_crash_timeout(self):
        for output, code, expected in [
            (b"x" * (verify.MAX_OUTPUT + 1), 0, "NATIVE_OUTPUT_REJECTED"),
            (b"private", 1, "NATIVE_OUTPUT_REJECTED"),
            (b"{}", 0, None),
        ]:
            process = Mock(
                stdin=io.BytesIO(), stdout=io.BytesIO(output), returncode=code
            )
            process.poll.return_value = code
            with patch.object(verify.subprocess, "Popen", return_value=process):
                if expected:
                    with self.assertRaisesRegex(verify.Rejected, expected):
                        verify._pipe("unused", b"fictional")
                else:
                    self.assertEqual(verify._pipe("unused", b"fictional"), output)
        process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(), returncode=0)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("private-string", 30), 0]
        with (
            patch.object(verify.subprocess, "Popen", return_value=process),
            self.assertRaisesRegex(verify.Rejected, "NATIVE_TIMEOUT"),
        ):
            verify._pipe("unused", b"fictional")
        process.kill.assert_called_once()

    def test_native_source_trust_order_and_no_private_spi(self):
        source = verify.SOURCE.read_text(encoding="utf-8")
        self.assertIn("status == .valid", source)
        self.assertIn("policy, false, &status, &trust, nil", source)
        evaluate = source.index("SecTrustEvaluateWithError")
        for setter in [
            "SecTrustSetPolicies",
            "SecTrustSetAnchorCertificates(",
            "SecTrustSetAnchorCertificatesOnly",
            "SecTrustSetNetworkFetchAllowed",
            "SecTrustSetVerifyDate",
        ]:
            self.assertLess(source.index(setter), evaluate)
        for forbidden in [
            "SecPolicyCreateiPhone",
            "SecTrustSetExceptions",
            "SecItemAdd",
            "SecKeychain",
            "http://",
            "https://",
            "SecPolicyCreateWithProperties",
        ]:
            self.assertNotIn(forbidden, source)

    @unittest.skipUnless(
        platform.system() == "Darwin",
        "Native CMS macOS evidence is mandatory in hosted rehearsal",
    )
    def test_actual_native_rehearsal(self):
        self.assertEqual(rehearsal.run(), "FICTIONAL_CMS_REHEARSAL_VERIFIED")


if __name__ == "__main__":
    unittest.main()
