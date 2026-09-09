"""Windows custody tests only create disposable fictional files."""

import ctypes
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import ios_certificate_custody as custody
from tools import ios_certificate_preparation as preparation


@unittest.skipUnless(sys.platform == "win32", "native Windows handles required")
class CustodyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Hosted Windows TEMP may use an 8.3 user-profile alias. Production
        # custody deliberately requires the canonical handle path spelling.
        self.path = Path(temporary.name).resolve(strict=True) / "fictional"
        self.path.mkdir()
        preparation.secure_acl(self.path, establish=True)
        for name in custody.INPUTS:
            native = custody.Native()
            handle = native.open_handle(self.path / name, create=True)
            try:
                native.acl(handle)
                data = b"fictional-public-or-encrypted-fixture"
                count = custody.w.DWORD()
                self.assertTrue(
                    native.write(
                        handle,
                        ctypes.create_string_buffer(data),
                        len(data),
                        ctypes.byref(count),
                        None,
                    )
                )
                self.assertEqual(count.value, len(data))
                self.assertTrue(native.flush(handle))
            finally:
                native.close(handle)

    def security_facts(self, native, handle):
        owner, dacl, descriptor = [ctypes.c_void_p() for _ in range(3)]
        self.assertEqual(
            native.get_security(
                handle,
                1,
                5,
                ctypes.byref(owner),
                None,
                ctypes.byref(dacl),
                None,
                ctypes.byref(descriptor),
            ),
            0,
        )
        try:
            control, revision = custody.w.WORD(), custody.w.DWORD()
            self.assertTrue(
                native.get_control(
                    descriptor, ctypes.byref(control), ctypes.byref(revision)
                )
            )
            one_user = False
            if (
                dacl
                and ctypes.cast(dacl, ctypes.POINTER(custody.ACLHeader)).contents.count
                == 1
            ):
                ace = ctypes.c_void_p()
                self.assertTrue(native.get_ace(dacl, 0, ctypes.byref(ace)))
                data = ctypes.string_at(ace, 8)
                one_user = (
                    data[0] == 0
                    and not data[1] & 8
                    and int.from_bytes(data[4:8], "little") == 0x1F01FF
                    and bool(native.equal_sid(ace.value + 8, native.sid))
                )
            return dict(
                owner_present=bool(owner),
                dacl_present=bool(dacl),
                owner_matches_token_user=bool(
                    owner and native.equal_sid(owner, native.sid)
                ),
                protected_dacl=bool(control.value & 0x1000),
                single_user_full_control=one_user,
            )
        finally:
            native.free(descriptor)

    def test_explicit_creation_security_and_noninheritable_handle(self):
        native = custody.Native()
        handle = native.open_handle(self.path / "explicit-fictional-file", create=True)
        try:
            self.assertTrue(all(self.security_facts(native, handle).values()))
            get_flags = native.bind(
                native.kernel,
                "GetHandleInformation",
                custody.w.BOOL,
                [custody.w.HANDLE, ctypes.POINTER(custody.w.DWORD)],
            )
            flags = custody.w.DWORD()
            self.assertTrue(get_flags(handle, ctypes.byref(flags)))
            self.assertEqual(flags.value & 1, 0)
        finally:
            native.close(handle)

    def test_default_created_file_owner_diagnostic(self):
        native = custody.Native()
        path = self.path / "default-fictional-file"
        path.write_bytes(b"fictional-default-owner-probe")
        handle = native.open_handle(path)
        try:
            facts = self.security_facts(native, handle)
            if not facts["owner_matches_token_user"]:
                with self.assertRaises(custody.CustodyError):
                    native.acl(handle)
        finally:
            native.close(handle)
        open_token = native.bind(
            native.security,
            "OpenProcessToken",
            custody.w.BOOL,
            [custody.w.HANDLE, custody.w.DWORD, ctypes.POINTER(custody.w.HANDLE)],
        )
        token_info = native.bind(
            native.security,
            "GetTokenInformation",
            custody.w.BOOL,
            [
                custody.w.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                custody.w.DWORD,
                ctypes.POINTER(custody.w.DWORD),
            ],
        )
        process = native.bind(native.kernel, "GetCurrentProcess", custody.w.HANDLE, [])
        token = custody.w.HANDLE()
        self.assertTrue(open_token(process(), 8, ctypes.byref(token)))
        try:
            size = custody.w.DWORD()
            token_info(token, 4, None, 0, ctypes.byref(size))
            self.assertTrue(0 < size.value <= 65536)
            buffer = ctypes.create_string_buffer(size.value)
            self.assertTrue(token_info(token, 4, buffer, size, ctypes.byref(size)))
            owner = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
            default_matches = bool(native.equal_sid(owner, native.sid))
        finally:
            native.close(token)
        diagnostic = {
            key: facts[key]
            for key in ("owner_present", "dacl_present", "owner_matches_token_user")
        }
        diagnostic["token_default_owner_matches_user"] = default_matches
        self.assertTrue(all(type(value) is bool for value in diagnostic.values()))
        print("DEFAULT_OWNER_DIAGNOSTIC " + json.dumps(diagnostic, sort_keys=True))

    def test_wrong_owner_comparison_rejected(self):
        native = custody.Native()
        handle = native.open_handle(self.path / custody.INPUTS[0])
        try:
            # Compare the actual descriptor against a known different SID;
            # no process token or existing file owner is changed.
            world_sid = ctypes.create_string_buffer(68)
            size = custody.w.DWORD(len(world_sid))
            create_sid = native.bind(
                native.security,
                "CreateWellKnownSid",
                custody.w.BOOL,
                [
                    ctypes.c_int,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.POINTER(custody.w.DWORD),
                ],
            )
            self.assertTrue(create_sid(1, None, world_sid, ctypes.byref(size)))
            with (
                patch.object(native, "sid", world_sid),
                self.assertRaises(custody.CustodyError),
            ):
                native.acl(handle)
        finally:
            native.close(handle)

    def test_descriptor_failure_never_calls_createfile(self):
        with custody.Custody(self.path) as session:
            with (
                patch.object(
                    session.native,
                    "creation_security",
                    side_effect=custody.CustodyError("ACL_REJECTED"),
                ),
                patch.object(session.native, "open") as createfile,
            ):
                with self.assertRaises(custody.CustodyError):
                    session.write_output(b"fictional-encrypted-output")
                createfile.assert_not_called()
                self.assertTrue(session.output_attempted)
        self.assertFalse((self.path / custody.OUTPUT).exists())

    def test_handle_read_write_locks_and_no_overwrite(self):
        with custody.Custody(self.path) as session:
            self.assertEqual(
                session.read_input(custody.INPUTS[0]),
                b"fictional-public-or-encrypted-fixture",
            )
            with self.assertRaises(OSError):
                (self.path / custody.INPUTS[0]).write_bytes(b"replacement")
            with self.assertRaises(OSError):
                (self.path / custody.INPUTS[0]).unlink()
            with self.assertRaises(OSError):
                (self.path / custody.INPUTS[0]).rename(self.path / "renamed-input")
            with self.assertRaises(OSError):
                self.path.rename(self.path.with_name("renamed"))
            session.write_output(b"fictional-encrypted-p12")
            with self.assertRaises(custody.CustodyError):
                session.write_output(b"second-output")
        self.assertEqual(
            (self.path / custody.OUTPUT).read_bytes(), b"fictional-encrypted-p12"
        )
        with self.assertRaises(custody.CustodyError):
            with custody.Custody(self.path):
                self.fail("existing output accepted")

    def test_short_alias_rejected_canonical_handle_path_accepted(self):
        directory = self.path / "fictional-long-directory"
        directory.mkdir()
        canonical = directory.resolve(strict=True)
        native = custody.Native()
        short_path = native.bind(
            native.kernel,
            "GetShortPathNameW",
            custody.w.DWORD,
            [custody.w.LPCWSTR, custody.w.LPWSTR, custody.w.DWORD],
        )
        buffer = ctypes.create_unicode_buffer(32768)
        length = short_path(str(canonical), buffer, len(buffer))
        self.assertGreater(length, 0)
        self.assertLess(length, len(buffer))
        alias = Path(buffer.value)
        if os.path.normcase(str(alias)) == os.path.normcase(str(canonical)):
            self.skipTest("8.3 aliases unavailable on the fixture volume")
        handle = native.open_handle(alias, directory=True)
        try:
            with self.assertRaises(custody.CustodyError) as error:
                native.metadata(handle, alias, directory=True)
            self.assertEqual(str(error.exception), "METADATA_REJECTED")
            native.metadata(handle, canonical, directory=True)
        finally:
            native.close(handle)

    def test_multiple_links_and_size_rejected(self):
        os.link(self.path / custody.INPUTS[0], self.path / "fictional-link")
        with self.assertRaises(custody.CustodyError):
            with custody.Custody(self.path):
                self.fail("hardlink accepted")
        (self.path / "fictional-link").unlink()
        (self.path / custody.INPUTS[0]).write_bytes(b"x" * (custody.LIMIT + 1))
        with self.assertRaises(custody.CustodyError):
            with custody.Custody(self.path):
                self.fail("oversized input accepted")

    def test_unprotected_directory_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(custody.CustodyError):
                with custody.Custody(Path(temporary).resolve(strict=True)):
                    self.fail("unprotected directory accepted")

    def test_output_acl_failure_preserves_empty_file_without_write(self):
        with custody.Custody(self.path) as session:
            original_acl = session.native.acl

            def reject_file(handle, *, directory=False):
                if not directory:
                    raise custody.CustodyError("ACL_REJECTED")
                return original_acl(handle, directory=directory)

            with (
                patch.object(session.native, "acl", side_effect=reject_file),
                patch.object(session.native, "write") as write,
            ):
                with self.assertRaises(custody.CustodyError):
                    session.write_output(b"fictional-encrypted-p12")
                self.assertTrue(session.output_attempted)
                write.assert_not_called()
        self.assertEqual((self.path / custody.OUTPUT).stat().st_size, 0)

    def test_reparse_input_rejected(self):
        source = self.path / custody.INPUTS[0]
        source.unlink()
        try:
            source.symlink_to(self.path / custody.INPUTS[1])
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        with self.assertRaises((custody.CustodyError, preparation.Rejected)):
            with custody.Custody(self.path):
                self.fail("reparse input accepted")

    def test_native_junction_ancestor_rejected(self):
        link = self.path.parent / "fictional-junction"
        link.mkdir()
        self.addCleanup(link.rmdir)
        native = custody.Native()
        handle = native.open(str(link), 0x40000000, 0, None, 3, 0x02200000, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            substitute = ("\\??\\" + str(self.path)).encode("utf-16-le")
            display = str(self.path).encode("utf-16-le")
            payload = substitute + b"\x00\x00" + display + b"\x00\x00"
            record = (
                struct.pack(
                    "<IHHHHHH",
                    0xA0000003,
                    len(payload) + 8,
                    0,
                    0,
                    len(substitute),
                    len(substitute) + 2,
                    len(display),
                )
                + payload
            )
            ioctl = native.bind(
                native.kernel,
                "DeviceIoControl",
                custody.w.BOOL,
                [
                    custody.w.HANDLE,
                    custody.w.DWORD,
                    ctypes.c_void_p,
                    custody.w.DWORD,
                    ctypes.c_void_p,
                    custody.w.DWORD,
                    ctypes.POINTER(custody.w.DWORD),
                    ctypes.c_void_p,
                ],
            )
            size = custody.w.DWORD()
            self.assertTrue(
                ioctl(
                    handle,
                    0x900A4,
                    ctypes.create_string_buffer(record),
                    len(record),
                    None,
                    0,
                    ctypes.byref(size),
                    None,
                )
            )
        finally:
            native.close(handle)
        with self.assertRaises(custody.CustodyError):
            with custody.Custody(link):
                self.fail("junction accepted")

    def test_null_file_dacl_rejected_under_protected_parent(self):
        native = custody.Native()
        handle = native.open(
            str(self.path / custody.INPUTS[0]), 0x10000000, 0, None, 3, 0x80, None
        )
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            setter = native.bind(
                native.security,
                "SetSecurityInfo",
                custody.w.DWORD,
                [
                    custody.w.HANDLE,
                    ctypes.c_int,
                    custody.w.DWORD,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
            )
            self.assertEqual(setter(handle, 1, 0x80000004, None, None, None, None), 0)
        finally:
            native.close(handle)
        with self.assertRaises(custody.CustodyError):
            with custody.Custody(self.path):
                self.fail("broad input ACL accepted")

    def test_partial_write_preserved_without_retry(self):
        with custody.Custody(self.path) as session:
            original = session.native.write

            def partial(handle, buffer, size, count, overlapped):
                original(handle, buffer, 2, count, overlapped)
                return False

            with patch.object(session.native, "write", side_effect=partial) as writer:
                with self.assertRaises(custody.CustodyError):
                    session.write_output(b"fictional-encrypted-p12")
                writer.assert_called_once()
                self.assertTrue(session.output_attempted)
        self.assertEqual((self.path / custody.OUTPUT).read_bytes(), b"fi")

    def test_flush_failure_preserved_without_retry(self):
        with custody.Custody(self.path) as session:
            with patch.object(session.native, "flush", return_value=False) as flush:
                with self.assertRaises(custody.CustodyError):
                    session.write_output(b"fictional-encrypted-p12")
                flush.assert_called_once()
                self.assertTrue(session.output_attempted)
        self.assertEqual(
            (self.path / custody.OUTPUT).read_bytes(), b"fictional-encrypted-p12"
        )


if __name__ == "__main__":
    unittest.main()
