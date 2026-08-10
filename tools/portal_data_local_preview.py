"""Validate, pseudonymize, and import a private local Portal preview bundle.

This operator never connects to a source database.  Export execution remains an
Owner action performed from the reviewed SQL contract.  Errors intentionally
name only contract fields and never include row values or connection strings.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from shared_module.portal_data.local_database import require_local_database_url
from shared_module.portal_data.models import (
    AuthIdentityRecord,
    LegacyAttendanceReplyTypeRecord,
    LegacyGameAttendanceReplyRecord,
    LegacyGameRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

BUNDLE_SCHEMA = "ntubtob-portal-preview-v1"
REQUIRED_REVISION = "0004_phase_c_identity_lifecycle"
TABLE_ORDER = (
    "people",
    "members",
    "games",
    "auth_identities",
    "person_qualifications",
    "game_attendance_replies",
)
ROW_LIMITS = {
    "people": 5_000,
    "members": 5_000,
    "games": 2_000,
    "auth_identities": 7_500,
    "person_qualifications": 10_000,
    "game_attendance_replies": 100_000,
}
FIELDS = {
    "people": {
        "id",
        "display_name",
        "formal_name",
        "portal_access_level",
        "portal_status",
        "version",
        "created_at",
        "updated_at",
    },
    "members": {
        "id",
        "name",
        "enroll_year",
        "major",
        "number",
        "positions",
        "person_id",
    },
    "games": {
        "id",
        "year",
        "season",
        "start_datetime",
        "duration",
        "location",
        "home_team",
        "away_team",
        "invitation_time",
        "cancellation_time",
        "cancellation_announcement_time",
    },
    "auth_identities": {
        "id",
        "provider",
        "person_id",
        "status",
        "created_at",
        "updated_at",
    },
    "person_qualifications": {
        "id",
        "person_id",
        "qualification",
        "status",
        "valid_from",
        "valid_until",
        "created_at",
        "updated_at",
    },
    "game_attendance_replies": {
        "id",
        "game_id",
        "member_id",
        "person_id",
        "reply",
        "updated_at",
    },
}
DERIVED_EXTRA_FIELDS = {"auth_identities": {"provider_subject"}}
MANIFEST_FIELDS = {"schema", "revision", "kind", "anchor_date", "files"}
FILE_MANIFEST_FIELDS = {"filename", "sha256", "rows"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class PreviewBundleError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise PreviewBundleError(message)


def _require_private_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == REPOSITORY_ROOT or resolved.is_relative_to(REPOSITORY_ROOT):
        _fail("private preview artifacts must remain outside the repository")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _datetime(value: object, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _fail(f"{field} must be a timezone-aware datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(f"{field} must be a timezone-aware datetime")
    if parsed.tzinfo is None:
        _fail(f"{field} must be a timezone-aware datetime")
    return parsed


def _integer(value: object, field: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{field} must be an integer")
    return value


def _text(
    value: object, field: str, *, nullable: bool = False, maximum: int = 1_000
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail(f"{field} must be bounded text")
    return value


def _validate_row(table: str, row: object, kind: str) -> dict:
    if not isinstance(row, dict):
        _fail(f"{table} row must be an object")
    expected = FIELDS[table] | (
        DERIVED_EXTRA_FIELDS.get(table, set()) if kind == "derived" else set()
    )
    if set(row) != expected:
        _fail(f"{table} fields do not match the fixed contract")
    for field in expected:
        if field.endswith("_at") or field in {
            "start_datetime",
            "invitation_time",
            "cancellation_time",
            "cancellation_announcement_time",
            "valid_from",
            "valid_until",
        }:
            _datetime(
                row[field],
                f"{table}.{field}",
                nullable=field not in {"created_at", "updated_at"},
            )
    _integer(row["id"], f"{table}.id")
    if row["id"] <= 0:
        _fail(f"{table}.id must be positive")

    if table == "people":
        _text(row["display_name"], "people.display_name", maximum=120)
        _text(row["formal_name"], "people.formal_name", nullable=True, maximum=120)
        if row["portal_access_level"] not in {"basic", "officer", "admin"}:
            _fail("people.portal_access_level is invalid")
        if row["portal_status"] not in {
            "pending",
            "active",
            "disabled",
            "inactive",
            "blocked",
        }:
            _fail("people.portal_status is invalid")
        _integer(row["version"], "people.version")
    elif table == "members":
        _text(row["name"], "members.name")
        for field in ("enroll_year", "number", "person_id"):
            _integer(row[field], f"members.{field}", nullable=True)
        _text(row["major"], "members.major", nullable=True)
        _text(row["positions"], "members.positions", nullable=True)
    elif table == "games":
        for field in ("year", "season", "duration"):
            _integer(row[field], f"games.{field}", nullable=True)
        for field in ("location", "home_team", "away_team"):
            _text(row[field], f"games.{field}", nullable=True)
    elif table == "auth_identities":
        if row["provider"] not in {"line", "google", "apple"}:
            _fail("auth_identities.provider is invalid")
        _integer(row["person_id"], "auth_identities.person_id", nullable=True)
        if row["status"] not in {"pending", "linked", "disabled", "blocked"}:
            _fail("auth_identities.status is invalid")
        if row["status"] == "pending" and row["person_id"] is not None:
            _fail("auth_identities link state is invalid")
        if row["status"] == "linked" and row["person_id"] is None:
            _fail("auth_identities link state is invalid")
        if kind == "derived":
            _text(
                row["provider_subject"], "auth_identities.provider_subject", maximum=255
            )
    elif table == "person_qualifications":
        _integer(row["person_id"], "person_qualifications.person_id")
        if row["qualification"] not in {
            "team_player",
            "guest_player",
            "affiliate",
            "staff",
        }:
            _fail("person_qualifications.qualification is invalid")
        if row["status"] not in {"active", "revoked"}:
            _fail("person_qualifications.status is invalid")
        valid_from = _datetime(
            row["valid_from"], "person_qualifications.valid_from", nullable=True
        )
        valid_until = _datetime(
            row["valid_until"], "person_qualifications.valid_until", nullable=True
        )
        if (
            valid_from is not None
            and valid_until is not None
            and valid_until <= valid_from
        ):
            _fail("person_qualifications validity is invalid")
        if row["qualification"] == "guest_player" and (
            valid_from is None
            or valid_until is None
            or (valid_until - valid_from).days > 5 * 366
        ):
            _fail("person_qualifications guest validity is invalid")
    else:
        for field in ("game_id", "member_id", "person_id"):
            _integer(
                row[field],
                f"game_attendance_replies.{field}",
                nullable=field != "game_id",
            )
        reply = _integer(row["reply"], "game_attendance_replies.reply")
        if reply not in {1, 2, 3, 4, 5}:
            _fail("game_attendance_replies.reply is invalid")
    return row


def _read_rows(path: Path, table: str, kind: str) -> list[dict]:
    rows = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    _fail(f"{table} contains an empty record")
                if line_number > ROW_LIMITS[table]:
                    _fail(f"{table} exceeds its row limit")
                try:
                    value = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    _fail(f"{table} contains invalid JSONL")
                rows.append(_validate_row(table, value, kind))
    except OSError:
        _fail(f"{table} file is not readable")
    return rows


def _validate_relationships(rows: Mapping[str, list[dict]]) -> None:
    ids = {
        table: {row["id"] for row in table_rows} for table, table_rows in rows.items()
    }
    if any(len(ids[table]) != len(rows[table]) for table in TABLE_ORDER):
        _fail("bundle contains duplicate primary keys")
    person_ids, member_ids, game_ids = ids["people"], ids["members"], ids["games"]
    for row in rows["members"]:
        if row["person_id"] is not None and row["person_id"] not in person_ids:
            _fail("members contains an unknown person reference")
    if len(
        [row["person_id"] for row in rows["members"] if row["person_id"] is not None]
    ) != len(
        {row["person_id"] for row in rows["members"] if row["person_id"] is not None}
    ):
        _fail("members contains duplicate person links")
    for table in ("auth_identities", "person_qualifications"):
        for row in rows[table]:
            if row["person_id"] is not None and row["person_id"] not in person_ids:
                _fail(f"{table} contains an unknown person reference")
    for row in rows["game_attendance_replies"]:
        if row["game_id"] not in game_ids:
            _fail("game_attendance_replies contains an unknown game reference")
        if row["member_id"] is not None and row["member_id"] not in member_ids:
            _fail("game_attendance_replies contains an unknown member reference")
        if row["person_id"] is not None and row["person_id"] not in person_ids:
            _fail("game_attendance_replies contains an unknown person reference")


def validate_bundle(directory: Path, expected_kind: str) -> dict[str, list[dict]]:
    directory = _require_private_path(directory)
    manifest_path = directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("bundle manifest is unreadable or invalid")
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        _fail("bundle manifest fields do not match the fixed contract")
    if manifest["schema"] != BUNDLE_SCHEMA or manifest["revision"] != REQUIRED_REVISION:
        _fail("bundle schema or revision is unsupported")
    if manifest["kind"] != expected_kind or expected_kind not in {"raw", "derived"}:
        _fail("bundle kind is unsupported")
    if (expected_kind == "raw" and manifest["anchor_date"] is not None) or (
        expected_kind == "derived" and not isinstance(manifest["anchor_date"], str)
    ):
        _fail("bundle anchor date is invalid")
    if expected_kind == "derived":
        try:
            date.fromisoformat(manifest["anchor_date"])
        except ValueError:
            _fail("bundle anchor date is invalid")
    if not isinstance(manifest["files"], dict) or set(manifest["files"]) != set(
        TABLE_ORDER
    ):
        _fail("bundle table set does not match the fixed contract")
    expected_names = {"manifest.json", *(f"{table}.jsonl" for table in TABLE_ORDER)}
    try:
        actual_names = {path.name for path in directory.iterdir() if path.is_file()}
    except OSError:
        _fail("bundle directory is unreadable")
    if actual_names != expected_names:
        _fail("bundle directory contains an unknown or missing file")

    all_rows = {}
    for table in TABLE_ORDER:
        item = manifest["files"][table]
        if not isinstance(item, dict) or set(item) != FILE_MANIFEST_FIELDS:
            _fail(f"{table} manifest entry is invalid")
        filename = f"{table}.jsonl"
        if (
            item["filename"] != filename
            or not isinstance(item["sha256"], str)
            or len(item["sha256"]) != 64
        ):
            _fail(f"{table} manifest entry is invalid")
        path = directory / filename
        if not hmac.compare_digest(_sha256(path), item["sha256"]):
            _fail(f"{table} checksum does not match")
        rows = _read_rows(path, table, expected_kind)
        if isinstance(item["rows"], bool) or item["rows"] != len(rows):
            _fail(f"{table} row count does not match")
        all_rows[table] = rows
    _validate_relationships(all_rows)
    return all_rows


def seal_raw_bundle(directory: Path) -> None:
    directory = _require_private_path(directory)
    if (directory / "manifest.json").exists():
        _fail("bundle manifest already exists")
    expected = {f"{table}.jsonl" for table in TABLE_ORDER}
    if {path.name for path in directory.iterdir() if path.is_file()} != expected:
        _fail("raw bundle files do not match the fixed contract")
    files = {}
    rows = {}
    for table in TABLE_ORDER:
        path = directory / f"{table}.jsonl"
        table_rows = _read_rows(path, table, "raw")
        files[table] = {
            "filename": path.name,
            "sha256": _sha256(path),
            "rows": len(table_rows),
        }
        rows[table] = table_rows
    _validate_relationships(rows)
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "revision": REQUIRED_REVISION,
        "kind": "raw",
        "anchor_date": None,
        "files": files,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _surrogate(seed: bytes, category: str, value: object) -> str:
    return hmac.new(seed, f"{category}:{value}".encode(), hashlib.sha256).hexdigest()[
        :16
    ]


def _id_maps(rows: Mapping[str, list[dict]], seed: bytes) -> dict[str, dict[int, int]]:
    result = {}
    used = set()
    for table in TABLE_ORDER:
        mapping = {}
        for row in sorted(rows[table], key=lambda item: item["id"]):
            candidate = (
                int(_surrogate(seed, table, row["id"]), 16) % 8_000_000_000_000 + 1
            )
            while candidate in used:
                candidate += 1
            used.add(candidate)
            mapping[row["id"]] = candidate
        result[table] = mapping
    return result


def pseudonymize_bundle(
    source: Path, destination: Path, seed: bytes, anchor: date
) -> None:
    if len(seed) < 32:
        _fail("pseudonymization seed must contain at least 32 bytes")
    rows = validate_bundle(source, "raw")
    destination = _require_private_path(destination)
    if destination.exists():
        _fail("derived bundle destination already exists")
    destination.mkdir(parents=False)
    maps = _id_maps(rows, seed)
    game_starts = [
        _datetime(row["start_datetime"], "games.start_datetime", nullable=True)
        for row in rows["games"]
    ]
    dated_games = [value for value in game_starts if value is not None]
    all_timestamps = []
    for table_rows in rows.values():
        for row in table_rows:
            for field, value in row.items():
                if value is not None and (
                    field.endswith("_at")
                    or field
                    in {
                        "start_datetime",
                        "invitation_time",
                        "cancellation_time",
                        "cancellation_announcement_time",
                        "valid_from",
                        "valid_until",
                    }
                ):
                    all_timestamps.append(_datetime(value, f"bundle.{field}"))
    shift = None
    first = min(dated_games or all_timestamps, default=None)
    if first is not None:
        target = datetime.combine(anchor, time(hour=10), tzinfo=first.tzinfo)
        shift = target - first
    enrollment_shift = int(_surrogate(seed, "enroll-year", "v1")[:2], 16) % 11 + 7

    def shifted(value: object) -> object:
        parsed = _datetime(value, "datetime", nullable=True)
        return (
            (parsed + shift).isoformat()
            if parsed is not None and shift is not None
            else value
        )

    derived = {table: [] for table in TABLE_ORDER}
    for row in rows["people"]:
        token = _surrogate(seed, "person-name", row["id"])[-6:]
        derived["people"].append(
            {
                **row,
                "id": maps["people"][row["id"]],
                "display_name": f"預覽成員 {token}",
                "formal_name": (
                    f"預覽姓名 {token}" if row["formal_name"] is not None else None
                ),
                "created_at": shifted(row["created_at"]),
                "updated_at": shifted(row["updated_at"]),
            }
        )
    for row in rows["members"]:
        linked_person_id = row["person_id"]
        token = _surrogate(
            seed,
            "person-name" if linked_person_id is not None else "member-name",
            linked_person_id if linked_person_id is not None else row["id"],
        )[-6:]
        derived["members"].append(
            {
                **row,
                "id": maps["members"][row["id"]],
                "name": (
                    f"預覽姓名 {token}"
                    if linked_person_id is not None
                    else f"預覽球員 {token}"
                ),
                "enroll_year": (
                    row["enroll_year"] + enrollment_shift
                    if row["enroll_year"] is not None
                    else None
                ),
                "major": f"預覽系所 {token}" if row["major"] is not None else None,
                "person_id": maps["people"].get(linked_person_id),
            }
        )
    for row in rows["games"]:
        token = _surrogate(seed, "game", row["id"])[-6:]
        updated = {
            **row,
            "id": maps["games"][row["id"]],
            "location": f"預覽球場 {token}" if row["location"] is not None else None,
            "home_team": f"預覽主隊 {token}" if row["home_team"] is not None else None,
            "away_team": f"預覽客隊 {token}" if row["away_team"] is not None else None,
        }
        for field in (
            "start_datetime",
            "invitation_time",
            "cancellation_time",
            "cancellation_announcement_time",
        ):
            updated[field] = shifted(row[field])
        if updated["start_datetime"] is not None:
            updated["year"] = _datetime(
                updated["start_datetime"], "games.start_datetime"
            ).year
        derived["games"].append(updated)
    for row in rows["auth_identities"]:
        derived["auth_identities"].append(
            {
                **row,
                "id": maps["auth_identities"][row["id"]],
                "person_id": maps["people"].get(row["person_id"]),
                "provider_subject": f"local-preview-{_surrogate(seed, 'identity', row['id'])}",
                "created_at": shifted(row["created_at"]),
                "updated_at": shifted(row["updated_at"]),
            }
        )
    for row in rows["person_qualifications"]:
        updated = {
            **row,
            "id": maps["person_qualifications"][row["id"]],
            "person_id": maps["people"][row["person_id"]],
        }
        for field in ("valid_from", "valid_until", "created_at", "updated_at"):
            updated[field] = shifted(row[field])
        derived["person_qualifications"].append(updated)
    for row in rows["game_attendance_replies"]:
        derived["game_attendance_replies"].append(
            {
                **row,
                "id": maps["game_attendance_replies"][row["id"]],
                "game_id": maps["games"][row["game_id"]],
                "member_id": maps["members"].get(row["member_id"]),
                "person_id": maps["people"].get(row["person_id"]),
                "updated_at": shifted(row["updated_at"]),
            }
        )

    files = {}
    for table in TABLE_ORDER:
        path = destination / f"{table}.jsonl"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            for row in derived[table]:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        files[table] = {
            "filename": path.name,
            "sha256": _sha256(path),
            "rows": len(derived[table]),
        }
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "revision": REQUIRED_REVISION,
        "kind": "derived",
        "anchor_date": anchor.isoformat(),
        "files": files,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_bundle(destination, "derived")


MODEL_BY_TABLE = {
    "people": PersonRecord,
    "members": LegacyMemberRecord,
    "games": LegacyGameRecord,
    "auth_identities": AuthIdentityRecord,
    "person_qualifications": PersonQualificationRecord,
    "game_attendance_replies": LegacyGameAttendanceReplyRecord,
}
ATTENDANCE_REPLY_TYPES = {
    1: "attending",
    2: "not attending",
    3: "tentative",
    4: "late",
    5: "unanswered",
}
LOCAL_FIXTURE_REPLY_IDS = {9101, 9102, 9103}


def _database_rows(table: str, rows: Iterable[dict]) -> list[dict]:
    result = []
    for row in rows:
        item = dict(row)
        for field, value in tuple(item.items()):
            if field.endswith("_at") or field in {
                "start_datetime",
                "invitation_time",
                "cancellation_time",
                "cancellation_announcement_time",
                "valid_from",
                "valid_until",
            }:
                item[field] = _datetime(value, f"{table}.{field}", nullable=True)
        if table == "people":
            item["admin_note"] = None
        elif table == "auth_identities":
            pass
        elif table == "person_qualifications":
            item.update(granted_by_person_id=None, reason=None)
        elif table == "game_attendance_replies":
            item["user_id"] = None
        result.append(item)
    return result


def import_bundle(
    directory: Path, database_url: str, engine_factory: Callable | None = None
) -> None:
    safe_url = require_local_database_url(database_url)
    rows = validate_bundle(directory, "derived")
    if engine_factory is None:
        from sqlalchemy import create_engine

        engine_factory = create_engine
    engine = engine_factory(safe_url)
    try:
        try:
            with Session(engine) as session, session.begin():
                revision = session.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                )
                if revision != REQUIRED_REVISION:
                    _fail("local database revision does not match the bundle")
                for table in reversed(TABLE_ORDER):
                    count = session.scalar(
                        select(func.count()).select_from(MODEL_BY_TABLE[table])
                    )
                    if count:
                        _fail("local preview target tables must be empty")
                for table in TABLE_ORDER:
                    values = _database_rows(table, rows[table])
                    if table == "game_attendance_replies":
                        reply_ids = set(
                            session.scalars(
                                select(LegacyAttendanceReplyTypeRecord.id)
                            ).all()
                        )
                        if reply_ids == LOCAL_FIXTURE_REPLY_IDS:
                            session.execute(delete(LegacyAttendanceReplyTypeRecord))
                            reply_ids = set()
                        if not reply_ids:
                            session.execute(
                                insert(LegacyAttendanceReplyTypeRecord),
                                [
                                    {"id": reply_id, "description": description}
                                    for reply_id, description in ATTENDANCE_REPLY_TYPES.items()
                                ],
                            )
                        elif reply_ids != set(ATTENDANCE_REPLY_TYPES):
                            _fail("local attendance reply types are incompatible")
                    if values:
                        session.execute(insert(MODEL_BY_TABLE[table]), values)
        except PreviewBundleError:
            raise
        except Exception:
            raise PreviewBundleError(
                "local preview import failed and was rolled back"
            ) from None
    finally:
        engine.dispose()


def _seed(path: Path) -> bytes:
    path = _require_private_path(path)
    try:
        return path.read_bytes()
    except OSError:
        _fail("pseudonymization seed file is unreadable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operate a private localhost Portal preview bundle"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    seal = commands.add_parser("seal-raw")
    seal.add_argument("bundle", type=Path)
    validate = commands.add_parser("validate")
    validate.add_argument("bundle", type=Path)
    validate.add_argument("--kind", choices=("raw", "derived"), required=True)
    pseudonymize = commands.add_parser("pseudonymize")
    pseudonymize.add_argument("source", type=Path)
    pseudonymize.add_argument("destination", type=Path)
    pseudonymize.add_argument("--seed-file", type=Path, required=True)
    pseudonymize.add_argument("--anchor-date", type=date.fromisoformat, required=True)
    importer = commands.add_parser("import")
    importer.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    if args.command == "seal-raw":
        seal_raw_bundle(args.bundle)
    elif args.command == "validate":
        validate_bundle(args.bundle, args.kind)
    elif args.command == "pseudonymize":
        pseudonymize_bundle(
            args.source, args.destination, _seed(args.seed_file), args.anchor_date
        )
    else:
        import_bundle(args.bundle, os.environ.get("PORTAL_DATA_DATABASE_URL", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
