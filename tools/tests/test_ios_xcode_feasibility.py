"""Fictional-only Xcode feasibility boundaries; never accept live credentials."""

import contextlib
import io
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import ios_xcode_feasibility as target


class FakeRunner:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure
        self.root = None

    def __call__(self, args, *, cwd, timeout, payload=b""):
        self.calls.append(args)
        self.root = Path(cwd) if Path(cwd).name != "custody" else Path(cwd).parent
        if args[0] == "/usr/bin/sw_vers":
            return 0, b"15.7.9" if args[-1] == "-productVersion" else b"24G123"
        if args[-1] == "-help":
            return (
                0,
                b"-exportArchive signingStyle manual destination export app-store-connect provisioningProfiles teamID signingCertificate",
            )
        if args[-1] == "SDKVersion":
            return 0, b"26.2"
        if args[-1] == "-version":
            return 0, (
                b"wrong"
                if self.failure == "toolchain"
                else b"Xcode 26.3\nBuild version 17C529"
            )
        if args[-1] == "archive":
            if self.failure == "cancel_archive":
                raise KeyboardInterrupt
            app = (
                Path(args[args.index("-archivePath") + 1])
                / "Products/Applications/Fictional.app"
            )
            app.mkdir(parents=True)
            (app / "Info.plist").write_bytes(
                plistlib.dumps(
                    {
                        "CFBundleIdentifier": (
                            "wrong" if self.failure == "target" else target.BUNDLE
                        )
                    }
                )
            )
        if args[0] == "/usr/bin/codesign":
            return 1, b"code object is not signed at all"
        if Path(args[0]).name == "native":
            if self.failure == "cancel_custody":
                raise KeyboardInterrupt
            if self.failure == "native_sentinel":
                return 0, b"private-sentinel"
            detail = {
                "reason": (
                    "AUTH_REJECTED"
                    if payload[0]
                    else (
                        "CERTIFICATE_MISMATCH"
                        if payload.endswith(b"wrong")
                        else "CUSTODY_VERIFIED"
                    )
                ),
                "phase": (
                    "import"
                    if payload[0]
                    else "certificate_match" if payload.endswith(b"wrong") else "verify"
                ),
                "error_class": "OS_AUTH_FAILED" if payload[0] else "OS_SUCCESS",
                "cleanup": "VERIFIED",
                "cleanup_error_class": "OS_SUCCESS",
                "cleanup_phase": "completed",
            }
            if self.failure == "native_cleanup":
                detail.update(
                    reason="CLEANUP_UNRESOLVED",
                    cleanup="DELETE_REJECTED",
                    cleanup_error_class="OS_OTHER",
                    cleanup_phase="delete",
                )
            elif self.failure == "import_cleaned":
                detail.update(
                    reason="CUSTODY_REJECTED", phase="import", error_class="OS_OTHER"
                )
            elif self.failure == "residual":
                (Path(cwd) / "fictional-residual").write_text("fictional")
            return 0, json.dumps(detail).encode()
        if "-exportArchive" in args:
            options = plistlib.loads(Path(args[-1]).read_bytes())
            if (
                options["signingStyle"] != "manual"
                or options["destination"] != "export"
            ):
                raise AssertionError
            return 70, (
                b"private-sentinel crash"
                if self.failure == "export"
                else b"error: No profiles for fictional were found"
            )
        return 0, b""


class FeasibilityTests(unittest.TestCase):
    def test_native_detail_strict_allowlist_and_no_disclosure(self):
        valid = {
            "reason": "CUSTODY_REJECTED",
            "phase": "import",
            "error_class": "OS_OTHER",
            "cleanup": "VERIFIED",
            "cleanup_error_class": "OS_SUCCESS",
            "cleanup_phase": "completed",
        }
        self.assertEqual(target.native_detail(json.dumps(valid).encode()), valid)
        for data in (
            b"private-sentinel",
            json.dumps({**valid, "phase": "private-sentinel"}).encode(),
            json.dumps({**valid, "extra": "private-sentinel"}).encode(),
            json.dumps({**valid, "cleanup_phase": "delete"}).encode(),
            json.dumps({**valid, "reason": "CLEANUP_UNRESOLVED"}).encode(),
            b'{"reason":"CUSTODY_REJECTED","reason":"CUSTODY_VERIFIED"}',
        ):
            with self.assertRaises(target.Rejected) as caught:
                target.native_detail(data)
            self.assertNotIn("private-sentinel", repr(caught.exception))

    def test_import_failure_preserves_confirmed_cleanup_and_case(self):
        result, runner = self.exercise("import_cleaned")
        self.assertEqual(result["classification"], "CUSTODY_REJECTED")
        self.assertTrue(result["cleanup_verified"])
        self.assertEqual(result["native_case"], 0)
        self.assertEqual(result["native_detail"]["phase"], "import")
        self.assertEqual(result["native_detail"]["error_class"], "OS_OTHER")
        self.assertEqual(result["native_detail"]["cleanup"], "VERIFIED")
        self.assertFalse(any("-exportArchive" in args for args in runner.calls))
        result, _ = self.exercise("residual")
        self.assertEqual(result["classification"], "CLEANUP_UNRESOLVED")
        self.assertFalse(result["cleanup_verified"])

    def exercise(self, failure=None):
        runner = FakeRunner(failure)
        with (
            patch.object(target.platform, "system", return_value="Darwin"),
            patch.object(target.platform, "machine", return_value="arm64"),
            patch.object(
                target.fixtures,
                "fictional_material",
                return_value=(b"fictional", b"certificate", b"wrong"),
            ),
        ):
            result = target.rehearse(_run=runner)
        self.assertFalse(runner.root.exists())
        self.assertNotIn("private-sentinel", repr(result))
        return result, runner

    def test_control_success_is_not_positive_export(self):
        result, runner = self.exercise()
        self.assertEqual(result["classification"], "CONTROL_VERIFIED_EXPORT_REJECTED")
        self.assertTrue(result["cleanup_verified"])
        self.assertFalse(result["positive_export_verified"])
        self.assertFalse(result["real_signing_authorized"])
        native = next(
            index
            for index, args in enumerate(runner.calls)
            if Path(args[0]).name == "native"
        )
        self.assertTrue(any(args[-1] == "archive" for args in runner.calls[:native]))
        self.assertFalse(
            any(
                args[-1] == "archive" or "swiftc" in args
                for args in runner.calls[native:]
            )
        )
        self.assertFalse(
            any(
                "-allowProvisioningUpdates" in args
                or "-allowProvisioningDeviceRegistration" in args
                for args in runner.calls
            )
        )

    def test_wrong_target_toolchain_and_unknown_export(self):
        for failure, expected in (
            ("toolchain", "TOOLCHAIN_UNSUPPORTED"),
            ("target", "ARCHIVE_REJECTED"),
            ("export", "EXPORT_INCONCLUSIVE"),
        ):
            result, runner = self.exercise(failure)
            self.assertEqual(result["classification"], expected)
            self.assertTrue(result["cleanup_verified"])
            if failure != "export":
                self.assertFalse(
                    any(Path(args[0]).name == "native" for args in runner.calls)
                )

    def test_cancel_and_native_uncertainty_never_claim_cleanup(self):
        result, _ = self.exercise("cancel_archive")
        self.assertEqual(result["classification"], "CANCELLED")
        self.assertTrue(result["cleanup_verified"])
        for failure in ("cancel_custody", "native_cleanup", "native_sentinel"):
            result, _ = self.exercise(failure)
            self.assertEqual(result["classification"], "CLEANUP_UNRESOLVED")
            self.assertFalse(result["cleanup_verified"])

    def test_paths_reject_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for path in (root / ".." / "outside", root.parent / "outside"):
                with self.assertRaises(target.Rejected):
                    target.safe_path(root, path)
            self.assertEqual(target.safe_path(root, root / "new"), root / "new")
            try:
                (root / "link").symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest(
                    "Symlink creation unavailable; native macOS path guard remains required"
                )
            with self.assertRaises(target.Rejected):
                target.safe_path(root, root / "link" / "new")

    def test_output_bound_timeout_and_environment(self):
        original = subprocess.Popen

        def launch(*args, **kwargs):
            # Windows Python needs its OS runtime path; production is macOS-only.
            if os.name == "nt":
                kwargs["env"] = {
                    **kwargs["env"],
                    "SystemRoot": os.environ["SystemRoot"],
                }
            return original(*args, **kwargs)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(target.subprocess, "Popen", side_effect=launch),
        ):
            for script, timeout in (
                ("print('x' * 300000)", 5),
                ("import time; time.sleep(30)", 0.05),
            ):
                with self.assertRaises(target.Rejected):
                    target.process(
                        [sys.executable, "-c", script], cwd=directory, timeout=timeout
                    )
            _, output = target.process(
                [
                    sys.executable,
                    "-c",
                    "import os; print('HOME' in os.environ or 'PRIVATE_SENTINEL' in os.environ)",
                ],
                cwd=directory,
            )
            self.assertEqual(output.strip(), b"False")

    @unittest.skipUnless(
        os.name == "posix", "POSIX process-group boundary requires hosted macOS/Linux"
    )
    def test_exited_leader_descendant_pipe_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            start = time.monotonic()
            with self.assertRaises(target.Rejected):
                target.process(
                    [
                        sys.executable,
                        "-c",
                        "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])",
                    ],
                    cwd=directory,
                    timeout=2,
                )
            self.assertLess(time.monotonic() - start, 10)

    def test_native_source_confines_import_and_cleanup(self):
        source = target.SOURCE.read_text()
        phases = set(
            re.findall(
                r'(?:predicate\(|status\(|phase\s*=|metadataPhase\s*=)\s*"([a-z_]+)"',
                source,
            )
        )
        self.assertLessEqual(phases, target.NATIVE_FIELDS["phase"])
        self.assertLessEqual(
            {
                "cwd_name",
                "root_name",
                "cwd_canonical",
                "temp_binding",
                "key_association",
                "key_target",
                "sign",
                "verify",
            },
            phases,
        )
        for required in (
            "kSecImportExportKeychain",
            "SecKeychainDelete(target)",
            "SecKeychainItemCopyKeychain",
            "SecKeyVerifySignature",
            "CERTIFICATE_MISMATCH",
            "CLEANUP_UNRESOLVED",
            "unchanged()",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "SecKeychainSetDefault(",
            "SecKeychainSetSearchList(",
            "SecKeychainLockAll(",
        ):
            self.assertNotIn(forbidden, source)

    def test_cleanup_failure_remains_unresolved(self):
        original = target.cleanup
        captured = []

        def failure(root, identity):
            captured.append((root, identity))
            raise OSError("private-sentinel")

        runner = FakeRunner()
        try:
            with (
                patch.object(target.platform, "system", return_value="Darwin"),
                patch.object(target.platform, "machine", return_value="arm64"),
                patch.object(
                    target.fixtures,
                    "fictional_material",
                    return_value=(b"fictional", b"certificate", b"wrong"),
                ),
                patch.object(target, "cleanup", side_effect=failure),
            ):
                result = target.rehearse(_run=runner)
            self.assertEqual(result["classification"], "CLEANUP_UNRESOLVED")
            self.assertFalse(result["cleanup_verified"])
            self.assertNotIn("private-sentinel", repr(result))
        finally:
            for root, identity in captured:
                original(root, identity)

    def test_cli_rejects_private_or_missing_arguments_without_work(self):
        for args in ([], ["private-sentinel"], ["--rehearsal", "private-sentinel"]):
            with (
                patch.object(target, "rehearse") as run,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(target.main(args), 1)
            run.assert_not_called()
            self.assertNotIn("private-sentinel", output.getvalue())

    def test_export_error_is_not_blanket_success(self):
        self.assertTrue(
            target.expected_export_rejection(
                70, b"error: No profiles for fictional were found"
            )
        )
        self.assertFalse(
            target.expected_export_rejection(70, b"private-sentinel crash")
        )
        self.assertFalse(
            target.expected_export_rejection(0, b"No profiles for fictional")
        )


if __name__ == "__main__":
    unittest.main()
