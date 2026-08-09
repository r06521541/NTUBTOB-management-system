"""Fail-closed production boundary for the one-time zero-admin bootstrap."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.identity_lifecycle import (
    BOOTSTRAP_REASON_PREFIX,
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.models import (
    AccessAuditRecord,
    AuthIdentityRecord,
    IdentityReviewThreadRecord,
    LegacyGameAttendanceReplyRecord,
    LegacyLineUserRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "tools" / "portal_data_production_zero_admin_bootstrap.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
DATABASE_ENV = "PORTAL_DATA_DATABASE_URL"
ALLOWLIST_ENV = "WEB_PORTAL_ADMIN_MEMBER_IDS"
EXECUTION_ENV = "TASK086_PRODUCTION_EXECUTION"
EXECUTION_ACKNOWLEDGEMENT = "EXECUTE TASK-086"
SCHEMA_REVISION = "0004_phase_c_identity_lifecycle"
BOOTSTRAP_REASON = "Owner-approved production administrative-entry bootstrap"
OUTPUT_FIELDS = (
    "mode",
    "status",
    "schema_ready",
    "logging_safe",
    "active_admin_count",
    "eligible_member_count",
    "eligible_identity_count",
    "audit_delta",
    "applied",
    "retry_verified",
)


class ProductionBootstrapError(RuntimeError):
    """Raised when the production bootstrap cannot be proven safe."""


@dataclass(frozen=True)
class Candidate:
    identity_id: int
    member_id: int
    person_id: int
    has_team_player: bool


@dataclass(frozen=True)
class Snapshot:
    people: int
    members: int
    identities: int
    pending_identities: int
    linked_identities: int
    active_people: int
    inactive_people: int
    linked_legacy_lines: int
    open_threads: int
    active_team_players: int
    attendance_replies: int
    audits: int


def verify_artifact() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(ARTIFACT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if not separator or name != ARTIFACT.name or digest != actual:
        raise ProductionBootstrapError("production operator checksum is invalid")


def _allowlist(value: str | None) -> frozenset[int]:
    if not value:
        raise ProductionBootstrapError("private allowlist is unavailable")
    parts = value.split(",")
    if any(not re.fullmatch(r"[1-9]\d*", part) for part in parts):
        raise ProductionBootstrapError("private allowlist is invalid")
    values = frozenset(int(part) for part in parts)
    if len(values) != len(parts):
        raise ProductionBootstrapError("private allowlist is ambiguous")
    return values


def _private_inputs(environ: Mapping[str, str]) -> tuple[str, frozenset[int]]:
    database_url = environ.get(DATABASE_ENV)
    if not database_url:
        raise ProductionBootstrapError("private database channel is unavailable")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise ProductionBootstrapError("private database channel is invalid")
    return database_url, _allowlist(environ.get(ALLOWLIST_ENV))


def _read_logging_safe(session: Session) -> bool:
    row = session.execute(
        text(
            "SELECT "
            "coalesce(current_setting('log_statement',true),'all') IN ('none','ddl','mod'),"
            "coalesce(current_setting('log_min_duration_statement',true),'0')::integer=-1,"
            "coalesce(current_setting('log_min_duration_sample',true),'0')::integer=-1,"
            "coalesce(current_setting('log_duration',true),'on')='off',"
            "coalesce(current_setting('log_transaction_sample_rate',true),'1')::numeric=0,"
            "coalesce(current_setting('pgaudit.log',true),'none') IN ('none',''),"
            "coalesce(current_setting('log_parameter_max_length_on_error',true),'-1')::integer=0"
        )
    ).one()
    return all(value is True for value in row)


def _write_logging_safe(session: Session) -> bool:
    mode = session.scalar(
        text("SELECT coalesce(current_setting('log_statement',true),'all')")
    )
    return mode in ("none", "ddl") and _read_logging_safe(session)


def _schema_ready(session: Session) -> bool:
    return (
        session.scalar(text("SELECT version_num FROM ntubtob.alembic_version"))
        == SCHEMA_REVISION
    )


def _active_admin_count(session: Session, allowlist: frozenset[int]) -> int:
    return int(
        session.scalar(
            select(func.count(func.distinct(PersonRecord.id)))
            .select_from(PersonRecord)
            .join(LegacyMemberRecord, LegacyMemberRecord.person_id == PersonRecord.id)
            .join(AuthIdentityRecord, AuthIdentityRecord.person_id == PersonRecord.id)
            .where(
                PersonRecord.portal_status == "active",
                LegacyMemberRecord.id.in_(allowlist),
                AuthIdentityRecord.provider == "line",
                AuthIdentityRecord.status == "linked",
            )
        )
        or 0
    )


def _discover(
    session: Session, allowlist: frozenset[int]
) -> tuple[Candidate | None, int, int]:
    member_rows = session.execute(
        select(
            LegacyMemberRecord.id,
            LegacyMemberRecord.person_id,
            PersonQualificationRecord.status,
        )
        .join(PersonRecord, PersonRecord.id == LegacyMemberRecord.person_id)
        .outerjoin(
            PersonQualificationRecord,
            (PersonQualificationRecord.person_id == PersonRecord.id)
            & (PersonQualificationRecord.qualification == "team_player"),
        )
        .where(
            LegacyMemberRecord.id.in_(allowlist),
            PersonRecord.portal_status == "inactive",
            (PersonQualificationRecord.id.is_(None))
            | (PersonQualificationRecord.status == "active"),
        )
    ).all()
    identity_rows = session.execute(
        select(AuthIdentityRecord.id)
        .join(
            LegacyLineUserRecord,
            LegacyLineUserRecord.line_user_id == AuthIdentityRecord.provider_subject,
        )
        .join(
            IdentityReviewThreadRecord,
            IdentityReviewThreadRecord.auth_identity_id == AuthIdentityRecord.id,
        )
        .where(
            AuthIdentityRecord.provider == "line",
            AuthIdentityRecord.status == "pending",
            AuthIdentityRecord.person_id.is_(None),
            LegacyLineUserRecord.member_id.is_(None),
            LegacyLineUserRecord.ignored.is_(False),
            IdentityReviewThreadRecord.status == "open",
            IdentityReviewThreadRecord.closed_at.is_(None),
            IdentityReviewThreadRecord.redacted_at.is_(None),
        )
    ).all()
    if len(member_rows) != 1 or len(identity_rows) != 1:
        return None, len(member_rows), len(identity_rows)
    member_id, person_id, qualification_status = member_rows[0]
    return (
        Candidate(
            identity_id=identity_rows[0][0],
            member_id=member_id,
            person_id=person_id,
            has_team_player=qualification_status == "active",
        ),
        1,
        1,
    )


def _snapshot(session: Session) -> Snapshot:
    count = lambda model: int(
        session.scalar(select(func.count()).select_from(model)) or 0
    )
    status_count = lambda model, column, value: int(
        session.scalar(select(func.count()).select_from(model).where(column == value))
        or 0
    )
    return Snapshot(
        people=count(PersonRecord),
        members=count(LegacyMemberRecord),
        identities=count(AuthIdentityRecord),
        pending_identities=status_count(
            AuthIdentityRecord, AuthIdentityRecord.status, "pending"
        ),
        linked_identities=status_count(
            AuthIdentityRecord, AuthIdentityRecord.status, "linked"
        ),
        active_people=status_count(PersonRecord, PersonRecord.portal_status, "active"),
        inactive_people=status_count(
            PersonRecord, PersonRecord.portal_status, "inactive"
        ),
        linked_legacy_lines=int(
            session.scalar(
                select(func.count())
                .select_from(LegacyLineUserRecord)
                .where(LegacyLineUserRecord.member_id.is_not(None))
            )
            or 0
        ),
        open_threads=status_count(
            IdentityReviewThreadRecord, IdentityReviewThreadRecord.status, "open"
        ),
        active_team_players=int(
            session.scalar(
                select(func.count())
                .select_from(PersonQualificationRecord)
                .where(
                    PersonQualificationRecord.qualification == "team_player",
                    PersonQualificationRecord.status == "active",
                )
            )
            or 0
        ),
        attendance_replies=count(LegacyGameAttendanceReplyRecord),
        audits=count(AccessAuditRecord),
    )


def _verify_delta(before: Snapshot, after: Snapshot, candidate: Candidate) -> None:
    expected = Snapshot(
        people=before.people,
        members=before.members,
        identities=before.identities,
        pending_identities=before.pending_identities - 1,
        linked_identities=before.linked_identities + 1,
        active_people=before.active_people + 1,
        inactive_people=before.inactive_people - 1,
        linked_legacy_lines=before.linked_legacy_lines + 1,
        open_threads=before.open_threads - 1,
        active_team_players=before.active_team_players
        + (0 if candidate.has_team_player else 1),
        attendance_replies=before.attendance_replies,
        audits=before.audits + 1,
    )
    if after != expected:
        raise ProductionBootstrapError("bootstrap aggregate post-check failed")


def _relationship_ready_after(
    session: Session, candidate: Candidate, request_id: str
) -> bool:
    identity = session.get(AuthIdentityRecord, candidate.identity_id)
    member = session.get(LegacyMemberRecord, candidate.member_id)
    person = session.get(PersonRecord, candidate.person_id)
    legacy = (
        session.scalar(
            select(LegacyLineUserRecord).where(
                LegacyLineUserRecord.line_user_id == identity.provider_subject
            )
        )
        if identity is not None
        else None
    )
    thread = session.scalar(
        select(IdentityReviewThreadRecord).where(
            IdentityReviewThreadRecord.auth_identity_id == candidate.identity_id
        )
    )
    audit = session.scalar(
        select(AccessAuditRecord).where(AccessAuditRecord.request_id == request_id)
    )
    return bool(
        identity is not None
        and identity.status == "linked"
        and identity.person_id == candidate.person_id
        and member is not None
        and member.person_id == candidate.person_id
        and person is not None
        and person.portal_status == "active"
        and legacy is not None
        and legacy.member_id == candidate.member_id
        and not legacy.ignored
        and thread is not None
        and thread.status == "closed"
        and thread.closed_at is not None
        and thread.redacted_at is None
        and audit is not None
        and audit.action == "identity_linked"
        and audit.actor_person_id is None
        and audit.target_person_id == candidate.person_id
        and audit.auth_identity_id == candidate.identity_id
        and audit.before_state == {"status": "pending"}
        and audit.after_state == {"status": "linked", "member_id": candidate.member_id}
        and audit.reason == f"{BOOTSTRAP_REASON_PREFIX}{BOOTSTRAP_REASON}"
    )


def _completed_relationship_count(session: Session, allowlist: frozenset[int]) -> int:
    return int(
        session.scalar(
            select(func.count(AccessAuditRecord.id))
            .select_from(AccessAuditRecord)
            .join(
                AuthIdentityRecord,
                AuthIdentityRecord.id == AccessAuditRecord.auth_identity_id,
            )
            .join(PersonRecord, PersonRecord.id == AccessAuditRecord.target_person_id)
            .join(LegacyMemberRecord, LegacyMemberRecord.person_id == PersonRecord.id)
            .join(
                LegacyLineUserRecord,
                (LegacyLineUserRecord.member_id == LegacyMemberRecord.id)
                & (
                    LegacyLineUserRecord.line_user_id
                    == AuthIdentityRecord.provider_subject
                ),
            )
            .join(
                IdentityReviewThreadRecord,
                IdentityReviewThreadRecord.auth_identity_id == AuthIdentityRecord.id,
            )
            .where(
                AccessAuditRecord.action == "identity_linked",
                AccessAuditRecord.actor_person_id.is_(None),
                AccessAuditRecord.reason
                == f"{BOOTSTRAP_REASON_PREFIX}{BOOTSTRAP_REASON}",
                LegacyMemberRecord.id.in_(allowlist),
                AuthIdentityRecord.provider == "line",
                AuthIdentityRecord.status == "linked",
                AuthIdentityRecord.person_id == PersonRecord.id,
                PersonRecord.portal_status == "active",
                LegacyLineUserRecord.ignored.is_(False),
                IdentityReviewThreadRecord.status == "closed",
                IdentityReviewThreadRecord.closed_at.is_not(None),
                IdentityReviewThreadRecord.redacted_at.is_(None),
            )
        )
        or 0
    )


def _emit(**values: object) -> None:
    if tuple(values) != OUTPUT_FIELDS:
        raise ProductionBootstrapError("production output schema is invalid")
    print(json.dumps(values, separators=(",", ":")))


def run(mode: str, *, environ: Mapping[str, str] | None = None) -> None:
    verify_artifact()
    environment = os.environ if environ is None else environ
    database_url, allowlist = _private_inputs(environment)
    engine: Engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(
                text("SET LOCAL idle_in_transaction_session_timeout = '30s'")
            )
            schema_ready = _schema_ready(session)
            logging_safe = _read_logging_safe(session)
            admin_count = _active_admin_count(session, allowlist)
            candidate, member_count, identity_count = _discover(session, allowlist)
            before = _snapshot(session)
            completed_count = _completed_relationship_count(session, allowlist)
        if mode == "post-check":
            if (
                not schema_ready
                or not logging_safe
                or admin_count != 1
                or completed_count != 1
            ):
                raise ProductionBootstrapError("production post-check failed")
            _emit(
                mode=mode,
                status="verified",
                schema_ready=True,
                logging_safe=True,
                active_admin_count=1,
                eligible_member_count=member_count,
                eligible_identity_count=identity_count,
                audit_delta=0,
                applied=True,
                retry_verified=True,
            )
            return
        if (
            not schema_ready
            or not logging_safe
            or admin_count != 0
            or candidate is None
        ):
            raise ProductionBootstrapError("production bootstrap preflight failed")
        if mode != "execute":
            _emit(
                mode=mode,
                status="ready",
                schema_ready=True,
                logging_safe=True,
                active_admin_count=0,
                eligible_member_count=member_count,
                eligible_identity_count=identity_count,
                audit_delta=0,
                applied=False,
                retry_verified=False,
            )
            return
        if environment.get(EXECUTION_ENV) != EXECUTION_ACKNOWLEDGEMENT:
            raise ProductionBootstrapError("production execution is not acknowledged")
        with Session(engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            if not _write_logging_safe(session):
                raise ProductionBootstrapError("production write logging is unsafe")
        request_id = f"task086-{uuid.uuid4()}"
        repository = IdentityLifecycleRepository(engine, allowlist)
        repository.bootstrap_zero_admin_member(
            candidate.identity_id,
            candidate.member_id,
            BOOTSTRAP_REASON,
            request_id,
        )
        with Session(engine) as session:
            after = _snapshot(session)
            admin_after = _active_admin_count(session, allowlist)
            relationship_ready = _relationship_ready_after(
                session, candidate, request_id
            )
        _verify_delta(before, after, candidate)
        if admin_after != 1 or not relationship_ready:
            raise ProductionBootstrapError("bootstrap relationship post-check failed")
        repository.bootstrap_zero_admin_member(
            candidate.identity_id,
            candidate.member_id,
            BOOTSTRAP_REASON,
            request_id,
        )
        with Session(engine) as session:
            retry = _snapshot(session)
        if retry != after:
            raise ProductionBootstrapError("bootstrap retry post-check failed")
        _emit(
            mode=mode,
            status="applied",
            schema_ready=True,
            logging_safe=True,
            active_admin_count=admin_after,
            eligible_member_count=member_count,
            eligible_identity_count=identity_count,
            audit_delta=1,
            applied=True,
            retry_verified=True,
        )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("discovery", "preflight", "dry-run", "execute", "post-check"),
        required=True,
    )
    args = parser.parse_args()
    try:
        run(args.mode)
    except Exception:
        raise SystemExit("production zero-admin bootstrap stopped") from None


if __name__ == "__main__":
    main()
