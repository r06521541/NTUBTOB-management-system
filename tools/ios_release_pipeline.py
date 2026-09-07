"""Secret-free iOS lifecycle rehearsal; no live adapter or private input.

Every operation below is a simulation, including cleanup and Apple processing.
This tool cannot build, sign, upload, provision or authorize a real candidate.
The existing hosted Flutter job separately proves no-codesign compilation.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Sequence

_SHA = re.compile(r"[0-9a-f]{40}")
STAGES = ("stage_material", "build", "inspect", "upload", "processing")
SCENARIOS = (
    "success",
    "stage_failure",
    "build_failure",
    "inspection_failure",
    "upload_rejected",
    "upload_uncertain",
    "processing_pending",
    "cleanup_failure",
)


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "ERROR: rehearsal arguments are invalid\n")


def rehearse(
    *,
    expected_commit: str,
    checkout_commit: str,
    scenario: str = "success",
) -> dict[str, object]:
    """Exercise fictional sequencing only; never accept live keys or adapters."""
    result: dict[str, object] = {
        "schema": 1,
        "classification": "STOP",
        "evidence_scope": "fictional_rehearsal",
        "reason": "INVALID_CONTRACT",
        "external_mutation_count": 0,
        "signed_artifact_created": False,
        "upload_authorized": False,
        "release_authorized": False,
        "provider_runtime_verified": False,
        "real_device_verified": False,
        "simulated_trace": [],
        "simulated_cleanup": "not_needed",
        "simulated_upload_attempts": 0,
        "retry_allowed": False,
        "next_action": "correct_contract",
    }
    if (
        not isinstance(expected_commit, str)
        or not _SHA.fullmatch(expected_commit)
        or expected_commit == "0" * 40
        or not isinstance(checkout_commit, str)
        or not _SHA.fullmatch(checkout_commit)
        or scenario not in SCENARIOS
    ):
        return result
    if expected_commit != checkout_commit:
        result["reason"] = "COMMIT_MISMATCH"
        return result
    result["commit"] = expected_commit
    trace = ["preflight"]
    result["simulated_trace"] = trace
    # Simulate partial material staging as well as fully staged resources. Once
    # attempted, cleanup runs even if staging/build/inspection/upload fails.
    material_attempted = False
    failures = {
        "stage_failure": ("stage_material", "MATERIAL_STAGING_FAILED"),
        "build_failure": ("build", "BUILD_FAILED"),
        "inspection_failure": ("inspect", "ARTIFACT_REJECTED"),
        "upload_rejected": ("upload", "UPLOAD_REJECTED"),
        "upload_uncertain": ("upload", "UPLOAD_UNCERTAIN"),
        "processing_pending": ("processing", "PROCESSING_PENDING"),
    }
    try:
        for stage in STAGES:
            trace.append(stage)
            if stage == "stage_material":
                material_attempted = True
            if stage == "upload":
                result["simulated_upload_attempts"] = 1
            failure = failures.get(scenario)
            if failure is not None and failure[0] == stage:
                result["reason"] = failure[1]
                result["next_action"] = (
                    "read_only_reconcile"
                    if scenario in {"upload_uncertain", "processing_pending"}
                    else "review_failure"
                )
                return result
        result["classification"] = "REHEARSAL_COMPLETE"
        result["reason"] = "FICTIONAL_ONLY"
        result["next_action"] = "owner_gate_before_live_work"
        return result
    finally:
        if material_attempted:
            trace.append("cleanup")
            result["simulated_cleanup"] = "completed"
            if scenario == "cleanup_failure":
                result["classification"] = "STOP"
                result["reason"] = "CLEANUP_FAILED"
                result["simulated_cleanup"] = "failed"
                result["next_action"] = "security_review"


def main(argv: Sequence[str] | None = None) -> int:
    # Deliberately no --execute, private paths, credentials or live adapter.
    parser = _SafeParser(description=__doc__)
    parser.add_argument("action", choices=("rehearse",))
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--checkout-commit", required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, default="success")
    arguments = parser.parse_args(argv)
    result = rehearse(
        expected_commit=arguments.expected_commit,
        checkout_commit=arguments.checkout_commit,
        scenario=arguments.scenario,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["classification"] == "REHEARSAL_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
