from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SQL_PATH = ROOT / "docs" / "operations" / "sql" / "TASK-068-identity-drift-inventory.sql"
FIELDS = ("section", "metric", "status", "boolean_value", "integer_value", "text_value")
REVISION = "0003_legacy_bigint_activity_game"


@dataclass(frozen=True)
class MetricSpec:
    field: str
    gate: Callable[[str], bool]


def _equals(expected: str) -> Callable[[str], bool]:
    return lambda value: value == expected


def _count(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))


def _zero() -> MetricSpec:
    return MetricSpec("integer_value", _equals("0"))


def _info() -> MetricSpec:
    return MetricSpec("integer_value", _count)


INVENTORY_SCHEMA = {
    ("00_session", "transaction_read_only"): MetricSpec("boolean_value", _equals("true")),
    ("01_phase_a", "revision"): MetricSpec("text_value", _equals(REVISION)),
    ("01_phase_a", "portal_table_count"): MetricSpec("integer_value", _equals("13")),
    ("01_phase_a", "portal_rls_enabled_count"): MetricSpec("integer_value", _equals("13")),
    ("01_phase_a", "portal_rls_forced_count"): _zero(),
    ("01_phase_a", "portal_policy_count"): _zero(),
    ("01_phase_a", "append_only_trigger_count"): MetricSpec("integer_value", _equals("2")),
    ("02_people", "member_count"): _info(),
    ("02_people", "people_count"): _info(),
    ("02_people", "unlinked_member_count"): _zero(),
    ("02_people", "nonbasic_person_count"): _zero(),
    ("02_people", "noninactive_person_count"): _zero(),
    ("02_people", "duplicate_person_link_count"): _zero(),
    ("03_identity", "reliable_linked_line_count"): _info(),
    ("03_identity", "linked_identity_count"): _info(),
    ("03_identity", "pending_candidate_count"): _info(),
    ("03_identity", "ignored_candidate_count"): _info(),
    ("03_identity", "missing_identity_count"): _zero(),
    ("03_identity", "wrong_person_link_count"): _zero(),
    ("03_identity", "identity_without_reliable_link_count"): _zero(),
    ("03_identity", "duplicate_provider_subject_count"): _zero(),
    ("03_identity", "orphan_member_link_count"): _zero(),
    ("04_qualification", "team_player_count"): _info(),
    ("04_qualification", "team_player_missing_count"): _zero(),
    ("04_qualification", "team_player_extra_count"): _zero(),
    ("04_qualification", "team_player_revoked_mismatch_count"): _zero(),
    ("05_audit", "access_audit_count"): _info(),
    ("05_audit", "unexpected_audit_count"): _zero(),
    ("05_audit", "inconsistent_audit_count"): _zero(),
}


class IdentityDriftEvidenceError(ValueError):
    pass


def verify_artifact(path: Path = INVENTORY_SQL_PATH) -> None:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum, separator, filename = checksum_path.read_text(encoding="ascii").strip().partition("  ")
    if not separator or filename != path.name or checksum != hashlib.sha256(path.read_bytes()).hexdigest():
        raise IdentityDriftEvidenceError("checksum mismatch")
    sql = path.read_text(encoding="utf-8")
    normalized = re.sub(r"'(?:''|[^'])*'", "''", re.sub(r"--[^\n]*", "", sql)).lower()
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    if not statements or statements[0] != "begin transaction read only" or statements[-1] != "rollback":
        raise IdentityDriftEvidenceError("inventory must be a read-only rollback transaction")
    if re.search(r"\b(alter|copy|create|delete|drop|grant|insert|merge|revoke|truncate|update)\b", normalized):
        raise IdentityDriftEvidenceError("forbidden SQL operation")
    if "select section,metric,status,boolean_value,integer_value,text_value from evidence" not in re.sub(r"\s+", " ", normalized):
        raise IdentityDriftEvidenceError("missing fixed sanitized output")


def validate_rows(rows: Iterable[dict[str, str]]) -> dict[tuple[str, str], str]:
    seen = {}
    observed_keys = []
    errors = []
    for line, source in enumerate(rows, start=2):
        row = dict(source)
        if tuple(row) != FIELDS:
            errors.append(f"row {line}: unexpected or reordered columns")
            continue
        key = (row["section"], row["metric"])
        spec = INVENTORY_SCHEMA.get(key)
        if spec is None or key in seen or row["status"] != "required":
            errors.append(f"row {line}: metric contract mismatch")
            continue
        values = {field: row[field].strip() for field in FIELDS[3:]}
        populated = [field for field, value in values.items() if value and value.lower() != "null"]
        if populated != [spec.field] or not spec.gate(values[spec.field]):
            errors.append(f"row {line}: metric gate failed")
            continue
        value = values[spec.field]
        if re.search(r"(?:https?|postgres(?:ql)?)://|@|secret|token|password", value, re.I):
            errors.append(f"row {line}: sensitive-looking value")
        seen[key] = value
        observed_keys.append(key)
    if set(seen) != set(INVENTORY_SCHEMA):
        errors.append("missing or extra metrics")
    if observed_keys != sorted(INVENTORY_SCHEMA):
        errors.append("metrics are missing, extra, duplicate, or reordered")
    if errors:
        raise IdentityDriftEvidenceError("; ".join(errors))
    return seen


def validate_csv(path: Path) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise IdentityDriftEvidenceError("CSV header does not match fixed contract")
        return validate_rows(reader)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "validate"))
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        verify_artifact()
    elif args.path is None:
        parser.error("validate requires one CSV path")
    else:
        validate_csv(args.path)


if __name__ == "__main__":
    main()
