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
from asn1crypto import x509 as asn1_x509

from tools import ios_profile_cms_rehearsal as rehearsal
from tools import ios_profile_cms_verification as verify


class CMSTests(unittest.TestCase):
    def test_compatibility_matrix_genuinely_signed_and_preserves_bytes(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        values = rehearsal.fixture(compatibility=True)
        self.assertEqual(len(values["compatibility"]), 384)
        self.assertEqual(len(set(values["compatibility"])), 384)
        self.assertEqual(len(values["protection_parameters"]), 24)
        public_key = x509.load_der_x509_certificate(values["der"]).public_key()
        combinations = set()
        for data in values["compatibility"] + values["protection_parameters"]:
            parsed = verify.preflight(data)
            self.assertEqual(parsed["cms"], data)
            self.assertEqual(parsed["payload"], values["payload"])
            signer = cms.ContentInfo.load(data)["content"]["signer_infos"][0]
            digest = signer["digest_algorithm"]["algorithm"].native
            if data in values["compatibility"]:
                outer = cms.ContentInfo.load(data)["content"]
                algorithms = (
                    outer["digest_algorithms"][0],
                    signer["digest_algorithm"],
                    signer["signature_algorithm"],
                )
                self.assertTrue(
                    all(
                        isinstance(item["parameters"], (core.Void, core.Null))
                        for item in algorithms
                    )
                )
                combinations.add(
                    (
                        digest,
                        signer["signature_algorithm"]["algorithm"].native,
                        tuple(
                            isinstance(item["parameters"], core.Null)
                            for item in algorithms
                        ),
                        tuple(
                            sorted(
                                item["type"].native for item in signer["signed_attrs"]
                            )
                        ),
                    )
                )
            public_key.verify(
                signer["signature"].native,
                signer["signed_attrs"].untag().dump(),
                padding.PKCS1v15(),
                {
                    "sha256": hashes.SHA256,
                    "sha384": hashes.SHA384,
                    "sha512": hashes.SHA512,
                }[digest](),
            )
        self.assertEqual(len(combinations), 384)
        protection_combinations = set()
        for data in values["protection_parameters"]:
            signer = cms.ContentInfo.load(data)["content"]["signer_infos"][0]
            protected = next(
                item
                for item in signer["signed_attrs"]
                if item["type"].native == "cms_algorithm_protection"
            )["values"][0]
            protection_combinations.add(
                (
                    signer["digest_algorithm"]["algorithm"].native,
                    signer["signature_algorithm"]["algorithm"].native,
                    isinstance(protected["digest_algorithm"]["parameters"], core.Null),
                    isinstance(
                        protected["signature_algorithm"]["parameters"], core.Null
                    ),
                )
            )
        self.assertEqual(len(protection_combinations), 24)

    def test_finite_crypto_and_typed_attribute_negative_deltas(self):
        for case in (
            "sha1",
            "md5",
            "sha224",
            "unknown_digest",
            "cross_digest",
            "rsa_mismatch",
            "pss",
            "ecdsa",
            "unknown_signature",
            "digest_value",
            "digest_length",
            "protection_oid",
            "protection_digest",
            "protection_mac",
            "protection_missing_signature",
            "protection_parameters",
            "protection_duplicate",
            "protection_multiple",
            "capabilities_oversize",
            "capabilities_multiple",
            "capabilities_depth",
        ):
            with self.subTest(case=case):
                document = self.document()
                signed = document["content"]
                signer = signed["signer_infos"][0]
                attrs = signer["signed_attrs"]
                protection = cms.CMSAttribute(
                    {
                        "type": "cms_algorithm_protection",
                        "values": [
                            {
                                "digest_algorithm": {"algorithm": "sha256"},
                                "signature_algorithm": {"algorithm": "rsassa_pkcs1v15"},
                            }
                        ],
                    }
                )
                if case in {"sha1", "md5", "sha224", "unknown_digest"}:
                    algorithm = "1.2.3" if case == "unknown_digest" else case
                    signed["digest_algorithms"][0]["algorithm"] = algorithm
                    signer["digest_algorithm"]["algorithm"] = algorithm
                elif case == "cross_digest":
                    signed["digest_algorithms"][0]["algorithm"] = "sha384"
                elif case in {"rsa_mismatch", "pss", "ecdsa", "unknown_signature"}:
                    signer["signature_algorithm"] = {
                        "algorithm": {
                            "rsa_mismatch": "sha384_rsa",
                            "pss": "rsassa_pss",
                            "ecdsa": "sha256_ecdsa",
                            "unknown_signature": "1.2.3",
                        }[case]
                    }
                elif case in {"digest_value", "digest_length"}:
                    next(
                        item
                        for item in attrs
                        if item["type"].native == "message_digest"
                    )["values"] = [b"x" * (32 if case == "digest_value" else 31)]
                elif case.startswith("protection"):
                    value = protection["values"][0]
                    if case == "protection_oid":
                        value["signature_algorithm"] = {"algorithm": "sha256_rsa"}
                    elif case == "protection_digest":
                        value["digest_algorithm"] = {"algorithm": "sha384"}
                    elif case == "protection_mac":
                        value["mac_algorithm"] = {"algorithm": "sha256"}
                    elif case == "protection_missing_signature":
                        value["signature_algorithm"] = None
                    elif case == "protection_parameters":
                        value["signature_algorithm"] = {
                            "algorithm": "1.2.3",
                            "parameters": core.Integer(1),
                        }
                    elif case == "protection_multiple":
                        protection["values"].append(value)
                    attrs.append(protection)
                    if case == "protection_duplicate":
                        attrs.append(protection)
                else:
                    capabilities = cms.CMSAttribute(
                        {
                            "type": "smime_capabilities",
                            "values": [
                                [{"capability_id": "1.2.3"}]
                                * (33 if case == "capabilities_oversize" else 1)
                            ],
                        }
                    )
                    if case == "capabilities_multiple":
                        capabilities["values"].append(capabilities["values"][0])
                    if case == "capabilities_depth":

                        class Nested(core.SequenceOf):
                            _child_spec = core.Any

                        encoded = core.Null().dump()
                        for _ in range(34):
                            encoded = b"\x30" + bytes([len(encoded)]) + encoded
                        capabilities["values"][0][0]["parameters"] = Nested.load(
                            encoded
                        )
                    attrs.append(capabilities)
                with (
                    patch.object(verify, "_pipe") as native,
                    self.assertRaisesRegex(verify.Rejected, "CMS_STRUCTURE_REJECTED"),
                ):
                    verify._native_verified(
                        {"cms": document.dump(force=True)}, rehearsal.NOW, "unused"
                    )
                native.assert_not_called()

    def test_optional_metadata_tamper_does_not_become_signature_evidence(self):
        from cryptography import x509
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        # Existing signature is deliberately not recomputed after adding metadata.
        document = self.document()
        signer = document["content"]["signer_infos"][0]
        signer["signed_attrs"].append(
            cms.CMSAttribute(
                {
                    "type": "smime_capabilities",
                    "values": [[{"capability_id": "1.3.14.3.2.26"}]],
                }
            )
        )
        data = document.dump(force=True)
        verify.preflight(data)
        with self.assertRaises(InvalidSignature):
            x509.load_der_x509_certificate(self.fixture["der"]).public_key().verify(
                signer["signature"].native,
                signer["signed_attrs"].untag().dump(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        capabilities = next(
            item
            for item in signer["signed_attrs"]
            if item["type"].native == "smime_capabilities"
        )
        capabilities["values"] = [[{"capability_id": "1.3.14.3.2.26"}] * 32]
        with (
            patch.object(verify, "_pipe") as native,
            patch("builtins.open", side_effect=AssertionError("private-sentinel")),
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("private-sentinel"),
            ),
        ):
            verify.preflight(document.dump(force=True))
        native.assert_not_called()

    def test_fictional_matrix_failure_alias_is_fixed_and_non_private(self):
        for label, expected in [
            ("compatibility_407", "compatibility_407"),
            ("private-sentinel", "preflight"),
        ]:
            with (
                patch.object(
                    rehearsal,
                    "run",
                    side_effect=verify.Rejected("REHEARSAL_CASE_FAILED", label),
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(rehearsal.main([]), 1)
            result = json.loads(output.getvalue())
            self.assertEqual(result["stage"], expected)
            self.assertNotIn("private-sentinel", output.getvalue())
            self.assertFalse(result["signing_authorized"])

    def test_content_digest_is_checked_before_native(self):
        with self.assertRaises(verify.Rejected):
            verify.preflight(rehearsal.tampered(self.fixture["cms"], "content"))

    def predicate_corpus(self):
        """Fictional rule mutations, also reusable for one-time frozen-base parity."""
        cases = {}
        for key in verify.PREDICATE_KEYS:
            document = self.document()
            signed = document["content"]
            signer = signed["signer_infos"][0]
            attrs = signer["signed_attrs"]
            if key == "digest_set_cardinality":
                signed["digest_algorithms"] = []
            elif key == "digest_set_algorithm":
                signed["digest_algorithms"][0]["algorithm"] = "sha1"
            elif key == "signer_version":
                signer["version"] = "v3"
            elif key == "signer_identifier":
                signer["sid"] = cms.SignerIdentifier(
                    {"subject_key_identifier": b"fictional"}
                )
            elif key == "unsigned_attributes_absent":
                signer["unsigned_attrs"] = []
            elif key == "signer_digest_algorithm":
                signer["digest_algorithm"]["algorithm"] = "sha1"
            elif key == "signature_algorithm":
                signer["signature_algorithm"]["algorithm"] = "sha1_rsa"
            elif key == "signature_size":
                signer["signature"] = b"fictional"
            elif key.endswith("parameters"):
                algorithm = (
                    signed["digest_algorithms"][0]
                    if key == "digest_set_parameters"
                    else (
                        signer["digest_algorithm"]
                        if key == "signer_digest_parameters"
                        else signer["signature_algorithm"]
                    )
                )
                # Unknown algorithms use Any parameters; known RSA/SHA types
                # enforce NULL in the library schema before predicate collection.
                algorithm["algorithm"] = "1.2.3.4"
                algorithm["parameters"] = core.Integer(1)
            elif key == "attribute_cardinality":
                signer["signed_attrs"] = []
            elif key == "attribute_types":
                attrs[0] = cms.CMSAttribute(
                    {"type": "1.2.3.4", "values": [core.Null()]}
                )
            elif key == "attribute_uniqueness":
                attrs[1] = attrs[0]
            elif key == "attribute_value_cardinality":
                attrs[0]["values"] = []
            elif key in {"content_type_value", "message_digest_value"}:
                name = (
                    "content_type" if key == "content_type_value" else "message_digest"
                )
                attribute = next(item for item in attrs if item["type"].native == name)
                attribute["values"] = [
                    "signed_data" if name == "content_type" else b"fictional"
                ]
            elif key == "signing_time_value":
                # A wrong type is rejected by the ASN.1 schema, not this
                # post-materialization datetime predicate. Test that separately.
                continue
            elif key == "attribute_required":
                signer["signed_attrs"] = [
                    item for item in attrs if item["type"].native != "message_digest"
                ]
            elif key == "certificate_choices":
                signed["certificates"][0] = cms.CertificateChoices(
                    name="other",
                    value={"other_cert_format": "1.2.3", "other_cert": core.Null()},
                )
            elif key == "certificate_size":
                signed["certificates"][0].chosen["tbs_certificate"]["subject"] = (
                    asn1_x509.Name.build({"common_name": "f" * 66000})
                )
            elif key == "certificate_encoding":
                signed["certificates"][0].chosen["tbs_certificate"]["version"] = 4
            elif key == "certificate_uniqueness":
                signed["certificates"][1] = signed["certificates"][0]
            elif key == "signer_binding":
                signer["sid"].chosen["serial_number"] = 123456789
            elif key == "digest_consistency":
                signer["digest_algorithm"]["algorithm"] = "sha384"
            elif key == "signature_digest_consistency":
                signer["signature_algorithm"]["algorithm"] = "sha384_rsa"
            elif key == "message_digest_matches":
                next(item for item in attrs if item["type"].native == "message_digest")[
                    "values"
                ] = [b"x" * 32]
            elif key == "smime_capabilities_value":
                attrs.append(
                    cms.CMSAttribute(
                        {
                            "type": "smime_capabilities",
                            "values": [[{"capability_id": "1.2.3"}] * 33],
                        }
                    )
                )
            elif key == "algorithm_protection_value":
                attrs.append(
                    cms.CMSAttribute(
                        {
                            "type": "cms_algorithm_protection",
                            "values": [
                                {
                                    "digest_algorithm": {"algorithm": "sha384"},
                                    "signature_algorithm": {
                                        "algorithm": "rsassa_pkcs1v15"
                                    },
                                }
                            ],
                        }
                    )
                )
            elif key == "canonical_der":
                raw = document.dump(force=True)
                cases[key] = b"\x30\x83\x00" + raw[2:]
                continue
            cases[key] = document.dump(force=True)
        return cases

    def test_every_reachable_predicate_and_fixed_output(self):
        valid = verify.diagnose_predicates(self.fixture["cms"])
        self.assertEqual(valid["stage"], "CMS_STRUCTURE_PASS")
        self.assertEqual(
            {
                key
                for key, value in valid["predicates"].items()
                if value == "NOT_CHECKED"
            },
            {"smime_capabilities_value", "algorithm_protection_value"},
        )
        self.assertNotIn("REJECTED", valid["predicates"].values())
        for key, data in self.predicate_corpus().items():
            with self.subTest(rule=key):
                result = verify.diagnose_predicates(data)
                self.assertEqual(result["predicates"][key], "REJECTED")
                self.assertEqual(set(result), {"stage", "predicates"})
                self.assertEqual(set(result["predicates"]), set(verify.PREDICATE_KEYS))
                self.assertLessEqual(
                    set(result["predicates"].values()),
                    {"PASS", "REJECTED", "NOT_CHECKED"},
                )
                with self.assertRaises(verify.Rejected) as caught:
                    verify.preflight(data)
                self.assertEqual(caught.exception.args, ("CMS_STRUCTURE_REJECTED",))

    def test_predicates_zero_io_schema_unknown_and_optional_prerequisites(self):
        document = self.document()
        signer = document["content"]["signer_infos"][0]
        signer["signed_attrs"] = [
            item
            for item in signer["signed_attrs"]
            if item["type"].native != "signing_time"
        ]
        optional = document.dump(force=True)
        with (
            patch("builtins.open", side_effect=AssertionError("private-sentinel")),
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("private-sentinel"),
            ),
            patch.object(
                subprocess, "Popen", side_effect=AssertionError("private-sentinel")
            ),
            patch.object(
                verify,
                "_compile_native",
                side_effect=AssertionError("private-sentinel"),
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = verify.diagnose_predicates(optional)
            self.assertEqual(result["stage"], "CMS_STRUCTURE_PASS")
            self.assertEqual(result["predicates"]["signing_time_value"], "NOT_CHECKED")
            for data in [
                b"private-sentinel",
                self.fixture["cms"] + b"private-sentinel",
            ]:
                result = verify.diagnose_predicates(data)
                self.assertEqual(set(result["predicates"].values()), {"NOT_CHECKED"})
                self.assertNotIn("private-sentinel", repr(result))
            with patch.object(
                verify, "_materialize", side_effect=RuntimeError("private-sentinel")
            ):
                result = verify.diagnose_predicates(optional)
                self.assertEqual(result["stage"], "CMS_UNKNOWN_REJECTED")
                self.assertEqual(set(result["predicates"].values()), {"NOT_CHECKED"})
            self.assertEqual(output.getvalue(), "")

    def test_predicates_collect_independent_failures(self):
        document = self.document()
        signer = document["content"]["signer_infos"][0]
        signer["digest_algorithm"]["algorithm"] = "sha1"
        signer["signed_attrs"] = []
        signer["sid"].chosen["serial_number"] = 123456789
        result = verify.diagnose_predicates(document.dump(force=True))
        self.assertEqual(result["stage"], "CMS_ALGORITHM_REJECTED")
        for key in (
            "signer_digest_algorithm",
            "attribute_cardinality",
            "signer_binding",
        ):
            self.assertEqual(result["predicates"][key], "REJECTED")
        self.assertEqual(result["predicates"]["canonical_der"], "PASS")
        raw = document.dump(force=True)
        result = verify.diagnose_predicates(b"\x30\x83\x00" + raw[2:])
        self.assertEqual(result["predicates"]["canonical_der"], "REJECTED")
        self.assertEqual(result["stage"], "CMS_ALGORITHM_REJECTED")
        _, x509, _ = verify._dependencies()
        with patch.object(
            x509,
            "load_der_x509_certificate",
            side_effect=RuntimeError("private-sentinel"),
        ):
            result = verify.diagnose_predicates(raw)
        self.assertEqual(result["stage"], "CMS_ALGORITHM_REJECTED")
        self.assertEqual(result["predicates"]["certificate_encoding"], "REJECTED")
        self.assertEqual(result["predicates"]["signer_binding"], "NOT_CHECKED")
        self.assertEqual(result["predicates"]["canonical_der"], "PASS")
        self.assertNotIn("private-sentinel", repr(result))

    def test_attribute_value_prerequisites_and_wrong_time_schema(self):
        document = self.document()
        attrs = document["content"]["signer_infos"][0]["signed_attrs"]
        content = next(item for item in attrs if item["type"].native == "content_type")
        content["values"] = []
        result = verify.diagnose_predicates(document.dump(force=True))["predicates"]
        self.assertEqual(result["attribute_value_cardinality"], "REJECTED")
        self.assertEqual(result["content_type_value"], "NOT_CHECKED")
        for key in ("message_digest_value", "signing_time_value", "canonical_der"):
            self.assertEqual(result[key], "PASS")
        document = self.document()
        attrs = document["content"]["signer_infos"][0]["signed_attrs"]
        time_attribute = next(
            item for item in attrs if item["type"].native == "signing_time"
        )
        raw_attribute = time_attribute.dump()
        raw_time = time_attribute["values"][0].dump()
        malformed = document.dump().replace(
            raw_attribute, raw_attribute.replace(raw_time, b"\x04" + raw_time[1:]), 1
        )
        result = verify.diagnose_predicates(malformed)
        self.assertEqual(result["stage"], "CMS_SCHEMA_REJECTED")
        self.assertEqual(set(result["predicates"].values()), {"NOT_CHECKED"})

    def test_predicate_prerequisites_do_not_mask_unrelated_rules(self):
        document = self.document()
        document["content"]["digest_algorithms"] = []
        signer = document["content"]["signer_infos"][0]
        signer["sid"] = cms.SignerIdentifier({"subject_key_identifier": b"fictional"})
        result = verify.diagnose_predicates(document.dump(force=True))["predicates"]
        for key in ("digest_set_algorithm", "digest_set_parameters", "signer_binding"):
            self.assertEqual(result[key], "NOT_CHECKED")
        for key in ("digest_set_cardinality", "signer_identifier"):
            self.assertEqual(result[key], "REJECTED")
        for key in ("attribute_required", "certificate_encoding", "canonical_der"):
            self.assertEqual(result[key], "PASS")

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
            for field in ["signature"]:
                parsed = verify.preflight(rehearsal.tampered(values["cms"], field))
                self.assertIn("payload", parsed)
            with self.assertRaisesRegex(verify.Rejected, "CMS_STRUCTURE_REJECTED"):
                verify.preflight(rehearsal.tampered(values["cms"], "content"))

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
