from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = re.compile(r"^portal-data-backup-\d{8}T\d{6}Z\.dump$")
MANIFEST_FIELDS = (
    "format_version",
    "purpose",
    "created_at_utc",
    "archive_basename",
    "archive_bytes",
    "sha256",
    "pg_restore_client_major",
    "validation",
)
VALIDATION_FIELDS = ("custom_format", "schema_scope", "listing_verified")
PURPOSE = "portal-data-phase-a-recovery"
SENSITIVE = re.compile(
    r"(?:postgres(?:ql)?://|https?://|password|secret|token|project[_ -]?ref|"
    r"\b(?:host|port|user|role|database|dsn)\b|\b(?:select|insert|update|delete|"
    r"drop|alter|create|grant|revoke|copy)\b)",
    re.IGNORECASE,
)
TOC_LINE = re.compile(
    r"^\d+;\s+\d+\s+\d+\s+(?P<body>.+)$",
    re.IGNORECASE,
)
COMMENT_METADATA = (
    ("blank", re.compile(r"^;$")),
    (
        "archive_created",
        re.compile(r"^; Archive created at \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$"),
    ),
    ("dbname", re.compile(r"^;\s+dbname: [A-Za-z0-9_.-]+$")),
    ("toc_entries", re.compile(r"^;\s+TOC Entries: \d+$")),
    (
        "compression",
        re.compile(r"^;\s+Compression: (?:-?\d+|none|gzip|lz4|zstd)$"),
    ),
    (
        "dump_version",
        re.compile(r"^;\s+Dump Version: \d+(?:\.\d+)+(?:-\d+)?$"),
    ),
    ("format", re.compile(r"^;\s+Format: CUSTOM$")),
    ("integer", re.compile(r"^;\s+Integer: [48] bytes$")),
    ("offset", re.compile(r"^;\s+Offset: [48] bytes$")),
    (
        "source_version",
        re.compile(
            r"^;\s+Dumped from database version: "
            r"\d+[A-Za-z0-9.+~() :_-]{0,120}$"
        ),
    ),
    (
        "client_version",
        re.compile(
            r"^;\s+Dumped by pg_dump version: "
            r"\d+[A-Za-z0-9.+~() :_-]{0,120}$"
        ),
    ),
    ("selected_entries", re.compile(r"^; Selected TOC Entries:$")),
)
REQUIRED_COMMENT_METADATA = {
    "archive_created",
    "dbname",
    "format",
    "source_version",
    "client_version",
    "selected_entries",
}
GLOBAL_OBJECT_TYPES = ("ENCODING", "STDSTRINGS", "SEARCHPATH")
SCHEMA_OBJECT_TYPES = (
    "SEQUENCE OWNED BY",
    "MATERIALIZED VIEW DATA",
    "MATERIALIZED VIEW",
    "DATABASE PROPERTIES",
    "DEFAULT ACL",
    "FK CONSTRAINT",
    "TABLE ATTACH",
    "TABLE DATA",
    "SEQUENCE SET",
    "BLOB COMMENTS",
    "PROCEDURAL LANGUAGE",
    "ROW SECURITY",
    "SECURITY LABEL",
    "FOREIGN TABLE",
    "TEXT SEARCH CONFIGURATION",
    "TEXT SEARCH DICTIONARY",
    "TEXT SEARCH PARSER",
    "TEXT SEARCH TEMPLATE",
    "ACCESS METHOD",
    "AGGREGATE",
    "ATTRDEF",
    "CAST",
    "COLLATION",
    "COMMENT",
    "CONSTRAINT",
    "CONVERSION",
    "DEFAULT",
    "DOMAIN",
    "DUMMY TYPE",
    "EVENT TRIGGER",
    "EXTENSION",
    "FUNCTION",
    "INDEX ATTACH",
    "INDEX",
    "OPERATOR CLASS",
    "OPERATOR FAMILY",
    "OPERATOR",
    "POLICY",
    "PROCEDURE",
    "PUBLICATION TABLE",
    "PUBLICATION",
    "RULE",
    "SCHEMA",
    "SEQUENCE",
    "SERVER",
    "STATISTICS",
    "TABLE",
    "TRANSFORM",
    "TRIGGER",
    "TS CONFIGURATION",
    "TS DICTIONARY",
    "TS PARSER",
    "TS TEMPLATE",
    "TYPE",
    "USER MAPPING",
    "VIEW",
    "ACL",
)


class BackupArtifactError(RuntimeError):
    pass


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _reject_unsafe_path(path: Path, *, must_exist: bool) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise BackupArtifactError("artifact paths must be absolute without traversal")
    raw_probe = path
    while True:
        if raw_probe.is_symlink() or (
            os.path.lexists(raw_probe) and _is_reparse_point(raw_probe)
        ):
            raise BackupArtifactError("symlink or reparse-point paths are forbidden")
        if raw_probe.parent == raw_probe:
            break
        raw_probe = raw_probe.parent
    candidate = path.resolve(strict=must_exist)
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise BackupArtifactError("backup artifacts must remain outside the repository")

    probe = candidate if must_exist else candidate.parent
    while True:
        if probe.is_symlink() or _is_reparse_point(probe):
            raise BackupArtifactError("symlink or reparse-point paths are forbidden")
        if probe.parent == probe:
            break
        probe = probe.parent
    if must_exist:
        if not candidate.is_file():
            raise BackupArtifactError("artifact must be a regular file")
    elif not candidate.parent.is_dir():
        raise BackupArtifactError("artifact parent must be an existing directory")
    return candidate


def _paths(
    archive: Path, manifest: Path, checksum: Path, *, creating: bool
) -> tuple[Path, Path, Path]:
    archive = _reject_unsafe_path(archive, must_exist=True)
    manifest = _reject_unsafe_path(manifest, must_exist=not creating)
    checksum = _reject_unsafe_path(checksum, must_exist=not creating)
    if not ARCHIVE_NAME.fullmatch(archive.name):
        raise BackupArtifactError(
            "archive filename does not match the fixed UTC naming contract"
        )
    stem = archive.name.removesuffix(".dump")
    if (
        manifest.name != f"{stem}.manifest.json"
        or checksum.name != f"{stem}.sha256"
    ):
        raise BackupArtifactError(
            "manifest and checksum filenames must match the archive"
        )
    if creating and (manifest.exists() or checksum.exists()):
        raise BackupArtifactError("refusing to overwrite an existing output")
    if archive.stat().st_size <= 0:
        raise BackupArtifactError("archive must be non-empty")
    return archive, manifest, checksum


def validate_planned_paths(archive: Path, manifest: Path, checksum: Path) -> None:
    archive = _reject_unsafe_path(archive, must_exist=False)
    manifest = _reject_unsafe_path(manifest, must_exist=False)
    checksum = _reject_unsafe_path(checksum, must_exist=False)
    if not ARCHIVE_NAME.fullmatch(archive.name):
        raise BackupArtifactError(
            "archive filename does not match the fixed UTC naming contract"
        )
    stem = archive.name.removesuffix(".dump")
    if (
        manifest.name != f"{stem}.manifest.json"
        or checksum.name != f"{stem}.sha256"
    ):
        raise BackupArtifactError(
            "manifest and checksum filenames must match the archive"
        )
    if any(path.exists() for path in (archive, manifest, checksum)):
        raise BackupArtifactError("refusing to use an existing planned output")


def _run_pg_restore(args: Sequence[str], timeout: int = 30) -> str:
    executable = shutil.which("pg_restore")
    if not executable:
        raise BackupArtifactError("pg_restore is unavailable")
    safe_env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR"}
    }
    try:
        completed = subprocess.run(
            [executable, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=safe_env,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        raise BackupArtifactError("pg_restore inspection timed out") from error
    except OSError as error:
        raise BackupArtifactError("pg_restore inspection could not start") from error
    if completed.returncode != 0:
        raise BackupArtifactError("pg_restore inspection failed")
    return completed.stdout


def _client_major(run: Callable[[Sequence[str], int], str]) -> int:
    output = run(("--version",), 10)
    match = re.fullmatch(r"pg_restore \(PostgreSQL\) (\d+)(?:\.\d+)*\s*", output)
    if not match:
        raise BackupArtifactError("pg_restore version output is invalid")
    return int(match.group(1))


def _validate_listing(listing: str) -> None:
    if "\x00" in listing or "\r" in listing:
        raise BackupArtifactError(
            "archive listing failed the sanitized-content contract"
        )
    comment_metadata: set[str] = set()
    found_schema_object = False
    for line in listing.splitlines():
        if not line:
            continue
        if line.startswith(";"):
            metadata = next(
                (name for name, pattern in COMMENT_METADATA if pattern.fullmatch(line)),
                None,
            )
            if metadata is None:
                raise BackupArtifactError(
                    "archive listing contains unsupported comment metadata"
                )
            if metadata != "blank" and metadata in comment_metadata:
                raise BackupArtifactError(
                    "archive listing contains duplicate comment metadata"
                )
            comment_metadata.add(metadata)
            continue
        if SENSITIVE.search(line):
            raise BackupArtifactError(
                "archive TOC failed the sanitized-content contract"
            )
        match = TOC_LINE.fullmatch(line)
        if not match:
            raise BackupArtifactError("archive listing contains an invalid TOC line")
        body = match.group("body")
        object_type = next(
            (
                candidate
                for candidate in (*GLOBAL_OBJECT_TYPES, *SCHEMA_OBJECT_TYPES)
                if body.upper().startswith(f"{candidate} ")
            ),
            None,
        )
        if object_type is None:
            raise BackupArtifactError(
                "archive listing contains an unsupported object type"
            )
        schema = body[len(object_type) :].lstrip().split(maxsplit=1)[0]
        if object_type in GLOBAL_OBJECT_TYPES:
            if schema != "-":
                raise BackupArtifactError(
                    "global archive metadata has an invalid namespace"
                )
        elif object_type == "SCHEMA":
            if schema != "-" or " ntubtob " not in f" {body} ":
                raise BackupArtifactError(
                    "archive listing contains an unapproved schema"
                )
            found_schema_object = True
        elif schema != "ntubtob":
            raise BackupArtifactError("archive listing contains an unapproved schema")
        else:
            found_schema_object = True
    if not found_schema_object:
        raise BackupArtifactError("archive listing contains no ntubtob schema objects")
    if not REQUIRED_COMMENT_METADATA <= comment_metadata:
        raise BackupArtifactError("archive listing comment metadata is incomplete")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(
    archive: Path, listing: str, client_major: int, now: datetime
) -> dict[str, object]:
    _validate_listing(listing)
    if now.tzinfo is None:
        raise BackupArtifactError("manifest timestamp must be timezone-aware")
    return {
        "format_version": 1,
        "purpose": PURPOSE,
        "created_at_utc": now.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "archive_basename": archive.name,
        "archive_bytes": archive.stat().st_size,
        "sha256": _digest(archive),
        "pg_restore_client_major": client_major,
        "validation": {
            "custom_format": True,
            "schema_scope": "ntubtob",
            "listing_verified": True,
        },
    }


def create_evidence(
    archive_path: Path,
    manifest_path: Path,
    checksum_path: Path,
    *,
    run: Callable[[Sequence[str], int], str] = _run_pg_restore,
    now: datetime | None = None,
) -> None:
    archive, manifest_path, checksum_path = _paths(
        archive_path, manifest_path, checksum_path, creating=True
    )
    listing = run(("--list", os.fspath(archive)), 30)
    manifest = _manifest(
        archive,
        listing,
        _client_major(run),
        now or datetime.now(timezone.utc),
    )
    checksum_text = f"{manifest['sha256']}  {archive.name}\n"
    with checksum_path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(checksum_text)
    with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=True)
        stream.write("\n")


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BackupArtifactError("manifest is unreadable or invalid") from error
    if not isinstance(value, dict) or tuple(value.keys()) != MANIFEST_FIELDS:
        raise BackupArtifactError("manifest fields do not match the fixed contract")
    validation = value.get("validation")
    if (
        not isinstance(validation, dict)
        or tuple(validation.keys()) != VALIDATION_FIELDS
    ):
        raise BackupArtifactError(
            "manifest validation fields do not match the fixed contract"
        )
    if any(SENSITIVE.search(item) for item in _string_values(value)):
        raise BackupArtifactError("manifest contains sensitive-looking content")
    if type(value.get("format_version")) is not int:
        raise BackupArtifactError("manifest format version type is invalid")
    if type(value.get("archive_bytes")) is not int:
        raise BackupArtifactError("manifest archive size type is invalid")
    if type(value.get("pg_restore_client_major")) is not int:
        raise BackupArtifactError("manifest client major type is invalid")
    return value


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(_string_values(child))
        return result
    return []


def verify_evidence(
    archive_path: Path,
    manifest_path: Path,
    checksum_path: Path,
    *,
    run: Callable[[Sequence[str], int], str] = _run_pg_restore,
) -> None:
    archive, manifest_path, checksum_path = _paths(
        archive_path, manifest_path, checksum_path, creating=False
    )
    listing = run(("--list", os.fspath(archive)), 30)
    _validate_listing(listing)
    manifest = _read_manifest(manifest_path)
    digest = _digest(archive)
    expected_manifest = {
        "format_version": 1,
        "purpose": PURPOSE,
        "archive_basename": archive.name,
        "archive_bytes": archive.stat().st_size,
        "sha256": digest,
        "validation": {
            "custom_format": True,
            "schema_scope": "ntubtob",
            "listing_verified": True,
        },
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise BackupArtifactError("manifest does not match the archive contract")
    if manifest["pg_restore_client_major"] <= 0:
        raise BackupArtifactError("manifest client major is invalid")
    if manifest["pg_restore_client_major"] != _client_major(run):
        raise BackupArtifactError("pg_restore client major differs from the manifest")
    timestamp = manifest.get("created_at_utc")
    if not isinstance(timestamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", timestamp
    ):
        raise BackupArtifactError("manifest timestamp is invalid")
    try:
        checksum_text = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise BackupArtifactError(
            "checksum sidecar is unreadable or invalid"
        ) from error
    if checksum_text != f"{digest}  {archive.name}\n":
        raise BackupArtifactError("checksum sidecar does not match the archive")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify local-only sanitized logical-backup evidence."
    )
    parser.add_argument("action", choices=("preflight", "create", "verify"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("checksum", type=Path)
    args = parser.parse_args()
    if args.action == "preflight":
        validate_planned_paths(args.archive, args.manifest, args.checksum)
        print("logical-backup output paths verified outside the repository")
    elif args.action == "create":
        create_evidence(args.archive, args.manifest, args.checksum)
        print("logical-backup evidence created outside the repository")
    else:
        verify_evidence(args.archive, args.manifest, args.checksum)
        print("logical-backup evidence verified")


if __name__ == "__main__":
    main()
