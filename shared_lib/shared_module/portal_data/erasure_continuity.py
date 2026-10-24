"""Read operator-approved deadline extensions without changing original evidence.

The caller must already hold the canonical locks and exact request row in the
same transaction. No receipt/proof/effect authority is created here. A valid
extension does not prove key custody, backup expiry, or permission to purge.
"""

import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

REVISION = "0021_erasure_continuity"
LEGACY = frozenset(
    {
        ("0015_account_generations",),
        ("0016_erasure_cancellation",),
        ("0017_erasure_work_items",),
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
    }
)


class ContinuityUnavailable(RuntimeError):
    """Fixed integrity/infrastructure failure, with no private input details."""


@dataclass(frozen=True, repr=False)
class EffectiveDeadlines:
    receipt_until: datetime
    evidence_until: datetime


def _reject():
    raise ContinuityUnavailable("continuity_unavailable") from None


def _instant(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _reject()
    return value.astimezone(timezone.utc)


def effective_expiry(connection, root, field, *, revisions=None):
    """Compatibility boundary: never query candidate tables on old revisions."""
    if field not in {"receipt_expires_at", "evidence_expires_at"}:
        _reject()
    try:
        if revisions is None:
            revisions = tuple(
                connection.scalars(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ).all()
            )
        if revisions in LEGACY:
            return _instant(root[field])
        deadlines = effective_deadlines(connection, root, revisions=revisions)
        return (
            deadlines.receipt_until
            if field == "receipt_expires_at"
            else deadlines.evidence_until
        )
    except ContinuityUnavailable:
        raise
    except Exception:
        _reject()


def effective_deadlines(connection, root, *, revisions):
    """Check the complete append-only chain; never overwrite the root mapping."""
    try:
        if (
            not isinstance(connection, Connection)
            or connection.in_transaction() is not True
            or connection.get_isolation_level() != "READ COMMITTED"
            or connection.connection.dbapi_connection.autocommit is not False
            or revisions not in LEGACY | {(REVISION,), ("0022_erasure_retention",)}
        ):
            _reject()
        receipt = _instant(root["receipt_expires_at"])
        evidence = _instant(root["evidence_expires_at"])
        requested = _instant(root["requested_at"])
        if receipt <= requested or evidence < receipt:
            _reject()
        if revisions in LEGACY:
            return EffectiveDeadlines(receipt, evidence)
        identifier = str(root["id"])
        generation = str(root["expected_generation"])
        if (
            str(UUID(identifier)) != identifier
            or str(UUID(generation)) != generation
            or root["target_kind"] not in {"person", "pending_identity"}
            or type(root["receipt_secret_hash"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", root["receipt_secret_hash"]) is None
            or connection.scalar(
                text(
                    "SELECT pg_catalog.row_security_active('ntubtob.account_erasure_continuity_events'::regclass)"
                )
            )
            is not False
        ):
            _reject()
        rows = (
            connection.execute(
                text(
                    "SELECT * FROM ntubtob.account_erasure_continuity_events "
                    "WHERE request_id=:id ORDER BY sequence FOR SHARE"
                ),
                {"id": identifier},
            )
            .mappings()
            .all()
        )
        previous_time = requested
        for sequence, event in enumerate(rows, 1):
            occurred = _instant(event["occurred_at"])
            next_receipt = _instant(event["receipt_until"])
            next_evidence = _instant(event["evidence_until"])
            if (
                str(event["request_id"]) != identifier
                or event["target_kind"] != root["target_kind"]
                or str(event["expected_generation"]) != generation
                or _instant(event["original_requested_at"]) != requested
                or not hmac.compare_digest(
                    event["original_receipt_hash"], root["receipt_secret_hash"]
                )
                or type(event["sequence"]) is not int
                or event["sequence"] != sequence
                or _instant(event["previous_receipt_until"]) != receipt
                or _instant(event["previous_evidence_until"]) != evidence
                or not previous_time <= occurred < receipt
                or next_receipt <= receipt
                or next_evidence < max(evidence, next_receipt)
            ):
                _reject()
            receipt, evidence, previous_time = next_receipt, next_evidence, occurred
        return EffectiveDeadlines(receipt, evidence)
    except ContinuityUnavailable:
        raise
    except Exception:
        _reject()
