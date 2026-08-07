from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = (
    ROOT
    / "docs"
    / "operations"
    / "sql"
    / "TASK-052-supabase-readonly-access-boundary.sql"
)
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "task052_supabase_access_inventory_fake.csv"
)

FIELDS = (
    "section",
    "metric",
    "status",
    "boolean_value",
    "integer_value",
    "text_value",
)
VALUE_FIELDS = ("boolean_value", "integer_value", "text_value")
EXPECTED_METRICS = {
    "00_session": {
        "transaction_read_only",
        "server_major",
        "session_is_superuser",
        "session_bypasses_rls",
        "session_can_create_role",
        "session_can_create_database",
    },
    "01_schema": {
        "ntubtob_exists",
        "session_has_usage",
        "session_has_create",
        "schema_owner_relation",
    },
    "02_catalog": {
        "legacy_table_count",
        "legacy_table_fingerprint_matches",
        "legacy_column_fingerprint_matches",
        "legacy_constraint_fingerprint_matches",
        "alembic_version_exists",
        "new_portal_table_count",
    },
    "03_owner": {"legacy_owned_by_session_count", "legacy_owned_by_other_count"},
    "04_privilege": {
        "legacy_selectable_count",
        "legacy_insertable_count",
        "legacy_updatable_count",
        "legacy_deletable_count",
        "legacy_truncatable_count",
        "other_visible_grant_count",
        "public_grant_count",
        "session_named_grant_count",
        "visible_write_grant_count",
    },
    "05_rls": {
        "legacy_rls_enabled_count",
        "legacy_rls_forced_count",
        "policy_count",
        "public_policy_count",
        "write_policy_count",
        "policy_expression_present_count",
    },
}
ALLOWED_RELATIONS = {
    "pg_catalog.pg_class",
    "pg_catalog.pg_constraint",
    "pg_catalog.pg_namespace",
    "pg_catalog.pg_policies",
    "pg_catalog.pg_roles",
    "information_schema.columns",
    "information_schema.table_privileges",
}
ALLOWED_QUERY_SOURCES = ALLOWED_RELATIONS | {
    "column_fingerprint",
    "constraint_fingerprint",
    "inventory",
    "legacy_tables",
    "portal_tables",
    "relations",
    "session_role",
    "table_fingerprint",
}
ALLOWED_FUNCTIONS = {
    "any",
    "coalesce",
    "count",
    "current_setting",
    "exists",
    "has_schema_privilege",
    "has_table_privilege",
    "md5",
    "pg_get_constraintdef",
    "string_agg",
}
FORBIDDEN_WORDS = {
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
}
SENSITIVE_RESULT_PATTERNS = (
    re.compile(r"(?:postgres(?:ql)?|mysql)://", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b"),
    re.compile(
        r"\b(?:host|database|dsn|secret|password|token|role_name|owner_name)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:using|with check)\s*\(", re.IGNORECASE),
)


class InventoryValidationError(ValueError):
    pass


def _without_comments_and_literals(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


def verify_sql(sql: str) -> None:
    errors: list[str] = []
    normalized = _without_comments_and_literals(sql)
    lowered = normalized.lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    if not statements or not re.match(
        r"^begin\s+(?:transaction\s+)?read\s+only$", statements[0], re.IGNORECASE
    ):
        errors.append("first statement must be a read-only transaction")
    if not statements or statements[-1].lower() != "rollback":
        errors.append("last statement must be ROLLBACK")
    if lowered.count("rollback") != 1:
        errors.append("exactly one ROLLBACK is required")
    if re.search(r"\bset\s+(?:local\s+)?role\b", lowered):
        errors.append("SET ROLE is forbidden")
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{word}\b", lowered):
            errors.append(f"forbidden SQL operation: {word}")
    for dangerous in (
        "pg_read_file",
        "pg_read_binary_file",
        "lo_import",
        "lo_export",
        "dblink",
        "postgres_fdw",
        "http_get",
        "http_post",
        "net.http",
    ):
        if dangerous in lowered:
            errors.append(f"forbidden helper: {dangerous}")
    if re.search(r"\b(?:from|join)\s+ntubtob\s*\.", lowered):
        errors.append("application table row reads are forbidden")

    emitted = {
        (section, metric)
        for section, metric in re.findall(
            r"select\s+'([0-9]{2}_[a-z]+)'\s*,\s*'([a-z0-9_]+)'",
            sql,
            re.IGNORECASE,
        )
    }
    expected_emitted = {
        (section, metric)
        for section, metrics in EXPECTED_METRICS.items()
        for metric in metrics
    }
    if emitted != expected_emitted:
        errors.append("query metrics do not match the fixed result contract")

    relations = set(re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_.]*)", lowered))
    unknown_relations = relations - ALLOWED_QUERY_SOURCES
    if unknown_relations:
        errors.append(f"catalog relation not allowlisted: {sorted(unknown_relations)}")

    functions = set(re.findall(r"\b(?:pg_catalog\.)?([a-z_][a-z0-9_.]*)\s*\(", lowered))
    sql_keywords = {
        "and",
        "as",
        "in",
        "inventory",
        "legacy_tables",
        "portal_tables",
        "values",
    }
    unknown_functions = functions - ALLOWED_FUNCTIONS - sql_keywords
    if unknown_functions:
        errors.append(f"function not allowlisted: {sorted(unknown_functions)}")

    select_tail = re.search(
        r"select\s+section,\s*metric,\s*status,\s*boolean_value,\s*integer_value,\s*text_value\s+from\s+inventory",
        lowered,
    )
    if not select_tail:
        errors.append("final output columns are not the fixed sanitized contract")
    for raw_name in (
        "current_user",
        "current_role",
        "session_user",
        "current_database",
    ):
        if re.search(rf"\b{raw_name}\b\s*(?:as\s+\w+)?\s*(?:,|from)", lowered):
            errors.append(f"raw identity/session output is forbidden: {raw_name}")
    for identity_column in ("policyname", "tableowner"):
        if re.search(rf"\b{identity_column}\b", lowered):
            errors.append(
                f"identity-bearing catalog column is forbidden: {identity_column}"
            )
    if re.search(r"\b(?:rolname|grantee|qual|with_check)\b\s*(?:::|,|as\b)", lowered):
        errors.append("role name or policy expression output is forbidden")
    if errors:
        raise InventoryValidationError("; ".join(errors))


def validate_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    materialized: list[dict[str, str]] = []
    seen: dict[str, set[str]] = {section: set() for section in EXPECTED_METRICS}
    errors: list[str] = []
    for index, source_row in enumerate(rows, start=2):
        row = dict(source_row)
        if tuple(row.keys()) != FIELDS:
            errors.append(f"row {index}: unexpected or reordered columns")
            continue
        for name in VALUE_FIELDS:
            value = row[name]
            if value is not None and value.strip().lower() == "null":
                row[name] = ""
        materialized.append(row)
        section = row["section"]
        metric = row["metric"]
        if any(
            value is not None and value.strip().lower() == "null"
            for name, value in row.items()
            if name not in VALUE_FIELDS
        ):
            errors.append(f"row {index}: null token is only allowed in value columns")
        if section not in EXPECTED_METRICS or metric not in EXPECTED_METRICS.get(
            section, set()
        ):
            errors.append(f"row {index}: unknown section or metric")
        elif metric in seen[section]:
            errors.append(f"row {index}: duplicate metric")
        else:
            seen[section].add(metric)
        populated = [
            name
            for name in VALUE_FIELDS
            if row[name] != ""
        ]
        if len(populated) != 1:
            errors.append(f"row {index}: exactly one value column is required")
        if row["boolean_value"] not in ("", "true", "false"):
            errors.append(f"row {index}: invalid boolean")
        if row["integer_value"] and not re.fullmatch(r"\d+", row["integer_value"]):
            errors.append(f"row {index}: invalid non-negative integer")
        if row["text_value"] and row["text_value"] not in {
            "same",
            "different",
            "unknown",
        }:
            errors.append(f"row {index}: invalid text classification")
        serialized = "|".join(row.values())
        if any(pattern.search(serialized) for pattern in SENSITIVE_RESULT_PATTERNS):
            errors.append(f"row {index}: sensitive-looking value")
    for section, expected in EXPECTED_METRICS.items():
        missing = expected - seen[section]
        if missing:
            errors.append(f"{section}: missing metrics {sorted(missing)}")
    if errors:
        raise InventoryValidationError("; ".join(errors))
    return materialized


def validate_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise InventoryValidationError(
                "CSV header does not match the fixed contract"
            )
        return validate_rows(reader)


def verify_repository_artifacts() -> None:
    verify_sql(SQL_PATH.read_text(encoding="utf-8"))
    validate_csv(FIXTURE_PATH)


if __name__ == "__main__":
    verify_repository_artifacts()
    print("TASK-052 access inventory artifacts verified")
