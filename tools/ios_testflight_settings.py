"""Owner-editable metadata only, never a secret cache or execution authority.

The fixed JSON lives in existing private KnownFolder custody, not the repository.
Only the empty template is written by this module; filled values are never echoed.
"""

import ctypes as c
import json

from tools import ios_certificate_custody as custody
from tools import ios_certificate_preparation as preparation
from tools import ios_testflight_intake as intake
from tools import ios_testflight_wire as wire

FILENAME = "testflight-inputs.json"
FIELDS = {
    "apple_team_id": "APPLE_TEAM",
    "asc_key_id": "ASC_KEY_ID",
    "asc_issuer_id": "ASC_ISSUER",
    "google_ios_client_id": "GOOGLE_IOS",
    "owner_email": "OWNER_EMAIL",
    "asc_p8_path": "ASC_PATH",
}
TEMPLATE = (json.dumps(dict.fromkeys(FIELDS, ""), indent=2) + "\n").encode("ascii")
REASONS = intake.REASONS | {
    "SETTINGS_READY",
    "SETTINGS_TEMPLATE_CREATED",
    "SETTINGS_JSON_REJECTED",
    "SETTINGS_FIELDS_REJECTED",
    "SETTINGS_WRITE_REJECTED",
}


class Rejected(Exception):
    def __init__(self, reason="SETTINGS_JSON_REJECTED"):
        super().__init__(
            reason
            if type(reason) is str and reason in REASONS
            else "SETTINGS_JSON_REJECTED"
        )


def parse(raw, *, google_web):
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
            raise ValueError()
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=wire._unique)
        if type(value) is not dict or set(value) != set(FIELDS):
            raise ValueError()
    except Exception:
        raise Rejected() from None
    result, invalid = {}, False
    for key, field in FIELDS.items():
        try:
            result[key] = str(
                intake.validate_field(field, value[key], google_web=google_web)
            )
        except intake.Rejected:
            invalid = True
            print(f"settings_rejected field={field}", flush=True)
    if invalid:
        raise Rejected("SETTINGS_FIELDS_REJECTED")
    return result


def _close(reader):
    if reader is not None:
        try:
            reader.close()
        except Exception:
            raise Rejected("CLOSE_UNRESOLVED") from None


def load(*, google_web, reader_factory=intake.Reader):
    reader = None
    try:
        root = preparation.local_app_data() / preparation.DIRECTORY
        reader = reader_factory()
        reader.directory(root)
        raw = reader.file(root / FILENAME, 65536)
        reader.verify()
        return parse(raw, google_web=google_web)
    except (custody.CustodyError, intake.Rejected) as error:
        raise Rejected(
            error.args[0] if len(error.args) == 1 else "SETTINGS_JSON_REJECTED"
        ) from None
    except Rejected:
        raise
    except (Exception, KeyboardInterrupt):
        raise Rejected() from None
    finally:
        _close(reader)


def prepare(*, reader_factory=intake.Reader):
    """Create exactly one empty template with CREATE_NEW + protected Owner ACL."""
    reader = None
    try:
        root = preparation.local_app_data() / preparation.DIRECTORY
        reader = reader_factory()
        reader.directory(root)
        path = root / FILENAME
        native = reader.native
        handle = native.open_handle(path, create=True)
        reader.handles.append(handle)
        expected = custody.Native.metadata(native, handle, path, allow_empty=True)
        native.acl(handle)
        count = custody.w.DWORD()
        if (
            not native.write(
                handle,
                c.create_string_buffer(TEMPLATE),
                len(TEMPLATE),
                c.byref(count),
                None,
            )
            or count.value != len(TEMPLATE)
            or not native.flush(handle)
        ):
            raise Rejected("SETTINGS_WRITE_REJECTED")
        after = native.metadata(handle, path, limit=65536)
        if after[:3] != expected[:3] or after[3] != len(TEMPLATE):
            raise Rejected("SETTINGS_WRITE_REJECTED")
        buffer = c.create_string_buffer(len(TEMPLATE))
        if (
            not native.seek(handle, 0, None, 0)
            or not native.read(handle, buffer, len(TEMPLATE), c.byref(count), None)
            or count.value != len(TEMPLATE)
            or buffer.raw != TEMPLATE
            or native.metadata(handle, path, limit=65536) != after
        ):
            raise Rejected("SETTINGS_WRITE_REJECTED")
        native.acl(handle)
        for dh, dp, before, directory, private, limit in reader.records:
            # Expected parent mtime changes on creation; retain identity/path/type.
            if (
                native.metadata(dh, dp, directory=directory, limit=limit)[:3]
                != before[:3]
            ):
                raise Rejected("INPUT_CHANGED")
            if private:
                native.acl(dh, directory=True)
    except (custody.CustodyError, intake.Rejected) as error:
        raise Rejected(
            error.args[0] if len(error.args) == 1 else "SETTINGS_WRITE_REJECTED"
        ) from None
    except Rejected:
        raise
    except (Exception, KeyboardInterrupt):
        raise Rejected("SETTINGS_WRITE_REJECTED") from None
    finally:
        _close(reader)
