"""Only fictional memory/native temporary fixtures, never Owner assets."""

import ctypes as c
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from asn1crypto import keys
from asn1crypto import pem as asn1_pem
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tools import ios_testflight_key_custody as key

WEB = "123-fictionalweb.apps.googleusercontent.com"


def values(path):
    return dict(
        apple_team_id="FICTTEAM01",
        asc_key_id="FICTKEY001",
        asc_issuer_id="11111111-1111-4111-8111-111111111111",
        google_ios_client_id="123-fictionalios.apps.googleusercontent.com",
        owner_email="fictional@example.invalid",
        asc_p8_path=str(path),
    )


def pem():
    return ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


class FakeNative:
    def __init__(self):
        self.files, self.handles = {}, {}
        self.next_handle = 1
        self.reads, self.writes = [], []
        self.fail_write = None
        self.fail_acl = self.fail_close = False
        self.mutate = lambda path: None

    def open_handle(self, path, *, directory=False, ancestor=False, create=False):
        if create:
            if path in self.files:
                raise key.Rejected("OUTPUT_EXISTS")
            self.files[path] = b""
        elif not directory and path not in self.files:
            raise key.Rejected("HANDLE_REJECTED")
        handle = self.next_handle
        self.next_handle += 1
        self.handles[handle] = (path, directory)
        return handle

    def settings_handle(self, path):
        return self.open_handle(path)

    def metadata(self, handle, path, *, directory=False, allow_empty=False):
        if self.handles[handle] != (path, directory):
            raise key.Rejected("METADATA_REJECTED")
        raw = b"" if directory else self.files[path]
        if not directory and not (0 if allow_empty else 1) <= len(raw) <= 65536:
            raise key.Rejected("METADATA_REJECTED")
        return (1, 0, hash(path), len(raw), 0, hash(raw))

    def acl(self, handle, *, directory=False):
        if self.fail_acl:
            raise key.Rejected("ACL_REJECTED")

    source_acl = acl

    def read_bytes(self, handle, size):
        path = self.handles[handle][0]
        self.reads.append(path)
        raw = self.files[path]
        self.mutate(path)
        return raw

    def write_checked(self, handle, path, raw, *, truncate=False):
        self.writes.append(path)
        if path.name == self.fail_write:
            self.files[path] = b"partial"
            raise key.Rejected("WRITE_REJECTED")
        self.files[path] = raw

    def close(self, handle):
        del self.handles[handle]
        return not self.fail_close


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.root = (
            Path("C:/fictional") if sys.platform == "win32" else Path("/fictional")
        )
        self.source = self.root / "download" / "AuthKey_FICTKEY001.p8"
        self.private = self.root / key.preparation.DIRECTORY
        self.native = FakeNative()
        self.original = json.dumps(values(self.source)).encode()
        self.native.files[self.private / key.settings.FILENAME] = self.original
        self.native.files[self.source] = pem()
        self.addCleanup(patch.stopall)
        patch.object(key, "Native", return_value=self.native).start()
        patch.object(key.preparation, "local_app_data", return_value=self.root).start()
        patch.object(key.preparation, "safe_directory").start()
        patch.object(
            key, "_exists", side_effect=lambda path: path in self.native.files
        ).start()

    def test_preview_does_not_read_key_or_write(self):
        self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_READY")
        self.assertNotIn(self.source, self.native.reads)
        self.assertEqual(self.native.writes, [])
        self.assertEqual(self.native.handles, {})

    def test_non_serializer_pkcs8_is_copied_byte_exact_without_rewriting(self):
        _, _, der = asn1_pem.unarmor(self.native.files[self.source])
        info = keys.PrivateKeyInfo.load(der)
        inner = info["private_key"].parsed
        inner["parameters"] = keys.ECDomainParameters(name="named", value="secp256r1")
        info["private_key"] = inner
        raw = asn1_pem.armor("PRIVATE KEY", info.dump())
        self.native.files[self.source] = raw
        self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_READY")
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        self.assertEqual(self.native.files[self.source], raw)
        self.assertEqual(self.native.files[self.private / key.DESTINATION], raw)
        writes = list(self.native.writes)
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        self.assertEqual(self.native.writes, writes)

    def test_success_preserves_source_backup_and_other_fields_no_repeat(self):
        original_source = self.native.files[self.source]
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        backup, destination = self.private / key.BACKUP, self.private / key.DESTINATION
        self.assertEqual(
            self.native.writes,
            [backup, destination, self.private / key.settings.FILENAME],
        )
        self.assertEqual(self.native.files[backup], self.original)
        self.assertEqual(self.native.files[self.source], original_source)
        current, old = json.loads(
            self.native.files[self.private / key.settings.FILENAME]
        ), json.loads(self.original)
        self.assertEqual(
            {k: v for k, v in current.items() if k != "asc_p8_path"},
            {k: v for k, v in old.items() if k != "asc_p8_path"},
        )
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        self.assertEqual(len(self.native.writes), 3)
        self.assertEqual(self.native.handles, {})
        self.native.reads.clear()
        self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_PRESENT")
        self.assertNotIn(self.source, self.native.reads)
        self.assertNotIn(destination, self.native.reads)

    def test_every_partial_write_preserved_and_not_retried(self):
        for name in (key.BACKUP, key.DESTINATION, key.settings.FILENAME):
            with self.subTest(name=name):
                self.setUp()
                self.native.fail_write = name
                original = self.native.files[self.source]
                self.assertEqual(
                    key.import_key(google_web=WEB), "ASC_IMPORT_UNRESOLVED"
                )
                before = len(self.native.writes)
                self.native.fail_write = None
                self.assertNotEqual(
                    key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE"
                )
                self.assertEqual(len(self.native.writes), before)
                self.assertEqual(self.native.files[self.source], original)

    def test_completed_import_revalidates_equal_keys_without_writes(self):
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        destination = self.private / key.DESTINATION
        original = self.native.files[self.source]
        wrong_curve = ec.generate_private_key(ec.SECP384R1())
        invalid_keys = (
            b"fictional-invalid-key",
            wrong_curve.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            wrong_curve.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )
        writes = list(self.native.writes)
        for raw in invalid_keys:
            self.native.files[self.source] = self.native.files[destination] = raw
            self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_UNRESOLVED")
            self.assertEqual(self.native.writes, writes)
        self.native.files[self.source] = self.native.files[destination] = original
        with patch.object(
            key.inputs, "load_asc_key", wraps=key.inputs.load_asc_key
        ) as parse:
            self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        parse.assert_called_once_with(
            original,
            key_id="FICTKEY001",
            issuer_id="11111111-1111-4111-8111-111111111111",
        )
        self.assertEqual(self.native.writes, writes)

    def test_existing_partial_copy_or_backup_never_overwritten(self):
        for name in (key.DESTINATION, key.BACKUP):
            self.native.files[self.private / name] = b"fictional-existing"
            self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_UNRESOLVED")
            self.assertEqual(self.native.writes, [])

    def test_filename_and_invalid_key_before_backup(self):
        self.native.files[self.source] = b"fictional-invalid-key"
        self.assertEqual(key.import_key(google_web=WEB), "KEY_REJECTED")
        self.assertEqual(self.native.writes, [])
        raw = values(self.source)
        raw["asc_key_id"] = "OTHERKEY01"
        self.native.files[self.private / key.settings.FILENAME] = json.dumps(
            raw
        ).encode()
        self.assertEqual(key.check_import(google_web=WEB), "ASC_FILENAME_REJECTED")

    def test_bounds_acl_and_close_fail_closed(self):
        self.native.files[self.source] = b"x" * 4097
        self.assertEqual(key.check_import(google_web=WEB), "METADATA_REJECTED")
        self.native.files[self.source] = pem()
        self.native.fail_acl = True
        self.assertEqual(key.check_import(google_web=WEB), "ACL_REJECTED")
        self.native.fail_acl = False
        self.native.fail_close = True
        self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_UNRESOLVED")

    def test_changed_selected_source_stops_before_backup(self):
        def mutate(path):
            if path == self.source:
                self.native.files[path] = b"changed-fictional"

        self.native.mutate = mutate
        self.assertEqual(key.import_key(google_web=WEB), "INPUT_CHANGED")
        self.assertEqual(self.native.writes, [])

    def test_second_key_never_opened_and_fixed_errors(self):
        other = self.source.parent / "AuthKey_OTHERKEY01.p8"
        self.native.files[other] = b"private-sentinel"
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        self.assertNotIn(other, self.native.reads)
        self.assertEqual(str(key.Rejected("private-sentinel")), "ASC_IMPORT_REJECTED")

    def test_unsafe_parent_duplicate_settings_and_completed_mismatch_stop(self):
        with patch.object(
            key.preparation, "safe_directory", side_effect=key.preparation.Rejected()
        ):
            self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_REJECTED")
        self.assertEqual(self.native.writes, [])
        path = self.private / key.settings.FILENAME
        self.native.files[path] = b'{"asc_p8_path":"a","asc_p8_path":"b"}'
        self.assertEqual(key.check_import(google_web=WEB), "SETTINGS_FIELDS_REJECTED")
        self.native.files[path] = self.original
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
        self.native.files[self.private / key.DESTINATION] = b"different-fictional"
        writes = len(self.native.writes)
        self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_UNRESOLVED")
        self.assertEqual(len(self.native.writes), writes)


@unittest.skipUnless(sys.platform == "win32", "Windows fictional native fixture")
class NativeTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            private, source = root / key.preparation.DIRECTORY, root / "source"
            private.mkdir()
            source.mkdir()
            key.preparation.secure_acl(private, establish=True)
            selected = source / "AuthKey_FICTKEY001.p8"
            selected.write_bytes(pem())
            (source / "AuthKey_OTHERKEY01.p8").write_bytes(
                b"fictional-other-never-opened"
            )
            raw = json.dumps(values(selected)).encode()
            native = key.Native()
            # New objects use the process token's default owner, which is not
            # necessarily its user SID on a hosted Windows runner. Establish
            # this fictional source fixture's required owner explicitly without
            # changing its inherited DACL or the production custody checks.
            set_owner = native.bind(
                native.security,
                "SetNamedSecurityInfoW",
                key.custody.w.DWORD,
                [key.custody.w.LPWSTR, key.custody.w.DWORD, key.custody.w.DWORD]
                + [c.c_void_p] * 4,
            )
            for fixture_path in (source, selected):
                self.assertEqual(
                    set_owner(str(fixture_path), 1, 1, native.sid, None, None, None),
                    0,
                )
            h = native.open_handle(private / key.settings.FILENAME, create=True)
            try:
                native.write_checked(h, private / key.settings.FILENAME, raw)
            finally:
                native.close(h)
            with patch.object(key.preparation, "local_app_data", return_value=root):
                yield private, source, selected, raw

    def test_complete_import_inherited_source_acl_and_source_preserved(self):
        with self.fixture() as (private, source, selected, raw):
            before = selected.read_bytes()
            self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_READY")
            self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")
            self.assertEqual((private / key.BACKUP).read_bytes(), raw)
            self.assertEqual((private / key.DESTINATION).read_bytes(), before)
            self.assertEqual(selected.read_bytes(), before)
            self.assertEqual(
                (source / "AuthKey_OTHERKEY01.p8").read_bytes(),
                b"fictional-other-never-opened",
            )
            self.assertEqual(key.check_import(google_web=WEB), "ASC_IMPORT_PRESENT")
            self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_COMPLETE")

    def test_native_hardlinked_source_rejected_and_owner_check(self):
        with self.fixture() as (private, source, selected, raw):
            os.link(selected, source / "fictional-alias.p8")
            self.assertEqual(key.check_import(google_web=WEB), "METADATA_REJECTED")
            self.assertFalse((private / key.BACKUP).exists())
            native = key.Native()
            handle = native.open_handle(selected)
            try:
                native.equal_sid = lambda *args: False
                with self.assertRaises(key.Rejected):
                    native.source_acl(handle)
            finally:
                native.close(handle)

    def test_native_partial_settings_preserves_backup_and_key_no_retry(self):
        with self.fixture() as (private, source, selected, raw):
            original = key.Native.write_checked

            def failure(native, handle, path, data, *, truncate=False):
                if truncate:
                    self.assertTrue(native.seek(handle, 0, None, 0))
                    end = native.bind(
                        native.kernel,
                        "SetEndOfFile",
                        key.custody.w.BOOL,
                        [key.custody.w.HANDLE],
                    )
                    self.assertTrue(end(handle))
                    self.assertTrue(native.flush(handle))
                    raise key.Rejected("WRITE_REJECTED")
                return original(native, handle, path, data)

            with patch.object(key.Native, "write_checked", failure):
                self.assertEqual(
                    key.import_key(google_web=WEB), "ASC_IMPORT_UNRESOLVED"
                )
            self.assertEqual((private / key.settings.FILENAME).read_bytes(), b"")
            self.assertEqual((private / key.BACKUP).read_bytes(), raw)
            self.assertEqual(
                (private / key.DESTINATION).read_bytes(), selected.read_bytes()
            )
            self.assertEqual(key.import_key(google_web=WEB), "ASC_IMPORT_UNRESOLVED")

    def test_exclusive_settings_backup_and_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            native = key.Native()
            path = root / "fictional-settings.json"
            h = native.open_handle(path, create=True)
            native.write_checked(h, path, b"original-six-values")
            native.close(h)
            h = native.settings_handle(path)
            try:
                with self.assertRaises(key.custody.CustodyError):
                    native.open_handle(path)
                backup = native.open_handle(root / "fictional-backup.json", create=True)
                try:
                    native.write_checked(
                        backup, root / "fictional-backup.json", native.read_bytes(h, 19)
                    )
                    native.write_checked(h, path, b"updated", truncate=True)
                    self.assertEqual(native.read_bytes(h, 7), b"updated")
                    self.assertEqual(
                        native.read_bytes(backup, 19), b"original-six-values"
                    )
                    native.acl(h)
                    native.acl(backup)
                finally:
                    native.close(backup)
            finally:
                native.close(h)


if __name__ == "__main__":
    unittest.main()
