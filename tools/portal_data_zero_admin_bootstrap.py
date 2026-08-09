"""Fail-closed interactive operator for the one-time zero-admin bootstrap."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import (
    AccessAuditRecord,
    AuthIdentityRecord,
    IdentityReviewThreadRecord,
    LegacyLineUserRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "tools" / "portal_data_zero_admin_bootstrap.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
OUTPUT_FIELDS = (
    "mode",
    "status",
    "target_ready",
    "active_admin_count_before",
    "active_admin_count_after",
    "audit_delta",
    "applied",
)


class BootstrapOperatorError(RuntimeError):
    pass


def verify_artifact() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(ARTIFACT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if not separator or name != ARTIFACT.name or digest != actual:
        raise BootstrapOperatorError("operator artifact checksum is invalid")


def _integer(value: str, label: str) -> int:
    if not re.fullmatch(r"[1-9]\d*", value):
        raise BootstrapOperatorError(f"{label} is invalid")
    return int(value)


def _allowlist(value: str) -> frozenset[int]:
    parts = value.split(",")
    if not parts or any(part != part.strip() for part in parts):
        raise BootstrapOperatorError("allowlist is invalid")
    values = frozenset(_integer(part, "allowlist") for part in parts)
    if len(values) != len(parts):
        raise BootstrapOperatorError("allowlist is ambiguous")
    return values


def _active_admin_count(session: Session, allowlist: frozenset[int]) -> int:
    return int(
        session.scalar(
            select(func.count(func.distinct(PersonRecord.id)))
            .select_from(PersonRecord)
            .join(LegacyMemberRecord, LegacyMemberRecord.person_id == PersonRecord.id)
            .join(AuthIdentityRecord, AuthIdentityRecord.person_id == PersonRecord.id)
            .where(
                PersonRecord.portal_status == "active",
                LegacyMemberRecord.id.in_(allowlist or {-1}),
                AuthIdentityRecord.status == "linked",
            )
        )
        or 0
    )


def _target_ready(
    session: Session, identity_id: int, member_id: int, allowlist: frozenset[int]
) -> bool:
    identity = session.get(AuthIdentityRecord, identity_id)
    member = session.get(LegacyMemberRecord, member_id)
    if (
        member_id not in allowlist
        or identity is None
        or identity.provider != "line"
        or identity.status != "pending"
        or identity.person_id is not None
        or member is None
        or member.person_id is None
    ):
        return False
    person = session.get(PersonRecord, member.person_id)
    legacy = session.scalar(
        select(LegacyLineUserRecord).where(
            LegacyLineUserRecord.line_user_id == identity.provider_subject
        )
    )
    thread = session.scalar(
        select(IdentityReviewThreadRecord).where(
            IdentityReviewThreadRecord.auth_identity_id == identity_id
        )
    )
    qualification = session.scalar(
        select(PersonQualificationRecord).where(
            PersonQualificationRecord.person_id == member.person_id,
            PersonQualificationRecord.qualification == "team_player",
        )
    )
    return bool(
        person is not None
        and person.portal_status not in {"disabled", "blocked"}
        and legacy is not None
        and legacy.member_id is None
        and not legacy.ignored
        and thread is not None
        and thread.status == "open"
        and thread.closed_at is None
        and thread.redacted_at is None
        and (qualification is None or qualification.status == "active")
    )


def _emit(**values: object) -> None:
    if tuple(values) != OUTPUT_FIELDS:
        raise BootstrapOperatorError("operator output schema is invalid")
    print(json.dumps(values, sort_keys=False, separators=(",", ":")))


def run(mode: str) -> None:
    verify_artifact()
    database_url = require_local_database_url(
        os.environ.get("PORTAL_DATA_DATABASE_URL")
    )
    allowlist = _allowlist(getpass.getpass("Full admin Member-ID allowlist: "))
    identity_id = _integer(getpass.getpass("Pending identity ID: "), "identity")
    member_id = _integer(getpass.getpass("Allowlisted Member ID: "), "member")
    reason = getpass.getpass("Bootstrap reason: ").strip()
    request_id = getpass.getpass("Opaque request ID: ").strip()
    if not 3 <= len(reason) <= 270 or not 1 <= len(request_id) <= 100:
        raise BootstrapOperatorError("operator input is invalid")
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            before_admins = _active_admin_count(session, allowlist)
            ready = _target_ready(session, identity_id, member_id, allowlist)
            audit_before = int(
                session.scalar(select(func.count(AccessAuditRecord.id))) or 0
            )
        if before_admins != 0 or not ready:
            raise BootstrapOperatorError("bootstrap preflight failed")
        if mode != "execute":
            _emit(
                mode=mode,
                status="ready",
                target_ready=True,
                active_admin_count_before=before_admins,
                active_admin_count_after=before_admins,
                audit_delta=0,
                applied=False,
            )
            return
        if getpass.getpass("Type EXECUTE TASK-085: ") != "EXECUTE TASK-085":
            raise BootstrapOperatorError("execution acknowledgement failed")
        repository = IdentityLifecycleRepository(engine, allowlist)
        repository.bootstrap_zero_admin_member(
            identity_id, member_id, reason, request_id
        )
        with Session(engine) as session:
            after_admins = _active_admin_count(session, allowlist)
            audit_after = int(
                session.scalar(select(func.count(AccessAuditRecord.id))) or 0
            )
            applied_audit = session.scalar(
                select(AccessAuditRecord).where(
                    AccessAuditRecord.request_id == request_id
                )
            )
        if (
            after_admins != 1
            or audit_after - audit_before != 1
            or applied_audit is None
            or applied_audit.action != "identity_linked"
            or applied_audit.actor_person_id is not None
        ):
            raise BootstrapOperatorError("bootstrap post-check failed")
        _emit(
            mode=mode,
            status="applied",
            target_ready=True,
            active_admin_count_before=before_admins,
            active_admin_count_after=after_admins,
            audit_delta=1,
            applied=True,
        )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("preflight", "dry-run", "execute"), required=True
    )
    args = parser.parse_args()
    try:
        run(args.mode)
    except Exception:
        raise SystemExit("zero-admin bootstrap stopped") from None


if __name__ == "__main__":
    main()
