"""Fail-closed, redacted Phase C identity-maintenance closeout evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
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
        "statement_logging_safe",
        "people_count",
        "member_count",
        "identity_count",
        "reliable_linked_line_count",
        "admin_principal_count",
        "identity_drift_count",
        "member_person_drift_count",
        "duplicate_person_link_count",
        "qualification_drift_count",
        "missing_identity_count",
        "wrong_person_link_count",
        "identity_without_reliable_link_count",
        "orphan_member_link_count",
        "team_player_missing_count",
        "team_player_extra_count",
        "team_player_revoked_mismatch_count",
        "active_team_player_count",
        "game_attendance_reply_count",
        "audit_count",
        "duplicate_request_id_count",
        "safe_ignore_candidate_count",
        "safe_unignore_candidate_count",
        "mutation_ignored_action_count",
        "mutation_other_action_count",
        "recovery_unignored_action_count",
        "recovery_other_action_count",
        "bounded_same_target_count",
    }
)
CSV_FIELDS = (
    "section",
    "metric",
    "status",
    "boolean_value",
    "integer_value",
    "text_value",
)
CSV_METRICS = {
    ("00_session", "transaction_read_only"): ("boolean_value", "true"),
    ("00_session", "statement_logging_safe"): ("boolean_value", "true"),
    ("01_schema", "revision"): ("text_value", "0004_phase_c_identity_lifecycle"),
    ("02_identity", "people_count"): ("integer_value", None),
    ("02_identity", "member_count"): ("integer_value", None),
    ("02_identity", "identity_count"): ("integer_value", None),
    ("02_identity", "reliable_linked_line_count"): ("integer_value", None),
    ("02_identity", "active_linked_allowlisted_admin_count"): ("integer_value", None),
    ("02_identity", "safe_ignore_candidate_count"): ("integer_value", None),
    ("02_identity", "safe_unignore_candidate_count"): ("integer_value", None),
    ("02_identity", "identity_drift_count"): ("integer_value", "0"),
    ("02_identity", "member_person_drift_count"): ("integer_value", "0"),
    ("02_identity", "duplicate_person_link_count"): ("integer_value", "0"),
    ("02_identity", "missing_identity_count"): ("integer_value", "0"),
    ("02_identity", "wrong_person_link_count"): ("integer_value", "0"),
    ("02_identity", "identity_without_reliable_link_count"): ("integer_value", "0"),
    ("02_identity", "orphan_member_link_count"): ("integer_value", "0"),
    ("03_audit", "access_audit_count"): ("integer_value", None),
    ("03_audit", "duplicate_request_id_count"): ("integer_value", "0"),
    ("03_audit", "mutation_ignored_action_count"): ("integer_value", None),
    ("03_audit", "mutation_other_action_count"): ("integer_value", "0"),
    ("03_audit", "recovery_unignored_action_count"): ("integer_value", None),
    ("03_audit", "recovery_other_action_count"): ("integer_value", "0"),
    ("03_audit", "bounded_same_target_count"): ("integer_value", None),
    ("04_qualification", "active_team_player_count"): ("integer_value", None),
    ("04_qualification", "qualification_drift_count"): ("integer_value", "0"),
    ("04_qualification", "team_player_missing_count"): ("integer_value", "0"),
    ("04_qualification", "team_player_extra_count"): ("integer_value", "0"),
    ("04_qualification", "team_player_revoked_mismatch_count"): ("integer_value", "0"),
    ("05_attendance", "game_attendance_reply_count"): ("integer_value", None),
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
    observed = {
        (section, metric)
        for section, metric in re.findall(
            r"(?:select|union all select)\s*'([^']+)'\s*,\s*'([^']+)'", sql
        )
    }
    if observed != set(CSV_METRICS):
        raise CloseoutEvidenceError("inventory metric contract is invalid")


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CloseoutEvidenceError(f"{label} is invalid")
    return value


def parse_inventory_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != CSV_FIELDS:
        raise CloseoutEvidenceError("inventory CSV header is invalid")
    return list(reader)


def ingest_inventory_rows(rows: list[dict[str, str]]) -> dict:
    """Strictly ingest every row emitted by the fixed sanitized SQL."""
    seen = {}
    for row in rows:
        if tuple(row) != CSV_FIELDS:
            raise CloseoutEvidenceError("inventory CSV columns are invalid")
        key = (row["section"], row["metric"])
        field, expected = CSV_METRICS.get(key, (None, None))
        values = [name for name in CSV_FIELDS[3:] if row[name] not in ("", "null")]
        expected_status = (
            "classification"
            if key[1].startswith("safe_")
            else (
                "bounded"
                if key[0] == "03_audit"
                and (
                    key[1].startswith("mutation_")
                    or key[1].startswith("recovery_")
                    or key[1] == "bounded_same_target_count"
                )
                else "required"
            )
        )
        if (
            key in seen
            or field is None
            or row["status"] != expected_status
            or values != [field]
            or (expected is not None and row[field] != expected)
        ):
            raise CloseoutEvidenceError("inventory CSV metric is invalid")
        if field == "integer_value" and not re.fullmatch(r"\d+", row[field]):
            raise CloseoutEvidenceError("inventory CSV count is invalid")
        seen[key] = row[field]
    if set(seen) != set(CSV_METRICS):
        raise CloseoutEvidenceError("inventory CSV is incomplete")
    return {
        "schema_revision": seen[("01_schema", "revision")],
        "statement_logging_safe": seen[("00_session", "statement_logging_safe")]
        == "true",
        "people_count": int(seen[("02_identity", "people_count")]),
        "member_count": int(seen[("02_identity", "member_count")]),
        "identity_count": int(seen[("02_identity", "identity_count")]),
        "reliable_linked_line_count": int(
            seen[("02_identity", "reliable_linked_line_count")]
        ),
        "admin_principal_count": int(
            seen[("02_identity", "active_linked_allowlisted_admin_count")]
        ),
        "identity_drift_count": int(seen[("02_identity", "identity_drift_count")]),
        "member_person_drift_count": int(
            seen[("02_identity", "member_person_drift_count")]
        ),
        "duplicate_person_link_count": int(
            seen[("02_identity", "duplicate_person_link_count")]
        ),
        "missing_identity_count": int(seen[("02_identity", "missing_identity_count")]),
        "wrong_person_link_count": int(
            seen[("02_identity", "wrong_person_link_count")]
        ),
        "identity_without_reliable_link_count": int(
            seen[("02_identity", "identity_without_reliable_link_count")]
        ),
        "orphan_member_link_count": int(
            seen[("02_identity", "orphan_member_link_count")]
        ),
        "qualification_drift_count": int(
            seen[("04_qualification", "qualification_drift_count")]
        ),
        "team_player_missing_count": int(
            seen[("04_qualification", "team_player_missing_count")]
        ),
        "team_player_extra_count": int(
            seen[("04_qualification", "team_player_extra_count")]
        ),
        "team_player_revoked_mismatch_count": int(
            seen[("04_qualification", "team_player_revoked_mismatch_count")]
        ),
        "active_team_player_count": int(
            seen[("04_qualification", "active_team_player_count")]
        ),
        "game_attendance_reply_count": int(
            seen[("05_attendance", "game_attendance_reply_count")]
        ),
        "audit_count": int(seen[("03_audit", "access_audit_count")]),
        "duplicate_request_id_count": int(
            seen[("03_audit", "duplicate_request_id_count")]
        ),
        "safe_ignore_candidate_count": int(
            seen[("02_identity", "safe_ignore_candidate_count")]
        ),
        "safe_unignore_candidate_count": int(
            seen[("02_identity", "safe_unignore_candidate_count")]
        ),
        "mutation_ignored_action_count": int(
            seen[("03_audit", "mutation_ignored_action_count")]
        ),
        "mutation_other_action_count": int(
            seen[("03_audit", "mutation_other_action_count")]
        ),
        "recovery_unignored_action_count": int(
            seen[("03_audit", "recovery_unignored_action_count")]
        ),
        "recovery_other_action_count": int(
            seen[("03_audit", "recovery_other_action_count")]
        ),
        "bounded_same_target_count": int(
            seen[("03_audit", "bounded_same_target_count")]
        ),
    }


def compare_sequence(
    before: Mapping[str, object],
    action: Mapping[str, object],
    retry: Mapping[str, object],
    recovery: Mapping[str, object],
    post: Mapping[str, object],
) -> None:
    """Require one action audit, no retry audit, one recovery audit and restored protected counts."""
    manifests = [
        build_manifest(item["database"], item["runtime"])
        for item in (before, action, retry, recovery, post)
    ]
    databases = [entry["database"] for entry in manifests]
    if any(
        manifest["runtime"] != manifests[0]["runtime"] for manifest in manifests[1:]
    ):
        raise CloseoutEvidenceError("runtime evidence drifted")
    counts = [entry["audit_count"] for entry in databases]
    if counts != [
        counts[0],
        counts[0] + 1,
        counts[0] + 1,
        counts[0] + 2,
        counts[0] + 2,
    ]:
        raise CloseoutEvidenceError("audit sequence is invalid")
    expected_actions = ((0, 0), (1, 0), (1, 0), (1, 1), (1, 1))
    expected_same_target = (0, 0, 0, 1, 1)
    if any(
        (item["mutation_ignored_action_count"], item["recovery_unignored_action_count"])
        != expected
        or item["mutation_other_action_count"] != 0
        or item["recovery_other_action_count"] != 0
        or item["bounded_same_target_count"] != same_target
        for item, expected, same_target in zip(
            databases, expected_actions, expected_same_target
        )
    ):
        raise CloseoutEvidenceError("bounded action sequence is invalid")
    protected = (
        "people_count",
        "member_count",
        "identity_count",
        "reliable_linked_line_count",
        "admin_principal_count",
        "identity_drift_count",
        "member_person_drift_count",
        "duplicate_person_link_count",
        "qualification_drift_count",
        "missing_identity_count",
        "wrong_person_link_count",
        "identity_without_reliable_link_count",
        "orphan_member_link_count",
        "team_player_missing_count",
        "team_player_extra_count",
        "team_player_revoked_mismatch_count",
        "active_team_player_count",
        "game_attendance_reply_count",
        "duplicate_request_id_count",
    )
    if any(
        database[field] != databases[0][field]
        for database in databases[1:]
        for field in protected
    ):
        raise CloseoutEvidenceError("protected closeout counts drifted")
    if (
        databases[0]["safe_ignore_candidate_count"] < 1
        or databases[1]["safe_ignore_candidate_count"]
        != databases[0]["safe_ignore_candidate_count"] - 1
        or databases[1]["safe_unignore_candidate_count"]
        != databases[0]["safe_unignore_candidate_count"] + 1
        or any(
            databases[phase][field] != databases[1][field]
            for phase in (2,)
            for field in (
                "safe_ignore_candidate_count",
                "safe_unignore_candidate_count",
            )
        )
        or databases[3]["safe_ignore_candidate_count"]
        != databases[0]["safe_ignore_candidate_count"]
        or databases[3]["safe_unignore_candidate_count"]
        != databases[0]["safe_unignore_candidate_count"]
        or any(
            databases[4][field] != databases[3][field]
            for field in (
                "safe_ignore_candidate_count",
                "safe_unignore_candidate_count",
            )
        )
    ):
        raise CloseoutEvidenceError("candidate classification did not recover")


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
    if database["statement_logging_safe"] is not True:
        raise CloseoutEvidenceError("statement logging boundary is unsafe")
    result = {
        name: _integer(database[name], name)
        for name in DATABASE_FIELDS
        if name not in ("schema_revision", "statement_logging_safe")
    }
    if result["admin_principal_count"] < 1:
        raise CloseoutEvidenceError("no active allowlisted admin classification")
    for name in (
        "identity_drift_count",
        "member_person_drift_count",
        "duplicate_person_link_count",
        "qualification_drift_count",
        "missing_identity_count",
        "wrong_person_link_count",
        "identity_without_reliable_link_count",
        "orphan_member_link_count",
        "team_player_missing_count",
        "team_player_extra_count",
        "team_player_revoked_mismatch_count",
        "duplicate_request_id_count",
    ):
        if result[name] != 0:
            raise CloseoutEvidenceError("database drift classification is unsafe")
    return {
        "schema": "phase-c-closeout-v1",
        "database": {
            "schema_revision": database["schema_revision"],
            "statement_logging_safe": True,
            **result,
        },
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
