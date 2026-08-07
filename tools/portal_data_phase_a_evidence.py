from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "docs" / "operations" / "sql"
PRE_SQL_PATH = SQL_DIR / "TASK-062-phase-a-precheck.sql"
POST_SQL_PATH = SQL_DIR / "TASK-062-phase-a-postcheck.sql"
PRE_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "task062_phase_a_pre_fake.csv"
POST_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "task062_phase_a_post_fake.csv"

FIELDS = (
    "section",
    "metric",
    "status",
    "boolean_value",
    "integer_value",
    "text_value",
)
VALUE_FIELDS = FIELDS[3:]
LEGACY_TABLES = (
    "attendance_reply_types",
    "ballparks",
    "cancellations",
    "discord_webhooks",
    "game_attendance_replies",
    "games",
    "line_groups",
    "line_notify_tokens",
    "line_users",
    "members",
)
PORTAL_TABLES = (
    "access_audit",
    "activities",
    "activity_attendance_replies",
    "auth_identities",
    "event_attendance_replies",
    "event_audit",
    "event_eligibility_rules",
    "event_invitee_overrides",
    "event_invitees",
    "event_managers",
    "events",
    "people",
    "person_qualifications",
)

COMMON_EXACT = {
    ("00_session", "transaction_read_only"): "true",
    ("01_legacy", "legacy_table_count"): "10",
    ("01_legacy", "legacy_rls_enabled_count"): "10",
    ("01_legacy", "legacy_rls_forced_count"): "0",
    ("01_legacy", "legacy_policy_count"): "0",
}
PRE_EXACT = {
    **COMMON_EXACT,
    ("02_gate", "alembic_version_exists"): "false",
    ("02_gate", "portal_table_count"): "0",
    ("02_gate", "members_person_id_exists"): "false",
}
POST_EXACT = {
    **COMMON_EXACT,
    ("02_revision", "revision_matches"): "true",
    ("03_catalog", "portal_table_count"): "13",
    ("03_catalog", "portal_column_count"): "97",
    ("03_catalog", "portal_column_fingerprint_matches"): "true",
    ("03_catalog", "portal_constraint_count"): "75",
    ("03_catalog", "portal_constraint_fingerprint_matches"): "true",
    ("03_catalog", "expected_index_count"): "3",
    ("03_catalog", "expected_index_fingerprint_matches"): "true",
    ("03_catalog", "append_only_function_count"): "1",
    ("03_catalog", "append_only_function_matches"): "true",
    ("03_catalog", "append_only_trigger_count"): "2",
    ("03_catalog", "append_only_trigger_fingerprint_matches"): "true",
    ("04_members", "person_id_is_nullable_bigint"): "true",
    ("04_members", "person_id_unique_constraint_count"): "1",
    ("04_members", "person_id_fk_constraint_count"): "1",
    ("04_members", "person_id_nonnull_count"): "0",
    ("05_portal", "portal_total_row_count"): "0",
    ("05_portal", "portal_rls_enabled_count"): "13",
    ("05_portal", "portal_rls_forced_count"): "0",
    ("05_portal", "portal_policy_count"): "0",
    ("05_portal", "portal_public_grant_count"): "0",
}


class PhaseAEvidenceError(ValueError):
    pass


def _expected_metrics(kind: str) -> set[tuple[str, str]]:
    exact = PRE_EXACT if kind == "pre" else POST_EXACT
    return set(exact) | {("90_counts", table) for table in LEGACY_TABLES}


def _without_comments_and_literals(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


def verify_sql(path: Path, kind: str) -> None:
    sql = path.read_text(encoding="utf-8")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    checksum, separator, filename = (
        sidecar.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    errors: list[str] = []
    if not separator or filename != path.name or checksum != actual:
        errors.append("SQL checksum sidecar mismatch")
    normalized = _without_comments_and_literals(sql).lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    if not statements or not re.match(
        r"^begin\s+transaction\s+read\s+only$", statements[0]
    ):
        errors.append("first statement must be BEGIN TRANSACTION READ ONLY")
    if not statements or statements[-1] != "rollback":
        errors.append("last statement must be ROLLBACK")
    if normalized.count("rollback") != 1:
        errors.append("exactly one ROLLBACK is required")
    for operation in (
        "alter", "copy", "create", "delete", "do", "drop", "grant", "insert",
        "merge", "revoke", "truncate", "update",
    ):
        if re.search(rf"\b{operation}\b", normalized):
            errors.append(f"forbidden SQL operation: {operation}")
    if re.search(r"\bset\s+(?:local\s+)?role\b", normalized):
        errors.append("SET ROLE is forbidden")
    emitted = set(
        re.findall(
            r"select\s+'([0-9]{2}_[a-z]+)'\s*,\s*'([a-z0-9_]+)'", sql, re.I
        )
    )
    if emitted != _expected_metrics(kind):
        errors.append("query metrics do not match the fixed contract")
    if not re.search(
        r"select\s+section,\s*metric,\s*status,\s*boolean_value,\s*integer_value,"
        r"\s*text_value\s+from\s+evidence",
        normalized,
    ):
        errors.append("final output is not the six-column sanitized contract")
    for sensitive in (
        "current_user",
        "session_user",
        "current_role",
        "current_database",
        "rolname",
        "tableowner",
        "policyname",
        "qual",
        "with_check",
    ):
        if re.search(rf"\b{sensitive}\b", normalized):
            errors.append(f"identity or policy detail is forbidden: {sensitive}")
    if errors:
        raise PhaseAEvidenceError("; ".join(errors))


def validate_rows(
    rows: Iterable[dict[str, str]], kind: str
) -> dict[tuple[str, str], str]:
    exact = PRE_EXACT if kind == "pre" else POST_EXACT
    expected = _expected_metrics(kind)
    seen: dict[tuple[str, str], str] = {}
    errors: list[str] = []
    for line, source in enumerate(rows, start=2):
        row = dict(source)
        if tuple(row) != FIELDS:
            errors.append(f"row {line}: unexpected or reordered columns")
            continue
        for field in VALUE_FIELDS:
            if row[field].strip().lower() == "null":
                row[field] = ""
        key = (row["section"], row["metric"])
        if key not in expected:
            errors.append(f"row {line}: unknown metric")
        elif key in seen:
            errors.append(f"row {line}: duplicate metric")
        expected_status = "compare" if key[0] == "90_counts" else "required"
        if kind == "pre" and key in {
            ("02_gate", "alembic_version_exists"),
            ("02_gate", "members_person_id_exists"),
        }:
            expected_status = "stop_if_true"
        if kind == "pre" and key == ("02_gate", "portal_table_count"):
            expected_status = "stop_if_nonzero"
        if row["status"] != expected_status:
            errors.append(f"row {line}: unexpected status")
        populated = [field for field in VALUE_FIELDS if row[field] != ""]
        if len(populated) != 1:
            errors.append(f"row {line}: exactly one value is required")
            continue
        value = row[populated[0]]
        if populated[0] == "boolean_value" and value not in ("true", "false"):
            errors.append(f"row {line}: invalid boolean")
        if populated[0] == "integer_value" and not re.fullmatch(r"\d+", value):
            errors.append(f"row {line}: invalid integer")
        if populated[0] == "text_value" and value != "0003_legacy_bigint_activity_game":
            errors.append(f"row {line}: unexpected text value")
        serialized = "|".join(row[field] for field in VALUE_FIELDS)
        if re.search(
            r"(?:postgres(?:ql)?|https?)://|@|password|secret|token|role_name|owner_name",
            serialized,
            re.I,
        ):
            errors.append(f"row {line}: sensitive-looking value")
        seen[key] = value
    missing = expected - set(seen)
    if missing:
        errors.append(f"missing metrics: {sorted(missing)}")
    for key, expected_value in exact.items():
        if seen.get(key) != expected_value:
            errors.append(f"{key[0]}.{key[1]} must equal {expected_value}")
    if errors:
        raise PhaseAEvidenceError("; ".join(errors))
    return seen


def validate_csv(path: Path, kind: str) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise PhaseAEvidenceError("CSV header does not match the fixed contract")
        return validate_rows(reader, kind)


def compare_evidence(
    pre: Mapping[tuple[str, str], str], post: Mapping[tuple[str, str], str]
) -> None:
    drift = [
        table
        for table in LEGACY_TABLES
        if pre.get(("90_counts", table)) != post.get(("90_counts", table))
    ]
    if drift:
        raise PhaseAEvidenceError(f"legacy aggregate drift: {drift}")


def verify_repository_artifacts() -> None:
    verify_sql(PRE_SQL_PATH, "pre")
    verify_sql(POST_SQL_PATH, "post")
    compare_evidence(
        validate_csv(PRE_FIXTURE_PATH, "pre"),
        validate_csv(POST_FIXTURE_PATH, "post"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate sanitized TASK-062 Phase A evidence."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("verify-repository")
    validate = subparsers.add_parser("validate")
    validate.add_argument("pre_csv", type=Path)
    validate.add_argument("post_csv", type=Path)
    args = parser.parse_args()
    if args.action == "verify-repository":
        verify_repository_artifacts()
        print("TASK-062 Phase A evidence artifacts verified")
        return
    pre = validate_csv(args.pre_csv, "pre")
    post = validate_csv(args.post_csv, "post")
    compare_evidence(pre, post)
    print("TASK-062 Phase A pre/post evidence passed")


if __name__ == "__main__":
    main()
