"""Fictional-only compatibility checks; native execution mandatory on macOS CI."""

import contextlib
import io
import json
import os
import platform
import struct
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from tools import ios_pkcs12_compatibility as compatibility


def process_fixture(output=b"", code=0, timeout=False):
    process = Mock()
    process.stdin = io.BytesIO()
    process.stdout = io.BytesIO(output)
    process.returncode = code
    process.poll.return_value = code
    process.wait.side_effect = (
        [subprocess.TimeoutExpired("private-string", 30), code] if timeout else None
    )
    return process


class CompatibilityTests(unittest.TestCase):
    def test_real_packaging_recipe_in_memory(self):
        with patch.object(
            compatibility.packaging,
            "package_material",
            wraps=compatibility.packaging.package_material,
        ) as package:
            p12, certificate, other = compatibility.fictional_material()
        package.assert_called_once()
        key, cert, chain = pkcs12.load_key_and_certificates(p12, compatibility.NEW)
        self.assertIsNotNone(key)
        self.assertEqual(cert.public_bytes(serialization.Encoding.DER), certificate)
        self.assertEqual(len(chain), 2)
        self.assertNotEqual(certificate, other)
        with self.assertRaises(ValueError):
            pkcs12.load_key_and_certificates(p12, b"fictional-wrong-password")

    def test_framing_bounds_types_and_selector(self):
        self.assertEqual(
            compatibility.frame(b"a", b"b", True), struct.pack(">BII", 1, 1, 1) + b"ab"
        )
        for first, second, selector in [
            (b"", b"b", False),
            (b"x" * 65537, b"b", False),
            (b"a", b"x" * 65537, False),
            ("private-string", b"a", False),
            (b"a", b"b", 1),
        ]:
            with (
                self.subTest(),
                self.assertRaisesRegex(
                    compatibility.CompatibilityError, "^FRAME_REJECTED$"
                ),
            ):
                compatibility.frame(first, second, selector)

    def test_output_allowlist_crash_and_timeout(self):
        for output, code in [
            (b"private-string", 0),
            (b"AUTH_REJECTED\n", 1),
            (b"x" * 129, 0),
            (b"AUTH_REJECTED\nextra", 0),
        ]:
            with (
                patch.object(
                    compatibility.subprocess,
                    "Popen",
                    return_value=process_fixture(output, code),
                ),
                self.assertRaisesRegex(
                    compatibility.CompatibilityError, "^NATIVE_OUTPUT_REJECTED$"
                ),
            ):
                compatibility.native_case("fictional-binary", b"fictional-data")
        with (
            patch.object(
                compatibility.subprocess,
                "Popen",
                return_value=process_fixture(timeout=True),
            ),
            self.assertRaisesRegex(
                compatibility.CompatibilityError, "^NATIVE_TIMEOUT$"
            ),
        ):
            compatibility.native_case("fictional-binary", b"fictional-data")
        for reason in compatibility.NATIVE_REASONS:
            with patch.object(
                compatibility.subprocess,
                "Popen",
                return_value=process_fixture((reason + "\n").encode()),
            ) as run:
                self.assertEqual(
                    compatibility.native_case("fictional-binary", b"fixture"), reason
                )
                self.assertEqual(run.call_args.kwargs["stdin"], subprocess.PIPE)
                run.return_value.wait.assert_any_call(timeout=30)
                self.assertNotIn("shell", run.call_args.kwargs)

    def test_platform_stops_before_compile_or_generation(self):
        for system, version in [
            ("Windows", ""),
            ("Linux", ""),
            ("Darwin", "14.9"),
            ("Darwin", ""),
        ]:
            with (
                patch.object(compatibility.platform, "system", return_value=system),
                patch.object(
                    compatibility.platform, "mac_ver", return_value=(version, (), "")
                ),
                patch.object(compatibility.subprocess, "run") as run,
                patch.object(compatibility, "fictional_material") as fixture,
                self.assertRaisesRegex(
                    compatibility.CompatibilityError, "^PLATFORM_UNSUPPORTED$"
                ),
            ):
                compatibility.run_fictional_checks()
            run.assert_not_called()
            fixture.assert_not_called()

    def test_no_arguments_and_no_raw_exception_output(self):
        for args, error in [
            (["private-string"], None),
            ([], RuntimeError("private-string")),
            ([], compatibility.CompatibilityError("private-string")),
        ]:
            with (
                patch.object(
                    compatibility, "run_fictional_checks", side_effect=error
                ) as run,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(compatibility.main(args), 1)
            result = json.loads(output.getvalue())
            self.assertNotIn("private-string", output.getvalue())
            self.assertTrue(
                all(
                    value is False
                    for name, value in result.items()
                    if name not in {"classification", "stage"}
                )
            )
            if args:
                run.assert_not_called()

    def test_compile_failure_and_exact_negative_contract(self):
        with (
            patch.object(compatibility.platform, "system", return_value="Darwin"),
            patch.object(
                compatibility.platform, "mac_ver", return_value=("15.0", (), "")
            ),
        ):
            for effect, expected in [
                (SimpleNamespace(returncode=1), "NATIVE_COMPILE_FAILED"),
                (subprocess.TimeoutExpired("private", 60), "NATIVE_COMPILE_TIMEOUT"),
            ]:
                with (
                    patch.object(compatibility.subprocess, "run", side_effect=[effect]),
                    patch.object(compatibility, "fictional_material") as fixture,
                    self.assertRaisesRegex(
                        compatibility.CompatibilityError, "^" + expected + "$"
                    ),
                ):
                    compatibility.run_fictional_checks()
                fixture.assert_not_called()
            expected = [
                "MEMORY_IMPORT_VERIFIED",
                "AUTH_REJECTED",
                "DECODE_REJECTED",
                "AUTH_REJECTED",
                "CERTIFICATE_MISMATCH",
                "FRAME_REJECTED",
            ]
            for failure in range(7):
                responses = expected.copy()
                if failure < 6:
                    responses[failure] = "IMPORT_REJECTED"
                with (
                    patch.object(
                        compatibility.subprocess,
                        "run",
                        return_value=SimpleNamespace(returncode=0),
                    ),
                    patch.object(
                        compatibility,
                        "fictional_material",
                        return_value=(b"p12", b"leaf", b"root"),
                    ),
                    patch.object(compatibility, "native_case", side_effect=responses),
                ):
                    if failure < 6:
                        with self.assertRaisesRegex(
                            compatibility.CompatibilityError, "NATIVE_CASE_FAILED"
                        ):
                            compatibility.run_fictional_checks()
                    else:
                        self.assertEqual(
                            compatibility.run_fictional_checks(),
                            "FICTITIOUS_NATIVE_IMPORT_VERIFIED",
                        )

    def test_real_pipe_is_bounded_and_no_payload_file(self):
        original = subprocess.Popen
        for code, accepted in [
            (
                "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'AUTH_REJECTED\\n')",
                True,
            ),
            (
                "import sys; sys.stdout.buffer.write(b'x'*65536); sys.stdout.flush()",
                False,
            ),
        ]:

            def launch(args, **kwargs):
                # Fixed fictional child code only; no fixture bytes in argv/files.
                if platform.system() == "Windows":
                    kwargs["env"]["SystemRoot"] = os.environ["SystemRoot"]
                return original([sys.executable, "-c", code], **kwargs)

            with patch.object(compatibility.subprocess, "Popen", side_effect=launch):
                if accepted:
                    self.assertEqual(
                        compatibility.native_case("unused", b"fictional"),
                        "AUTH_REJECTED",
                    )
                else:
                    with self.assertRaises(compatibility.CompatibilityError):
                        compatibility.native_case("unused", b"fictional")

    def test_native_source_boundary(self):
        source = compatibility.SOURCE.read_text(encoding="utf-8")
        self.assertIn("guard #available(macOS 15.0, *)", source)
        self.assertIn("kSecImportToMemoryOnly as String: true", source)
        self.assertEqual(source.count("SecPKCS12Import("), 1)
        for forbidden in [
            "SecItemAdd(",
            "SecKeychain",
            "SecTrustEvaluate",
            "readToEnd",
            "contentsOfFile",
            "write(to:",
        ]:
            self.assertNotIn(forbidden, source)
        self.assertIn("items.count == 1", source)
        self.assertIn("SecKeyVerifySignature", source)

    @unittest.skipUnless(
        platform.system() == "Darwin",
        "Native macOS15+ required; mandatory hosted entry is not skipped",
    )
    def test_actual_memory_only_import(self):
        self.assertEqual(
            compatibility.run_fictional_checks(), "FICTITIOUS_NATIVE_IMPORT_VERIFIED"
        )


if __name__ == "__main__":
    unittest.main()
