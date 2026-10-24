"""Default-unused trusted request-plan composition, not a runtime factory.

Both callbacks are PREAUTHORIZED local read-only code. They must not open a
transaction, mutate data, perform external I/O, or infer permission from a JSON
payload. This builder checks binding/shape, not reviewer authority or completeness
of a free-text search. Missing review is never an empty approval. Explicitly
reviewed empty input is valid only if the existing capture finds no required rows.

Use only before initial request insertion, on that repository's same Connection.
The repository owns commit and sealed-plan custody; an existing job must load its
original plan instead. Explicit policy metadata does not establish key custody,
retention enforcement, provider dispatch, worker, or public/native enablement.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..erasure_restore_binding import RestoreBindingCodec, RestoreBindingUnavailable
from .erasure_fulfillment import (
    SCOPE_VERSION,
    PendingIdentitySnapshot,
    _connection,
    _hash,
    capture_pending_snapshot,
)
from .erasure_person_fulfillment import PersonSnapshot, capture_person_snapshot
from .erasure_provider_execution import _Rejected
from .erasure_request import (
    CapturedErasureRequestPlan,
    ErasureRequestPlan,
    ErasureRequestRejected,
    _instant,
)
from .erasure_review_input import ReviewInputRejected, import_person_review


class ErasurePlanRejected(ValueError):
    """Fixed invalid/missing/stale trusted input; no values in diagnostics."""


class ErasurePlanUnavailable(RuntimeError):
    """Capture or trusted source unavailable; no automatic retry permission."""


@dataclass(frozen=True)
class ErasurePlanPolicy:
    """Approved metadata only; construction never enables automatic cleanup."""

    retention_policy_version: int
    fulfillment_due_at: datetime
    receipt_expires_at: datetime
    evidence_expires_at: datetime

    @classmethod
    def initial_request(cls, requested_at):
        """TASK203-WIRE-01 initial horizons, not runtime or purge authority.

        Unfinished receipts need controlled continuity; restore suppression
        remains bound to actual restorable-copy expiry, not these dates.
        """
        try:
            requested_at = _instant(requested_at)
            receipt_expires_at = requested_at + timedelta(days=180)
            return cls(
                retention_policy_version=20261019,
                fulfillment_due_at=requested_at + timedelta(days=30),
                receipt_expires_at=receipt_expires_at,
                evidence_expires_at=receipt_expires_at,
            )
        except (ErasureRequestRejected, OverflowError):
            _reject()


def _reject():
    raise ErasurePlanRejected("plan_capture_rejected") from None


def _identifier(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        _reject()


def _canonical_uuid(value):
    try:
        if type(value) is str and str(UUID(value)) == value:
            return
    except ValueError:
        pass
    _reject()


class TrustedErasurePlanBuilder:
    """Fixed Person / supported pending capture from explicit trusted sources.

    Callbacks receive keyword arguments connection, job_id, person_id,
    identity_id, target_generation, requested_at. review_source returns the
    already authorized Person review bytes for import_person_review, or the
    exact tuple of reviewed pending access-audit (id, digest) rows. None rejects.
    policy_source returns ErasurePlanPolicy, never a caller-selected scope hash.

    restore_codec and provider_audiences are trusted configuration. Bindings are
    derived from the actual locked identities, never accepted from a client.
    """

    def __init__(
        self, *, review_source, policy_source, restore_codec, provider_audiences
    ):
        if (
            not callable(review_source)
            or not callable(policy_source)
            or type(restore_codec) is not RestoreBindingCodec
            or type(provider_audiences) is not dict
            or not provider_audiences
        ):
            _reject()
        for provider, audience in provider_audiences.items():
            if (
                type(provider) is not str
                or provider not in {"apple", "google", "line"}
                or type(audience) is not str
                or not 1 <= len(audience) <= 255
                or any(
                    ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
                    for char in audience
                )
            ):
                _reject()
        self._review_source = review_source
        self._policy_source = policy_source
        self._restore_codec = restore_codec
        self._provider_audiences = dict(provider_audiences)

    def intake_policy(self, **values):
        """Explicit policy only; never invoke human review or capture at intake."""
        return self._policy_source(**values)

    def __call__(
        self,
        *,
        connection,
        job_id,
        person_id,
        identity_id,
        target_generation,
        requested_at,
    ):
        try:
            _canonical_uuid(job_id)
            _canonical_uuid(target_generation)
            _identifier(identity_id)
            if person_id is not None:
                _identifier(person_id)
            if not isinstance(connection, Connection):
                _reject()
            requested_at = _instant(requested_at)
            connection = _connection(connection)
            if (
                connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs WHERE id=:job)"
                    ),
                    {"job": job_id},
                )
                is not False
            ):
                _reject()
            values = dict(
                connection=connection,
                job_id=job_id,
                person_id=person_id,
                identity_id=identity_id,
                target_generation=target_generation,
                requested_at=requested_at,
            )
            policy = self._policy_source(**values)
            if (
                type(policy) is not ErasurePlanPolicy
                or type(policy.retention_policy_version) is not int
                or not 0 < policy.retention_policy_version <= 2147483647
            ):
                _reject()
            due, receipt, evidence = (
                _instant(value)
                for value in (
                    policy.fulfillment_due_at,
                    policy.receipt_expires_at,
                    policy.evidence_expires_at,
                )
            )
            if (
                due <= requested_at
                or receipt <= requested_at
                or evidence < max(due, receipt)
            ):
                _reject()
            review = self._review_source(**values)
            if person_id is None:
                snapshot = self._pending(
                    connection, identity_id, target_generation, review
                )
            else:
                if type(review) is not bytes or not review:
                    _reject()
                reviewed = import_person_review(
                    connection,
                    payload=review,
                    person_id=person_id,
                    generation=target_generation,
                )
                snapshot = capture_person_snapshot(
                    connection,
                    person_id,
                    reviewed_dispositions=reviewed,
                    restore_codec=self._restore_codec,
                    provider_audiences=dict(self._provider_audiences),
                )
                if (
                    type(snapshot) is not PersonSnapshot
                    or snapshot.person_id != person_id
                    or sum(i.identity_id == identity_id for i in snapshot.identities)
                    != 1
                ):
                    _reject()
            if snapshot.generation != target_generation:
                _reject()
            scope_hash = snapshot.scope_hash
            _hash(scope_hash)
            return CapturedErasureRequestPlan(
                ErasureRequestPlan(
                    SCOPE_VERSION,
                    scope_hash,
                    policy.retention_policy_version,
                    due,
                    receipt,
                    evidence,
                ),
                snapshot,
            )
        except ErasurePlanRejected:
            raise
        except (
            _Rejected,
            ErasureRequestRejected,
            RestoreBindingUnavailable,
            ReviewInputRejected,
        ):
            _reject()
        except Exception:
            raise ErasurePlanUnavailable("plan_capture_unavailable") from None

    def _pending(self, connection, identity_id, generation, review):
        if type(review) is not tuple:
            _reject()
        identity = (
            connection.execute(
                text(
                    "SELECT provider,person_id,status,account_generation::text AS generation,"
                    "provider_subject FROM ntubtob.auth_identities WHERE id=:identity FOR UPDATE"
                ),
                {"identity": identity_id},
            )
            .mappings()
            .first()
        )
        if (
            identity is None
            or identity["provider"] not in {"apple", "google", "line"}
            or identity["person_id"] is not None
            or identity["status"] not in {"pending", "disabled", "blocked"}
            or identity["generation"] != generation
        ):
            _reject()
        binding = self._restore_codec.bind(
            provider=identity["provider"],
            audience=self._provider_audiences.get(identity["provider"]),
            subject=identity["provider_subject"],
            generation=generation,
        )
        snapshot = capture_pending_snapshot(
            connection, identity_id, reviewed_audits=review, restore_binding=binding
        )
        if (
            type(snapshot) is not PendingIdentitySnapshot
            or snapshot.identity_id != identity_id
            or snapshot.restore_binding != binding
        ):
            _reject()
        return snapshot
