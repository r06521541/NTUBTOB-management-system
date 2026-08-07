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
REVISION = "0003_legacy_bigint_activity_game"


@dataclass(frozen=True)
class MetricSpec:
    status: str
    field: str
    gate: Callable[[str], bool]


def _equals(expected: str) -> Callable[[str], bool]:
    return lambda value: value == expected


def _count(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))


def _compare(field: str = "integer_value") -> MetricSpec:
    return MetricSpec("compare", field, _count)


def _zero(status: str = "required") -> MetricSpec:
    return MetricSpec(status, "integer_value", _equals("0"))


INVENTORY_SCHEMA: dict[tuple[str, str], MetricSpec] = {
    ("00_session", "transaction_read_only"): MetricSpec(
        "required", "boolean_value", _equals("true")
    ),
    ("01_phase_a", "revision"): MetricSpec("required", "text_value", _equals(REVISION)),
    ("01_phase_a", "portal_table_count"): MetricSpec(
        "required", "integer_value", _equals("13")
    ),
    ("01_phase_a", "portal_rls_enabled_count"): MetricSpec(
        "required", "integer_value", _equals("13")
    ),
    ("01_phase_a", "portal_rls_forced_count"): _zero(),
    ("01_phase_a", "portal_policy_count"): _zero(),
    ("01_phase_a", "append_only_trigger_count"): MetricSpec(
        "required", "integer_value", _equals("2")
    ),
    ("02_precondition", "member_count"): _compare(),
    ("02_precondition", "linked_member_count"): _zero("stop_if_nonzero"),
    ("02_precondition", "people_count"): _zero("stop_if_nonzero"),
    ("02_precondition", "identity_count"): _zero("stop_if_nonzero"),
    ("02_precondition", "qualification_count"): _zero("stop_if_nonzero"),
    ("02_precondition", "access_audit_count"): _zero("stop_if_nonzero"),
    ("02_precondition", "other_portal_row_count"): _zero("stop_if_nonzero"),
    ("03_line", "line_user_count"): _compare(),
    ("03_line", "linked_nonignored_line_count"): _compare(),
    ("03_line", "linked_nonignored_member_count"): _compare(),
    ("03_line", "linked_ignored_line_count"): _compare(),
    ("03_line", "unlinked_nonignored_line_count"): _compare(),
    ("03_line", "unlinked_ignored_line_count"): _compare(),
    ("03_line", "duplicate_line_subject_groups"): _zero(),
    ("03_line", "orphan_line_member_count"): _zero(),
}

POSTCHECK_SCHEMA: dict[tuple[str, str], MetricSpec] = {
    ("00_session", "transaction_read_only"): MetricSpec(
        "required", "boolean_value", _equals("true")
    ),
    ("01_phase_a", "revision"): MetricSpec("required", "text_value", _equals(REVISION)),
    ("01_phase_a", "portal_table_count"): MetricSpec(
        "required", "integer_value", _equals("13")
    ),
    ("01_phase_a", "portal_rls_enabled_count"): MetricSpec(
        "required", "integer_value", _equals("13")
    ),
    ("01_phase_a", "portal_rls_forced_count"): _zero(),
    ("01_phase_a", "portal_policy_count"): _zero(),
    ("02_people", "member_count"): _compare(),
    ("02_people", "people_count"): _compare(),
    ("02_people", "unlinked_member_count"): _zero(),
    ("02_people", "nonbasic_person_count"): _zero(),
    ("02_people", "noninactive_person_count"): _zero(),
    ("02_people", "duplicate_person_link_count"): _zero(),
    ("03_identity", "linked_identity_count"): _compare(),
    ("03_identity", "identity_without_reliable_link_count"): _zero(),
    ("03_identity", "ignored_identity_count"): _zero(),
    ("04_qualification", "team_player_count"): _compare(),
    ("04_qualification", "team_player_without_line_count"): _zero(),
    ("05_audit", "access_audit_count"): _compare(),
    ("05_audit", "member_audit_count"): _compare(),
    ("05_audit", "identity_audit_count"): _compare(),
    ("05_audit", "qualification_audit_count"): _compare(),
    ("05_audit", "unexpected_audit_count"): _zero(),
    ("05_audit", "inconsistent_audit_count"): _zero(),
    ("06_unchanged", "other_portal_row_count"): _zero(),
}

INVENTORY_METRICS = set(INVENTORY_SCHEMA)
POSTCHECK_METRICS = set(POSTCHECK_SCHEMA)
PLACEHOLDER_KEYS = (
    "member_count",
    "line_user_count",
    "linked_nonignored_line_count",
    "linked_nonignored_member_count",
    "linked_ignored_line_count",
    "unlinked_nonignored_line_count",
    "unlinked_ignored_line_count",
)


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


def verify_mutation_template(path: Path) -> None:
    verify_checksum(path)
    sql = path.read_text(encoding="utf-8")
    normalized = _without_comments_and_literals(sql).lower()
    raw_lower = sql.lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    errors: list[str] = []
    if not statements or statements[0] != "begin":
        errors.append("first statement must be BEGIN")
    if not statements or statements[-1] != "commit":
        errors.append("last statement must be COMMIT")
    for key in PLACEHOLDER_KEYS:
        if sql.count("{{" + key + "}}") < 1:
            errors.append(f"missing approved inventory placeholder: {key}")
    for marker in (
        "pg_advisory_xact_lock",
        "lock_timeout",
        "statement_timeout",
        REVISION,
        "portal_access_level",
        "'basic'",
        "portal_status",
        "'inactive'",
        "ignored is false",
    ):
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
    if kind not in ("inventory", "postcheck"):
        raise PhaseBEvidenceError("unknown evidence kind")
    schema = INVENTORY_SCHEMA if kind == "inventory" else POSTCHECK_SCHEMA
    seen: dict[tuple[str, str], str] = {}
    errors: list[str] = []
    for line, source in enumerate(rows, start=2):
        row = dict(source)
        if tuple(row) != FIELDS:
            errors.append(f"row {line}: unexpected or reordered columns")
            continue
        key = (row["section"], row["metric"])
        spec = schema.get(key)
        if spec is None:
            errors.append(f"row {line}: unknown metric")
            continue
        if key in seen:
            errors.append(f"row {line}: duplicate metric")
            continue
        if row["status"] != spec.status:
            errors.append(f"row {line}: unexpected status")
        normalized_values = {
            field: "" if row[field].strip().lower() == "null" else row[field].strip()
            for field in FIELDS[3:]
        }
        populated = [field for field, value in normalized_values.items() if value]
        if populated != [spec.field]:
            errors.append(f"row {line}: unexpected value field")
            continue
        value = normalized_values[spec.field]
        if not spec.gate(value):
            errors.append(f"row {line}: metric gate failed")
        if re.search(
            r"(?:https?|postgres(?:ql)?)://|@|secret|token|password", value, re.I
        ):
            errors.append(f"row {line}: sensitive-looking value")
        seen[key] = value
    missing = set(schema) - set(seen)
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


def _inventory_counts(inventory: Mapping[tuple[str, str], str]) -> dict[str, str]:
    return {
        "member_count": inventory[("02_precondition", "member_count")],
        **{
            key: inventory[("03_line", key)]
            for key in PLACEHOLDER_KEYS
            if key != "member_count"
        },
    }


def _validate_inventory_mapping(inventory: Mapping[tuple[str, str], str]) -> None:
    supplied = set(inventory)
    expected = set(INVENTORY_SCHEMA)
    if supplied != expected:
        missing = sorted(expected - supplied)
        unknown = sorted(supplied - expected)
        raise PhaseBEvidenceError(
            f"inventory mapping contract mismatch; missing={missing}; unknown={unknown}"
        )
    errors = []
    for key, spec in INVENTORY_SCHEMA.items():
        value = inventory[key]
        if not isinstance(value, str) or not spec.gate(value):
            errors.append(key)
    if errors:
        raise PhaseBEvidenceError(f"inventory mapping gate failed: {sorted(errors)}")


def render_backfill(inventory: Mapping[tuple[str, str], str]) -> str:
    _validate_inventory_mapping(inventory)
    verify_mutation_template(BACKFILL_SQL_PATH)
    counts = _inventory_counts(inventory)
    sql = BACKFILL_SQL_PATH.read_text(encoding="utf-8")
    for key, value in counts.items():
        if not re.fullmatch(r"\d+", value):
            raise PhaseBEvidenceError(f"invalid inventory count: {key}")
        sql = sql.replace("{{" + key + "}}", value)
    if re.search(r"\{\{[a-z_]+\}\}", sql):
        raise PhaseBEvidenceError("unresolved backfill placeholder")
    return sql


def render_rollback_rehearsal(inventory: Mapping[tuple[str, str], str]) -> str:
    sql = render_backfill(inventory)
    prefix, separator, suffix = sql.rpartition("COMMIT;")
    if not separator or suffix.strip():
        raise PhaseBEvidenceError("backfill must end with exactly one COMMIT")
    return prefix + "ROLLBACK;\n"


def compare_evidence(
    inventory: Mapping[tuple[str, str], str],
    postcheck: Mapping[tuple[str, str], str],
) -> None:
    member_count = inventory[("02_precondition", "member_count")]
    linked_line_count = inventory[("03_line", "linked_nonignored_line_count")]
    linked_member_count = inventory[("03_line", "linked_nonignored_member_count")]
    total_audit_count = str(
        int(member_count) + int(linked_line_count) + int(linked_member_count)
    )
    comparisons = {
        ("02_people", "member_count"): member_count,
        ("02_people", "people_count"): member_count,
        ("05_audit", "member_audit_count"): member_count,
        ("03_identity", "linked_identity_count"): linked_line_count,
        ("04_qualification", "team_player_count"): linked_member_count,
        ("05_audit", "identity_audit_count"): linked_line_count,
        ("05_audit", "qualification_audit_count"): linked_member_count,
        ("05_audit", "access_audit_count"): total_audit_count,
    }
    drift = [
        key for key, expected in comparisons.items() if postcheck.get(key) != expected
    ]
    if drift:
        raise PhaseBEvidenceError(f"Phase B aggregate drift: {sorted(drift)}")


def verify_repository_artifacts() -> None:
    verify_read_only_sql(INVENTORY_SQL_PATH)
    verify_read_only_sql(POSTCHECK_SQL_PATH)
    verify_mutation_template(BACKFILL_SQL_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate TASK-065 Phase B artifacts")
    parser.add_argument("command", choices=("verify", "validate", "compare", "render"))
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--kind", choices=("inventory", "postcheck"))
    args = parser.parse_args()
    if args.command == "verify":
        verify_repository_artifacts()
    elif args.command == "validate":
        if args.kind is None or len(args.paths) != 1:
            parser.error("validate requires --kind and one CSV path")
        validate_csv(args.paths[0], args.kind)
    elif args.command == "compare":
        if len(args.paths) != 2:
            parser.error("compare requires inventory and post-check CSV paths")
        compare_evidence(
            validate_csv(args.paths[0], "inventory"),
            validate_csv(args.paths[1], "postcheck"),
        )
    else:
        if len(args.paths) != 1:
            parser.error("render requires one validated inventory CSV")
        print(render_backfill(validate_csv(args.paths[0], "inventory")), end="")


if __name__ == "__main__":
    main()
