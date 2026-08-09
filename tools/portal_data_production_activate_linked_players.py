"""Fail-closed activation for the existing reliably linked player cohort."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
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
    LegacyLineUserRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)
from tools import portal_data_production_activate_allowlisted_admins as boundary

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "tools" / "portal_data_production_activate_linked_players.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
EXECUTION_ENV = "TASK087_LINKED_PLAYERS_EXECUTION"
EXECUTION_ACKNOWLEDGEMENT = "EXECUTE TASK-087 LINKED PLAYERS"
REASON = "Owner-approved existing reliably linked team-player activation"
OUTPUT_FIELDS = (
    "mode",
    "status",
    "schema_ready",
    "logging_safe",
    "eligible_cohort_count",
    "active_control_count",
    "drift_count",
    "activation_delta",
    "audit_delta",
    "retry_verified",
)


class LinkedPlayerActivationError(RuntimeError):
    """Raised when the reliable-player cohort cannot be proven exact."""


def verify_artifact() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(ARTIFACT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if not separator or name != ARTIFACT.name or digest != actual:
        raise LinkedPlayerActivationError("linked-player checksum is invalid")


def _activation_audits(session: Session, person_ids: tuple[int, ...]) -> int:
    rows = session.scalars(
        select(AccessAuditRecord).where(
            AccessAuditRecord.action == "status_changed",
            AccessAuditRecord.actor_person_id.is_(None),
            AccessAuditRecord.target_person_id.in_(person_ids),
            AccessAuditRecord.auth_identity_id.is_(None),
            AccessAuditRecord.reason == REASON,
        )
    ).all()
    exact = sum(
        row.before_state == {"status": "inactive"}
        and row.after_state == {"status": "active"}
        for row in rows
    )
    if exact != len(rows):
        raise LinkedPlayerActivationError("batch audit shape drifted")
    return exact


def _lock_and_discover(
    session: Session, allowlist: frozenset[int], *, lock_rows: bool = True
) -> tuple[tuple[PersonRecord, ...], bool]:
    if lock_rows:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": boundary.ADMIN_LOCK_KEY},
        )
    people_query = (
        select(PersonRecord)
        .join(
            PersonQualificationRecord,
            PersonQualificationRecord.person_id == PersonRecord.id,
        )
        .where(
            PersonQualificationRecord.qualification == "team_player",
            PersonQualificationRecord.status == "active",
        )
        .order_by(PersonRecord.id)
    )
    if lock_rows:
        people_query = people_query.with_for_update(of=PersonRecord)
    people = tuple(session.scalars(people_query).all())
    if len(people) <= 2 or len({person.id for person in people}) != len(people):
        raise LinkedPlayerActivationError("team-player cohort is unavailable")

    controls: list[PersonRecord] = []
    cohort: list[PersonRecord] = []
    for person in people:
        members = session.scalars(
            select(LegacyMemberRecord).where(LegacyMemberRecord.person_id == person.id)
        ).all()
        if len(members) != 1:
            raise LinkedPlayerActivationError("Member relationship drifted")
        member = members[0]
        lines = session.scalars(
            select(LegacyLineUserRecord).where(
                LegacyLineUserRecord.member_id == member.id,
                LegacyLineUserRecord.ignored.is_(False),
            )
        ).all()
        if len(lines) != 1:
            raise LinkedPlayerActivationError("legacy LINE relationship drifted")
        identities = session.scalars(
            select(AuthIdentityRecord).where(
                AuthIdentityRecord.provider == "line",
                AuthIdentityRecord.provider_subject == lines[0].line_user_id,
            )
        ).all()
        if (
            len(identities) != 1
            or identities[0].status != "linked"
            or identities[0].person_id != person.id
        ):
            raise LinkedPlayerActivationError("LINE identity relationship drifted")
        if member.id in allowlist:
            if person.portal_status != "active":
                raise LinkedPlayerActivationError("active control drifted")
            controls.append(person)
        else:
            cohort.append(person)

    if len(controls) != 2 or {
        session.scalar(
            select(LegacyMemberRecord.id).where(
                LegacyMemberRecord.person_id == person.id
            )
        )
        for person in controls
    } != set(allowlist):
        raise LinkedPlayerActivationError("allowlisted controls drifted")
    if not cohort:
        raise LinkedPlayerActivationError("eligible cohort is empty")
    statuses = {person.portal_status for person in cohort}
    if statuses not in ({"inactive"}, {"active"}):
        raise LinkedPlayerActivationError("cohort status is partial or unsafe")

    pending = int(
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
    if pending:
        raise LinkedPlayerActivationError("pending identity drifted")

    cohort_tuple = tuple(cohort)
    audit_count = _activation_audits(
        session, tuple(person.id for person in cohort_tuple)
    )
    completed = statuses == {"active"}
    if (completed and audit_count != len(cohort_tuple)) or (
        not completed and audit_count != 0
    ):
        raise LinkedPlayerActivationError("batch audit relationship drifted")
    return cohort_tuple, completed


def _verify_delta(
    before: boundary.Snapshot, after: boundary.Snapshot, cohort_count: int
) -> None:
    expected = boundary.Snapshot(
        people=before.people,
        members=before.members,
        identities=before.identities,
        legacy_lines=before.legacy_lines,
        qualifications=before.qualifications,
        attendance_replies=before.attendance_replies,
        inactive_people=before.inactive_people - cohort_count,
        active_people=before.active_people + cohort_count,
        audits=before.audits + cohort_count,
    )
    if after != expected:
        raise LinkedPlayerActivationError("batch aggregate delta failed")


def _emit(**values: object) -> None:
    if tuple(values) != OUTPUT_FIELDS:
        raise LinkedPlayerActivationError("batch output schema is invalid")
    print(json.dumps(values, separators=(",", ":")))


def run(
    mode: str,
    *,
    environ: Mapping[str, str] | None = None,
    approved_cohort_count: int | None = None,
    fail_after: int | None = None,
) -> None:
    verify_artifact()
    environment = os.environ if environ is None else environ
    database_url, allowlist = boundary._private_inputs(environment)
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
                == boundary.SCHEMA_REVISION
            )
            logging_safe = boundary._read_logging_safe(session)
        if not schema_ready or not logging_safe:
            raise LinkedPlayerActivationError("batch read preflight failed")

        if mode in ("discovery", "preflight", "post-check"):
            with Session(engine) as session, session.begin():
                session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                session.execute(text("SET LOCAL statement_timeout = '15s'"))
                session.execute(text("SET LOCAL lock_timeout = '5s'"))
                session.execute(
                    text("SET LOCAL idle_in_transaction_session_timeout = '30s'")
                )
                cohort, completed = _lock_and_discover(
                    session, allowlist, lock_rows=False
                )
            if mode == "discovery":
                if approved_cohort_count is not None:
                    raise LinkedPlayerActivationError(
                        "discovery cannot accept an approved cohort count"
                    )
            elif (
                not isinstance(approved_cohort_count, int)
                or isinstance(approved_cohort_count, bool)
                or approved_cohort_count <= 0
                or len(cohort) != approved_cohort_count
            ):
                raise LinkedPlayerActivationError("approved cohort count drifted")
            if mode == "post-check" and not completed:
                raise LinkedPlayerActivationError("batch post-check failed")
            _emit(
                mode=mode,
                status="verified" if completed else "ready",
                schema_ready=True,
                logging_safe=True,
                eligible_cohort_count=len(cohort),
                active_control_count=2,
                drift_count=0,
                activation_delta=0,
                audit_delta=0,
                retry_verified=completed,
            )
            return
        if (
            mode != "execute"
            or environment.get(EXECUTION_ENV) != EXECUTION_ACKNOWLEDGEMENT
        ):
            raise LinkedPlayerActivationError("batch execution is not acknowledged")
        with Session(engine) as session, session.begin():
            if not boundary._write_logging_safe(session):
                raise LinkedPlayerActivationError("batch write logging is unsafe")
            before = boundary._snapshot(session)
            cohort, completed = _lock_and_discover(session, allowlist)
            if (
                not isinstance(approved_cohort_count, int)
                or isinstance(approved_cohort_count, bool)
                or approved_cohort_count <= 0
                or len(cohort) != approved_cohort_count
            ):
                raise LinkedPlayerActivationError("approved cohort count drifted")
            if completed:
                _emit(
                    mode=mode,
                    status="verified",
                    schema_ready=True,
                    logging_safe=True,
                    eligible_cohort_count=len(cohort),
                    active_control_count=2,
                    drift_count=0,
                    activation_delta=0,
                    audit_delta=0,
                    retry_verified=True,
                )
                return
            now = datetime.now(timezone.utc)
            for index, person in enumerate(cohort, start=1):
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
                        request_id=f"task087-linked-{uuid.uuid4()}",
                        created_at=now,
                    )
                )
                session.flush()
                if fail_after is not None and index == fail_after:
                    raise LinkedPlayerActivationError("injected batch failure")
            after = boundary._snapshot(session)
            _verify_delta(before, after, len(cohort))
        _emit(
            mode=mode,
            status="applied",
            schema_ready=True,
            logging_safe=True,
            eligible_cohort_count=len(cohort),
            active_control_count=2,
            drift_count=0,
            activation_delta=len(cohort),
            audit_delta=len(cohort),
            retry_verified=False,
        )
    finally:
        engine.dispose()


def main() -> None:
    raise SystemExit("linked-player activation requires the reviewed launcher")


if __name__ == "__main__":
    main()
