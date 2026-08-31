"""Validate deidentified Android Closed Testing evidence without side effects.

The input is an externally prepared JSON record.  This module does not log in,
build, sign, upload, call a network service, or operate Play Console.  Successful
validation means only that the supplied record satisfies the repository evidence
contract; it does not independently establish that an external observation is true.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "android-closed-testing-evidence-v1"
PACKAGE_NAME = "tw.org.ntubtob.portal"
MAX_EVIDENCE_BYTES = 262_144
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]+\.[0-9]+$")
EVIDENCE_REF = re.compile(r"^EV-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
FORBIDDEN_VALUE = re.compile(
    r"(?i)(://|@|-----BEGIN|bearer\s|secret|password|token|keystore|"
    r"private[_ -]?key|client[_ -]?id|provider[_ -]?id|endpoint)"
)
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "channel",
        "reviewed_commit_sha",
        "artifact",
        "signer",
        "runtime",
        "scope",
        "compliance",
        "device_matrix",
        "track",
        "remaining_blockers",
    }
)
SCENARIOS = frozenset(
    {
        "install",
        "upgrade",
        "cold_start",
        "line_login",
        "google_login",
        "refresh",
        "logout",
        "schedule_event_attendance",
        "offline",
    }
)
OPTIONAL_PROVIDER_SCENARIOS = frozenset({"line_login", "google_login"})


class EvidenceError(ValueError):
    """A safe-to-report Closed Testing evidence validation failure."""


def _fail(message: str) -> None:
    raise EvidenceError(message)


def _mapping(
    value: object, fields: set[str] | frozenset[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != set(fields):
        _fail(f"{label} fields are incomplete or unsupported")
    return value


def _safe_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or EVIDENCE_REF.fullmatch(value) is None:
        _fail(f"{label} must be a deidentified evidence reference")
    return value


def _scan_values(value: object) -> None:
    if isinstance(value, str):
        if FORBIDDEN_VALUE.search(value):
            _fail("evidence contains a forbidden sensitive-shaped value")
    elif isinstance(value, dict):
        for child in value.values():
            _scan_values(child)
    elif isinstance(value, list):
        for child in value:
            _scan_values(child)


def _exact(value: object, expected: object, label: str) -> None:
    if value != expected or type(value) is not type(expected):
        _fail(f"{label} does not match the Closed Testing contract")


def _validate_artifact(value: object) -> dict[str, object]:
    artifact = _mapping(
        value,
        {
            "package_name",
            "version_name",
            "version_code",
            "previous_version_code",
            "sha256",
            "strict_inspection",
        },
        "artifact",
    )
    _exact(artifact["package_name"], PACKAGE_NAME, "artifact package")
    if (
        not isinstance(artifact["version_name"], str)
        or SEMVER.fullmatch(artifact["version_name"]) is None
        or artifact["version_name"] == "0.0.0"
    ):
        _fail("artifact version_name must be a non-debug semantic version")
    version_code = artifact["version_code"]
    if type(version_code) is not int or version_code < 1:
        _fail("artifact version_code must be a positive integer")
    previous_version_code = artifact["previous_version_code"]
    if (
        type(previous_version_code) is not int
        or previous_version_code < 0
        or version_code <= previous_version_code
    ):
        _fail("artifact version_code must be greater than the prior track version")
    if (
        not isinstance(artifact["sha256"], str)
        or SHA256.fullmatch(artifact["sha256"]) is None
    ):
        _fail("artifact sha256 must be a lowercase SHA-256")
    _exact(artifact["strict_inspection"], "passed", "artifact inspection")
    return dict(artifact)


def _validate_signer(value: object) -> None:
    signer = _mapping(
        value,
        {"expected_sha256", "observed_sha256", "comparison", "evidence_ref"},
        "signer",
    )
    for field in ("expected_sha256", "observed_sha256"):
        if (
            not isinstance(signer[field], str)
            or SHA256.fullmatch(signer[field]) is None
        ):
            _fail("signer fingerprint must be a lowercase SHA-256")
    if signer["expected_sha256"] != signer["observed_sha256"]:
        _fail("signer fingerprint comparison did not match")
    _exact(signer["comparison"], "match", "signer comparison")
    _safe_ref(signer["evidence_ref"], "signer evidence_ref")


def _validate_runtime(value: object) -> None:
    runtime = _mapping(
        value,
        {
            "environment",
            "client_mode",
            "data_scope",
            "production_access",
            "evidence_ref",
        },
        "runtime",
    )
    _exact(runtime["environment"], "staging", "runtime environment")
    _exact(runtime["client_mode"], "real", "runtime client mode")
    _exact(runtime["data_scope"], "isolated-test-data", "runtime data scope")
    _exact(runtime["production_access"], False, "runtime production access")
    _safe_ref(runtime["evidence_ref"], "runtime evidence_ref")


def _validate_scope(value: object) -> None:
    scope = _mapping(
        value,
        {
            "release_scope",
            "officer_admin",
            "push_delivery",
            "deep_link_delivery",
            "anonymous_crash_reporting",
        },
        "scope",
    )
    _exact(scope["release_scope"], "basic-only", "release scope")
    for field in (
        "officer_admin",
        "push_delivery",
        "deep_link_delivery",
        "anonymous_crash_reporting",
    ):
        _exact(scope[field], False, f"scope {field}")


def _validate_compliance(value: object, unavailable: list[str]) -> None:
    compliance = _mapping(
        value,
        {"data_safety", "privacy", "support", "deletion", "tester_notes"},
        "compliance",
    )
    evidence_refs: list[str] = []
    for name in ("data_safety", "privacy", "support", "deletion"):
        item = _mapping(compliance[name], {"status", "evidence_ref"}, name)
        _exact(item["status"], "verified", f"{name} status")
        evidence_refs.append(_safe_ref(item["evidence_ref"], f"{name} evidence_ref"))

    notes = _mapping(
        compliance["tester_notes"],
        {
            "status",
            "evidence_ref",
            "declares_staging",
            "declares_basic_only",
            "declares_no_push",
            "declares_no_deep_link_delivery",
            "declares_no_crash_reporting",
            "unavailable_provider_scenarios",
        },
        "tester_notes",
    )
    _exact(notes["status"], "verified", "tester_notes status")
    evidence_refs.append(_safe_ref(notes["evidence_ref"], "tester_notes evidence_ref"))
    if len(evidence_refs) != len(set(evidence_refs)):
        _fail("compliance evidence references must be distinct")
    for field in (
        "declares_staging",
        "declares_basic_only",
        "declares_no_push",
        "declares_no_deep_link_delivery",
        "declares_no_crash_reporting",
    ):
        _exact(notes[field], True, f"tester_notes {field}")
    if notes["unavailable_provider_scenarios"] != unavailable:
        _fail(
            "tester_notes unavailable provider scenarios do not match device evidence"
        )


def _validate_device_matrix(value: object, artifact_sha256: str) -> list[str]:
    matrix = _mapping(
        value,
        {
            "artifact_sha256",
            "device_class",
            "os_major",
            "device_identifier_recorded",
            "test_data",
            "scenarios",
        },
        "device_matrix",
    )
    _exact(matrix["artifact_sha256"], artifact_sha256, "device artifact sha256")
    _exact(matrix["device_class"], "android-phone", "device class")
    _exact(matrix["os_major"], 15, "device OS major")
    _exact(matrix["device_identifier_recorded"], False, "device identifier boundary")
    _exact(matrix["test_data"], "fictional", "device test data")
    scenarios = _mapping(matrix["scenarios"], SCENARIOS, "device scenarios")

    unavailable: list[str] = []
    for name in sorted(SCENARIOS):
        item = _mapping(scenarios[name], {"result", "evidence_ref"}, f"scenario {name}")
        result = item["result"]
        if result == "unavailable" and name in OPTIONAL_PROVIDER_SCENARIOS:
            unavailable.append(name)
        elif result != "passed":
            _fail(f"device scenario {name} has no acceptable result")
        _safe_ref(item["evidence_ref"], f"scenario {name} evidence_ref")
    return unavailable


def _validate_track(value: object, artifact: Mapping[str, object]) -> None:
    track = _mapping(
        value,
        {
            "name",
            "processing_state",
            "package_name",
            "version_name",
            "version_code",
            "artifact_sha256",
            "open_testing",
            "production_rollout",
            "tester_notification",
            "evidence_ref",
        },
        "track",
    )
    expected = {
        "name": "closed",
        "processing_state": "available-to-closed-testers",
        "package_name": artifact["package_name"],
        "version_name": artifact["version_name"],
        "version_code": artifact["version_code"],
        "artifact_sha256": artifact["sha256"],
        "open_testing": False,
        "production_rollout": False,
        "tester_notification": "not-performed",
    }
    for field, expected_value in expected.items():
        _exact(track[field], expected_value, f"track {field}")
    _safe_ref(track["evidence_ref"], "track evidence_ref")


def validate_evidence(value: object) -> dict[str, object]:
    """Validate an already collected, deidentified evidence record.

    The returned summary deliberately omits signer fingerprints and evidence
    references.  Validation errors never echo caller-controlled values.
    """
    evidence = _mapping(value, TOP_LEVEL_FIELDS, "evidence")
    _scan_values(evidence)
    _exact(evidence["schema"], SCHEMA, "schema")
    _exact(evidence["channel"], "android-closed", "channel")
    if (
        not isinstance(evidence["reviewed_commit_sha"], str)
        or COMMIT_SHA.fullmatch(evidence["reviewed_commit_sha"]) is None
    ):
        _fail("reviewed_commit_sha must be a lowercase 40-character SHA")
    artifact = _validate_artifact(evidence["artifact"])
    _validate_signer(evidence["signer"])
    _validate_runtime(evidence["runtime"])
    _validate_scope(evidence["scope"])
    unavailable = _validate_device_matrix(
        evidence["device_matrix"], str(artifact["sha256"])
    )
    _validate_compliance(evidence["compliance"], unavailable)
    _validate_track(evidence["track"], artifact)
    _exact(evidence["remaining_blockers"], [], "remaining blockers")
    return {
        "schema": SCHEMA,
        "result": "validated",
        "channel": "android-closed",
        "reviewed_commit_sha": evidence["reviewed_commit_sha"],
        "package_name": artifact["package_name"],
        "version_name": artifact["version_name"],
        "version_code": artifact["version_code"],
        "artifact_sha256": artifact["sha256"],
        "signer_match": True,
        "runtime": "staging-isolated",
        "release_scope": "basic-only",
        "device_os_major": 15,
        "track_state": "closed/available-to-closed-testers",
        "external_truth_attested": False,
    }


def _no_duplicate_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("evidence JSON contains a duplicate key")
        result[key] = value
    return result


def load_evidence(path: Path) -> object:
    """Load one bounded UTF-8 JSON input without following a non-file target."""
    if not path.is_file() or path.is_symlink():
        _fail("evidence input must be an existing regular file")
    size = path.stat().st_size
    if size < 1 or size > MAX_EVIDENCE_BYTES:
        _fail("evidence input is empty or exceeds the size limit")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        _fail("evidence input has forbidden encoding markers")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except UnicodeDecodeError as error:
        raise EvidenceError("evidence input is not UTF-8") from error
    except json.JSONDecodeError as error:
        raise EvidenceError("evidence input is not valid JSON") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate local, deidentified Android Closed Testing evidence."
    )
    parser.add_argument(
        "evidence", type=Path, help="Path to an external JSON evidence record"
    )
    args = parser.parse_args(argv)
    try:
        summary = validate_evidence(load_evidence(args.evidence))
    except EvidenceError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("BLOCKED: unable to read evidence input", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
