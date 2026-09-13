import ctypes as c
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import ios_testflight_journal as journal


class JournalTests(unittest.TestCase):
    def start(self):
        return dict(
            sha="a" * 40,
            nonce="b" * 64,
            version="1.0.0",
            build=1,
            previous_build=0,
            issued=100,
            expires=7300,
        )

    def fake(self, raw=b""):
        native = mock.Mock()
        native.data = raw
        native.open_handle.return_value = 1
        native.journal_handle.return_value = 2
        native.metadata.side_effect = lambda handle, path, **kw: (
            1,
            0,
            handle,
            len(native.data) if handle == 2 else 0,
            0,
            0,
        )
        native.close.return_value = True
        native.seek.return_value = True
        native.flush.return_value = True

        def read(handle, buffer, size, count, _):
            buffer.raw = native.data[:size] or b"\0"
            c.cast(count, c.POINTER(journal.custody.w.DWORD)).contents.value = size
            return True

        def write(handle, buffer, size, count, _):
            native.data += c.string_at(buffer, size)
            c.cast(count, c.POINTER(journal.custody.w.DWORD)).contents.value = size
            return True

        native.read.side_effect = read
        native.write.side_effect = write
        return native

    def opening(self, native, create=True):
        with (
            mock.patch.object(
                journal.preparation, "local_app_data", return_value=Path("C:/fictional")
            ),
            mock.patch.object(journal.preparation, "safe_directory"),
            mock.patch.object(Path, "exists", return_value=True),
        ):
            return journal.Journal.open(create=create, nativefactory=lambda: native)

    def test_private_fields_rejected(self):
        with self.assertRaises(journal.Rejected):
            journal.encode_event([], "START", {"password": "private-sentinel"})

    def test_flush_readback_before_ack_and_copy(self):
        native = self.fake()
        value = self.opening(native)
        row = value.record("START", **self.start())
        self.assertTrue(value.intact)
        self.assertEqual(row["seq"], 0)
        native.flush.assert_called_once_with(2)
        value.events.clear()
        self.assertEqual(len(value.events), 1)
        value.record("DISPATCH_ATTEMPT")
        with self.assertRaises(journal.Rejected):
            value.record("DISPATCH_ATTEMPT")
        self.assertFalse(value.intact)
        value.close()
        self.assertIn(mock.call(2), native.close.call_args_list)

    def test_torn_or_corrupt_prefix_readonly(self):
        row = journal.encode_event([], "START", self.start())
        for tail in (b'{"seq":1', b"invalid\n", row, b"\n"):
            value = self.opening(self.fake(row + tail), create=False)
            self.assertFalse(value.intact)
            self.assertEqual(len(value.events), 1)
            with self.assertRaises(journal.Rejected):
                value.record("DISPATCH_ATTEMPT")
            value.close()
        value = self.opening(self.fake(), create=False)
        self.assertFalse(value.intact)

    def test_failure_never_acknowledges_or_retries(self):
        for failure in ("flush", "readback", "acl"):
            native = self.fake()
            value = self.opening(native)
            if failure == "flush":
                native.flush.return_value = False
            elif failure == "readback":

                def wrong(handle, buffer, size, count, _):
                    native.data += b"x" * size
                    c.cast(count, c.POINTER(journal.custody.w.DWORD)).contents.value = (
                        size
                    )
                    return True

                native.write.side_effect = wrong
            else:
                native.acl.side_effect = OSError("private-sentinel")
            with self.assertRaises(journal.Rejected) as error:
                value.record("START", **self.start())
            self.assertNotIn("private-sentinel", str(error.exception))
            count = native.write.call_count
            with self.assertRaises(journal.Rejected):
                value.record("START", **self.start())
            self.assertEqual(native.write.call_count, count)
            value.close()

    def test_event_prerequisites_names_and_private_schema(self):
        row = journal.encode_event([], "START", self.start())
        events, _ = journal.parse(row)
        for event, data in (
            ("SECRET_PUT_ATTEMPT", {"name": journal.wire.SECRETS[0]}),
            (
                "DISPATCH_CONFIRMED",
                {"run_id": True, "workflow_id": 1, "environment_id": 2},
            ),
            ("APPROVAL_ATTEMPT", {}),
            (
                "RESULT",
                {
                    "classification": "private-sentinel",
                    "cleanup_verified": True,
                    "secret_absence_verified": True,
                    "owner_distribution_verified": True,
                },
            ),
        ):
            with self.assertRaises(journal.Rejected):
                journal.encode_event(events, event, data)
        with self.assertRaises(journal.Rejected):
            journal.encode_event([], "START", self.start() | {"nonce": "bad"})
        self.assertEqual(journal.parse(b"x" * 65537), ([], False))

    def test_existing_share_zero_and_create_no_overwrite(self):
        native = object.__new__(journal.Native)
        native.open = mock.Mock(return_value=7)
        self.assertEqual(native.journal_handle(Path("fictional"), create=False), 7)
        self.assertEqual(native.open.call_args.args[2], 0)
        self.assertEqual(native.open.call_args.args[4], 3)
        native.open_handle = mock.Mock(return_value=8)
        self.assertEqual(native.journal_handle(Path("fictional"), create=True), 8)
        native.open_handle.assert_called_once_with(Path("fictional"), create=True)

    def test_existing_directory_never_repaired_and_failure_closes(self):
        native = self.fake()
        native.journal_handle.side_effect = OSError("already-exists")
        with mock.patch.object(journal.preparation, "secure_acl") as repair:
            with self.assertRaises(journal.Rejected):
                self.opening(native)
        repair.assert_not_called()
        self.assertTrue(native.close.called)

    def test_mutation_confirmation_and_duplicate_name(self):
        value = self.opening(self.fake())
        value.record("START", **self.start())
        value.record("DISPATCH_ATTEMPT")
        value.record("DISPATCH_CONFIRMED", run_id=1, workflow_id=2, environment_id=3)
        value.record("SECRET_PUT_ATTEMPT", name=journal.wire.SECRETS[0])
        value.record("SECRET_PUT_CONFIRMED", name=journal.wire.SECRETS[0])
        value.record("SECRET_DELETE_ATTEMPT", name=journal.wire.SECRETS[0])
        value.record("SECRET_ABSENT", name=journal.wire.SECRETS[0])
        with self.assertRaises(journal.Rejected):
            value.record("SECRET_DELETE_ATTEMPT", name=journal.wire.SECRETS[0])
        value.close()


@unittest.skipUnless(sys.platform == "win32", "Native Windows journal fixture")
class NativeJournalTests(unittest.TestCase):
    def test_native_create_append_reopen(self):
        # Only a newly created fictional temporary directory; no Owner journal,
        # credentials, network, or mocked native/ACL operations.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            (root / "Temp").mkdir()
            with mock.patch.object(
                journal.preparation, "local_app_data", return_value=root
            ):
                value = journal.Journal.open(create=True)
                try:
                    value.record("START", **JournalTests().start())
                    value.record("DISPATCH_ATTEMPT")
                    self.assertTrue(value.intact)
                finally:
                    value.close()
                reopened = journal.Journal.open(create=False)
                try:
                    self.assertTrue(reopened.intact)
                    self.assertEqual(len(reopened.events), 2)
                finally:
                    reopened.close()


if __name__ == "__main__":
    unittest.main()
