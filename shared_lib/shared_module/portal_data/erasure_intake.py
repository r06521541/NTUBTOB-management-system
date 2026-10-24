"""Default-off intake and one-shot reviewed materialization, not a queue.

Only original policy metadata is accepted at intake; review/capture is deferred.
Fresh proof uses the existing coordinators. Internal materialization freezes the
existing execution job and encrypted plan atomically, preserving receipt dates.
No provider I/O, automatic retry, user reapplication or placeholder scope exists.
"""

import hashlib
import hmac
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..mobile_api import MobilePrincipal, utc_now
from .erasure_cancellation import _connection
from .erasure_composition import ErasurePlanPolicy, TrustedErasurePlanBuilder
from .erasure_continuity import effective_expiry
from .erasure_intake_routing import (
    INTAKES,
    JOBS,
    REVISION,
    receipt_table,
    target_row,
    unfiltered,
)
from .erasure_request import (
    CapturedErasureRequestPlan,
    ErasureRequestReceipt,
    ErasureRequestRejected,
    ErasureRequestUnavailable,
    _instant,
    _uuid,
)
from .erasure_restricted_request import RestrictedErasureRequestRepository

FIELDS = "id,target_kind,person_id,auth_identity_id,expected_generation,status,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at"


def _row(connection, sql, **values):
    return connection.execute(text(sql), values).mappings().one_or_none()


def _intake_connection(session):
    connection = _connection(session)
    if tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) not in {(REVISION,), ("0021_erasure_continuity",), ("0022_erasure_retention",)}:
        raise ErasureRequestUnavailable("intake_schema_not_ready")
    unfiltered(connection)
    unfiltered(connection, "account_erasure_intake_attempts")
    for table in (
        "account_erasure_request_attempts",
        "mobile_sessions",
        "account_deletion_requests",
    ):
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                )
            )
            is not False
        ):
            raise ErasureRequestUnavailable("unfiltered_intake_required")
    return connection


class ErasureIntakeRepository(RestrictedErasureRequestRepository):
    def __init__(
        self, engine, key, *, policy_source, verifier, audience, clock=utc_now
    ):
        if not isinstance(engine, Engine) or not callable(policy_source):
            raise ErasureRequestRejected("invalid_intake_configuration")
        super().__init__(
            engine,
            key,
            lambda **values: None,
            verifier=verifier,
            audience=audience,
            clock=clock,
        )
        self.policy_source = policy_source

    def _admit(self, connection, identity, person, now):
        person_id = None if person is None else person["id"]
        kind = "pending_identity" if person is None else "person"
        column = "auth_identity_id" if person is None else "person_id"
        target = identity["id"] if person is None else person_id
        generation = _uuid(
            (identity if person is None else person)["account_generation"]
        )
        existing = target_row(connection, column, target, FIELDS, (REVISION,))
        if person is not None:
            legacy = _row(
                connection,
                "SELECT status FROM ntubtob.account_deletion_requests WHERE person_id=:id FOR UPDATE",
                id=person_id,
            )
            if legacy is not None and legacy["status"] != "requested":
                raise ErasureRequestRejected("legacy_request_unavailable")
            for table in (JOBS, INTAKES):
                if connection.scalar(
                    text(
                        f"SELECT EXISTS(SELECT 1 FROM ntubtob.{table} WHERE auth_identity_id IN (SELECT id FROM ntubtob.auth_identities WHERE person_id=:id))"
                    ),
                    {"id": person_id},
                ):
                    raise ErasureRequestRejected("intake_scope_changed")
        if existing is not None:
            if (
                existing["status"] != "requested"
                or existing["target_kind"] != kind
                or str(existing["expected_generation"]) != generation
                or _instant(existing["requested_at"]) > now
                or effective_expiry(connection, existing, "receipt_expires_at") <= now
            ):
                raise ErasureRequestRejected("intake_scope_changed")
            identifier = _uuid(existing["id"])
            secret = self._secret(identifier)
            if not hmac.compare_digest(
                existing["receipt_secret_hash"],
                hashlib.sha256(secret.encode("ascii")).hexdigest(),
            ):
                raise ErasureRequestRejected("receipt_key_mismatch")
            return ErasureRequestReceipt(
                identifier, secret, existing["requested_at"]
            ), effective_expiry(connection, existing, "receipt_expires_at")
        identifier = str(uuid4())
        policy = self.policy_source(
            connection=connection,
            job_id=identifier,
            person_id=person_id,
            identity_id=identity["id"],
            target_generation=generation,
            requested_at=now,
        )
        if (
            type(policy) is not ErasurePlanPolicy
            or type(policy.retention_policy_version) is not int
            or not 0 < policy.retention_policy_version <= 2147483647
        ):
            raise ErasureRequestRejected("invalid_intake_policy")
        due, receipt, evidence = map(
            _instant,
            (
                policy.fulfillment_due_at,
                policy.receipt_expires_at,
                policy.evidence_expires_at,
            ),
        )
        if min(due, receipt) <= now or evidence < max(due, receipt):
            raise ErasureRequestRejected("invalid_intake_deadlines")
        secret = self._secret(identifier)
        connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_intakes (id,target_kind,person_id,auth_identity_id,expected_generation,status,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) VALUES (:id,:kind,:person,:identity,:generation,'requested',:hash,:policy,:now,:now,:due,:receipt,:evidence)"
            ),
            dict(
                id=identifier,
                kind=kind,
                person=person_id,
                identity=identity["id"] if person is None else None,
                generation=generation,
                hash=hashlib.sha256(secret.encode("ascii")).hexdigest(),
                policy=policy.retention_policy_version,
                now=now,
                due=due,
                receipt=receipt,
                evidence=evidence,
            ),
        )
        return ErasureRequestReceipt(identifier, secret, now), min(due, receipt)

    def request(self, principal):
        if type(principal) is not MobilePrincipal or any(
            type(v) is not int or v <= 0
            for v in (
                principal.person_id,
                principal.identity_id,
                principal.access_epoch,
            )
        ):
            raise ErasureRequestRejected("invalid_principal")
        session_id = _uuid(principal.session_id)
        try:
            with Session(self.engine) as session, session.begin():
                connection = _intake_connection(session)
                identity = _row(
                    connection,
                    "SELECT * FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE",
                    id=principal.identity_id,
                )
                person = _row(
                    connection,
                    "SELECT * FROM ntubtob.people WHERE id=:id FOR UPDATE",
                    id=principal.person_id,
                )
                device = _row(
                    connection,
                    "SELECT * FROM ntubtob.mobile_sessions WHERE id=:id FOR UPDATE",
                    id=session_id,
                )
                now = _instant(self.clock())
                if (
                    identity is None
                    or person is None
                    or identity["person_id"] != principal.person_id
                    or identity["status"] != "linked"
                    or person["portal_status"] != "active"
                ):
                    raise ErasureRequestRejected("active_account_required")
                if (
                    device is None
                    or device["person_id"] != principal.person_id
                    or device["auth_identity_id"] != principal.identity_id
                    or device["status"] != "active"
                    or device["access_epoch"] != principal.access_epoch
                    or _instant(device["refresh_family_expires_at"]) <= now
                ):
                    raise ErasureRequestRejected("active_session_required")
                result, deadline = self._admit(connection, identity, person, now)
                finished = _instant(self.clock())
                if (
                    not now
                    <= finished
                    < min(deadline, _instant(device["refresh_family_expires_at"]))
                ):
                    raise ErasureRequestRejected("request_expired_during_planning")
            return result
        except (ErasureRequestRejected, ErasureRequestUnavailable):
            raise
        except Exception:
            raise ErasureRequestUnavailable("intake_request_unavailable") from None

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
                connection = _intake_connection(session)
                now = self._fresh(proof)
                attempts = []
                for table, key in (
                    ("account_erasure_intake_attempts", "intake_id"),
                    ("account_erasure_request_attempts", "job_id"),
                ):
                    row = _row(
                        connection,
                        f"SELECT {key} AS receipt_id,assertion_binding,proof_expires_at FROM ntubtob.{table} WHERE attempt_id=:id FOR UPDATE",
                        id=proof.attempt_id,
                    )
                    if row is not None:
                        attempts.append(row)
                if len(attempts) > 1:
                    raise ErasureRequestRejected("attempt_binding_changed")
                identity = _row(
                    connection,
                    "SELECT * FROM ntubtob.auth_identities WHERE provider=:provider AND provider_subject=:subject FOR UPDATE",
                    provider=proof.provider,
                    subject=proof.provider_subject,
                )
                if identity is None:
                    raise ErasureRequestRejected("existing_identity_required")
                person = None
                if identity["person_id"] is not None:
                    if identity["status"] not in {"linked", "blocked", "disabled"}:
                        raise ErasureRequestRejected("identity_scope_changed")
                    person = _row(
                        connection,
                        "SELECT * FROM ntubtob.people WHERE id=:id FOR UPDATE",
                        id=identity["person_id"],
                    )
                    if person is None:
                        raise ErasureRequestRejected("identity_scope_changed")
                elif identity["status"] not in {"pending", "blocked", "disabled"}:
                    raise ErasureRequestRejected("identity_scope_changed")
                if attempts:
                    attempt = attempts[0]
                    if (
                        not hmac.compare_digest(attempt["assertion_binding"], binding)
                        or attempt["proof_expires_at"] != proof.expires_at
                    ):
                        raise ErasureRequestRejected("attempt_binding_changed")
                    table = receipt_table(
                        connection, str(attempt["receipt_id"]), (REVISION,)
                    )
                    row = _row(
                        connection,
                        f"SELECT status FROM ntubtob.{table} WHERE id=:id FOR UPDATE",
                        id=attempt["receipt_id"],
                    )
                    if row is None or row["status"] != "requested":
                        raise ErasureRequestRejected("attempt_already_consumed")
                result, deadline = self._admit(connection, identity, person, now)
                if attempts and str(attempts[0]["receipt_id"]) != result.job_id:
                    raise ErasureRequestRejected("attempt_binding_changed")
                if not attempts:
                    table = receipt_table(connection, result.job_id, (REVISION,))
                    attempts_table, key = (
                        ("account_erasure_intake_attempts", "intake_id")
                        if table == INTAKES
                        else ("account_erasure_request_attempts", "job_id")
                    )
                    connection.execute(
                        text(
                            f"INSERT INTO ntubtob.{attempts_table} (attempt_id,{key},assertion_binding,created_at,proof_expires_at) VALUES (:attempt,:id,:binding,:now,:expiry)"
                        ),
                        dict(
                            attempt=proof.attempt_id,
                            id=result.job_id,
                            binding=binding,
                            now=now,
                            expiry=proof.expires_at,
                        ),
                    )
                if not now <= self._fresh(proof) < deadline:
                    raise ErasureRequestRejected("request_expired")
            return result
        except (ErasureRequestRejected, ErasureRequestUnavailable):
            raise
        except Exception:
            raise ErasureRequestUnavailable("restricted_intake_unavailable") from None


class ErasureIntakeMaterializer:
    def __init__(self, engine, builder, store, *, clock=utc_now):
        if (
            not isinstance(engine, Engine)
            or type(builder) is not TrustedErasurePlanBuilder
            or not callable(clock)
        ):
            raise ValueError("invalid_intake_materializer")
        self.engine, self.builder, self.store, self.clock = (
            engine,
            builder,
            store,
            clock,
        )

    def materialize(self, *, job_id, identity_id):
        """Internal reviewed operation. No deadline reset, second proof or effects."""
        job_id = _uuid(job_id)
        if type(identity_id) is not int or identity_id <= 0:
            raise ErasureRequestRejected("invalid_intake_identity")
        try:
            with Session(self.engine) as session, session.begin():
                connection = _intake_connection(session)
                intake = _row(
                    connection,
                    "SELECT * FROM ntubtob.account_erasure_intakes WHERE id=:id FOR UPDATE",
                    id=job_id,
                )
                if intake is None or intake["status"] != "verified":
                    raise ErasureRequestRejected("verified_intake_required")
                identity = _row(
                    connection,
                    "SELECT person_id,status,account_generation FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE",
                    id=identity_id,
                )
                if identity is None or identity["person_id"] != intake["person_id"]:
                    raise ErasureRequestRejected("intake_target_changed")
                if intake["target_kind"] == "pending_identity":
                    if identity_id != intake["auth_identity_id"] or identity[
                        "status"
                    ] not in {"pending", "blocked", "disabled"}:
                        raise ErasureRequestRejected("intake_target_changed")
                    generation = str(identity["account_generation"])
                else:
                    if identity["status"] not in {"linked", "blocked", "disabled"}:
                        raise ErasureRequestRejected("intake_target_changed")
                    generation = connection.scalar(
                        text(
                            "SELECT account_generation::text FROM ntubtob.people WHERE id=:id FOR UPDATE"
                        ),
                        {"id": intake["person_id"]},
                    )
                if generation != str(intake["expected_generation"]):
                    raise ErasureRequestRejected("intake_generation_changed")
                now = _instant(self.clock())
                if (
                    not intake["updated_at"]
                    <= now
                    < min(
                        effective_expiry(connection, intake, "receipt_expires_at"),
                        effective_expiry(connection, intake, "evidence_expires_at"),
                    )
                ):
                    raise ErasureRequestRejected("intake_expired")
                captured = self.builder(
                    connection=connection,
                    job_id=job_id,
                    person_id=intake["person_id"],
                    identity_id=identity_id,
                    target_generation=generation,
                    requested_at=intake["requested_at"],
                )
                if type(captured) is not CapturedErasureRequestPlan:
                    raise ErasureRequestRejected("captured_plan_required")
                plan = captured.metadata
                if any(
                    getattr(plan, key) != intake[key]
                    for key in (
                        "retention_policy_version",
                        "fulfillment_due_at",
                        "receipt_expires_at",
                        "evidence_expires_at",
                    )
                ):
                    raise ErasureRequestRejected("intake_policy_changed")
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_jobs (id,target_kind,person_id,auth_identity_id,expected_generation,status,scope_version,scope_hash,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) VALUES (:id,:kind,:person,:identity,:generation,'requested',:version,:hash,:receipt_hash,:policy,:requested,:requested,:due,:receipt,:evidence)"
                    ),
                    dict(
                        id=job_id,
                        kind=intake["target_kind"],
                        person=intake["person_id"],
                        identity=intake["auth_identity_id"],
                        generation=generation,
                        version=plan.scope_version,
                        hash=plan.scope_hash,
                        receipt_hash=intake["receipt_secret_hash"],
                        policy=intake["retention_policy_version"],
                        requested=intake["requested_at"],
                        due=intake["fulfillment_due_at"],
                        receipt=intake["receipt_expires_at"],
                        evidence=intake["evidence_expires_at"],
                    ),
                )
                self.store.store_requested(connection, job_id, captured.snapshot)
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_jobs SET status='verified',verified_at=:verified,updated_at=:now WHERE id=:id"
                    ),
                    dict(id=job_id, verified=intake["verified_at"], now=now),
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_steps (job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,'verification',1,1,'confirmed','succeeded',:verified)"
                    ),
                    dict(id=job_id, verified=intake["verified_at"]),
                )
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_intakes SET status='materialized',materialized_job_id=id,person_id=NULL,auth_identity_id=NULL,updated_at=:now WHERE id=:id"
                    ),
                    dict(id=job_id, now=now),
                )
                finished = _instant(self.clock())
                if (
                    not now
                    <= finished
                    < min(
                        effective_expiry(connection, intake, "receipt_expires_at"),
                        effective_expiry(connection, intake, "evidence_expires_at"),
                    )
                ):
                    raise ErasureRequestRejected("intake_expired")
            return job_id
        except (ErasureRequestRejected, ErasureRequestUnavailable):
            raise
        except Exception:
            raise ErasureRequestUnavailable(
                "intake_materialization_unavailable"
            ) from None
