"""Pure TASK203-WIRE-01 retention eligibility, not a cleanup capability.

Trusted composition must bind observations to the exact environment/request/
generation and persist independently reviewed inventory evidence. A constructed
DTO, clock, expiry date or True flag is NOT proof of custody, authorization,
complete backup absence or successful deletion. This module performs no I/O,
renewal, dispatch, key destruction, runtime enablement or SQL mutation.

The global dispatch gate must aggregate block_new_irreversible over ALL retained
requests, not only the current job. It must preserve intake/receipt/cancellation
and completion/reconciliation of effects already durably started. SQL enforcement,
private operator permissions, durable cleanup fences and exact-copy readback are
separate requirements; do not wire this helper directly to an untrusted payload.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_STATUSES = frozenset(
    {
        "requested",
        "verified",
        "processing",
        "needs_attention",
        "online_completed",
        "completed",
        "cancelled",
    }
)


class RetentionRejected(ValueError):
    """Fixed invalid trusted-fact diagnostic; no request or inventory details."""


def retention_failure_reason(error):
    """Expose only exact literal server checks, never raw DB/provider messages."""
    message = getattr(
        getattr(getattr(error, "orig", None), "diag", None), "message_primary", None
    )
    if type(message) is str and message in {
        "retention_backup_horizon_unresolved",
        "retention_schema_not_ready",
        "retention_unfiltered_state_required",
        "retention_transaction_rejected",
    }:
        return message
    return None


@dataclass(frozen=True, repr=False)
class BackupObservation:
    checked_at: datetime
    inventory_complete: bool
    last_restorable_until: datetime | None
    suppression_verified_at: datetime | None
    binding_readable: bool
    key_readable: bool


@dataclass(frozen=True, repr=False)
class RetentionFacts:
    requested_at: datetime
    status: str
    online_completed_at: datetime | None
    receipt_until: datetime
    evidence_until: datetime
    unresolved_effects: bool
    executor_needs_plan: bool
    authority_target_detached: bool
    backup: BackupObservation | None


@dataclass(frozen=True)
class RetentionDecision:
    private_plan_due: bool
    minimal_evidence_eligible: bool
    block_new_irreversible: bool
    next_action: str


def _reject():
    raise RetentionRejected("retention_input_rejected") from None


def _instant(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _reject()
    return value.astimezone(timezone.utc)


def _boolean(value):
    if type(value) is not bool:
        _reject()


def evaluate_retention(facts, *, now):
    """Return eligibility only; stale/unknown inventory is never zero retention.

    online+30 controls identifiable working copies, not the shared encryption
    key. Request+180 and effective receipt/evidence expiry are necessary but not
    sufficient for minimal-ledger cleanup. An unfinished request is retained;
    continuity is a separate explicit operator action, never automatic here.
    """
    if type(facts) is not RetentionFacts:
        _reject()
    now = _instant(now)
    requested = _instant(facts.requested_at)
    receipt = _instant(facts.receipt_until)
    evidence = _instant(facts.evidence_until)
    if (
        type(facts.status) is not str
        or facts.status not in _STATUSES
        or requested > now
        or receipt <= requested
        or evidence < receipt
    ):
        _reject()
    for value in (
        facts.unresolved_effects,
        facts.executor_needs_plan,
        facts.authority_target_detached,
    ):
        _boolean(value)
    online = facts.online_completed_at
    if online is not None:
        online = _instant(online)
        if not requested <= online <= now:
            _reject()
    if facts.status in {"online_completed", "completed"} and online is None:
        _reject()

    custody_ready = horizon_known = suppression_ready = False
    backup = facts.backup
    if backup is not None:
        if type(backup) is not BackupObservation:
            _reject()
        checked = _instant(backup.checked_at)
        if not requested <= checked <= now:
            _reject()
        for value in (
            backup.inventory_complete,
            backup.binding_readable,
            backup.key_readable,
        ):
            _boolean(value)
        horizon = backup.last_restorable_until
        if horizon is not None:
            horizon = _instant(horizon)
        verified = backup.suppression_verified_at
        if verified is not None:
            verified = _instant(verified)
            if not requested <= verified <= checked:
                _reject()
        fresh = now - checked <= timedelta(days=30)
        custody_ready = fresh and backup.binding_readable and backup.key_readable
        horizon_known = (
            custody_ready and backup.inventory_complete and horizon is not None
        )
        suppression_ready = (
            horizon_known
            and horizon <= now
            and verified is not None
            and verified >= horizon
        )
    no_pending_work = not facts.unresolved_effects and not facts.executor_needs_plan
    plan_due = (
        facts.status in {"online_completed", "completed"}
        and online is not None
        and now - online >= timedelta(days=30)
        and no_pending_work
        and custody_ready
    )
    minimal = (
        facts.status in {"completed", "cancelled"}
        and now - requested >= timedelta(days=180)
        and now >= evidence
        and no_pending_work
        and facts.authority_target_detached
        and suppression_ready
    )
    block = now - requested >= timedelta(days=150) and not horizon_known
    return RetentionDecision(
        bool(plan_due),
        bool(minimal),
        bool(block),
        "inventory_exception_review" if block else "authorized_custody_review",
    )
