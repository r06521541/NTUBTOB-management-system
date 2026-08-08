"""Render a redacted, local-only Phase C activation release manifest."""

from __future__ import annotations

import json
import re
from typing import Mapping

from tools import phase_c_transition_controller as transition


SERVICE_REVISIONS = {
    "web_portal": re.compile(r"^web-portal-[a-z0-9-]+$"),
    "line_webhook": re.compile(r"^line-webhook-handler-[a-z0-9-]+$"),
    "notify_cron": re.compile(r"^notify-cronjob-service-[a-z0-9-]+$"),
}
STOP_CRITERIA = (
    "flag_or_revision_drift",
    "mixed_unfrozen_state",
    "readiness_or_private_boundary_failure",
    "unexpected_attendance_or_notification_effect",
)


class ReleaseManifestError(RuntimeError):
    """A safe-to-report local release-manifest validation failure."""


def _revisions(values: Mapping[str, str], label: str) -> dict[str, str]:
    if set(values) != set(SERVICE_REVISIONS):
        raise ReleaseManifestError(f"{label} must name every rollout service")
    result = {}
    for service, pattern in SERVICE_REVISIONS.items():
        value = values[service]
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            raise ReleaseManifestError(f"{label} contains an invalid revision")
        result[service] = value
    return result


def build_manifest(
    current: transition.RolloutVector,
    target: transition.RolloutVector,
    *,
    source_commit: str,
    expected_source_commit: str,
    artifact_fingerprint: str,
    expected_artifact_fingerprint: str,
    current_revisions: Mapping[str, str],
    rollback_revisions: Mapping[str, str],
) -> dict:
    """Return bounded release evidence without env, Secret or identity data."""
    try:
        plan = transition.plan_transition(
            current,
            target,
            source_commit=source_commit,
            expected_source_commit=expected_source_commit,
            artifact_fingerprint=artifact_fingerprint,
            expected_artifact_fingerprint=expected_artifact_fingerprint,
        )
    except transition.TransitionPlanError as error:
        raise ReleaseManifestError(str(error)) from error
    return {
        "schema": "phase-c-release-manifest-v1",
        "source_commit": plan.source_commit,
        "artifact_fingerprint": plan.artifact_fingerprint,
        "current_revisions": _revisions(current_revisions, "current revisions"),
        "rollback_revisions": _revisions(rollback_revisions, "rollback revisions"),
        "current_mode": plan.current_mode,
        "target_mode": plan.target_mode,
        "direction": plan.direction,
        "steps": [
            {"service": step.service, "flag": step.flag, "value": step.value}
            for step in plan.steps
        ],
        "scheduler_boundary": "no_scheduler_mutation_or_invocation",
        "observation_minutes": {"per_step": 15, "all_on": 30},
        "stop_criteria": STOP_CRITERIA,
    }


def render_manifest(manifest: Mapping[str, object]) -> str:
    """Render the fixed manifest schema without accepting arbitrary payloads."""
    allowed = {
        "schema",
        "source_commit",
        "artifact_fingerprint",
        "current_revisions",
        "rollback_revisions",
        "current_mode",
        "target_mode",
        "direction",
        "steps",
        "scheduler_boundary",
        "observation_minutes",
        "stop_criteria",
    }
    if set(manifest) != allowed:
        raise ReleaseManifestError("manifest contains unsupported fields")
    return json.dumps(manifest, sort_keys=True)
