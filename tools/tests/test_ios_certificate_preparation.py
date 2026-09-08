"""Offline tests use only fictional, ephemeral key material."""

import contextlib
import getpass
import io
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

from tools import ios_certificate_preparation as op

SHA = "a" * 40
PRIVATE = (
    "Fictional Test Owner",
    "fixture@example.invalid",
    b"fictional-test-passphrase",
)

ACL_STAGES = (
    "script_started",
    "utility_import_started",
    "security_import_started",
    "imports_ready",
    "identity_started",
    "security_object_started",
    "security_object_ready",
    "access_rule_started",
    "access_rule_ready",
    "set_acl_started",
    "set_acl_ready",
    "get_acl_started",
    "get_acl_ready",
    "verification_passed",
)


def diagnostic_acl_script():
    # Only this fictional test adds markers. The production script is unchanged.
    script = op.ACL_SCRIPT
    points = (
        ("$ErrorActionPreference", "script_started"),
        (
            "  Import-Module ($PSHOME + '\\Modules\\Microsoft.PowerShell.Utility",
            "utility_import_started",
        ),
        (
            "  Import-Module ($PSHOME + '\\Modules\\Microsoft.PowerShell.Security",
            "security_import_started",
        ),
        ("  $p =", "imports_ready"),
        ("  $sid =", "identity_started"),
        ("    $acl = New-Object", "security_object_started"),
        ("    $acl.SetOwner", "security_object_ready"),
        ("    $rule = New-Object", "access_rule_started"),
        ("    $acl.AddAccessRule", "access_rule_ready"),
        ("    Set-Acl", "set_acl_started"),
        ("  }\n  $acl = Get-Acl", "set_acl_ready"),
        ("  $acl = Get-Acl", "get_acl_started"),
        ("  $rules =", "get_acl_ready"),
        ("  exit 0", "verification_passed"),
    )
    for source, stage in points:
        if script.count(source) != 1:
            raise AssertionError("ACL_DIAGNOSTIC instrumentation_mismatch")
        marker = "[Console]::WriteLine('ACL_STAGE " + stage + "');\n"
        script = script.replace(source, marker + source, 1)
    return script


def diagnostic_acl_run(run, *args, **kwargs):
    started = time.monotonic()
    output = b""
    status = "failed"
    failure = False
    try:
        # stderr remains DEVNULL. Never render commands, paths or exceptions.
        result = run(*args, **dict(kwargs, stdout=subprocess.PIPE))
        output = result.stdout or b""
        status = "success" if result.returncode == 0 else "rejected"
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        status = "timeout"
        failure = True
    except (Exception, KeyboardInterrupt):
        failure = True
    allowed = {("ACL_STAGE " + stage).encode("ascii") for stage in ACL_STAGES}
    if isinstance(output, bytes):
        for line in output.splitlines():
            if line in allowed:
                print(line.decode("ascii"), flush=True)
    elapsed = max(0, int((time.monotonic() - started) * 1000))
    print("ACL_DIAGNOSTIC status=" + status + " elapsed_ms=" + str(elapsed), flush=True)
    if failure:
        raise AssertionError("ACL_DIAGNOSTIC process_failed") from None
    return result


def diagnostic_secure_acl(path, *, establish):
    run = op.subprocess.run
    with (
        patch.object(op, "ACL_SCRIPT", diagnostic_acl_script()),
        patch.object(
            op.subprocess,
            "run",
            side_effect=lambda *args, **kwargs: diagnostic_acl_run(
                run, *args, **kwargs
            ),
        ),
    ):
        op.secure_acl(path, establish=establish)


class DiagnosticTests(unittest.TestCase):
    def test_native_imports_disable_discovery_before_cmdlets(self):
        script = op.ACL_SCRIPT
        disable = script.index("$PSModuleAutoLoadingPreference = 'None'")
        imports = [
            line.strip() for line in script.splitlines() if "Import-Module" in line
        ]
        self.assertEqual(
            imports,
            [
                "Import-Module ($PSHOME + '\\Modules\\Microsoft.PowerShell.Utility\\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop",
                "Import-Module ($PSHOME + '\\Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop",
            ],
        )
        self.assertLess(disable, script.index(imports[0]))
        self.assertLess(script.index(imports[1]), script.index("New-Object"))
        self.assertLess(script.index(imports[1]), script.index("Get-Acl"))
        self.assertNotIn("Join-Path", script)
        self.assertNotIn("Get-Command", script)

    def test_diagnostic_script_has_only_fixed_stages(self):
        script = diagnostic_acl_script()
        for stage in ACL_STAGES:
            self.assertEqual(script.count("ACL_STAGE " + stage + "'"), 1)
        for line in op.ACL_SCRIPT.splitlines():
            self.assertIn(line, script)

    def test_output_allowlist_and_timeout_no_retry(self):
        private = b"fictional-private-command-path-env"
        payload = (
            b"ACL_STAGE script_started\n"
            + private
            + b"\nACL_STAGE set_acl_started injected\n"
        )
        runner = Mock(
            side_effect=subprocess.TimeoutExpired(
                private, 30, output=payload, stderr=private
            )
        )
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            self.assertRaises(AssertionError) as error,
        ):
            diagnostic_acl_run(runner, [private], timeout=30, stderr=subprocess.DEVNULL)
        runner.assert_called_once()
        self.assertIn("ACL_STAGE script_started\n", output.getvalue())
        self.assertIn("ACL_DIAGNOSTIC status=timeout elapsed_ms=", output.getvalue())
        self.assertNotIn(private.decode(), output.getvalue() + str(error.exception))
        self.assertNotIn("injected", output.getvalue())
        self.assertTrue(error.exception.__suppress_context__)

    def test_success_and_unexpected_failure_sanitized(self):
        for result in (
            Mock(returncode=0, stdout=b"private-untrusted"),
            OSError("private-untrusted"),
        ):
            runner = (
                Mock(side_effect=result)
                if isinstance(result, Exception)
                else Mock(return_value=result)
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                try:
                    diagnostic_acl_run(runner)
                except AssertionError as error:
                    self.assertNotIn("private-untrusted", str(error))
            self.assertNotIn("private-untrusted", output.getvalue())
            runner.assert_called_once()


class CryptoTests(unittest.TestCase):
    def test_encrypted_key_and_valid_csr_match(self):
        x509, hashes, serialization, _ = op.dependencies()
        key_pem, csr_pem = op.material(*PRIVATE)
        self.assertTrue(key_pem.startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----"))
        key = serialization.load_pem_private_key(key_pem, PRIVATE[2])
        csr = x509.load_pem_x509_csr(csr_pem)
        self.assertTrue(csr.is_signature_valid)
        self.assertIsInstance(csr.signature_hash_algorithm, hashes.SHA256)
        self.assertEqual(key.key_size, 2048)
        self.assertEqual(
            key.public_key().public_numbers(), csr.public_key().public_numbers()
        )
        self.assertEqual(
            csr.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value,
            PRIVATE[0],
        )
        self.assertEqual(
            csr.subject.get_attributes_for_oid(x509.NameOID.EMAIL_ADDRESS)[0].value,
            PRIVATE[1],
        )
        for password in (None, b"wrong-fictional-passphrase"):
            with self.assertRaises((ValueError, TypeError)):
                serialization.load_pem_private_key(key_pem, password)


class InputTests(unittest.TestCase):
    def test_hidden_feedback_is_length_only(self):
        output = io.StringIO()
        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch.object(sys.stderr, "isatty", return_value=True),
            patch.object(op.getpass, "getpass", return_value="fictional-private"),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(op.hidden("Fixed prompt: "), "fictional-private")
        self.assertEqual(output.getvalue(), "input_accepted length=17\n")

    def test_non_tty_never_reads(self):
        with (
            patch.object(sys.stdin, "isatty", return_value=False),
            patch.object(op.getpass, "getpass") as reader,
        ):
            with self.assertRaises(op.Rejected):
                op.hidden("Fixed prompt: ")
            reader.assert_not_called()

    def test_no_warning_fallback(self):
        def fallback(prompt):
            warnings.warn("fixture", getpass.GetPassWarning)
            self.fail("visible fallback reached")

        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch.object(sys.stderr, "isatty", return_value=True),
            patch.object(op.getpass, "getpass", side_effect=fallback),
        ):
            with self.assertRaises(getpass.GetPassWarning):
                op.hidden("Fixed prompt: ")

    def test_private_validation(self):
        values = [PRIVATE[0], PRIVATE[1], PRIVATE[2].decode(), PRIVATE[2].decode()]
        with patch.object(op, "hidden", side_effect=values):
            self.assertEqual(op.private_input(), PRIVATE)
        for index, invalid in (
            (0, "x" * 65),
            (1, "not email"),
            (2, "short"),
            (3, "wrong confirmation"),
        ):
            invalid_values = values.copy()
            invalid_values[index] = invalid
            with (
                patch.object(op, "hidden", side_effect=invalid_values),
                self.assertRaises(op.Rejected),
            ):
                op.private_input()

    def test_parser_never_echoes_invalid_argument(self):
        for argv in ([], ["--unknown-private-value"], ["--expected-commit"]):
            output, error = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                self.assertEqual(op.main(argv), 1)
            self.assertEqual(error.getvalue(), "")
            self.assertEqual(
                output.getvalue(),
                "IOS_CSR_RESULT target=local_apple_distribution classification=pre_execution_rejected\n",
            )


class PreflightTests(unittest.TestCase):
    def test_missing_native_temp_fails_before_spawn(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(op, "local_app_data", return_value=Path(temporary)),
            patch.object(op, "fixed_drive", return_value=True),
            patch.object(op.subprocess, "run") as run,
            self.assertRaises(op.Rejected),
        ):
            op.acl_environment(
                Path("/fictional/Windows/System32/WindowsPowerShell/v1.0")
            )
        run.assert_not_called()

    def test_acl_child_receives_only_bounded_environment(self):
        with (
            patch.dict(
                os.environ,
                {
                    "FICTIONAL_PRIVATE_ENV": "never-forward",
                    "LOCALAPPDATA": "never-forward",
                    "TMP": "never-forward",
                    "TEMP": "never-forward",
                },
            ),
            patch.object(
                op,
                "powershell_home",
                return_value=Path("/fictional/Windows/System32/WindowsPowerShell/v1.0"),
            ),
            patch.object(op.subprocess, "CREATE_NO_WINDOW", 0, create=True),
            patch.object(op, "local_app_data", return_value=Path("/fictional/Local")),
            patch.object(op, "safe_directory") as safe,
            patch.object(op.subprocess, "run", return_value=Mock(returncode=0)) as run,
        ):
            op.secure_acl(Path("/fictional-target"), establish=True)
        self.assertEqual(
            set(run.call_args.kwargs["env"]),
            {
                "SYSTEMROOT",
                "WINDIR",
                "PSMODULEPATH",
                "LOCALAPPDATA",
                "TMP",
                "TEMP",
                "NTUBTOB_CSR_ACL_TARGET",
                "NTUBTOB_CSR_ACL_SET",
            },
        )
        self.assertNotIn("never-forward", str(run.call_args))
        self.assertEqual(
            run.call_args.kwargs["env"]["TEMP"], str(Path("/fictional/Local/Temp"))
        )
        self.assertEqual(
            run.call_args.kwargs["env"]["TMP"], run.call_args.kwargs["env"]["TEMP"]
        )
        safe.assert_called_once_with(Path("/fictional/Local/Temp"), fresh=False)

    def test_failures_precede_input_and_keygen(self):
        cases = [
            {"platform": "linux"},
            {"commit": "bad"},
            {"dependency": RuntimeError("private fixture error")},
            {"powershell": op.Rejected()},
            {"git": ["b" * 40]},
            {"git": [SHA, "dirty"]},
            {"path": op.Rejected()},
        ]
        for case in cases:
            with (
                self.subTest(case=case),
                patch.object(sys, "platform", case.get("platform", "win32")),
                patch.object(op, "dependencies", side_effect=case.get("dependency")),
                patch.object(op, "powershell_home", side_effect=case.get("powershell")),
                patch.object(op, "git", side_effect=case.get("git", [SHA, ""])),
                patch.object(
                    op, "local_app_data", return_value=Path(tempfile.gettempdir())
                ),
                patch.object(op, "safe_directory", side_effect=case.get("path")),
                patch.object(op, "private_input") as reader,
                patch.object(op, "material") as keygen,
            ):
                self.assertEqual(
                    op.execute(case.get("commit", SHA)), "pre_execution_rejected"
                )
                reader.assert_not_called()
                keygen.assert_not_called()

    def test_read_only_default(self):
        with (
            patch.object(op, "preflight") as preflight,
            patch.object(op, "execute") as execute,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(op.main(["--expected-commit", SHA]), 0)
            preflight.assert_called_once_with(SHA)
            execute.assert_not_called()

    def test_path_rejections(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(op, "fixed_drive", return_value=True),
        ):
            parent = Path(temporary)
            op.safe_directory(parent / "new", fresh=True)
            for target in (
                parent,
                Path("relative"),
                op.ROOT / "new",
                parent / "missing" / "new",
            ):
                with self.subTest(target=target), self.assertRaises(op.Rejected):
                    op.safe_directory(target, fresh=True)
            sync = parent / "OneDrive"
            sync.mkdir()
            with self.assertRaises(op.Rejected):
                op.safe_directory(sync / "new", fresh=True)
            with (
                patch.object(op, "fixed_drive", return_value=False),
                self.assertRaises(op.Rejected),
            ):
                op.safe_directory(parent / "new", fresh=True)
            fake_stat = Mock(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            with (
                patch.object(Path, "lstat", return_value=fake_stat),
                self.assertRaises(op.Rejected),
            ):
                op.safe_directory(parent / "new", fresh=False)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name) / "new"
        for name, kwargs in (
            ("preflight", {"return_value": self.target}),
            ("private_input", {"return_value": PRIVATE}),
            ("hidden", {"return_value": "CREATE CSR " + SHA}),
            ("secure_acl", {}),
            ("safe_directory", {}),
            ("material", {"return_value": (b"fictional-key", b"fictional-csr")}),
        ):
            patcher = patch.object(op, name, **kwargs)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.capture = contextlib.redirect_stdout(io.StringIO())
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def test_success_once_and_no_overwrite(self):
        self.assertEqual(op.execute(SHA), "confirmed_success")
        self.material.assert_called_once_with(*PRIVATE)
        self.assertEqual((self.target / op.CSR_FILE).read_bytes(), b"fictional-csr")
        self.assertEqual(op.execute(SHA), "uncertain")
        self.material.assert_called_once()

    def test_cancel_mismatch_and_recheck_generate_nothing(self):
        for failure in (op.Rejected(), KeyboardInterrupt(), EOFError()):
            self.private_input.side_effect = failure
            self.assertEqual(op.execute(SHA), "pre_execution_rejected")
            self.material.assert_not_called()
            self.assertFalse(self.target.exists())
        self.private_input.side_effect = None
        self.hidden.return_value = "CREATE CSR wrong-sha"
        self.assertEqual(op.execute(SHA), "pre_execution_rejected")
        self.material.assert_not_called()
        self.hidden.return_value = "CREATE CSR " + SHA
        self.preflight.side_effect = [self.target, op.Rejected()]
        self.assertEqual(op.execute(SHA), "pre_execution_rejected")
        self.material.assert_not_called()

    def test_acl_failure_never_generates(self):
        self.secure_acl.side_effect = op.Rejected()
        self.assertEqual(op.execute(SHA), "uncertain")
        self.material.assert_not_called()
        self.assertTrue(self.target.is_dir())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_acl_verification_failure_never_generates(self):
        self.secure_acl.side_effect = [None, op.Rejected()]
        self.assertEqual(op.execute(SHA), "uncertain")
        self.material.assert_not_called()

    def test_partial_write_failure_preserves_protected_directory(self):
        with patch.object(
            Path, "open", side_effect=OSError("fictional private detail")
        ):
            self.assertEqual(op.execute(SHA), "uncertain")
        self.assertTrue(self.target.is_dir())
        self.material.assert_called_once()

    def test_partial_failure_preserves_key_no_retry(self):
        self.secure_acl.side_effect = [None, None, None, KeyboardInterrupt()]
        self.assertEqual(op.execute(SHA), "uncertain")
        self.assertEqual((self.target / op.KEY_FILE).read_bytes(), b"fictional-key")
        self.assertFalse((self.target / op.CSR_FILE).exists())
        self.material.assert_called_once()


@unittest.skipUnless(sys.platform == "win32", "requires real Windows ACL APIs")
class WindowsTests(unittest.TestCase):
    def test_missing_native_manifest_rejected(self):
        is_file = Path.is_file
        for module in ("Microsoft.PowerShell.Utility", "Microsoft.PowerShell.Security"):
            with (
                self.subTest(module=module),
                patch.object(
                    Path,
                    "is_file",
                    lambda path: (
                        False if path.name == module + ".psd1" else is_file(path)
                    ),
                ),
                self.assertRaises(op.Rejected),
            ):
                op.powershell_home()

    def test_unc_and_unprotected_directory_rejected(self):
        with self.assertRaises(op.Rejected):
            op.safe_directory(Path(r"\\fictional-server\share\folder"), fresh=True)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(op.Rejected):
                diagnostic_secure_acl(Path(temporary), establish=False)

    def test_known_folder_ignores_environment(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "Z:\\fictional-network"}):
            result = op.local_app_data()
        self.assertTrue(result.is_absolute())
        self.assertNotEqual(str(result), "Z:\\fictional-network")

    def test_real_restrictive_acl_and_fictional_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "fictional-csr"
            target.mkdir()
            diagnostic_secure_acl(target, establish=True)
            diagnostic_secure_acl(target, establish=False)
            op.safe_directory(target, fresh=False)
            key, csr = op.material(*PRIVATE)
            (target / op.KEY_FILE).write_bytes(key)
            (target / op.CSR_FILE).write_bytes(csr)
            self.assertEqual(len(list(target.iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
