"""Offline tests use only fictional, ephemeral key material."""

import contextlib
import getpass
import io
import os
import stat
import sys
import tempfile
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
    def test_unc_and_unprotected_directory_rejected(self):
        with self.assertRaises(op.Rejected):
            op.safe_directory(Path(r"\\fictional-server\share\folder"), fresh=True)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(op.Rejected):
                op.secure_acl(Path(temporary), establish=False)

    def test_known_folder_ignores_environment(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "Z:\\fictional-network"}):
            result = op.local_app_data()
        self.assertTrue(result.is_absolute())
        self.assertNotEqual(str(result), "Z:\\fictional-network")

    def test_real_restrictive_acl_and_fictional_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "fictional-csr"
            target.mkdir()
            op.secure_acl(target, establish=True)
            op.secure_acl(target, establish=False)
            op.safe_directory(target, fresh=False)
            key, csr = op.material(*PRIVATE)
            (target / op.KEY_FILE).write_bytes(key)
            (target / op.CSR_FILE).write_bytes(csr)
            self.assertEqual(len(list(target.iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
