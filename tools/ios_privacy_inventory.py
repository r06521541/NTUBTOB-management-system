"""Read-only evidence from an unsigned fictional CI app, not a privacy validator.

No signing, network, archive export, subprocesses or filesystem writes. Only
selected metadata is read. Resolution does not prove binary linkage; manifest
shape does not prove Apple acceptance, runtime behavior or legal compliance.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import stat
from pathlib import Path
from typing import Sequence

from tools.artifact_digest import digest_bytes

MAX_ENTRIES = 50_000
MAX_DEPTH = 32
MAX_FILE_BYTES = 1_048_576
MAX_METADATA_BYTES = 8_388_608
MAX_MANIFESTS = 256
MAX_ITEMS = 512
_SHA = re.compile(r"[0-9a-f]{40}")
_VERSION = re.compile(r"[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}")
# Exact public naming hints only; upstream references are in MOBILE_PRIVACY_DRAFT.
# Neither these names nor a matching manifest digest authenticate SDK provenance.
_PUBLIC_PACKAGES = {
    "googlesignin-ios": "google_sign_in",
    "line-sdk-ios-swift": "line_sdk",
    "appauth-ios": "app_auth",
    "gtmappauth": "gtm_app_auth",
    "gtm-session-fetcher": "gtm_session_fetcher",
    "googletoolboxformac": "google_toolbox_for_mac",
    "googleutilities": "google_utilities",
    "promises": "promises",
    "app-check": "app_check",
    "interop-ios-for-google-sdks": "google_interop",
}
_PUBLIC_BUNDLES = {
    "Flutter.framework": "flutter_engine",
    "App.framework": "flutter_application",
    "GoogleSignIn.framework": "google_sign_in",
    "GoogleSignIn_GoogleSignIn.bundle": "google_sign_in",
    "LineSDK.framework": "line_sdk",
    "LineSDK_LineSDK.bundle": "line_sdk",
    "AppAuth_AppAuth.bundle": "app_auth",
    "AppAuth_AppAuthCore.bundle": "app_auth",
    "GTMAppAuth_GTMAppAuth.bundle": "gtm_app_auth",
    "GTMSessionFetcher_GTMSessionFetcher.bundle": "gtm_session_fetcher",
    "GTMSessionFetcher_GTMSessionFetcherCore.bundle": "gtm_session_fetcher",
    "GoogleUtilities_GoogleUtilities-Environment.bundle": "google_utilities",
    "GoogleUtilities_GoogleUtilities-Logger.bundle": "google_utilities",
    "GoogleUtilities_GoogleUtilities-UserDefaults.bundle": "google_utilities",
    "Promises_FBLPromises.bundle": "promises",
    "google_sign_in_ios_google_sign_in_ios.bundle": "google_sign_in_plugin",
    "flutter_secure_storage_darwin_flutter_secure_storage_darwin.bundle": "secure_storage_plugin",
}
_FIELDS = {
    "NSPrivacyTracking": "tracking",
    "NSPrivacyTrackingDomains": "tracking_domains",
    "NSPrivacyCollectedDataTypes": "collected_data",
    "NSPrivacyAccessedAPITypes": "accessed_apis",
}


class InventoryError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class _UniqueDict(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError("duplicate key")
        super().__setitem__(key, value)


def _unique_pairs(pairs):
    result = _UniqueDict()
    for key, value in pairs:
        result[key] = value
    return result


def _linked(metadata) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _check_path(path: Path, *, missing_ok: bool = False) -> bool:
    # Do not resolve first: that would erase evidence of linked ancestors.
    if ".." in path.parts:
        raise InventoryError("PATH_TRAVERSAL_REJECTED")
    absolute = Path(os.path.abspath(path))
    for current in (*reversed(absolute.parents), absolute):
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if missing_ok:
                return False
            raise InventoryError("PATH_UNAVAILABLE") from None
        if _linked(metadata):
            raise InventoryError("LINK_REJECTED")
    return True


def _fingerprint(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_metadata(path: Path, budget: list[int]) -> bytes:
    _check_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise InventoryError("NON_REGULAR_FILE")
    if before.st_size > MAX_FILE_BYTES:
        raise InventoryError("FILE_SIZE_LIMIT")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
            raise InventoryError("INPUT_CHANGED")
        source = stream.read(MAX_FILE_BYTES + 1)
        if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
            raise InventoryError("INPUT_CHANGED")
    if _fingerprint(path.lstat()) != _fingerprint(before):
        raise InventoryError("INPUT_CHANGED")
    if len(source) > MAX_FILE_BYTES:
        raise InventoryError("FILE_SIZE_LIMIT")
    budget[0] += len(source)
    if budget[0] > MAX_METADATA_BYTES:
        raise InventoryError("METADATA_SIZE_LIMIT")
    return source


def _walk_app(app: Path) -> list[Path]:
    pending = [(app, 0)]
    manifests = []
    count = 0
    while pending:
        directory, depth = pending.pop()
        _check_path(directory)
        if depth > MAX_DEPTH:
            raise InventoryError("DEPTH_LIMIT")
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise InventoryError("ENTRY_LIMIT")
                metadata = entry.stat(follow_symlinks=False)
                if _linked(metadata):
                    raise InventoryError("LINK_REJECTED")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append((Path(entry.path), depth + 1))
                elif not stat.S_ISREG(metadata.st_mode):
                    raise InventoryError("NON_REGULAR_FILE")
                elif entry.name.lower().endswith(".xcprivacy"):
                    manifests.append(Path(entry.path))
                    if len(manifests) > MAX_MANIFESTS:
                        raise InventoryError("MANIFEST_LIMIT")
    return sorted(manifests, key=lambda path: path.relative_to(app).as_posix())


def _strings(value) -> bool:
    return (
        type(value) is list
        and len(value) <= MAX_ITEMS
        and all(type(item) is str and 0 < len(item) <= 512 for item in value)
    )


def _field(value, name: str, findings: list[str]) -> dict:
    if name == "tracking":
        if type(value) is bool:
            return {"state": "present", "value": value}
        findings.append("tracking:INVALID_TYPE")
        return {"state": "invalid_type"}
    if type(value) is not list or len(value) > MAX_ITEMS:
        findings.append(name + ":INVALID_TYPE_OR_COUNT")
        return {"state": "invalid_type"}
    row = {"state": "present" if value else "empty", "count": len(value)}
    if name == "tracking_domains":
        if not _strings(value):
            findings.append("tracking_domains:INVALID_ITEM")
            row["state"] = "invalid_type"
        return row
    required = (
        {
            "NSPrivacyAccessedAPIType": str,
            "NSPrivacyAccessedAPITypeReasons": list,
        }
        if name == "accessed_apis"
        else {
            "NSPrivacyCollectedDataType": str,
            "NSPrivacyCollectedDataTypeLinked": bool,
            "NSPrivacyCollectedDataTypeTracking": bool,
            "NSPrivacyCollectedDataTypePurposes": list,
        }
    )
    invalid = 0
    extras = 0
    for item in value:
        if not isinstance(item, dict):
            invalid += 1
            continue
        extras += len(item.keys() - required.keys())
        if any(
            key not in item
            or type(item[key]) is not kind
            or (kind is str and not 0 < len(item[key]) <= 512)
            or (kind is list and not _strings(item[key]))
            for key, kind in required.items()
        ):
            invalid += 1
        elif any(kind is list and not item[key] for key, kind in required.items()):
            findings.append(name + ":EMPTY_REASONS_OR_PURPOSES")
    row.update(invalid_item_count=invalid, unknown_key_count=extras)
    if invalid:
        findings.append(name + ":INVALID_ITEM")
    if extras:
        findings.append(name + ":UNRECOGNIZED_KEYS")
    return row


def _manifest(source: bytes, relative: Path, ordinal: int) -> dict:
    parents = relative.parts[:-1]
    kind = "app_root" if not parents else "other"
    alias = "application" if not parents else "unknown_component"
    for parent in reversed(parents):
        if parent.endswith((".framework", ".bundle")):
            kind = "framework" if parent.endswith(".framework") else "bundle"
            alias = _PUBLIC_BUNDLES.get(parent, "unknown_component")
            break
    row = {
        "ordinal": ordinal,
        "component": alias,
        "location_kind": kind,
        "bytes": len(source),
        "sha256": digest_bytes(source, text=not source.startswith(b"bplist00")),
        "plist_decoded": False,
        "values_validated": False,
        "fields": {},
        "findings": [],
    }
    if alias == "unknown_component":
        row["findings"].append("manifest:UNRECOGNIZED_COMPONENT")
    if relative.name != "PrivacyInfo.xcprivacy":
        row["findings"].append("filename:NOT_STANDARD_NAME")
    try:
        value = plistlib.loads(source, dict_type=_UniqueDict)
        if not isinstance(value, dict):
            raise ValueError
    except Exception:
        row["findings"].append("plist:INVALID_OR_DUPLICATE_KEYS")
        return row
    row["plist_decoded"] = True
    row["unknown_key_count"] = len(value.keys() - _FIELDS.keys())
    if row["unknown_key_count"]:
        row["findings"].append("manifest:UNRECOGNIZED_KEYS")
    for key, name in _FIELDS.items():
        row["fields"][name] = (
            _field(value[key], name, row["findings"])
            if key in value
            else {"state": "absent"}
        )
    if any(key not in value for key in _FIELDS):
        row["findings"].append("manifest:UNDECLARED_KEYS")
    row["findings"] = sorted(set(row["findings"]))
    return row


def _package(source: bytes, slot: int) -> dict:
    row = {
        "slot": slot,
        "state": "invalid_json",
        "sha256": digest_bytes(source, text=True),
        "unknown_identity_count": 0,
        "dependencies": [],
        "findings": [],
    }
    try:
        value = json.loads(source, object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        row["findings"].append("JSON_INVALID_OR_DUPLICATE_KEYS")
        return row
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] not in {2, 3}
    ):
        row["state"] = "unsupported_schema"
        row["findings"].append("SCHEMA_NOT_SUPPORTED")
        return row
    pins = value.get("pins")
    if type(pins) is not list or len(pins) > MAX_ITEMS:
        row["state"] = "invalid_shape"
        row["findings"].append("PINS_INVALID")
        return row
    row["state"] = "parsed"
    seen = set()
    for pin in pins:
        if not isinstance(pin, dict) or type(pin.get("identity")) is not str:
            row["findings"].append("PIN_INVALID")
            continue
        identity = pin["identity"]
        if identity in seen:
            row["findings"].append("DUPLICATE_IDENTITY")
        seen.add(identity)
        alias = _PUBLIC_PACKAGES.get(identity)
        if alias is None:
            row["unknown_identity_count"] += 1
            continue
        state = pin.get("state")
        version = state.get("version") if isinstance(state, dict) else None
        if type(version) is not str or not _VERSION.fullmatch(version):
            version = None
            row["findings"].append("NATIVE_VERSION_UNKNOWN")
        row["dependencies"].append({"component": alias, "version": version})
    if row["unknown_identity_count"]:
        row["findings"].append("UNRECOGNIZED_IDENTITIES")
    row["findings"] = sorted(set(row["findings"]))
    row["dependencies"].sort(
        key=lambda item: (item["component"], item["version"] or "")
    )
    return row


def _result() -> dict:
    return {
        "schema": 1,
        "classification": "STOP",
        "scope": "unsigned_fictional_ci_app",
        "scan_complete": False,
        "source_commit": None,
        "root_manifest": "not_observed",
        "manifests": [],
        "package_sources": [],
        "native_dependencies": [],
        "failure": None,
        "compliance_verified": False,
        "runtime_verified": False,
        "sdk_coverage_verified": False,
        "xcode_privacy_report_verified": False,
        "signature_verified": False,
        "upload_authorized": False,
        "release_authorized": False,
        "next_action": "review_inventory_failure",
    }


def inspect_app(
    app: Path, *, source_commit: str, package_paths: Sequence[Path] = ()
) -> dict:
    result = _result()
    stage, check = "input", "source_commit"
    try:
        if (
            type(source_commit) is not str
            or not _SHA.fullmatch(source_commit)
            or source_commit == "0" * 40
        ):
            raise InventoryError("INVALID_FORMAT")
        result["source_commit"] = source_commit
        check = "package_slots"
        if len(package_paths) > 2:
            raise InventoryError("SLOT_LIMIT")
        stage, check = "application", "root"
        _check_path(app)
        if app.suffix != ".app" or not app.is_dir():
            raise InventoryError("APPLICATION_PATH_REJECTED")
        check = "unsigned_application"
        if any(
            os.path.lexists(app / name)
            for name in ("_CodeSignature", "embedded.mobileprovision")
        ):
            raise InventoryError("SIGNED_INPUT_NOT_SUPPORTED")
        check = "application_info"
        budget = [0]
        try:
            info = plistlib.loads(
                _read_metadata(app / "Info.plist", budget), dict_type=_UniqueDict
            )
        except (ValueError, plistlib.InvalidFileException) as error:
            if isinstance(error, InventoryError):
                raise
            raise InventoryError("PLIST_INVALID") from None
        if (
            not isinstance(info, dict)
            or info.get("CFBundleIdentifier") != "tw.org.ntubtob.portal"
        ):
            raise InventoryError("METADATA_REJECTED")
        stage, check = "scan", "application_tree"
        paths = _walk_app(app)
        result["root_manifest"] = (
            "present" if app / "PrivacyInfo.xcprivacy" in paths else "absent"
        )
        for ordinal, path in enumerate(paths, 1):
            stage, check = "manifest", "metadata_read_" + str(ordinal)
            result["manifests"].append(
                _manifest(_read_metadata(path, budget), path.relative_to(app), ordinal)
            )
        for slot, path in enumerate(package_paths, 1):
            stage, check = "dependencies", "package_slot_" + str(slot)
            if not _check_path(path, missing_ok=True):
                result["package_sources"].append(
                    {"slot": slot, "state": "absent", "findings": ["LOCK_NOT_FOUND"]}
                )
            else:
                result["package_sources"].append(
                    _package(_read_metadata(path, budget), slot)
                )
        combined = {}
        for package in result["package_sources"]:
            for dependency in package.get("dependencies", []):
                row = combined.setdefault(
                    dependency["component"],
                    {"versions": set(), "slots": set(), "unknown": False},
                )
                row["slots"].add(package["slot"])
                if dependency["version"] is None:
                    row["unknown"] = True
                else:
                    row["versions"].add(dependency["version"])
        for component, row in sorted(combined.items()):
            result["native_dependencies"].append(
                {
                    "component": component,
                    "state": (
                        "conflict"
                        if len(row["versions"]) > 1
                        else (
                            "native_version_unknown"
                            if row["unknown"]
                            else "resolved_version"
                        )
                    ),
                    "versions": sorted(row["versions"]),
                    "slots": sorted(row["slots"]),
                }
            )
        has_findings = (
            result["root_manifest"] != "present"
            or not package_paths
            or any(
                row["findings"]
                for row in result["manifests"] + result["package_sources"]
            )
            or any(
                row["state"] != "resolved_version"
                for row in result["native_dependencies"]
            )
        )
        stage, check = "evidence", "summary_digest"
        result["inspected_evidence_sha256"] = digest_bytes(
            json.dumps(
                {
                    "manifests": result["manifests"],
                    "package_sources": result["package_sources"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
            text=True,
        )
        result["classification"] = (
            "INVENTORY_COMPLETE_WITH_FINDINGS" if has_findings else "INVENTORY_COMPLETE"
        )
        result["scan_complete"] = True
        result["next_action"] = "review_declarations_and_unverified_runtime"
    except InventoryError as error:
        result["failure"] = {"stage": stage, "check": check, "reason": error.reason}
    except OSError:
        result["failure"] = {"stage": stage, "check": check, "reason": "READ_FAILED"}
    except Exception:
        result["failure"] = {
            "stage": stage,
            "check": check,
            "reason": "UNEXPECTED_ERROR",
        }
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InventoryError("ARGUMENTS_INVALID")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--packages", type=Path, action="append", default=[])
    try:
        args = parser.parse_args(argv)
        result = inspect_app(
            args.app, source_commit=args.source_commit, package_paths=args.packages
        )
    except InventoryError:
        result = _result()
        result["failure"] = {
            "stage": "input",
            "check": "arguments",
            "reason": "ARGUMENTS_INVALID",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["scan_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
