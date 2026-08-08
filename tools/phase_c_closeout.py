"""Fail-closed, redacted Phase C identity-maintenance closeout evidence."""

from __future__ import annotations

import json
import hashlib
import re
import csv
from pathlib import Path
from typing import Mapping


class CloseoutEvidenceError(ValueError):
    """Raised when an offline closeout manifest is incomplete or unsafe."""


SERVICE_PATTERNS = {
    "web_portal": re.compile(r"^web-portal-[a-z0-9-]+$"),
    "line_webhook": re.compile(r"^line-webhook-handler-[a-z0-9-]+$"),
    "notify_cron": re.compile(r"^notify-cronjob-service-[a-z0-9-]+$"),
}
ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SQL_PATH = (
    ROOT / "docs" / "operations" / "sql" / "TASK-084-phase-c-closeout-inventory.sql"
)
DATABASE_FIELDS = frozenset(
    {
        "schema_revision",
        "admin_principal_count",
        "identity_drift_count",
        "member_person_drift_count",
        "qualification_drift_count",
        "audit_count",
        "duplicate_request_id_count",
        "safe_candidate_count",
    }
)
CSV_FIELDS = ("section", "metric", "status", "boolean_value", "integer_value", "text_value")
CSV_METRICS = {
    ("00_session", "transaction_read_only"): ("boolean_value", "true"),
    ("01_schema", "revision"): ("text_value", "0004_phase_c_identity_lifecycle"),
    ("02_identity", "safe_ignore_candidate_count"): ("integer_value", None),
    ("02_identity", "safe_unignore_candidate_count"): ("integer_value", None),
    ("03_audit", "access_audit_count"): ("integer_value", None),
    ("03_audit", "duplicate_request_id_count"): ("integer_value", "0"),
    ("04_qualification", "active_team_player_count"): ("integer_value", None),
}
RUNTIME_FIELDS = frozenset(
    {"revisions", "traffic", "iam", "phase_c", "freeze", "maintenance"}
)


def verify_inventory_artifact(path: Path = INVENTORY_SQL_PATH) -> None:
    raw = path.read_bytes()
    checksum, separator, filename = (
        path.with_suffix(path.suffix + ".sha256")
        .read_text(encoding="ascii")
        .strip()
        .partition("  ")
    )
    if (
        not separator
        or filename != path.name
        or checksum != hashlib.sha256(raw).hexdigest()
    ):
        raise CloseoutEvidenceError("inventory checksum is invalid")
    sql = re.sub(r"--[^\n]*", "", raw.decode("utf-8")).lower()
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    if (
        not statements
        or statements[0] != "begin transaction read only"
        or statements[-1] != "rollback"
    ):
        raise CloseoutEvidenceError("inventory transaction is invalid")
    if re.search(
        r"\b(alter|copy|create|delete|do|drop|grant|insert|merge|revoke|truncate|update)\b",
        sql,
    ):
        raise CloseoutEvidenceError("inventory contains a mutation")


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CloseoutEvidenceError(f"{label} is invalid")
    return value


def ingest_inventory_rows(rows: list[dict[str, str]], *, admin_principal_count: int, identity_drift_count: int, member_person_drift_count: int, qualification_drift_count: int) -> dict:
    """Strictly ingest the fixed sanitized SQL columns; external aggregates remain explicit."""
    seen = {}
    for row in rows:
        if tuple(row) != CSV_FIELDS:
            raise CloseoutEvidenceError("inventory CSV columns are invalid")
        key = (row["section"], row["metric"])
        field, expected = CSV_METRICS.get(key, (None, None))
        values = [name for name in CSV_FIELDS[3:] if row[name] not in ("", "null")]
        if key in seen or field is None or values != [field] or (expected is not None and row[field] != expected):
            raise CloseoutEvidenceError("inventory CSV metric is invalid")
        if field == "integer_value" and not re.fullmatch(r"\d+", row[field]):
            raise CloseoutEvidenceError("inventory CSV count is invalid")
        seen[key] = row[field]
    if set(seen) != set(CSV_METRICS):
        raise CloseoutEvidenceError("inventory CSV is incomplete")
    return {
        "schema_revision": seen[("01_schema", "revision")],
        "admin_principal_count": admin_principal_count,
        "identity_drift_count": identity_drift_count,
        "member_person_drift_count": member_person_drift_count,
        "qualification_drift_count": qualification_drift_count,
        "audit_count": int(seen[("03_audit", "access_audit_count")]),
        "duplicate_request_id_count": int(seen[("03_audit", "duplicate_request_id_count")]),
        "safe_candidate_count": int(seen[("02_identity", "safe_ignore_candidate_count")]),
    }


def compare_sequence(before: Mapping[str, object], retry: Mapping[str, object], recovery: Mapping[str, object], post: Mapping[str, object]) -> None:
    """Require one action audit, no retry audit, one recovery audit and restored protected counts."""
    manifests = [build_manifest(item["database"], item["runtime"]) for item in (before, retry, recovery, post)]
    counts = [entry["database"]["audit_count"] for entry in manifests]
    if counts[1] != counts[0] + 1 or counts[2] != counts[1] or counts[3] != counts[2] + 1:
        raise CloseoutEvidenceError("audit sequence is invalid")
    protected = ("admin_principal_count", "identity_drift_count", "member_person_drift_count", "qualification_drift_count", "duplicate_request_id_count")
    if any(manifests[0]["database"][field] != manifests[-1]["database"][field] for field in protected):
        raise CloseoutEvidenceError("protected closeout counts drifted")


def _runtime(evidence: Mapping[str, object]) -> dict:
    if set(evidence) != RUNTIME_FIELDS:
        raise CloseoutEvidenceError("runtime evidence fields are invalid")
    revisions, traffic, iam, phase_c, freeze = (
        evidence["revisions"],
        evidence["traffic"],
        evidence["iam"],
        evidence["phase_c"],
        evidence["freeze"],
    )
    if not all(
        isinstance(value, Mapping) and set(value) == set(SERVICE_PATTERNS)
        for value in (revisions, traffic, iam, phase_c, freeze)
    ):
        raise CloseoutEvidenceError("runtime service vector is incomplete")
    for service, pattern in SERVICE_PATTERNS.items():
        if (
            not isinstance(revisions[service], str)
            or pattern.fullmatch(revisions[service]) is None
        ):
            raise CloseoutEvidenceError("runtime revision is invalid")
        if (
            traffic[service] != 100
            or phase_c[service] is not True
            or freeze[service] is not False
        ):
            raise CloseoutEvidenceError(
                "runtime vector is not an all-on unfrozen state"
            )
    if iam != {
        "web_portal": "public",
        "line_webhook": "public",
        "notify_cron": "private",
    }:
        raise CloseoutEvidenceError("runtime IAM classification is invalid")
    if type(evidence["maintenance"]) is not bool:
        raise CloseoutEvidenceError("maintenance classification is invalid")
    return dict(evidence)


def build_manifest(
    database: Mapping[str, object], runtime: Mapping[str, object]
) -> dict:
    """Validate only redacted aggregate evidence and return a fixed manifest."""
    if set(database) != DATABASE_FIELDS:
        raise CloseoutEvidenceError("database evidence fields are invalid")
    if database["schema_revision"] != "0004_phase_c_identity_lifecycle":
        raise CloseoutEvidenceError("schema revision is invalid")
    result = {
        name: _integer(database[name], name)
        for name in DATABASE_FIELDS
        if name != "schema_revision"
    }
    if result["admin_principal_count"] < 1:
        raise CloseoutEvidenceError("no active allowlisted admin classification")
    for name in (
        "identity_drift_count",
        "member_person_drift_count",
        "qualification_drift_count",
        "duplicate_request_id_count",
    ):
        if result[name] != 0:
            raise CloseoutEvidenceError("database drift classification is unsafe")
    return {
        "schema": "phase-c-closeout-v1",
        "database": {"schema_revision": database["schema_revision"], **result},
        "runtime": _runtime(runtime),
        "candidate_boundary": "owner_supplies-target-outside-repository",
        "mutation_boundary": "domain-recovery-only-new-request-id",
        "stop_on_drift": True,
    }


def render_manifest(manifest: Mapping[str, object]) -> str:
    if set(manifest) != {
        "schema",
        "database",
        "runtime",
        "candidate_boundary",
        "mutation_boundary",
        "stop_on_drift",
    }:
        raise CloseoutEvidenceError("manifest fields are invalid")
    if (
        manifest.get("schema") != "phase-c-closeout-v1"
        or manifest.get("stop_on_drift") is not True
    ):
        raise CloseoutEvidenceError("manifest safety boundary is invalid")
    rendered = json.dumps(manifest, sort_keys=True)
    if re.search(
        r"(?:secret|token|password|https?://|postgres(?:ql)?://)", rendered, re.I
    ):
        raise CloseoutEvidenceError("manifest contains sensitive-looking content")
    return rendered
