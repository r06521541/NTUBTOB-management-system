"""Windows custody tests only create disposable fictional files."""

import ctypes
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
        self.path = Path(temporary.name) / "fictional"
        self.path.mkdir()
        preparation.secure_acl(self.path, establish=True)
        for name in custody.INPUTS:
            (self.path / name).write_bytes(b"fictional-public-or-encrypted-fixture")

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
                with custody.Custody(Path(temporary)):
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
