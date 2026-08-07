from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "docs" / "operations" / "sql"
INVENTORY_SQL_PATH = SQL_DIR / "TASK-065-phase-b-inventory.sql"
BACKFILL_SQL_PATH = SQL_DIR / "TASK-065-phase-b-backfill.sql"
POSTCHECK_SQL_PATH = SQL_DIR / "TASK-065-phase-b-postcheck.sql"

FIELDS = (
    "section",
    "metric",
    "status",
    "boolean_value",
    "integer_value",
    "text_value",
)
INVENTORY_METRICS = {
    ("00_session", "transaction_read_only"),
    ("01_revision", "revision"),
    ("02_precondition", "member_count"),
    ("02_precondition", "linked_member_count"),
    ("02_precondition", "people_count"),
    ("02_precondition", "identity_count"),
    ("02_precondition", "qualification_count"),
    ("02_precondition", "access_audit_count"),
    ("03_line", "linked_nonignored_line_count"),
    ("03_line", "linked_nonignored_member_count"),
    ("03_line", "linked_ignored_line_count"),
    ("03_line", "unlinked_nonignored_line_count"),
    ("03_line", "unlinked_ignored_line_count"),
    ("03_line", "duplicate_line_subject_groups"),
    ("03_line", "orphan_line_member_count"),
}
POSTCHECK_METRICS = {
    ("00_session", "transaction_read_only"),
    ("01_revision", "revision"),
    ("02_people", "member_count"),
    ("02_people", "people_count"),
    ("02_people", "unlinked_member_count"),
    ("02_people", "nonbasic_person_count"),
    ("02_people", "noninactive_person_count"),
    ("02_people", "duplicate_person_link_count"),
    ("03_identity", "linked_identity_count"),
    ("03_identity", "identity_without_reliable_link_count"),
    ("03_identity", "ignored_identity_count"),
    ("04_qualification", "team_player_count"),
    ("04_qualification", "team_player_without_line_count"),
    ("05_audit", "member_audit_count"),
    ("05_audit", "identity_audit_count"),
    ("05_audit", "qualification_audit_count"),
}


class PhaseBEvidenceError(ValueError):
    pass


def _without_comments_and_literals(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


def verify_checksum(path: Path) -> None:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum, separator, filename = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not separator or filename != path.name or checksum != actual:
        raise PhaseBEvidenceError(f"checksum mismatch: {path.name}")


def verify_read_only_sql(path: Path) -> None:
    verify_checksum(path)
    normalized = _without_comments_and_literals(
        path.read_text(encoding="utf-8")
    ).lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    errors: list[str] = []
    if not statements or statements[0] != "begin transaction read only":
        errors.append("first statement must be BEGIN TRANSACTION READ ONLY")
    if not statements or statements[-1] != "rollback":
        errors.append("last statement must be ROLLBACK")
    for operation in (
        "alter",
        "copy",
        "create",
        "delete",
        "drop",
        "grant",
        "insert",
        "merge",
        "revoke",
        "truncate",
        "update",
    ):
        if re.search(rf"\b{operation}\b", normalized):
            errors.append(f"forbidden SQL operation: {operation}")
    if not re.search(
        r"select\s+section,\s*metric,\s*status,\s*boolean_value,\s*integer_value,\s*text_value\s+from\s+evidence",
        normalized,
    ):
        errors.append("missing sanitized six-column output")
    if errors:
        raise PhaseBEvidenceError("; ".join(errors))


def verify_mutation_sql(path: Path, *, final_statement: str) -> None:
    verify_checksum(path)
    sql = path.read_text(encoding="utf-8")
    normalized = _without_comments_and_literals(sql).lower()
    raw_lower = sql.lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    errors: list[str] = []
    if not statements or statements[0] != "begin":
        errors.append("first statement must be BEGIN")
    if not statements or statements[-1] != final_statement.lower():
        errors.append(f"last statement must be {final_statement}")
    required = (
        "pg_advisory_xact_lock",
        "lock_timeout",
        "statement_timeout",
        "0003_legacy_bigint_activity_game",
        "portal_access_level",
        "'basic'",
        "portal_status",
        "'inactive'",
        "ignored is false",
    )
    for marker in required:
        if marker.lower() not in raw_lower:
            errors.append(f"missing fail-closed marker: {marker}")
    for forbidden in ("'admin'", "'officer'", "current_setting", "set role"):
        if forbidden in raw_lower:
            errors.append(f"forbidden promotion/runtime dependency: {forbidden}")
    if errors:
        raise PhaseBEvidenceError("; ".join(errors))


def validate_rows(
    rows: Iterable[dict[str, str]], kind: str
) -> dict[tuple[str, str], str]:
    expected = INVENTORY_METRICS if kind == "inventory" else POSTCHECK_METRICS
    seen: dict[tuple[str, str], str] = {}
    errors: list[str] = []
    for line, source in enumerate(rows, start=2):
        row = dict(source)
        if tuple(row) != FIELDS:
            errors.append(f"row {line}: unexpected or reordered columns")
            continue
        key = (row["section"], row["metric"])
        if key not in expected:
            errors.append(f"row {line}: unknown metric")
        elif key in seen:
            errors.append(f"row {line}: duplicate metric")
        values = []
        for field in FIELDS[3:]:
            value = row[field].strip()
            if value.lower() == "null":
                value = ""
            if value:
                values.append((field, value))
        if len(values) != 1:
            errors.append(f"row {line}: exactly one value is required")
            continue
        field, value = values[0]
        if field == "boolean_value" and value not in ("true", "false"):
            errors.append(f"row {line}: invalid boolean")
        if field == "integer_value" and not re.fullmatch(r"\d+", value):
            errors.append(f"row {line}: invalid integer")
        if field == "text_value" and value != "0003_legacy_bigint_activity_game":
            errors.append(f"row {line}: unexpected text value")
        if re.search(
            r"(?:https?|postgres(?:ql)?)://|@|secret|token|password", value, re.I
        ):
            errors.append(f"row {line}: sensitive-looking value")
        if row["status"] == "required" and value == "false":
            errors.append(f"row {line}: required gate failed")
        if row["status"] == "stop_if_nonzero" and value != "0":
            errors.append(f"row {line}: nonzero stop gate")
        seen[key] = value
    missing = expected - set(seen)
    if missing:
        errors.append(f"missing metrics: {sorted(missing)}")
    if errors:
        raise PhaseBEvidenceError("; ".join(errors))
    return seen


def validate_csv(path: Path, kind: str) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise PhaseBEvidenceError("CSV header does not match the fixed contract")
        return validate_rows(reader, kind)


def compare_evidence(
    inventory: Mapping[tuple[str, str], str],
    postcheck: Mapping[tuple[str, str], str],
) -> None:
    member_count = inventory[("02_precondition", "member_count")]
    linked_line_count = inventory[("03_line", "linked_nonignored_line_count")]
    linked_member_count = inventory[("03_line", "linked_nonignored_member_count")]
    comparisons = {
        ("02_people", "member_count"): member_count,
        ("02_people", "people_count"): member_count,
        ("05_audit", "member_audit_count"): member_count,
        ("03_identity", "linked_identity_count"): linked_line_count,
        ("04_qualification", "team_player_count"): linked_member_count,
        ("05_audit", "identity_audit_count"): linked_line_count,
        ("05_audit", "qualification_audit_count"): linked_member_count,
    }
    drift = [
        key for key, expected in comparisons.items() if postcheck.get(key) != expected
    ]
    if drift:
        raise PhaseBEvidenceError(f"Phase B aggregate drift: {sorted(drift)}")


def verify_repository_artifacts() -> None:
    verify_read_only_sql(INVENTORY_SQL_PATH)
    verify_read_only_sql(POSTCHECK_SQL_PATH)
    verify_mutation_sql(BACKFILL_SQL_PATH, final_statement="COMMIT")


def render_rollback_rehearsal() -> str:
    """Return the exact checksummed backfill with transaction commit replaced by rollback."""
    verify_mutation_sql(BACKFILL_SQL_PATH, final_statement="COMMIT")
    sql = BACKFILL_SQL_PATH.read_text(encoding="utf-8")
    prefix, separator, suffix = sql.rpartition("COMMIT;")
    if not separator or suffix.strip():
        raise PhaseBEvidenceError("backfill must end with exactly one COMMIT")
    return prefix + "ROLLBACK;\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate TASK-065 Phase B artifacts")
    parser.add_argument("command", choices=("verify", "validate", "compare"))
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--kind", choices=("inventory", "postcheck"))
    args = parser.parse_args()
    if args.command == "verify":
        verify_repository_artifacts()
    elif args.command == "validate":
        if args.kind is None or len(args.paths) != 1:
            parser.error("validate requires --kind and one CSV path")
        validate_csv(args.paths[0], args.kind)
    else:
        if len(args.paths) != 2:
            parser.error("compare requires inventory and post-check CSV paths")
        compare_evidence(
            validate_csv(args.paths[0], "inventory"),
            validate_csv(args.paths[1], "postcheck"),
        )


if __name__ == "__main__":
    main()
