"""One ASC import with durable metadata backup, NOT an atomic transaction.

Settings stay locked from first read to close. Backup precedes key copy/update.
Partial files remain untouched; there is no automatic retry/restore/delete.
Only the JSON-selected source may have current-Owner inherited ACLs. No other
key is enumerated or opened. No CLI, network or source repair. Existing limits
against same-user/admin malware and guaranteed memory wiping still apply.
"""

import ctypes as c
import json

from tools import ios_certificate_custody as custody
from tools import ios_certificate_preparation as preparation
from tools import ios_testflight_inputs as inputs
from tools import ios_testflight_intake as intake
from tools import ios_testflight_settings as settings
from tools import ios_testflight_wire as wire

DESTINATION = "asc-upload.p8"
BACKUP = "testflight-inputs.pre-import.json"
REASONS = (
    frozenset(
        {
            "ASC_IMPORT_READY",
            "ASC_IMPORT_PRESENT",
            "ASC_IMPORT_COMPLETE",
            "ASC_IMPORT_UNRESOLVED",
            "ASC_IMPORT_REJECTED",
            "ASC_FILENAME_REJECTED",
            "SETTINGS_FIELDS_REJECTED",
            "KEY_REJECTED",
        }
    )
    | custody.REASONS
)


class Rejected(Exception):
    def __init__(self, reason="ASC_IMPORT_REJECTED"):
        super().__init__(
            reason
            if type(reason) is str and reason in REASONS
            else "ASC_IMPORT_REJECTED"
        )


class Native(custody.Native):
    def settings_handle(self, path):
        handle = self.open(str(path), 0xC0020000, 0, None, 3, 0x00200080, None)
        if handle == c.c_void_p(-1).value:
            raise Rejected("HANDLE_REJECTED")
        return handle

    def source_acl(self, handle, *, directory=False):
        try:
            self.acl(handle, directory=directory)
            return
        except custody.CustodyError:
            pass
        owner, dacl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        if self.get_security(
            handle, 1, 5, c.byref(owner), None, c.byref(dacl), None, c.byref(descriptor)
        ):
            raise Rejected("ACL_REJECTED")
        try:
            if not owner or not dacl or not self.equal_sid(owner, self.sid):
                raise Rejected("ACL_REJECTED")
            header = c.cast(dacl, c.POINTER(custody.ACLHeader)).contents
            if not 1 <= header.count <= 64:
                raise Rejected("ACL_REJECTED")
            for index in range(header.count):
                ace = c.c_void_p()
                if not self.get_ace(dacl, index, c.byref(ace)):
                    raise Rejected("ACL_REJECTED")
                prefix = c.string_at(ace, 4)
                if prefix[0] not in (0, 1) or not prefix[1] & 16:
                    raise Rejected("ACL_REJECTED")
        finally:
            self.free(descriptor)

    def read_bytes(self, handle, size):
        if type(size) is not int or not 1 <= size <= 65536:
            raise Rejected("READ_REJECTED")
        buffer, count = c.create_string_buffer(size), custody.w.DWORD()
        if (
            not self.seek(handle, 0, None, 0)
            or not self.read(handle, buffer, size, c.byref(count), None)
            or count.value != size
        ):
            raise Rejected("READ_REJECTED")
        return buffer.raw

    def write_checked(self, handle, path, raw, *, truncate=False):
        if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
            raise Rejected("WRITE_REJECTED")
        before = self.metadata(handle, path, allow_empty=True)
        self.acl(handle)
        if not self.seek(handle, 0, None, 0):
            raise Rejected("WRITE_REJECTED")
        if truncate:
            end = self.bind(
                self.kernel, "SetEndOfFile", custody.w.BOOL, [custody.w.HANDLE]
            )
            if not end(handle):
                raise Rejected("WRITE_REJECTED")
        count = custody.w.DWORD()
        if (
            not self.write(
                handle, c.create_string_buffer(raw), len(raw), c.byref(count), None
            )
            or count.value != len(raw)
            or not self.flush(handle)
        ):
            raise Rejected("WRITE_REJECTED")
        after = self.metadata(handle, path)
        if (
            after[:3] != before[:3]
            or after[3] != len(raw)
            or self.read_bytes(handle, len(raw)) != raw
            or self.metadata(handle, path) != after
        ):
            raise Rejected("READBACK_REJECTED")
        self.acl(handle)


def _parse(raw, google_web):
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=wire._unique)
        if type(value) is not dict or set(value) != set(settings.FIELDS):
            raise ValueError()
        for name, field in settings.FIELDS.items():
            intake.validate_field(field, value[name], google_web=google_web)
        return value
    except Exception:
        raise Rejected("SETTINGS_FIELDS_REJECTED") from None


def _exists(path):
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


class Session:
    def __init__(self, native):
        self.native, self.handles, self.records = native, [], []
        self.parents = set()

    def __repr__(self):
        return "<ASCImportCustody>"

    def check_acl(self, handle, mode, *, directory=False):
        if mode == "source":
            self.native.source_acl(handle, directory=directory)
        elif mode == "private":
            self.native.acl(handle, directory=directory)

    def directory(self, path, *, source=False):
        if ".." in path.parts:
            raise Rejected("METADATA_REJECTED")
        preparation.safe_directory(path, fresh=False)
        for parent in (*reversed(path.parents), path):
            if parent in self.parents and parent != path:
                continue
            handle = self.native.open_handle(
                parent, directory=True, ancestor=parent != path
            )
            self.handles.append(handle)
            expected = self.native.metadata(handle, parent, directory=True)
            mode = (
                "source"
                if source and parent == path
                else "private" if parent == path else "ancestor"
            )
            self.check_acl(handle, mode, directory=True)
            self.records.append((handle, parent, expected, True, mode))
            self.parents.add(parent)

    def file(self, path, *, limit, source=False, writable=False):
        handle = (
            self.native.settings_handle(path)
            if writable
            else self.native.open_handle(path)
        )
        self.handles.append(handle)
        expected = self.native.metadata(handle, path)
        if not 1 <= expected[3] <= limit:
            raise Rejected("METADATA_REJECTED")
        mode = "source" if source else "private"
        self.check_acl(handle, mode)
        record = (handle, path, expected, False, mode)
        self.records.append(record)
        return record

    def read(self, record):
        handle, path, expected, _, mode = record
        if self.native.metadata(handle, path) != expected:
            raise Rejected("INPUT_CHANGED")
        self.check_acl(handle, mode)
        raw = self.native.read_bytes(handle, expected[3])
        if self.native.metadata(handle, path) != expected:
            raise Rejected("INPUT_CHANGED")
        return raw

    def verify(self, *, modified_settings=None):
        for handle, path, expected, directory, mode in self.records:
            observed = self.native.metadata(handle, path, directory=directory)
            if directory or path == modified_settings:
                changed = observed[:3] != expected[:3]
            else:
                changed = observed != expected
            if changed:
                raise Rejected("INPUT_CHANGED")
            self.check_acl(handle, mode, directory=directory)

    def create(self, path, raw):
        handle = self.native.open_handle(path, create=True)
        self.handles.append(handle)
        self.native.write_checked(handle, path, raw)
        self.records.append(
            (handle, path, self.native.metadata(handle, path), False, "private")
        )
        return handle

    def close(self):
        failed = False
        for handle in reversed(self.handles):
            try:
                if not self.native.close(handle):
                    failed = True
            except Exception:
                failed = True
        self.handles.clear()
        if failed:
            raise Rejected("ASC_IMPORT_UNRESOLVED")


def _filename(path, key_id):
    if (
        path.name.lower().startswith("authkey_")
        and path.name != "AuthKey_" + key_id + ".p8"
    ):
        raise Rejected("ASC_FILENAME_REJECTED")


def _operate(google_web, *, execute):
    session, attempted, retained = None, False, False
    outcome = "ASC_IMPORT_REJECTED"
    try:
        root = preparation.local_app_data() / preparation.DIRECTORY
        native = Native()
        session = Session(native)
        session.directory(root)
        settings_path, backup, destination = (
            root / settings.FILENAME,
            root / BACKUP,
            root / DESTINATION,
        )
        retained = _exists(backup) or _exists(destination)
        record = session.file(settings_path, limit=65536, writable=execute)
        original = session.read(record)
        values = _parse(original, google_web)
        source = intake._path(values["asc_p8_path"])
        if source == destination:
            if not _exists(backup):
                raise Rejected("ASC_IMPORT_UNRESOLVED")
            prior = _parse(session.read(session.file(backup, limit=65536)), google_web)
            if (
                any(
                    prior[k] != values[k] for k in settings.FIELDS if k != "asc_p8_path"
                )
                or intake._path(prior["asc_p8_path"]) == destination
            ):
                raise Rejected("ASC_IMPORT_UNRESOLVED")
            source = intake._path(prior["asc_p8_path"])
            _filename(source, values["asc_key_id"])
            session.directory(source.parent, source=True)
            src = session.file(source, limit=4096, source=True)
            dst = session.file(destination, limit=4096)
            if execute:
                raw = session.read(src)
                if raw != session.read(dst):
                    raise Rejected("ASC_IMPORT_UNRESOLVED")
                inputs.load_asc_key(
                    raw, key_id=values["asc_key_id"], issuer_id=values["asc_issuer_id"]
                )
            session.verify()
            outcome = "ASC_IMPORT_COMPLETE" if execute else "ASC_IMPORT_PRESENT"
        else:
            if _exists(backup) or _exists(destination):
                raise Rejected("ASC_IMPORT_UNRESOLVED")
            _filename(source, values["asc_key_id"])
            session.directory(source.parent, source=True)
            selected = session.file(source, limit=4096, source=True)
            session.verify()
            if not execute:
                outcome = "ASC_IMPORT_READY"
            else:
                raw = session.read(selected)
                inputs.load_asc_key(
                    raw, key_id=values["asc_key_id"], issuer_id=values["asc_issuer_id"]
                )
                encoded = (
                    json.dumps(
                        dict(values, asc_p8_path=destination.as_posix()),
                        ensure_ascii=True,
                        indent=2,
                    )
                    + "\n"
                ).encode("ascii")
                if len(encoded) > 65536:
                    raise Rejected("SETTINGS_FIELDS_REJECTED")
                session.verify()
                attempted = True
                session.create(backup, original)
                session.verify()
                session.create(destination, raw)
                session.verify()
                if session.read(record) != original:
                    raise Rejected("INPUT_CHANGED")
                native.write_checked(record[0], settings_path, encoded, truncate=True)
                session.verify(modified_settings=settings_path)
                outcome = "ASC_IMPORT_COMPLETE"
    except (Exception, KeyboardInterrupt) as error:
        reason = error.args[0] if len(error.args) == 1 else None
        outcome = (
            "ASC_IMPORT_UNRESOLVED"
            if attempted or retained
            else (
                reason
                if type(reason) is str and reason in REASONS
                else "ASC_IMPORT_REJECTED"
            )
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                outcome = "ASC_IMPORT_UNRESOLVED"
    return outcome


def check_import(*, google_web):
    return _operate(google_web, execute=False)


def import_key(*, google_web):
    return _operate(google_web, execute=True)
