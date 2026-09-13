"""Finite diagnostics only: no raw exceptions, values or implicit authority."""

_CHECKS = {
    "source_preflight": {"source"},
    "journal_preflight": {"journal_path", "existing_journal", "journal_integrity"},
    "saved_inputs": {"settings"},
    "asc_preflight": {"asc_scope"},
    "signing_input": {"signing_material"},
    "frame_validation": {"frames"},
    "journal_open": {"journal_path", "journal_integrity"},
    "journal_start": {"journal_write"},
    "dispatch_preflight": {
        "github_user",
        "repository",
        "main_head",
        "workflow",
        "environment",
        "admin_bypass",
        "branch_policy",
        "reviewers",
        "protection_rules",
        "policy_identity",
        "secret_inventory",
        "secret_absence",
        "dispatch_result",
    },
    "dispatch_request": {"dispatch_result"},
    "awaiting_job": {"run_binding", "pending_approval", "job_status"},
    "secret_transfer": {
        "secret_inventory",
        "secret_absence",
        "secret_public_key",
        "frames",
        "secret_write",
    },
    "approval": {
        "secret_binding",
        "run_binding",
        "pending_approval",
        "job_status",
        "approval_result",
    },
    "observe_run": {"run_binding", "job_status"},
    "artifact_verification": {"artifact", "run_binding", "job_status"},
    "apple_reconcile": {"apple_result"},
    "cancel": {"run_binding", "cancel_result"},
    "cleanup": {"retention", "secret_inventory", "secret_delete", "secret_absence"},
    "recovery": {
        "run_binding",
        "run_listing",
        "journal_integrity",
        "existing_journal",
        "source",
    },
    "unknown": set(),
}
STAGES = frozenset(_CHECKS)
CHECKS = frozenset().union(*_CHECKS.values(), {"unexpected", "journal_write"})
_COMMON = frozenset(
    {"CHECK_REJECTED", "UNEXPECTED_INTERNAL_ERROR", "INTERRUPTED", "READ_ONLY_REQUIRED"}
)
_HTTP = frozenset(
    {
        "HTTP_UNAUTHENTICATED",
        "HTTP_FORBIDDEN",
        "HTTP_NOT_FOUND",
        "HTTP_RATE_LIMITED",
        "HTTP_SERVER_ERROR",
        "HTTP_STATUS_REJECTED",
        "TRANSPORT_TIMEOUT",
        "TRANSPORT_REJECTED",
        "REQUEST_BUDGET_EXHAUSTED",
        "DEADLINE_EXCEEDED",
    }
)
REASONS = (
    _COMMON
    | _HTTP
    | {"JOURNAL_REJECTED", "EXISTING_OPERATION", "LEGACY_REASON_UNAVAILABLE"}
)
_NETWORK_CHECKS = frozenset().union(
    *(
        _CHECKS[s]
        for s in (
            "dispatch_preflight",
            "dispatch_request",
            "awaiting_job",
            "secret_transfer",
            "approval",
            "observe_run",
            "artifact_verification",
            "cancel",
            "cleanup",
            "recovery",
        )
    )
) - {"source", "journal_integrity", "existing_journal", "frames"}


def valid(value):
    if (
        type(value) is not dict
        or set(value) != {"stage", "check", "reason"}
        or any(type(v) is not str for v in value.values())
    ):
        return False
    stage, check, reason = value["stage"], value["check"], value["reason"]
    if stage not in STAGES or check not in (
        _CHECKS[stage] | {"unexpected", "journal_write"}
    ):
        return False
    if reason in _COMMON:
        return True
    if reason in _HTTP:
        return check in _NETWORK_CHECKS
    if reason == "JOURNAL_REJECTED":
        return check in {
            "journal_path",
            "journal_integrity",
            "journal_write",
            "existing_journal",
        }
    if reason == "EXISTING_OPERATION":
        return check in {"journal_path", "existing_journal"}
    return (
        reason == "LEGACY_REASON_UNAVAILABLE"
        and stage in {"recovery", "unknown"}
        and check in {"unexpected", "journal_integrity", "existing_journal"}
    )


def sanitize(value):
    return dict(value) if valid(value) else None


def failure(stage, check, reason):
    value = {"stage": stage, "check": check, "reason": reason}
    return sanitize(value) or {
        "stage": "unknown",
        "check": "unexpected",
        "reason": "UNEXPECTED_INTERNAL_ERROR",
    }
