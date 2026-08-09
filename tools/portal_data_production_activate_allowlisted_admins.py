"""Fail-closed exact-two allowlisted administrator activation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

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
ARTIFACT = ROOT / "tools" / "portal_data_production_activate_allowlisted_admins.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
DATABASE_ENV = "PORTAL_DATA_DATABASE_URL"
ALLOWLIST_ENV = "WEB_PORTAL_ADMIN_MEMBER_IDS"
EXECUTION_ENV = "TASK086_EXACT_TWO_EXECUTION"
EXECUTION_ACKNOWLEDGEMENT = "EXECUTE TASK-086 EXACT TWO"
SCHEMA_REVISION = "0004_phase_c_identity_lifecycle"
ADMIN_LOCK_KEY = 70070
REASON = "Owner-approved exact-two allowlisted administrator activation"
OUTPUT_FIELDS = (
    "mode",
    "status",
    "schema_ready",
    "logging_safe",
    "allowlisted_member_count",
    "active_admin_count",
    "activation_delta",
    "audit_delta",
    "retry_verified",
)


class ExactTwoActivationError(RuntimeError):
    """Raised when the exact-two activation cannot be proven safe."""


@dataclass(frozen=True)
class Snapshot:
    people: int
    members: int
    identities: int
    legacy_lines: int
    qualifications: int
    attendance_replies: int
    inactive_people: int
    active_people: int
    audits: int


def verify_artifact() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(ARTIFACT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if not separator or name != ARTIFACT.name or digest != actual:
        raise ExactTwoActivationError("activation checksum is invalid")


def _allowlist(value: str | None) -> frozenset[int]:
    if not value:
        raise ExactTwoActivationError("private allowlist is unavailable")
    parts = value.split(",")
    if len(parts) != 2 or any(not re.fullmatch(r"[1-9]\d*", part) for part in parts):
        raise ExactTwoActivationError("exact-two allowlist is invalid")
    values = frozenset(int(part) for part in parts)
    if len(values) != 2:
        raise ExactTwoActivationError("exact-two allowlist is ambiguous")
    return values


def _private_inputs(environ: Mapping[str, str]) -> tuple[str, frozenset[int]]:
    database_url = environ.get(DATABASE_ENV)
    if not database_url or not database_url.startswith(
        ("postgresql://", "postgresql+psycopg2://")
    ):
        raise ExactTwoActivationError("private database channel is invalid")
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


def _snapshot(session: Session) -> Snapshot:
    def count(model) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    def status_count(value: str) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(PersonRecord)
                .where(PersonRecord.portal_status == value)
            )
            or 0
        )

    return Snapshot(
        people=count(PersonRecord),
        members=count(LegacyMemberRecord),
        identities=count(AuthIdentityRecord),
        legacy_lines=count(LegacyLineUserRecord),
        qualifications=count(PersonQualificationRecord),
        attendance_replies=count(LegacyGameAttendanceReplyRecord),
        inactive_people=status_count("inactive"),
        active_people=status_count("active"),
        audits=count(AccessAuditRecord),
    )


def _activation_audit_count(session: Session, person_ids: tuple[int, ...]) -> int:
    rows = session.scalars(
        select(AccessAuditRecord).where(
            AccessAuditRecord.action == "status_changed",
            AccessAuditRecord.actor_person_id.is_(None),
            AccessAuditRecord.target_person_id.in_(person_ids),
            AccessAuditRecord.auth_identity_id.is_(None),
            AccessAuditRecord.reason == REASON,
        )
    ).all()
    return sum(
        row.before_state == {"status": "inactive"}
        and row.after_state == {"status": "active"}
        for row in rows
    )


def _lock_and_validate(
    session: Session, allowlist: frozenset[int]
) -> tuple[tuple[PersonRecord, ...], bool]:
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMIN_LOCK_KEY})
    rows = session.execute(
        select(PersonRecord, LegacyMemberRecord.id)
        .join(LegacyMemberRecord, LegacyMemberRecord.person_id == PersonRecord.id)
        .where(LegacyMemberRecord.id.in_(allowlist))
        .order_by(PersonRecord.id)
        .with_for_update(of=PersonRecord)
    ).all()
    if len(rows) != 2 or {member_id for _, member_id in rows} != set(allowlist):
        raise ExactTwoActivationError("exact-two Member relationship drifted")
    people = tuple(person for person, _ in rows)
    person_ids = tuple(person.id for person in people)
    statuses = {person.portal_status for person in people}
    if statuses not in ({"inactive"}, {"active"}):
        raise ExactTwoActivationError("exact-two Person state drifted")

    legacy_rows = session.execute(
        select(LegacyLineUserRecord.member_id, LegacyLineUserRecord.line_user_id)
        .where(
            LegacyLineUserRecord.member_id.in_(allowlist),
            LegacyLineUserRecord.ignored.is_(False),
        )
        .order_by(LegacyLineUserRecord.member_id)
    ).all()
    if len(legacy_rows) != 2 or {row.member_id for row in legacy_rows} != set(
        allowlist
    ):
        raise ExactTwoActivationError("exact-two legacy LINE relationship drifted")
    subjects = {row.line_user_id for row in legacy_rows}
    identities = session.execute(
        select(AuthIdentityRecord.person_id, AuthIdentityRecord.provider_subject).where(
            AuthIdentityRecord.provider == "line",
            AuthIdentityRecord.provider_subject.in_(subjects),
            AuthIdentityRecord.status == "linked",
        )
    ).all()
    if len(identities) != 2 or {row.provider_subject for row in identities} != subjects:
        raise ExactTwoActivationError("exact-two LINE identity relationship drifted")
    member_person = {member_id: person.id for person, member_id in rows}
    subject_member = {row.line_user_id: row.member_id for row in legacy_rows}
    if any(
        identity.person_id != member_person[subject_member[identity.provider_subject]]
        for identity in identities
    ):
        raise ExactTwoActivationError("LINE identity points to another Person")

    qualification_count = int(
        session.scalar(
            select(func.count(PersonQualificationRecord.id)).where(
                PersonQualificationRecord.person_id.in_(person_ids),
                PersonQualificationRecord.qualification == "team_player",
                PersonQualificationRecord.status == "active",
            )
        )
        or 0
    )
    if qualification_count != 2:
        raise ExactTwoActivationError("team-player relationship drifted")
    pending_count = int(
        session.scalar(
            select(func.count(AuthIdentityRecord.id))
            .select_from(AuthIdentityRecord)
            .join(
                LegacyLineUserRecord,
                LegacyLineUserRecord.line_user_id
                == AuthIdentityRecord.provider_subject,
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
        )
        or 0
    )
    if pending_count:
        raise ExactTwoActivationError("pending LINE relationship drifted")
    audit_count = _activation_audit_count(session, person_ids)
    completed = statuses == {"active"}
    if (completed and audit_count != 2) or (not completed and audit_count != 0):
        raise ExactTwoActivationError("activation audit relationship drifted")
    return people, completed


def _active_admin_count(session: Session, allowlist: frozenset[int]) -> int:
    return int(
        session.scalar(
            select(func.count(func.distinct(PersonRecord.id)))
            .select_from(PersonRecord)
            .join(LegacyMemberRecord, LegacyMemberRecord.person_id == PersonRecord.id)
            .join(AuthIdentityRecord, AuthIdentityRecord.person_id == PersonRecord.id)
            .where(
                LegacyMemberRecord.id.in_(allowlist),
                PersonRecord.portal_status == "active",
                AuthIdentityRecord.provider == "line",
                AuthIdentityRecord.status == "linked",
            )
        )
        or 0
    )


def _verify_delta(before: Snapshot, after: Snapshot) -> None:
    expected = Snapshot(
        people=before.people,
        members=before.members,
        identities=before.identities,
        legacy_lines=before.legacy_lines,
        qualifications=before.qualifications,
        attendance_replies=before.attendance_replies,
        inactive_people=before.inactive_people - 2,
        active_people=before.active_people + 2,
        audits=before.audits + 2,
    )
    if after != expected:
        raise ExactTwoActivationError("exact-two aggregate delta failed")


def _emit(**values: object) -> None:
    if tuple(values) != OUTPUT_FIELDS:
        raise ExactTwoActivationError("activation output schema is invalid")
    print(json.dumps(values, separators=(",", ":")))


def run(
    mode: str,
    *,
    environ: Mapping[str, str] | None = None,
    fail_after_first: bool = False,
) -> None:
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
            schema_ready = (
                session.scalar(text("SELECT version_num FROM ntubtob.alembic_version"))
                == SCHEMA_REVISION
            )
            logging_safe = _read_logging_safe(session)
        if not schema_ready or not logging_safe:
            raise ExactTwoActivationError("activation read preflight failed")
        if mode == "preflight":
            with Session(engine) as session, session.begin():
                _, completed = _lock_and_validate(session, allowlist)
                admin_count = _active_admin_count(session, allowlist)
            _emit(
                mode=mode,
                status="verified" if completed else "ready",
                schema_ready=True,
                logging_safe=True,
                allowlisted_member_count=2,
                active_admin_count=admin_count,
                activation_delta=0,
                audit_delta=0,
                retry_verified=completed,
            )
            return
        if mode == "post-check":
            with Session(engine) as session, session.begin():
                _, completed = _lock_and_validate(session, allowlist)
                admin_count = _active_admin_count(session, allowlist)
            if not completed or admin_count != 2:
                raise ExactTwoActivationError("exact-two post-check failed")
            _emit(
                mode=mode,
                status="verified",
                schema_ready=True,
                logging_safe=True,
                allowlisted_member_count=2,
                active_admin_count=2,
                activation_delta=0,
                audit_delta=0,
                retry_verified=True,
            )
            return
        if (
            mode != "execute"
            or environment.get(EXECUTION_ENV) != EXECUTION_ACKNOWLEDGEMENT
        ):
            raise ExactTwoActivationError("activation execution is not acknowledged")
        with Session(engine) as session, session.begin():
            if not _write_logging_safe(session):
                raise ExactTwoActivationError("activation write logging is unsafe")
            before = _snapshot(session)
            people, completed = _lock_and_validate(session, allowlist)
            if completed:
                if _active_admin_count(session, allowlist) != 2:
                    raise ExactTwoActivationError(
                        "activation retry relationship failed"
                    )
                _emit(
                    mode=mode,
                    status="verified",
                    schema_ready=True,
                    logging_safe=True,
                    allowlisted_member_count=2,
                    active_admin_count=2,
                    activation_delta=0,
                    audit_delta=0,
                    retry_verified=True,
                )
                return
            now = datetime.now(timezone.utc)
            for index, person in enumerate(people):
                person.portal_status = "active"
                person.version += 1
                person.updated_at = now
                session.add(
                    AccessAuditRecord(
                        action="status_changed",
                        actor_person_id=None,
                        target_person_id=person.id,
                        auth_identity_id=None,
                        before_state={"status": "inactive"},
                        after_state={"status": "active"},
                        reason=REASON,
                        request_id=f"task086-two-{uuid.uuid4()}",
                        created_at=now,
                    )
                )
                session.flush()
                if fail_after_first and index == 0:
                    raise ExactTwoActivationError("injected activation failure")
            after = _snapshot(session)
            _verify_delta(before, after)
            if _active_admin_count(session, allowlist) != 2:
                raise ExactTwoActivationError("active administrator post-check failed")
        _emit(
            mode=mode,
            status="applied",
            schema_ready=True,
            logging_safe=True,
            allowlisted_member_count=2,
            active_admin_count=2,
            activation_delta=2,
            audit_delta=2,
            retry_verified=False,
        )
    finally:
        engine.dispose()


def main() -> None:
    raise SystemExit("exact-two activation requires the reviewed launcher")


if __name__ == "__main__":
    main()
