"""One sanitized append-only operation record; never a secret transcript.

No reset/delete/archive. A damaged prefix is read-only and cannot establish that
an absent attempt did not happen. Same-user/administrator tampering is outside
this ACL boundary. Existing intact journals can append recovery observations.
"""

import ctypes as c
import json
import re
import threading
from copy import deepcopy

from tools import ios_certificate_custody as custody
from tools import ios_certificate_preparation as preparation
from tools import ios_testflight_wire as wire

DIRECTORY = "NTUBTOB-OwnerTestFlight-Journal"
FILENAME = "operation.jsonl"
LIMIT = 65536
ROW_LIMIT = 4096
FIELDS = {
    "START": {
        "sha",
        "nonce",
        "version",
        "build",
        "previous_build",
        "issued",
        "expires",
    },
    "DISPATCH_ATTEMPT": set(),
    "DISPATCH_CONFIRMED": {"run_id", "workflow_id", "environment_id"},
    "JOB_BOUND": {"job_id"},
    "SECRET_PUT_ATTEMPT": {"name"},
    "SECRET_PUT_CONFIRMED": {"name"},
    "SECRET_DELETE_ATTEMPT": {"name"},
    "SECRET_DELETE_CONFIRMED": {"name"},
    "SECRET_ABSENT": {"name"},
    "APPROVAL_ATTEMPT": set(),
    "APPROVAL_CONFIRMED": set(),
    "CANCEL_ATTEMPT": set(),
    "CANCEL_CONFIRMED": set(),
    "UNCERTAIN": set(),
    "TERMINAL": {"conclusion"},
    "CANDIDATE": {"sha256", "size"},
    "RESULT": {
        "classification",
        "cleanup_verified",
        "secret_absence_verified",
        "owner_distribution_verified",
    },
}
CLASSIFICATIONS = frozenset(
    {
        "STOP",
        "UNRESOLVED",
        "CLEANED",
        "PREPARED",
        "CANDIDATE_BOUND",
        "PREFLIGHT_PASSED",
        "PREFLIGHT_REJECTED",
        "SESSION_CONSUMED",
        "UPLOAD_COMMITTED",
        "UPLOAD_UNCERTAIN",
        "UNKNOWN_RESERVATION",
        "UPLOAD_FAILED",
        "UPLOAD_PENDING",
        "BUILD_PENDING",
        "BUILD_VALID_UNDISTRIBUTED",
        "BUILD_FAILED",
        "RECONCILIATION_UNRESOLVED",
        "OWNER_DISTRIBUTION_VERIFIED",
    }
)


class Rejected(Exception):
    def __init__(self):
        super().__init__("JOURNAL_REJECTED")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def encode_event(events, event, data):
    try:
        if (
            type(event) is not str
            or event not in FIELDS
            or type(data) is not dict
            or set(data) != FIELDS[event]
        ):
            raise ValueError()
        prior = [row["event"] for row in events]
        if (not events and event != "START") or (events and event == "START"):
            raise ValueError()
        if event == "START":
            for key, pattern in (
                ("sha", r"[0-9a-f]{40}"),
                ("nonce", r"[0-9a-f]{64}"),
                ("version", r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}"),
            ):
                if type(data[key]) is not str or not re.fullmatch(pattern, data[key]):
                    raise ValueError()
            if (
                not _integer(data["build"], 1, 2147483647)
                or not _integer(data["previous_build"], 0, data["build"] - 1)
                or not _integer(data["issued"], 0, 99999999999)
                or not _integer(
                    data["expires"], data["issued"] + 1, data["issued"] + 7200
                )
            ):
                raise ValueError()
        if event in {"DISPATCH_CONFIRMED", "JOB_BOUND"} and any(
            not _integer(v, 1, 10**20 - 1) for v in data.values()
        ):
            raise ValueError()
        if "name" in data and (
            type(data["name"]) is not str or data["name"] not in wire.SECRETS
        ):
            raise ValueError()
        if event == "CANDIDATE" and (
            type(data["sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", data["sha256"])
            or not _integer(data["size"], 1, 536870912)
        ):
            raise ValueError()
        if event == "TERMINAL" and data["conclusion"] not in {
            "success",
            "failure",
            "cancelled",
            "skipped",
            "timed_out",
            "action_required",
            "neutral",
            "stale",
            "startup_failure",
        }:
            raise ValueError()
        if event == "RESULT" and (
            data["classification"] not in CLASSIFICATIONS
            or any(
                type(data[key]) is not bool
                for key in (
                    "cleanup_verified",
                    "secret_absence_verified",
                    "owner_distribution_verified",
                )
            )
        ):
            raise ValueError()
        unique = {
            "DISPATCH_ATTEMPT",
            "DISPATCH_CONFIRMED",
            "APPROVAL_ATTEMPT",
            "APPROVAL_CONFIRMED",
            "CANCEL_ATTEMPT",
            "CANCEL_CONFIRMED",
            "JOB_BOUND",
            "CANDIDATE",
        }
        if event in unique and event in prior:
            raise ValueError()
        if (
            event.startswith("SECRET_")
            and event != "SECRET_ABSENT"
            and any(row["event"] == event and row["data"] == data for row in events)
        ):
            raise ValueError()
        required = {
            "DISPATCH_CONFIRMED": "DISPATCH_ATTEMPT",
            "APPROVAL_CONFIRMED": "APPROVAL_ATTEMPT",
            "CANCEL_CONFIRMED": "CANCEL_ATTEMPT",
            "JOB_BOUND": "DISPATCH_CONFIRMED",
            "CANCEL_ATTEMPT": "DISPATCH_CONFIRMED",
            "SECRET_PUT_ATTEMPT": "DISPATCH_CONFIRMED",
        }
        if event in required and required[event] not in prior:
            raise ValueError()
        secret_required = {
            "SECRET_PUT_CONFIRMED": "SECRET_PUT_ATTEMPT",
            "SECRET_DELETE_ATTEMPT": "SECRET_PUT_ATTEMPT",
            "SECRET_DELETE_CONFIRMED": "SECRET_DELETE_ATTEMPT",
            "SECRET_ABSENT": "SECRET_PUT_ATTEMPT",
        }
        if event in secret_required and not any(
            row["event"] == secret_required[event] and row["data"] == data
            for row in events
        ):
            raise ValueError()
        if event == "APPROVAL_ATTEMPT" and {
            row["data"]["name"]
            for row in events
            if row["event"] == "SECRET_PUT_CONFIRMED"
        } != set(wire.SECRETS):
            raise ValueError()
        row = (
            json.dumps(
                {"seq": len(events), "event": event, "data": data},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        if len(row) > ROW_LIMIT:
            raise ValueError()
        return row
    except Exception:
        raise Rejected() from None


def parse(raw):
    events = []
    if type(raw) is not bytes or len(raw) > LIMIT:
        return events, False
    for line in raw.splitlines(keepends=True):
        try:
            if len(line) > ROW_LIMIT or not line.endswith(b"\n"):
                raise ValueError()

            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError()
                    value[key] = item
                return value

            row = json.loads(line, object_pairs_hook=unique)
            if (
                type(row) is not dict
                or set(row) != {"seq", "event", "data"}
                or type(row["seq"]) is not int
                or row["seq"] != len(events)
                or encode_event(events, row["event"], row["data"]) != line
            ):
                raise ValueError()
            events.append(row)
        except Exception:
            return events, False
    return events, True


class Native(custody.Native):
    def journal_handle(self, path, *, create):
        if create:
            return self.open_handle(path, create=True)
        handle = self.open(str(path), 0xC0020000, 0, None, 3, 0x00200080, None)
        if handle == c.c_void_p(-1).value:
            raise Rejected()
        return handle


class Journal:
    def __init__(self):
        self._events = []
        self.intact = False
        self._raw = b""
        self._handles = []
        self._directories = []
        self._closed = False
        self._lock = threading.RLock()

    @property
    def events(self):
        return deepcopy(self._events)

    @classmethod
    def open(cls, create=False, *, nativefactory=Native):
        value = cls()
        try:
            if type(create) is not bool:
                raise Rejected()
            value.native = nativefactory()
            root = preparation.local_app_data() / DIRECTORY
            if create and not root.exists():
                preparation.safe_directory(root, fresh=True)
                root.mkdir()
                preparation.secure_acl(root, establish=True)
            preparation.safe_directory(root, fresh=False)
            for path in (*reversed(root.parents), root):
                handle = value.native.open_handle(
                    path, directory=True, ancestor=path != root
                )
                value._handles.append(handle)
                metadata = value.native.metadata(handle, path, directory=True)
                if path == root:
                    value.native.acl(handle, directory=True)
                value._directories.append((handle, path, metadata, path == root))
            value.path = root / FILENAME
            value.handle = value.native.journal_handle(value.path, create=create)
            value._handles.append(value.handle)
            value.expected = value.native.metadata(
                value.handle, value.path, allow_empty=True
            )
            value.native.acl(value.handle)
            value._raw = value._read(value.expected[3])
            value._events, value.intact = parse(value._raw)
            if not create and not value._raw:
                value.intact = False
            value._verify()
            return value
        except Exception:
            value.close()
            raise Rejected() from None

    def _verify(self):
        if (
            self._closed
            or self.native.metadata(self.handle, self.path, allow_empty=True)
            != self.expected
        ):
            raise Rejected()
        self.native.acl(self.handle)
        for handle, path, expected, private in self._directories:
            # Directory last-write time changes when the journal is first created;
            # preserve identity/type/path while not treating that expected change as drift.
            if self.native.metadata(handle, path, directory=True)[:3] != expected[:3]:
                raise Rejected()
            if private:
                self.native.acl(handle, directory=True)

    def _read(self, size):
        if type(size) is not int or not 0 <= size <= LIMIT:
            raise Rejected()
        buffer, count = c.create_string_buffer(max(1, size)), custody.w.DWORD()
        if (
            not self.native.seek(self.handle, 0, None, 0)
            or not self.native.read(self.handle, buffer, size, c.byref(count), None)
            or count.value != size
        ):
            raise Rejected()
        return buffer.raw[:size]

    def record(self, event, **data):
        with self._lock:
            return self._record(event, data)

    def _record(self, event, data):
        try:
            if not self.intact:
                raise Rejected()
            row = encode_event(self._events, event, data)
            intended = self._raw + row
            if len(intended) > LIMIT:
                raise Rejected()
            self._verify()
            if self._read(len(self._raw)) != self._raw:
                raise Rejected()
            self.intact = False
            if not self.native.seek(self.handle, 0, None, 2):
                raise Rejected()
            buffer, count = c.create_string_buffer(row), custody.w.DWORD()
            if (
                not self.native.write(
                    self.handle, buffer, len(row), c.byref(count), None
                )
                or count.value != len(row)
                or not self.native.flush(self.handle)
            ):
                raise Rejected()
            observed = self.native.metadata(self.handle, self.path, allow_empty=True)
            if (
                observed[:3] != self.expected[:3]
                or observed[3] != len(intended)
                or self._read(observed[3]) != intended
            ):
                raise Rejected()
            self.expected = observed
            self._verify()
            self._raw = intended
            self._events, self.intact = parse(intended)
            if not self.intact:
                raise Rejected()
            return deepcopy(self._events[-1])
        except Exception:
            self.intact = False
            raise Rejected() from None

    def close(self):
        with self._lock:
            self._close()

    def _close(self):
        failed = False
        for handle in reversed(self._handles):
            try:
                if not self.native.close(handle):
                    failed = True
            except Exception:
                failed = True
        self._handles.clear()
        self._closed = True
        if failed:
            raise Rejected()
