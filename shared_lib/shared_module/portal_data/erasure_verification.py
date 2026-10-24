"""Default-unused requested-job verification, not full erasure or access blocking.

The injected verifier is trusted, local, read-only validation of a fresh server-
bound assertion. It must perform no network, database mutation or session changes.
No implementation accepting a client boolean or an ordinary login token is supplied.
The caller owns commit/rollback; a return value is not evidence of a durable commit.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..mobile_api import utc_now
from .erasure_continuity import ContinuityUnavailable, effective_expiry
from .erasure_intake_routing import INTAKES, receipt_table
from .runtime import acquire_admin_event_locks

ERASURE_VERIFICATION_PURPOSE = "account_erasure_verification"


class ErasureVerificationRejected(ValueError):
    """Fixed input/proof/scope rejection without provider or account details."""


class ErasureVerificationUnavailable(RuntimeError):
    """Fixed storage/configuration failure; never permission to retry blindly."""


@dataclass(frozen=True, repr=False)
class FreshErasureProof:
    """Trusted verifier output, never deserialize client JSON into this type."""

    job_id: str
    purpose: str
    audience: str
    identity_id: int
    provider: str
    provider_subject: str
    identity_generation: str
    target_kind: str
    person_id: int | None
    target_generation: str
    authenticated_at: datetime
    expires_at: datetime


class LocalFreshProofVerifier(Protocol):
    def __call__(self, assertion: str) -> FreshErasureProof:
        """Validate integrity and fresh provider authentication, without I/O."""


@dataclass(frozen=True)
class VerifiedErasureRequest:
    job_id: str
    verified_at: datetime


def _uuid(value: str) -> None:
    try:
        valid = type(value) is str and str(UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise ErasureVerificationRejected("invalid_identifier")


def _instant(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ErasureVerificationRejected("invalid_proof_time")
    return value.astimezone(timezone.utc)


class ErasureVerificationCoordinator:
    def __init__(
        self,
        *,
        verifier: LocalFreshProofVerifier,
        audience: str,
        max_proof_age: timedelta,
        clock: Callable[[], datetime] = utc_now,
    ):
        if (
            not callable(verifier)
            or type(audience) is not str
            or not 1 <= len(audience) <= 200
            or not isinstance(max_proof_age, timedelta)
            or max_proof_age <= timedelta(0)
            or not callable(clock)
        ):
            raise ErasureVerificationUnavailable("invalid_configuration")
        self.verifier, self.audience = verifier, audience
        self.max_proof_age, self.clock = max_proof_age, clock

    def verify(
        self, session: Session, *, job_id: str, assertion: str
    ) -> VerifiedErasureRequest:
        """Verify one existing requested job and revoke its Person's sessions.

        Requires a clean active READ COMMITTED transaction before any account row
        locks. Stored generation and mapping are authoritative, not job metadata or
        proof alone. Already verified jobs reject replay; use a separate authorized
        receipt read after an uncertain commit. Pending targets revoke no Person's
        sessions. No access_block success is recorded: other callers need guards.
        """
        _uuid(job_id)
        if type(assertion) is not str or not 1 <= len(assertion) <= 16384:
            raise ErasureVerificationRejected("invalid_assertion")
        if (
            not session.in_transaction()
            or session.new
            or session.dirty
            or session.deleted
        ):
            raise ErasureVerificationUnavailable("clean_transaction_required")
        try:
            connection = session.connection()
            if (
                getattr(connection.connection.dbapi_connection, "autocommit", None)
                is not False
            ):
                raise ErasureVerificationUnavailable("transaction_required")
            if connection.get_isolation_level() != "READ COMMITTED":
                raise ErasureVerificationUnavailable("read_committed_required")
            acquire_admin_event_locks(connection)
            revisions = tuple(
                connection.scalars(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ).all()
            )
            if revisions not in (
                ("0015_account_generations",),
                ("0016_erasure_cancellation",),
                ("0017_erasure_work_items",),
                ("0018_erasure_privacy_mutation",),
                ("0019_erasure_admin_recovery",),
                ("0020_erasure_intake",),
                ("0021_erasure_continuity",),
                ("0022_erasure_retention",),
                ("0023_erasure_minimal_retention",),
                ("0024_erasure_provider_phases",),
            ):
                raise ErasureVerificationUnavailable("schema_not_ready")
            for table in (
                "account_erasure_jobs",
                "account_erasure_steps",
                "auth_identities",
                "people",
                "mobile_sessions",
            ):
                if (
                    connection.scalar(
                        text(
                            f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::pg_catalog.regclass)"
                        )
                    )
                    is not False
                ):
                    raise ErasureVerificationUnavailable("unfiltered_tables_required")
            table = receipt_table(connection, job_id, revisions)
            job = (
                connection.execute(
                    text(
                        "SELECT id,status,target_kind,person_id,auth_identity_id,expected_generation,requested_at,updated_at,receipt_expires_at,evidence_expires_at,receipt_secret_hash "
                        f"FROM ntubtob.{table} WHERE id=:id FOR UPDATE"
                    ),
                    {"id": job_id},
                )
                .mappings()
                .first()
            )
            if job is None or job["status"] != "requested":
                raise ErasureVerificationRejected("requested_job_required")
            try:
                proof = self.verifier(assertion)
            except Exception:
                raise ErasureVerificationRejected("proof_rejected") from None
            self._validate_proof(proof, job_id)
            identity = (
                connection.execute(
                    text(
                        "SELECT id,provider,provider_subject,person_id,status,account_generation "
                        "FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE"
                    ),
                    {"id": proof.identity_id},
                )
                .mappings()
                .first()
            )
            if (
                identity is None
                or identity["id"] != proof.identity_id
                or identity["provider"] != proof.provider
                or identity["provider_subject"] != proof.provider_subject
                or identity["person_id"] != proof.person_id
                or str(identity["account_generation"]) != proof.identity_generation
            ):
                raise ErasureVerificationRejected("identity_scope_changed")
            if (
                job["target_kind"] != proof.target_kind
                or job["person_id"] != proof.person_id
            ):
                raise ErasureVerificationRejected("target_scope_changed")
            if proof.target_kind == "person":
                if job["auth_identity_id"] is not None or identity["status"] not in {
                    "linked",
                    "disabled",
                    "blocked",
                }:
                    raise ErasureVerificationRejected("identity_scope_changed")
                person = (
                    connection.execute(
                        text(
                            "SELECT id,account_generation FROM ntubtob.people WHERE id=:id FOR UPDATE"
                        ),
                        {"id": proof.person_id},
                    )
                    .mappings()
                    .first()
                )
                if person is None or person["id"] != proof.person_id:
                    raise ErasureVerificationRejected("target_scope_changed")
                generation = str(person["account_generation"])
            else:
                if job["auth_identity_id"] != proof.identity_id or identity[
                    "status"
                ] not in {"pending", "disabled", "blocked"}:
                    raise ErasureVerificationRejected("identity_scope_changed")
                generation = str(identity["account_generation"])
            if generation != proof.target_generation or generation != str(
                job["expected_generation"]
            ):
                raise ErasureVerificationRejected("target_generation_changed")
            now = _instant(self.clock())
            authenticated_at, expires_at = _instant(proof.authenticated_at), _instant(
                proof.expires_at
            )
            if (
                authenticated_at > now
                or authenticated_at < job["requested_at"]
                or now - authenticated_at > self.max_proof_age
                or expires_at <= now
                or expires_at <= authenticated_at
                or now < job["updated_at"]
                or (
                    table == INTAKES
                    and effective_expiry(
                        connection, job, "receipt_expires_at", revisions=revisions
                    )
                    <= now
                )
            ):
                raise ErasureVerificationRejected("proof_not_fresh")
            # Core savepoint avoids Session.begin_nested's unconditional autoflush.
            # Even a caller catching our error cannot commit half of these writes.
            with connection.begin_nested():
                changed = connection.execute(
                    text(
                        f"UPDATE ntubtob.{table} SET status='verified',verified_at=:now,updated_at=:now "
                        "WHERE id=:id AND status='requested'"
                    ),
                    {"id": job_id, "now": now},
                )
                if changed.rowcount != 1:
                    raise ErasureVerificationRejected("requested_job_required")
                if proof.person_id is not None:
                    connection.execute(
                        text(
                            "UPDATE ntubtob.mobile_sessions SET status='revoked',revoked_at=:now,updated_at=:now,access_epoch=access_epoch+1 "
                            "WHERE person_id=:person AND status='active'"
                        ),
                        {"person": proof.person_id, "now": now},
                    )
                if table != INTAKES:
                    connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_erasure_steps "
                            "(job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at) "
                            "SELECT :job,'verification',COALESCE(MAX(attempt),0)+1,1,'confirmed','succeeded',:now "
                            "FROM ntubtob.account_erasure_steps WHERE job_id=:job AND stage='verification'"
                        ),
                        {"job": job_id, "now": now},
                    )
            return VerifiedErasureRequest(job_id, now)
        except (SQLAlchemyError, ContinuityUnavailable):
            raise ErasureVerificationUnavailable(
                "verification_storage_unavailable"
            ) from None

    def _validate_proof(self, proof: FreshErasureProof, job_id: str) -> None:
        if type(proof) is not FreshErasureProof:
            raise ErasureVerificationRejected("proof_rejected")
        for value in (proof.job_id, proof.identity_generation, proof.target_generation):
            _uuid(value)
        if (
            proof.job_id != job_id
            or type(proof.purpose) is not str
            or proof.purpose != ERASURE_VERIFICATION_PURPOSE
            or type(proof.audience) is not str
            or proof.audience != self.audience
            or type(proof.identity_id) is not int
            or proof.identity_id <= 0
            or type(proof.provider) is not str
            or proof.provider not in {"line", "apple", "google"}
            or type(proof.provider_subject) is not str
            or not 1 <= len(proof.provider_subject) <= 255
            or type(proof.target_kind) is not str
            or proof.target_kind not in {"person", "pending_identity"}
            or (
                proof.target_kind == "person"
                and (type(proof.person_id) is not int or proof.person_id <= 0)
            )
            or (proof.target_kind == "pending_identity" and proof.person_id is not None)
        ):
            raise ErasureVerificationRejected("proof_binding_mismatch")
