from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "docs" / "operations" / "sql"
INVENTORY_SQL_PATH = SQL_DIR / "TASK-071-phase-c-production-inventory.sql"
POSTCHECK_SQL_PATH = SQL_DIR / "TASK-071-phase-c-production-postcheck.sql"
FIELDS = (
    "section",
    "metric",
    "status",
    "boolean_value",
    "integer_value",
    "text_value",
)
REVISION_0003 = "0003_legacy_bigint_activity_game"
REVISION_0004 = "0004_phase_c_identity_lifecycle"


class PhaseCReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class MetricSpec:
    status: str
    field: str
    gate: Callable[[str], bool]


def _equals(expected: str) -> Callable[[str], bool]:
    return lambda value: value == expected


def _count(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))


def _boolean(value: str) -> bool:
    return value in ("true", "false")


def _exact(field: str, expected: str, status: str = "required") -> MetricSpec:
    return MetricSpec(status, field, _equals(expected))


def _zero(status: str = "required") -> MetricSpec:
    return _exact("integer_value", "0", status)


def _compare() -> MetricSpec:
    return MetricSpec("compare", "integer_value", _count)


COMMON_INVARIANTS = {
    ("01_contract", "legacy_table_count"): _exact("integer_value", "10"),
    ("01_contract", "phase_b_table_count"): _exact("integer_value", "13"),
    ("01_contract", "legacy_rls_enabled_count"): _exact("integer_value", "10"),
    ("01_contract", "phase_b_rls_enabled_count"): _exact("integer_value", "13"),
    ("01_contract", "forced_rls_count"): _zero(),
    ("01_contract", "policy_count"): _zero(),
    ("01_contract", "append_only_trigger_count"): _exact("integer_value", "2"),
    ("01_contract", "public_table_grant_count"): _zero(),
    ("01_contract", "legacy_table_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "legacy_column_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "legacy_constraint_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("02_phase_b", "member_count"): _compare(),
    ("02_phase_b", "people_count"): _compare(),
    ("02_phase_b", "unlinked_member_count"): _zero(),
    ("02_phase_b", "duplicate_person_link_count"): _zero(),
    ("02_phase_b", "linked_identity_count"): _compare(),
    ("02_phase_b", "identity_projection_drift_count"): _zero(),
    ("02_phase_b", "duplicate_provider_subject_count"): _zero(),
    ("02_phase_b", "team_player_count"): _compare(),
    ("02_phase_b", "team_player_drift_count"): _zero(),
    ("02_phase_b", "access_audit_count"): _compare(),
    ("02_phase_b", "unexpected_audit_count"): _zero(),
    ("02_phase_b", "audit_relationship_drift_count"): _zero(),
    ("04_attendance", "attendance_reply_count"): _compare(),
    ("04_attendance", "attendance_null_member_count"): _zero(),
    ("04_attendance", "attendance_orphan_member_count"): _zero(),
    ("04_attendance", "attendance_member_without_person_count"): _zero(),
    ("90_counts", "members"): _compare(),
    ("90_counts", "line_users"): _compare(),
    ("90_counts", "games"): _compare(),
    ("90_counts", "game_attendance_replies"): _compare(),
}

INVENTORY_SCHEMA = {
    ("00_session", "transaction_read_only"): _exact("boolean_value", "true"),
    ("00_session", "server_major_at_least_16"): _exact("boolean_value", "true"),
    ("00_session", "schema_owned_by_session"): _exact("boolean_value", "true"),
    ("00_session", "session_has_schema_usage"): _exact("boolean_value", "true"),
    ("00_session", "session_has_schema_create"): _exact("boolean_value", "true"),
    ("00_session", "session_superuser"): MetricSpec("risk", "boolean_value", _boolean),
    ("00_session", "session_bypassrls"): MetricSpec("risk", "boolean_value", _boolean),
    ("01_contract", "revision"): _exact("text_value", REVISION_0003),
    **COMMON_INVARIANTS,
    ("01_contract", "phase_b_column_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "phase_b_constraint_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "phase_b_index_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("03_collision", "alembic_revision_row_count"): _exact("integer_value", "1"),
    ("03_collision", "phase_c_column_count"): _zero(),
    ("03_collision", "phase_c_table_count"): _zero(),
    ("03_collision", "phase_c_constraint_count"): _zero(),
    ("03_collision", "phase_c_index_count"): _zero(),
    ("04_attendance", "attendance_person_column_count"): _zero(),
    ("04_attendance", "compatibility_backfill_candidate_count"): _zero(),
    ("04_attendance", "phase_c_backfill_audit_count"): _zero(),
    ("05_out_of_band", "runtime_flags"): _exact(
        "text_value", "not_checked_by_database", "out_of_band"
    ),
}

POSTCHECK_SCHEMA = {
    ("00_session", "transaction_read_only"): _exact("boolean_value", "true"),
    ("00_session", "server_major_at_least_16"): _exact("boolean_value", "true"),
    ("01_contract", "revision"): _exact("text_value", REVISION_0004),
    **COMMON_INVARIANTS,
    ("01_contract", "phase_b_column_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "phase_b_constraint_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "phase_b_index_fingerprint_matches"): _exact(
        "boolean_value", "true"
    ),
    ("01_contract", "phase_c_table_count"): _exact("integer_value", "2"),
    ("01_contract", "phase_c_rls_enabled_count"): _exact("integer_value", "2"),
    ("01_contract", "phase_c_policy_count"): _zero(),
    ("03_phase_c", "alembic_revision_row_count"): _exact("integer_value", "1"),
    ("03_phase_c", "phase_c_column_count"): _exact("integer_value", "3"),
    ("03_phase_c", "phase_c_constraint_count"): _exact("integer_value", "10"),
    ("03_phase_c", "phase_c_index_count"): _exact("integer_value", "3"),
    ("03_phase_c", "attendance_person_fk_count"): _exact("integer_value", "1"),
    ("03_phase_c", "guest_bound_constraint_count"): _exact("integer_value", "1"),
    ("04_attendance", "attendance_person_column_count"): _exact("integer_value", "1"),
    ("04_attendance", "attendance_null_person_count"): _zero(),
    ("04_attendance", "attendance_person_mismatch_count"): _zero(),
    ("04_attendance", "phase_c_backfill_audit_count"): _zero(),
    ("05_out_of_band", "runtime_flags"): _exact(
        "text_value", "not_checked_by_database", "out_of_band"
    ),
}


def _without_comments_and_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'", "''", re.sub(r"--[^\n]*", "", sql))


def verify_sql(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise PhaseCReadinessError(
            f"non-canonical encoding or line ending: {path.name}"
        )
    try:
        sql = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhaseCReadinessError(f"artifact is not UTF-8: {path.name}") from exc
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum, separator, filename = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if (
        not separator
        or filename != path.name
        or checksum != hashlib.sha256(raw).hexdigest()
    ):
        raise PhaseCReadinessError(f"checksum mismatch: {path.name}")
    normalized = _without_comments_and_literals(sql).lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    errors = []
    if not statements or statements[0] != "begin transaction read only":
        errors.append("first statement must be BEGIN TRANSACTION READ ONLY")
    if not statements or statements[-1] != "rollback":
        errors.append("last statement must be ROLLBACK")
    for marker in (
        "lock_timeout",
        "statement_timeout",
        "idle_in_transaction_session_timeout",
    ):
        if marker not in normalized:
            errors.append(f"transaction-local {marker} missing")
    for operation in (
        "alter",
        "copy",
        "create",
        "delete",
        "do",
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
    compact = re.sub(r"\s+", " ", normalized)
    if (
        "select section,metric,status,boolean_value,integer_value,text_value from evidence"
        not in compact
    ):
        errors.append("missing fixed sanitized six-column output")
    if errors:
        raise PhaseCReadinessError("; ".join(errors))


def validate_rows(
    rows: Iterable[dict[str, str]], kind: str
) -> dict[tuple[str, str], str]:
    schema = INVENTORY_SCHEMA if kind == "inventory" else POSTCHECK_SCHEMA
    seen: dict[tuple[str, str], str] = {}
    order = []
    errors = []
    for line, source in enumerate(rows, start=2):
        row = dict(source)
        if tuple(row) != FIELDS:
            errors.append(f"row {line}: unexpected or reordered columns")
            continue
        key = (row["section"], row["metric"])
        spec = schema.get(key)
        if spec is None or key in seen:
            errors.append(f"row {line}: unknown or duplicate metric")
            continue
        values = {field: row[field].strip() for field in FIELDS[3:]}
        populated = [
            field
            for field, value in values.items()
            if value and value.lower() != "null"
        ]
        if row["status"] != spec.status or populated != [spec.field]:
            errors.append(f"row {line}: status or value-field contract mismatch")
            continue
        value = values[spec.field]
        if not spec.gate(value):
            errors.append(f"row {line}: metric gate failed")
        if re.search(
            r"(?:https?|postgres(?:ql)?)://|@|secret|token|password|supabase",
            value,
            re.I,
        ):
            errors.append(f"row {line}: sensitive-looking value")
        seen[key] = value
        order.append(key)
    if set(seen) != set(schema) or order != sorted(schema):
        errors.append("metrics are missing, extra, duplicate, or reordered")
    if errors:
        raise PhaseCReadinessError("; ".join(errors))
    return seen


def validate_csv(path: Path, kind: str) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise PhaseCReadinessError("CSV header does not match the fixed contract")
        return validate_rows(reader, kind)


def compare_evidence(
    inventory: Mapping[tuple[str, str], str], postcheck: Mapping[tuple[str, str], str]
) -> str:
    if inventory.get(("01_contract", "revision")) != REVISION_0003:
        raise PhaseCReadinessError("inventory is not an approved 0003 baseline")
    post_revision = postcheck.get(("01_contract", "revision"))
    stable = [
        key for key, spec in COMMON_INVARIANTS.items() if spec.status == "compare"
    ]
    stable += [
        ("90_counts", name)
        for name in ("members", "line_users", "games", "game_attendance_replies")
    ]
    drift = [key for key in stable if inventory.get(key) != postcheck.get(key)]
    if post_revision == REVISION_0003:
        if drift:
            raise PhaseCReadinessError(
                f"semantic drift after confirmed rollback: {sorted(drift)}"
            )
        return "safe_retry_after_confirmed_rollback"
    if post_revision != REVISION_0004:
        raise PhaseCReadinessError("ambiguous_commit_state")
    if drift:
        raise PhaseCReadinessError(f"semantic drift: {sorted(drift)}")
    return "pass"


def verify_repository_artifacts() -> None:
    verify_sql(INVENTORY_SQL_PATH)
    verify_sql(POSTCHECK_SQL_PATH)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "validate", "compare"))
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--kind", choices=("inventory", "postcheck"))
    args = parser.parse_args()
    if args.command == "verify":
        verify_repository_artifacts()
    elif args.command == "validate":
        if args.kind is None or len(args.paths) != 1:
            parser.error("validate requires --kind and one CSV")
        validate_csv(args.paths[0], args.kind)
    else:
        if len(args.paths) != 2:
            parser.error("compare requires inventory and post-check CSVs")
        inventory = validate_csv(args.paths[0], "inventory")
        try:
            outcome = validate_csv(args.paths[1], "postcheck")
        except PhaseCReadinessError:
            outcome = validate_csv(args.paths[1], "inventory")
        print(compare_evidence(inventory, outcome))


if __name__ == "__main__":
    main()
