"""Callable Windows private intake. No CLI, copies, ACL repair or authority.

Caller supplies reviewed metadata. Downloaded key parent directories must already
meet the existing private-directory ACL contract. Python cannot wipe memory or
protect against another process with the same user/administrator authority.
"""

import ctypes as c
import os
import plistlib
import re
from dataclasses import dataclass
from pathlib import Path

from tools import ios_certificate_custody as custody
from tools import ios_certificate_preparation as preparation
from tools import ios_testflight_inputs as inputs
from tools import ios_testflight_signing as signing

PROMPTS = {
    "APPLE_TEAM": "Apple Team ID (10 characters, hidden): ",
    "ASC_KEY_ID": "ASC API key ID (10 characters, hidden): ",
    "ASC_ISSUER": "ASC API issuer ID (UUID, hidden): ",
    "GOOGLE_IOS": "Existing Google iOS client ID (hidden): ",
    "OWNER_EMAIL": "Owner Apple account email (hidden): ",
    "P12_PASSWORD": "P12 password (hidden): ",
    "ASC_PATH": "ASC p8 absolute path (hidden): ",
    "APPLE_LOGIN_PATH": "Apple Login p8 absolute path (hidden): ",
}
REASONS = (
    custody.REASONS
    | inputs.REASONS
    | {
        "CLOSE_UNRESOLVED",
        "INPUT_READ_REJECTED",
        "INPUT_CHECK_REJECTED",
        "PROFILE_CONTAINER_REJECTED",
        "SIGNING_MATERIAL_REJECTED",
    }
    | {field + "_INPUT_REJECTED" for field in PROMPTS}
)


class Rejected(Exception):
    def __init__(self, reason="INPUT_REJECTED"):
        super().__init__(
            reason if type(reason) is str and reason in REASONS else "INPUT_REJECTED"
        )


@dataclass(frozen=True, repr=False)
class Config:
    team: str
    asc_key_id: str
    asc_issuer_id: str
    apple_login_key_id: str
    api_base_url: str
    google_ios_client_id: str
    google_web_client_id: str
    line_channel_id: str
    version: str
    build: int
    asc_path: str = None
    apple_login_path: str = None

    def defines(self):
        return {
            "API_BASE_URL": self.api_base_url,
            "GOOGLE_CLIENT_ID": self.google_ios_client_id,
            "GOOGLE_SERVER_CLIENT_ID": self.google_web_client_id,
            "LINE_CHANNEL_ID": self.line_channel_id,
        }


@dataclass(frozen=True, repr=False)
class AscInput:
    pem: bytes
    material: inputs.AscMaterial


@dataclass(frozen=True, repr=False)
class AppleLoginInput:
    pem: bytes
    material: inputs.AppleLoginMaterial


@dataclass(frozen=True, repr=False)
class Materials:
    signing: dict
    asc: AscInput
    apple_login: AppleLoginInput | None


class IntakeNative(custody.Native):
    """Only file-size parameter differs from reviewed Native.metadata."""

    def metadata(self, handle, path, *, directory=False, limit=65536):
        if limit not in (4096, 65536, 262144):
            raise custody.CustodyError("METADATA_REJECTED")
        info = custody.FileInfo()
        final = c.create_unicode_buffer(32768)
        length = self.final(handle, final, len(final), 0)
        if not length or length >= len(final) or not self.info(handle, c.byref(info)):
            raise custody.CustodyError("METADATA_REJECTED")
        actual = final.value
        if actual.startswith("\\\\?\\"):
            actual = actual[4:]
        if (
            os.path.normcase(actual.rstrip("\\"))
            != os.path.normcase(str(path).rstrip("\\"))
            or self.kind(handle) != 1
            or info.attributes & 0x400
            or bool(info.attributes & 0x10) != directory
        ):
            raise custody.CustodyError("METADATA_REJECTED")
        size = (info.size_high << 32) | info.size_low
        if not directory and (info.links != 1 or not 1 <= size <= limit):
            raise custody.CustodyError("METADATA_REJECTED")
        return (
            info.volume,
            info.index_high,
            info.index_low,
            size,
            info.written.dwHighDateTime,
            info.written.dwLowDateTime,
        )


class Reader:
    def __init__(self, nativefactory=IntakeNative):
        self.native = nativefactory()
        self.handles = []
        self.records = []
        self.directories = set()

    def directory(self, path):
        if path in self.directories:
            return
        if ".." in path.parts:
            raise Rejected("METADATA_REJECTED")
        preparation.safe_directory(path, fresh=False)
        for parent in (*reversed(path.parents), path):
            handle = self.native.open_handle(
                parent, directory=True, ancestor=parent != path
            )
            self.handles.append(handle)
            expected = self.native.metadata(handle, parent, directory=True)
            if parent == path:
                self.native.acl(handle, directory=True)
            self.records.append((handle, parent, expected, True, parent == path, 65536))
        self.directories.add(path)

    def file(self, path, limit):
        if path.parent not in self.directories or limit not in (4096, 65536, 262144):
            raise Rejected()
        handle = self.native.open_handle(path)
        self.handles.append(handle)
        expected = self.native.metadata(handle, path, limit=limit)
        self.native.acl(handle)
        size = expected[3]
        if type(size) is not int or not 1 <= size <= limit:
            raise Rejected("METADATA_REJECTED")
        self.records.append((handle, path, expected, False, True, limit))
        buffer, count = c.create_string_buffer(size), custody.w.DWORD()
        if (
            not self.native.seek(handle, 0, None, 0)
            or not self.native.read(handle, buffer, size, c.byref(count), None)
            or count.value != size
        ):
            raise Rejected("READ_REJECTED")
        if self.native.metadata(handle, path, limit=limit) != expected:
            raise Rejected("INPUT_CHANGED")
        self.native.acl(handle)
        return buffer.raw[:size]

    def verify(self):
        for handle, path, expected, directory, check_acl, limit in self.records:
            if (
                self.native.metadata(handle, path, directory=directory, limit=limit)
                != expected
            ):
                raise Rejected("INPUT_CHANGED")
            if check_acl:
                self.native.acl(handle, directory=directory)

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
            raise Rejected("CLOSE_UNRESOLVED")


def _config(config):
    if type(config) is not Config:
        raise Rejected()
    inputs._identifier(config.team)
    inputs._identifier(config.asc_key_id)
    inputs._identifier(config.apple_login_key_id)
    inputs._issuer(config.asc_issuer_id)
    signing.frame(
        p12=b"placeholder",
        password=b"placeholder",
        profile=b"placeholder",
        certificate_der=b"placeholder",
        team=config.team,
        profile_uuid="00000000-0000-0000-0000-000000000000",
        version=config.version,
        build=config.build,
        build_defines=config.defines(),
    )


def _path(value):
    if (
        type(value) is not str
        or not 1 <= len(value) <= 32767
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise Rejected()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if '"' in value:
        raise Rejected()
    path = Path(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower() != ".p8"
        or ":" in path.name
    ):
        raise Rejected()
    return path


def validate_field(field, value, *, google_web=None):
    """Syntax only: no file/crypto/network access and no secret normalization."""
    if field not in PROMPTS:
        raise Rejected()
    try:
        if (
            type(value) is not str
            or not value
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
        ):
            raise ValueError()
        value.encode("utf-8")
        if field in {"APPLE_TEAM", "ASC_KEY_ID"}:
            inputs._identifier(value)
        elif field == "ASC_ISSUER":
            inputs._issuer(value)
        elif field == "GOOGLE_IOS":
            if (
                value == google_web
                or not re.fullmatch(
                    r"[A-Za-z0-9-]+\.apps\.googleusercontent\.com", value
                )
                or len(value) > 2048
            ):
                raise ValueError()
        elif field == "OWNER_EMAIL":
            if not re.fullmatch(r"[^\s@]{1,128}@[^\s@]{1,128}\.[^\s@]{1,64}", value):
                raise ValueError()
        elif field == "P12_PASSWORD":
            if len(value.encode("utf-8")) > 1024:
                raise ValueError()
        else:
            return _path(value)
        return value
    except (ValueError, UnicodeError, inputs.InputError, Rejected):
        raise Rejected(field + "_INPUT_REJECTED") from None


def read_field(field, *, prompt=preparation.hidden, google_web=None):
    """At most three syntax attempts for this field, before any operation intent."""
    if field not in PROMPTS:
        raise Rejected()
    for remaining in (2, 1, 0):
        try:
            value = prompt(PROMPTS[field])
        except (Exception, KeyboardInterrupt):
            raise Rejected("INPUT_READ_REJECTED") from None
        try:
            return validate_field(field, value, google_web=google_web)
        except Rejected:
            print(
                f"input_rejected field={field} remaining_attempts={remaining}",
                flush=True,
            )
            if not remaining:
                raise


def collect(
    config, *, prompt=preparation.hidden, custodyfactory=None, include_login=True
):
    """Field syntax is repairable; custody/cryptographic failures never retry."""
    reader = None
    try:
        _config(config)
        if type(include_login) is not bool:
            raise Rejected()
        preparation.dependencies()
        root = preparation.local_app_data() / preparation.DIRECTORY
        reader = (custodyfactory or Reader)()
        reader.directory(root)
        password = read_field("P12_PASSWORD", prompt=prompt)
        asc_path = (
            validate_field("ASC_PATH", config.asc_path)
            if config.asc_path is not None
            else read_field("ASC_PATH", prompt=prompt)
        )
        login_path = (
            (
                validate_field("APPLE_LOGIN_PATH", config.apple_login_path)
                if config.apple_login_path is not None
                else read_field("APPLE_LOGIN_PATH", prompt=prompt)
            )
            if include_login
            else None
        )
        if include_login and os.path.normcase(str(asc_path)) == os.path.normcase(
            str(login_path)
        ):
            raise Rejected("KEY_REUSE_REJECTED")
        for parent in dict.fromkeys(
            (asc_path.parent,) + ((login_path.parent,) if include_login else ())
        ):
            reader.directory(parent)
        p12 = reader.file(root / "distribution.p12", 65536)
        certificate = reader.file(root / "distribution.cer", 65536)
        raw_profile = reader.file(root / "distribution.mobileprovision", 262144)
        asc_pem = reader.file(asc_path, 4096)
        login_pem = reader.file(login_path, 4096) if include_login else None
        try:
            decoded = plistlib.loads(signing._profile_container(raw_profile))
        except Exception:
            raise Rejected("PROFILE_CONTAINER_REJECTED") from None
        if (
            type(decoded) is not dict
            or decoded.get("DeveloperCertificates") != [certificate]
            or decoded.get("TeamIdentifier") != [config.team]
        ):
            raise Rejected("PROFILE_REJECTED")
        uuid = decoded.get("UUID")
        material = dict(
            p12=p12,
            password=password.encode("utf-8"),
            profile=raw_profile,
            certificate_der=certificate,
            team=config.team,
            profile_uuid=uuid,
            version=config.version,
            build=config.build,
            build_defines=config.defines(),
        )
        try:
            signing.frame(**material)
            signing._certificate_binding(material)
        except Exception:
            raise Rejected("SIGNING_MATERIAL_REJECTED") from None
        asc = inputs.load_asc_key(
            asc_pem, key_id=config.asc_key_id, issuer_id=config.asc_issuer_id
        )
        login = None
        if include_login:
            login = inputs.load_apple_login_key(
                login_pem,
                key_id=config.apple_login_key_id,
                team=config.team,
                bundle=signing.BUNDLE,
            )
            inputs.validate_distinct_keys(asc, login)
        reader.verify()
        return Materials(
            material,
            AscInput(asc_pem, asc),
            AppleLoginInput(login_pem, login) if include_login else None,
        )
    except (custody.CustodyError, inputs.InputError, Rejected) as error:
        raise Rejected(
            error.args[0] if len(error.args) == 1 else "INPUT_REJECTED"
        ) from None
    except (Exception, KeyboardInterrupt):
        raise Rejected("INPUT_CHECK_REJECTED") from None
    finally:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                raise Rejected("CLOSE_UNRESOLVED") from None


def collect_upload(config):
    """Signing/upload do not require or read the separate Apple Login key."""
    return collect(config, include_login=False)
