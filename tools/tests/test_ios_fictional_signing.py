"""Fictional cross-process signing contract; no real assets."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import ios_fictional_signing as target
from tools.tests.test_ios_xcode_feasibility import FakeRunner as ToolchainRunner


class Runner(ToolchainRunner):
    def __call__(self, args, **kwargs):
        if "clang" in args:
            Path(args[-1]).write_bytes(b"fictional-mach-o")
        if Path(args[0]).name == "native":
            self.calls.append(args)
            if self.failure == "timeout":
                raise target.bounded.Rejected("PROCESS_TIMEOUT")
            if self.failure == "cancel":
                raise KeyboardInterrupt
            if self.failure == "raw":
                return 0, b"private-sentinel"
            payload = kwargs["payload"]
            reason = (
                "AUTH_REJECTED"
                if payload[0]
                else (
                    "CERTIFICATE_MISMATCH"
                    if payload.endswith(b"wrong")
                    else "SIGNING_VERIFIED"
                )
            )
            phase = (
                "import"
                if payload[0]
                else (
                    "certificate_match"
                    if reason == "CERTIFICATE_MISMATCH"
                    else "tamper_rejected"
                )
            )
            if self.failure == "signing":
                reason, phase = "CUSTODY_REJECTED", "codesign_exit"
            value = {
                **target.empty_observation(),
                "reason": reason,
                "phase": phase,
                "error_class": "OS_SUCCESS",
                "cleanup": "VERIFIED",
                "cleanup_phase": "completed",
                "cleanup_error_class": "OS_SUCCESS",
            }
            if reason == "SIGNING_VERIFIED":
                value.update(codesign_exit="ZERO", codesign_output="BOUNDED")
            if self.failure == "cleanup":
                value.update(
                    reason="CLEANUP_UNRESOLVED",
                    cleanup="DELETE_REJECTED",
                    cleanup_phase="delete",
                    cleanup_error_class="OS_OTHER",
                )
            return 0, json.dumps(value).encode()
        return super().__call__(args, **kwargs)


class SigningTests(unittest.TestCase):
    def test_codesign_observation_schema(self):
        value = {
            "reason": "CUSTODY_REJECTED",
            "phase": "codesign_exit",
            "error_class": "PREDICATE_REJECTED",
            "cleanup": "VERIFIED",
            "cleanup_phase": "completed",
            "cleanup_error_class": "OS_SUCCESS",
            **target.empty_observation(),
        }
        value["codesign_exit"] = "NONZERO"
        value["codesign_output"] = "BOUNDED"
        self.assertEqual(target.native_detail(json.dumps(value).encode()), value)
        for key, invalid in (
            ("codesign_exit", "private-sentinel"),
            ("codesign_output", "private-sentinel"),
            ("marker_internal_component", "private-sentinel"),
        ):
            with self.assertRaises(target.bounded.Rejected):
                target.native_detail(json.dumps({**value, key: invalid}).encode())
        with self.assertRaises(target.bounded.Rejected):
            target.native_detail(
                json.dumps(
                    {
                        **value,
                        "reason": "SIGNING_VERIFIED",
                        "phase": "tamper_rejected",
                        "error_class": "OS_SUCCESS",
                        "codesign_output": "OVERFLOW",
                    }
                ).encode()
            )

    def exercise(self, failure=None):
        runner = Runner(failure)
        with (
            patch.object(target.platform, "system", return_value="Darwin"),
            patch.object(target.platform, "machine", return_value="arm64"),
            patch.object(
                target.bounded,
                "os_temp_root",
                return_value=Path(tempfile.gettempdir()).resolve(),
            ),
            patch.object(
                target,
                "fictional_material",
                return_value=(b"fictional", b"certificate", b"wrong"),
            ),
        ):
            result = target.rehearse(_run=runner)
        self.assertFalse(runner.root.exists())
        self.assertNotIn("private-sentinel", repr(result))
        return result, runner

    def test_order_and_false_authority(self):
        result, runner = self.exercise()
        self.assertEqual(result["classification"], "FICTIONAL_SIGNING_VERIFIED")
        self.assertTrue(result["fictional_codesign_verified"])
        self.assertTrue(result["cleanup_verified"])
        first = next(
            i for i, args in enumerate(runner.calls) if Path(args[0]).name == "native"
        )
        self.assertEqual(len(runner.calls[first:]), 3)
        self.assertTrue(
            all(Path(args[0]).name == "native" for args in runner.calls[first:])
        )
        self.assertFalse(
            any(Path(args[0]).name == "fictional-mach-o" for args in runner.calls)
        )
        for key in (
            "positive_export_verified",
            "flutter_nested_signing_verified",
            "real_assets_verified",
            "real_signing_authorized",
            "signing_authorized",
            "upload_authorized",
            "release_authorized",
        ):
            self.assertFalse(result[key])

    def test_failure_and_cleanup_are_separate(self):
        result, _ = self.exercise("signing")
        self.assertEqual(result["classification"], "CUSTODY_REJECTED")
        self.assertTrue(result["cleanup_verified"])
        for failure in ("timeout", "cancel", "raw", "cleanup"):
            result, _ = self.exercise(failure)
            self.assertEqual(result["classification"], "CLEANUP_UNRESOLVED")
            self.assertFalse(result["cleanup_verified"])
            self.assertFalse(result["fictional_codesign_verified"])

    def test_compile_failure_precedes_key_generation(self):
        runner = Runner()

        def fail_compile(args, **kwargs):
            if "swiftc" in args:
                return 1, b"private-sentinel"
            return runner(args, **kwargs)

        with (
            patch.object(target.platform, "system", return_value="Darwin"),
            patch.object(target.platform, "machine", return_value="arm64"),
            patch.object(
                target.bounded,
                "os_temp_root",
                return_value=Path(tempfile.gettempdir()).resolve(),
            ),
            patch.object(target, "fictional_material") as material,
        ):
            result = target.rehearse(_run=fail_compile)
        material.assert_not_called()
        self.assertTrue(result["cleanup_verified"])
        self.assertFalse(result["fictional_codesign_verified"])
        self.assertNotIn("private-sentinel", repr(result))
        self.assertFalse(runner.root.exists())

    def test_platform_guard_does_not_allocate(self):
        with (
            patch.object(target.platform, "system", return_value="Windows"),
            patch.object(target.tempfile, "mkdtemp") as allocate,
        ):
            result = target.rehearse()
        self.assertEqual(result["classification"], "TOOLCHAIN_UNSUPPORTED")
        allocate.assert_not_called()

    def test_native_output_rejects_unknown_and_duplicate(self):
        valid = {
            **target.empty_observation(),
            "codesign_exit": "ZERO",
            "codesign_output": "BOUNDED",
            "reason": "SIGNING_VERIFIED",
            "phase": "tamper_rejected",
            "error_class": "OS_SUCCESS",
            "cleanup": "VERIFIED",
            "cleanup_phase": "completed",
            "cleanup_error_class": "OS_SUCCESS",
        }
        self.assertEqual(target.native_detail(json.dumps(valid).encode()), valid)
        for key, value in (
            ("phase", "import"),
            ("error_class", "OS_OTHER"),
            ("cleanup", "NOT_CREATED"),
            ("cleanup_phase", "delete"),
            ("cleanup_error_class", "OS_OTHER"),
        ):
            with self.assertRaises(target.bounded.Rejected):
                target.native_detail(json.dumps({**valid, key: value}).encode())
        for data in (
            b"private-sentinel",
            b'{"reason":"SIGNING_VERIFIED","reason":"SIGNING_VERIFIED"}',
            b"x" * 2049,
        ):
            with self.assertRaises(target.bounded.Rejected) as raised:
                target.native_detail(data)
            self.assertEqual(raised.exception.args, ("OUTPUT_REJECTED",))

    def test_fictional_material_encrypted_and_bound(self):
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs12

        p12, der, wrong = target.fictional_material()
        key, certificate, chain = pkcs12.load_key_and_certificates(
            p12, b"fictional-new-password"
        )
        self.assertEqual(
            key.public_key().public_numbers(), certificate.public_key().public_numbers()
        )
        self.assertEqual(x509.load_der_x509_certificate(der), certificate)
        self.assertFalse(chain)
        self.assertNotEqual(der, wrong)
        with self.assertRaises(ValueError):
            pkcs12.load_key_and_certificates(p12, b"fictional-wrong-password")

    def test_cli_has_no_private_entry(self):
        for args in ([], ["private-sentinel"], ["--rehearsal", "private-sentinel"]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(target.main(args), 1)
            self.assertNotIn("private-sentinel", output.getvalue())

    def test_native_contract(self):
        source = target.SOURCE.read_text()
        for required in (
            'SecTrustedApplicationCreateFromPath("/usr/bin/codesign"',
            "--timestamp=none",
            "kSecCSNoNetworkAccess",
            "errSecCSSignatureFailed",
            "SecKeychainDelete(target)",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "SecKeychainSetDefault",
            "SecKeychainSetSearchList",
            "set-key-partition-list",
            "NSTask",
            "--deep",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("[trustedApplication, signingApplication] as CFArray", source)
        self.assertIn(
            "SecCertificateCopyData(certificates[0]) as Data == expected", source
        )
        self.assertIn("child.standardError = stderrPipe", source)
        self.assertIn("ProcessInfo.processInfo.systemUptime + 20", source)
        self.assertIn("O_NONBLOCK", source)
        self.assertIn("8193 - captured.count", source)
        self.assertIn(
            'captured.count > 8192 { codesignOutput = "OVERFLOW"; return false }',
            source,
        )
        self.assertIn("if ended.wait(timeout: .now() + 2) == .timedOut", source)
        self.assertLess(
            source.index("kill(child.processIdentifier, SIGKILL)"),
            source.index("if ended.wait(timeout: .now() + 2) == .timedOut"),
        )
        self.assertNotIn('result["stderr"]', source)
        self.assertIn("kill(child.processIdentifier, SIGKILL)", source)


if __name__ == "__main__":
    unittest.main()
