"""Default-unused restricted intent repository, not job verification or erasure.

The injected verifier decrypts trusted local proof only; provider I/O must finish
before this call. The plan builder is trusted local read-only code. A consumed
attempt stays bound after cancellation; uncertainty is not retry permission.
"""

import hashlib
import hmac
import json
import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..erasure_restricted_proof import (
    RESTRICTED_ERASURE_PROOF_PURPOSE,
    FreshRestrictedErasureProof,
    RestrictedErasureProofRejected,
)
from ..mobile_api import utc_now
from .erasure_continuity import effective_expiry
from .erasure_request import (
    AccountErasureRequestRepository,
    ErasureRequestPlan,
    ErasureRequestReceipt,
    ErasureRequestRejected,
    ErasureRequestUnavailable,
    _instant,
    _uuid,
)
from .runtime import acquire_admin_event_locks


class RestrictedErasureRequestRepository(AccountErasureRequestRepository):
    def __init__(
        self,
        engine,
        key,
        plan_builder,
        *,
        verifier,
        audience,
        clock=utc_now,
        sealed_plan_store=None,
    ):
        super().__init__(
            engine, key, plan_builder, clock, sealed_plan_store=sealed_plan_store
        )
        if (
            not callable(verifier)
            or type(audience) is not str
            or not 1 <= len(audience) <= 200
        ):
            raise ErasureRequestRejected("invalid_configuration")
        self.verifier, self.audience = verifier, audience

    def _proof(self, assertion):
        try:
            proof = self.verifier(assertion)
        except RestrictedErasureProofRejected:
            raise ErasureRequestRejected("invalid_restricted_proof") from None
        if (
            type(proof) is not FreshRestrictedErasureProof
            or proof.purpose != RESTRICTED_ERASURE_PROOF_PURPOSE
            or proof.audience != self.audience
            or proof.provider not in {"line", "google", "apple"}
            or type(proof.provider_subject) is not str
            or not 1 <= len(proof.provider_subject) <= 255
            or not proof.provider_subject.strip()
        ):
            raise ErasureRequestRejected("invalid_restricted_proof")
        _uuid(proof.attempt_id)
        self._fresh(proof)
        return proof

    def _fresh(self, proof):
        now = _instant(self.clock())
        authenticated, expiry = _instant(proof.authenticated_at), _instant(
            proof.expires_at
        )
        if not authenticated <= now < expiry or expiry - authenticated > timedelta(
            minutes=5
        ):
            raise ErasureRequestRejected("restricted_proof_expired")
        return now

    def request_restricted(self, assertion):
        try:
            proof = self._proof(assertion)
            binding = hmac.new(
                self._key,
                b"ntubtob:erasure-request-attempt:v1\x00"
                + json.dumps(
                    [proof.attempt_id, proof.provider, proof.provider_subject],
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            with Session(self.engine) as session, session.begin():
                if (
                    not session.in_transaction()
                    or session.new
                    or session.dirty
                    or session.deleted
                ):
                    raise ErasureRequestUnavailable("clean_transaction_required")
                connection = session.connection()
                if (
                    getattr(connection.connection.dbapi_connection, "autocommit", None)
                    is not False
                    or connection.get_isolation_level() != "READ COMMITTED"
                ):
                    raise ErasureRequestUnavailable(
                        "read_committed_transaction_required"
                    )
                acquire_admin_event_locks(connection)
                revisions = tuple(
                    connection.scalars(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    )
                )
                if revisions not in (
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
                    raise ErasureRequestUnavailable("schema_not_ready")
                for table in (
                    "account_erasure_jobs",
                    "account_erasure_request_attempts",
                    "account_deletion_requests",
                    "auth_identities",
                    "people",
                ):
                    if (
                        connection.scalar(
                            text(
                                f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                            )
                        )
                        is not False
                    ):
                        raise ErasureRequestUnavailable("unfiltered_tables_required")

                def row(sql, **params):
                    return connection.execute(text(sql), params).mappings().first()

                now = self._fresh(proof)
                attempt = row(
                    "SELECT * FROM ntubtob.account_erasure_request_attempts WHERE attempt_id=:id FOR UPDATE",
                    id=proof.attempt_id,
                )
                job = None
                if attempt is not None:
                    if not hmac.compare_digest(attempt["assertion_binding"], binding):
                        raise ErasureRequestRejected("attempt_binding_changed")
                    if _instant(attempt["proof_expires_at"]) != _instant(
                        proof.expires_at
                    ):
                        raise ErasureRequestRejected("attempt_expiry_changed")
                    job = row(
                        "SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE",
                        id=attempt["job_id"],
                    )
                    if job is None or job["status"] != "requested":
                        raise ErasureRequestRejected("attempt_already_consumed")
                identity = row(
                    "SELECT id,person_id,status,account_generation FROM ntubtob.auth_identities WHERE provider=:provider AND provider_subject=:subject FOR UPDATE",
                    provider=proof.provider,
                    subject=proof.provider_subject,
                )
                if identity is None:
                    raise ErasureRequestRejected("existing_identity_required")
                person_id = identity["person_id"]
                kind = "pending_identity" if person_id is None else "person"
                column, target = (
                    ("auth_identity_id", identity["id"])
                    if person_id is None
                    else ("person_id", person_id)
                )
                if person_id is None:
                    if identity["status"] not in {"pending", "disabled", "blocked"}:
                        raise ErasureRequestRejected("identity_scope_changed")
                    generation = _uuid(identity["account_generation"])
                else:
                    person = row(
                        "SELECT account_generation FROM ntubtob.people WHERE id=:id FOR UPDATE",
                        id=person_id,
                    )
                    if person is None or identity["status"] not in {
                        "linked",
                        "disabled",
                        "blocked",
                    }:
                        raise ErasureRequestRejected("identity_scope_changed")
                    generation = _uuid(person["account_generation"])
                if job is None:
                    job = row(
                        f"SELECT * FROM ntubtob.account_erasure_jobs WHERE {column}=:id FOR UPDATE",
                        id=target,
                    )
                if job is not None:
                    if (
                        job["status"] != "requested"
                        or job["target_kind"] != kind
                        or job[column] != target
                        or _uuid(job["expected_generation"]) != generation
                    ):
                        raise ErasureRequestRejected("request_scope_changed")
                    job_id = _uuid(job["id"])
                    secret = self._secret(job_id)
                    if not hmac.compare_digest(
                        hashlib.sha256(secret.encode("ascii")).hexdigest(),
                        job["receipt_secret_hash"],
                    ):
                        raise ErasureRequestRejected("receipt_key_mismatch")
                    if (
                        effective_expiry(
                            connection, job, "receipt_expires_at", revisions=revisions
                        )
                        <= now
                        or _instant(job["requested_at"]) > now
                        or effective_expiry(
                            connection, job, "evidence_expires_at", revisions=revisions
                        )
                        < _instant(proof.expires_at)
                    ):
                        raise ErasureRequestRejected("receipt_unavailable")
                    requested_at = _instant(job["requested_at"])
                    receipt_deadline = effective_expiry(
                        connection, job, "receipt_expires_at", revisions=revisions
                    )
                    if self.sealed_plan_store is not None:
                        self.sealed_plan_store.load(connection, job_id)
                else:
                    # Legacy receipts are not new restricted authority. Keep their
                    # evidence untouched and reject a fulfillment already underway.
                    if person_id is not None:
                        legacy = row(
                            "SELECT status FROM ntubtob.account_deletion_requests WHERE person_id=:id FOR UPDATE",
                            id=person_id,
                        )
                        if legacy is not None and legacy["status"] != "requested":
                            raise ErasureRequestRejected("legacy_request_unavailable")
                    job_id, requested_at = str(uuid4()), now
                    plan, snapshot = self._build_plan(
                        connection,
                        job_id,
                        person_id=person_id,
                        identity_id=identity["id"],
                        target_generation=generation,
                        requested_at=now,
                    )
                    if (
                        type(plan) is not ErasureRequestPlan
                        or any(
                            type(v) is not int or not 0 < v <= 2147483647
                            for v in (plan.scope_version, plan.retention_policy_version)
                        )
                        or type(plan.scope_hash) is not str
                        or re.fullmatch(r"[0-9a-f]{64}", plan.scope_hash) is None
                    ):
                        raise ErasureRequestRejected("invalid_plan")
                    due, receipt, evidence = map(
                        _instant,
                        (
                            plan.fulfillment_due_at,
                            plan.receipt_expires_at,
                            plan.evidence_expires_at,
                        ),
                    )
                    receipt_deadline = min(due, receipt)
                    final_now = self._fresh(proof)
                    if (
                        final_now < now
                        or min(due, receipt) <= final_now
                        or evidence < max(due, receipt, _instant(proof.expires_at))
                    ):
                        raise ErasureRequestRejected("invalid_plan_deadlines")
                    secret = self._secret(job_id)
                    connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_erasure_jobs "
                            "(id,target_kind,person_id,auth_identity_id,expected_generation,status,scope_version,scope_hash,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) "
                            "VALUES (:id,:kind,:person,:identity,:generation,'requested',:scope_version,:scope_hash,:receipt_hash,:policy,:now,:now,:due,:receipt,:evidence)"
                        ),
                        dict(
                            id=job_id,
                            kind=kind,
                            person=person_id,
                            identity=target if person_id is None else None,
                            generation=generation,
                            scope_version=plan.scope_version,
                            scope_hash=plan.scope_hash,
                            receipt_hash=hashlib.sha256(
                                secret.encode("ascii")
                            ).hexdigest(),
                            policy=plan.retention_policy_version,
                            now=now,
                            due=due,
                            receipt=receipt,
                            evidence=evidence,
                        ),
                    )
                    if self.sealed_plan_store is not None:
                        self.sealed_plan_store.store_requested(
                            connection, job_id, snapshot
                        )
                if attempt is None:
                    connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_erasure_request_attempts "
                            "(attempt_id,job_id,assertion_binding,created_at,proof_expires_at) VALUES (:attempt,:job,:binding,:now,:expiry)"
                        ),
                        dict(
                            attempt=proof.attempt_id,
                            job=job_id,
                            binding=binding,
                            now=now,
                            expiry=proof.expires_at,
                        ),
                    )
                final_now = self._fresh(proof)
                if final_now < now or receipt_deadline <= final_now:
                    raise ErasureRequestRejected("request_expired")
                result = ErasureRequestReceipt(job_id, secret, requested_at)
            return result
        except (ErasureRequestRejected, ErasureRequestUnavailable):
            raise
        except Exception:
            raise ErasureRequestUnavailable(
                "restricted_request_storage_or_proof_failed"
            ) from None
