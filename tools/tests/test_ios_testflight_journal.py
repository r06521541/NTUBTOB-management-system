import ctypes as c
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import ios_testflight_journal as journal


class JournalTests(unittest.TestCase):
    def stopped(self):
        native = self.fake()
        value = self.opening(native)
        value.record("START", **self.start())
        value.record(
            "RESULT",
            classification="UNRESOLVED",
            cleanup_verified=False,
            secret_absence_verified=True,
            owner_distribution_verified=False,
        )
        return value, native

    def successor(self, snapshot):
        return self.start() | dict(
            sha="c" * 40,
            nonce="d" * 64,
            issued=200,
            expires=7400,
            parent_sha256=snapshot["digest"],
        )

    def test_unsent_successor_preserves_bytes_and_is_one_shot(self):
        value, native = self.stopped()
        before = native.data
        snapshot = value.unsent_snapshot()
        value.record("UNSENT_SUCCESSOR", **self.successor(snapshot))
        self.assertTrue(native.data.startswith(before))
        self.assertEqual(value.events[0]["data"]["sha"], "a" * 40)
        active = journal.active_events(value.events)
        self.assertEqual([row["event"] for row in active], ["START"])
        self.assertEqual(active[0]["data"]["sha"], "c" * 40)
        self.assertEqual(active[0]["data"]["nonce"], "d" * 64)
        self.assertEqual(journal.summary(value, "c" * 40)["attempt_number"], 2)
        self.assertTrue(journal.summary(value, "c" * 40)["source_matches"])
        with self.assertRaises(journal.Rejected):
            value.unsent_snapshot()
        value.record(
            "FAILURE",
            stage="dispatch_preflight",
            check="workflow",
            reason="CHECK_REJECTED",
        )
        value.record(
            "RESULT",
            classification="STOP",
            cleanup_verified=False,
            secret_absence_verified=False,
            owner_distribution_verified=False,
        )
        with self.assertRaises(journal.Rejected):
            value.record("UNSENT_SUCCESSOR", **self.successor(snapshot))
        value.close()

    def test_unsent_exact_predecessor_and_no_positive_cleanup(self):
        first = journal.encode_event([], "START", self.start())
        for event, data in (
            ("UNCERTAIN", {}),
            ("DISPATCH_ATTEMPT", {}),
            (
                "RESULT",
                dict(
                    classification="CLEANED",
                    cleanup_verified=True,
                    secret_absence_verified=True,
                    owner_distribution_verified=False,
                ),
            ),
            (
                "RESULT",
                dict(
                    classification="STOP",
                    cleanup_verified=False,
                    secret_absence_verified=False,
                    owner_distribution_verified=True,
                ),
            ),
        ):
            events, _ = journal.parse(first)
            raw = first + journal.encode_event(events, event, data)
            value = self.opening(self.fake(raw), create=False)
            with self.assertRaises(journal.Rejected):
                value.unsent_snapshot()
            value.close()
        value, native = self.stopped()
        value.record(
            "RESULT",
            classification="STOP",
            cleanup_verified=False,
            secret_absence_verified=False,
            owner_distribution_verified=False,
        )
        with self.assertRaises(journal.Rejected):
            value.unsent_snapshot()
        value.close()

    def test_successor_digest_nonce_schema_and_torn_append_fail_closed(self):
        for change in (
            {"parent_sha256": "e" * 64},
            {"nonce": "b" * 64},
            {"version": "9.9.9"},
            {"issued": 99},
            {"sha": "private-sentinel"},
        ):
            value, native = self.stopped()
            before = native.data
            with self.assertRaises(journal.Rejected):
                value.record(
                    "UNSENT_SUCCESSOR",
                    **(self.successor(value.unsent_snapshot()) | change),
                )
            self.assertEqual(native.data, before)
            value.close()
        value, native = self.stopped()
        before = native.data
        successor = self.successor(value.unsent_snapshot())
        native.flush.return_value = False
        with self.assertRaises(journal.Rejected):
            value.record("UNSENT_SUCCESSOR", **successor)
        self.assertFalse(value.intact)
        self.assertTrue(native.data.startswith(before))
        calls = native.write.call_count
        with self.assertRaises(journal.Rejected):
            value.record("UNSENT_SUCCESSOR", **successor)
        self.assertEqual(native.write.call_count, calls)
        value.close()
        # A complete readback after a lost acknowledgement still consumes the
        # only successor. A torn prefix stays damaged and cannot authorize one.
        for raw in (native.data, native.data[:-1]):
            reopened = self.opening(self.fake(raw), create=False)
            with self.assertRaises(journal.Rejected):
                reopened.unsent_snapshot()
            if raw != native.data:
                self.assertFalse(reopened.intact)
                self.assertEqual(
                    journal.summary(reopened, "c" * 40)["external_write_state"],
                    "UNKNOWN",
                )
            reopened.close()

    def test_successor_parser_checks_exact_prefix_and_old_reader_stops(self):
        value, native = self.stopped()
        value.record("UNSENT_SUCCESSOR", **self.successor(value.unsent_snapshot()))
        raw = native.data
        self.assertTrue(journal.parse(raw)[1])
        changed = raw.replace(
            b'"cleanup_verified":false', b'"cleanup_verified":true', 1
        )
        self.assertFalse(journal.parse(changed)[1])
        with mock.patch.dict(
            journal.FIELDS,
            {
                key: data
                for key, data in journal.FIELDS.items()
                if key != "UNSENT_SUCCESSOR"
            },
            clear=True,
        ):
            events, intact = journal.parse(raw)
        self.assertFalse(intact)
        self.assertEqual(len(events), 2)
        value.close()

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

    def opening(self, native, create=True, readonly=False):
        with (
            mock.patch.object(
                journal.preparation, "local_app_data", return_value=Path("C:/fictional")
            ),
            mock.patch.object(journal.preparation, "safe_directory"),
            mock.patch.object(Path, "exists", return_value=True),
        ):
            return journal.Journal.open(
                create=create, readonly=readonly, nativefactory=lambda: native
            )

    def test_readonly_handle_and_record_refused_without_damage(self):
        raw = journal.encode_event([], "START", self.start())
        native = self.fake(raw)
        value = self.opening(native, create=False, readonly=True)
        with self.assertRaises(journal.Rejected):
            value.record("DISPATCH_ATTEMPT")
        self.assertTrue(value.intact)
        native.write.assert_not_called()
        native.flush.assert_not_called()
        self.assertTrue(native.journal_handle.call_args.kwargs["readonly"])
        value.close()
        real = object.__new__(journal.Native)
        real.open = mock.Mock(return_value=7)
        real.journal_handle(Path("fictional"), create=False, readonly=True)
        self.assertEqual(real.open.call_args.args[1], 0x80020000)
        self.assertEqual(real.open.call_args.args[2], 0)
        with self.assertRaises(journal.Rejected):
            journal.Journal.open(
                create=True, readonly=True, nativefactory=lambda: native
            )

    def test_failure_exact_schema_once_and_legacy_summary(self):
        value = self.opening(self.fake())
        value.record("START", **self.start())
        value.record(
            "RESULT",
            classification="UNRESOLVED",
            cleanup_verified=False,
            secret_absence_verified=True,
            owner_distribution_verified=False,
        )
        legacy = journal.summary(value, "a" * 40)
        self.assertEqual(legacy["failure"]["reason"], "LEGACY_REASON_UNAVAILABLE")
        self.assertEqual(legacy["external_write_state"], "NOT_ATTEMPTED")
        self.assertEqual(legacy["secret_transfer_state"], "NOT_ATTEMPTED")
        self.assertFalse(legacy["secret_absence_verified"])
        failure = dict(
            stage="journal_open", check="journal_path", reason="JOURNAL_REJECTED"
        )
        value.record("FAILURE", **failure)
        self.assertEqual(journal.summary(value, "a" * 40)["failure"], failure)
        self.assertFalse(journal.summary(value, "c" * 40)["source_matches"])
        with self.assertRaises(journal.Rejected):
            journal.encode_event(value.events, "FAILURE", failure)
        for data in (
            failure | {"private": "private-sentinel"},
            failure | {"reason": "private-sentinel"},
        ):
            with self.assertRaises(journal.Rejected):
                journal.encode_event(value.events[:1], "FAILURE", data)
        value.intact = False
        damaged = journal.summary(value, "a" * 40)
        self.assertEqual(damaged["external_write_state"], "UNKNOWN")
        self.assertEqual(damaged["secret_transfer_state"], "UNRESOLVED")
        self.assertEqual(damaged["failure"]["reason"], "JOURNAL_REJECTED")
        value.close()

    def test_precheck_is_metadata_only_and_never_creates_or_repairs(self):
        native = self.fake()
        with (
            mock.patch.object(
                journal.preparation, "local_app_data", return_value=Path("C:/fictional")
            ),
            mock.patch.object(journal.preparation, "safe_directory"),
            mock.patch.object(journal.preparation, "secure_acl") as repair,
            mock.patch.object(Path, "mkdir") as mkdir,
            mock.patch.object(Path, "lstat") as stat,
        ):
            self.assertEqual(
                journal.new_operation_preflight(nativefactory=lambda: native),
                "EXISTING_OPERATION",
            )
            native.open_handle.assert_not_called()
            stat.side_effect = [object(), FileNotFoundError()]
            self.assertEqual(
                journal.new_operation_preflight(nativefactory=lambda: native),
                "READY_NO_JOURNAL",
            )
            stat.side_effect = [FileNotFoundError()]
            self.assertEqual(
                journal.new_operation_preflight(nativefactory=lambda: native),
                "READY_ROOT_NOT_CREATED",
            )
        mkdir.assert_not_called()
        repair.assert_not_called()
        native.journal_handle.assert_not_called()
        native.read.assert_not_called()
        native.write.assert_not_called()

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
    def test_native_exclusive_successor_blocks_second_writer_and_reuse(self):
        # All native handles refer ONLY to this new fictional temp fixture.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            (root / "Temp").mkdir()
            with mock.patch.object(
                journal.preparation, "local_app_data", return_value=root
            ):
                value = journal.Journal.open(create=True)
                try:
                    value.record("START", **JournalTests().start())
                    value.record(
                        "RESULT",
                        classification="UNRESOLVED",
                        cleanup_verified=False,
                        secret_absence_verified=True,
                        owner_distribution_verified=False,
                    )
                finally:
                    value.close()
                value = journal.Journal.open(create=False)
                try:
                    snapshot = value.unsent_snapshot()
                    with self.assertRaises(journal.Rejected):
                        journal.Journal.open(create=False)
                    value.record(
                        "UNSENT_SUCCESSOR", **JournalTests().successor(snapshot)
                    )
                finally:
                    value.close()
                reopened = journal.Journal.open(create=False, readonly=True)
                try:
                    self.assertTrue(reopened.intact)
                    self.assertEqual(
                        [r["event"] for r in reopened.events],
                        ["START", "RESULT", "UNSENT_SUCCESSOR"],
                    )
                    with self.assertRaises(journal.Rejected):
                        reopened.unsent_snapshot()
                finally:
                    reopened.close()

    def test_native_create_append_reopen(self):
        # Only a newly created fictional temporary directory; no Owner journal,
        # credentials, network, or mocked native/ACL operations.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            (root / "Temp").mkdir()
            with mock.patch.object(
                journal.preparation, "local_app_data", return_value=root
            ):
                self.assertEqual(
                    journal.new_operation_preflight(), "READY_ROOT_NOT_CREATED"
                )
                self.assertFalse((root / journal.DIRECTORY).exists())
                value = journal.Journal.open(create=True)
                try:
                    value.record("START", **JournalTests().start())
                    value.record("DISPATCH_ATTEMPT")
                    self.assertTrue(value.intact)
                finally:
                    value.close()
                self.assertEqual(
                    journal.new_operation_preflight(), "EXISTING_OPERATION"
                )
                reopened = journal.Journal.open(create=False, readonly=True)
                try:
                    self.assertTrue(reopened.intact)
                    self.assertEqual(len(reopened.events), 2)
                    with self.assertRaises(journal.Rejected):
                        reopened.record(
                            "RESULT",
                            classification="STOP",
                            cleanup_verified=False,
                            secret_absence_verified=False,
                            owner_distribution_verified=False,
                        )
                    self.assertTrue(reopened.intact)
                    self.assertEqual(len(reopened.events), 2)
                    self.assertEqual(
                        journal.summary(reopened, "a" * 40)["external_write_state"],
                        "ATTEMPTED",
                    )
                finally:
                    reopened.close()


if __name__ == "__main__":
    unittest.main()
