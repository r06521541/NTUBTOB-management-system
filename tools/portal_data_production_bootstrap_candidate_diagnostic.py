"""Fixed-schema, read-only TASK-086 candidate-state classifier."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared_lib.shared_module.portal_data.models import (
    AccessAuditRecord,
    AuthIdentityRecord,
    IdentityReviewThreadRecord,
    LegacyLineUserRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)
from tools import portal_data_production_bootstrap_diagnostic as boundary

ARTIFACT = ROOT / "tools" / "portal_data_production_bootstrap_candidate_diagnostic.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MATERIAL_CHECKSUMS = ROOT / "tools" / "TASK-086-candidate-diagnostic.sha256"
APPROVED_COMMIT_ENV = "TASK086_CANDIDATE_DIAGNOSTIC_APPROVED_MERGED_COMMIT"
BOOTSTRAP_REASON = (
    "zero-admin bootstrap: Owner-approved production administrative-entry bootstrap"
)
OUTPUT_FIELDS = (
    "runtime_artifact_git",
    "gcloud_metadata",
    "private_pg",
    "connection",
    "schema",
    "read_logging",
    "allowlisted_member",
    "person_state",
    "reliable_line_identity",
    "pending_review_thread",
    "legacy_line_link",
    "active_team_player",
    "bootstrap_audit",
)
COUNT_FIELDS = (
    "allowlisted_member",
    "pending_review_thread",
    "legacy_line_link",
    "active_team_player",
    "bootstrap_audit",
)
PERSON_STATES = ("absent", "inactive", "active", "blocked", "other")
IDENTITY_STATES = (
    "none",
    "pending_unlinked",
    "linked_same_person",
    "linked_other_person",
    "other",
)


class CandidateDiagnosticError(RuntimeError):
    """Internal fixed-boundary failure; its text is never emitted."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _verify_checksum(path: Path, checksum_path: Path) -> None:
    digest, separator, name = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != path.name or digest != _canonical_digest(path):
        raise CandidateDiagnosticError("artifact boundary failed")


def _verify_artifacts() -> None:
    _verify_checksum(ARTIFACT, CHECKSUM)
    expected = {}
    for line in MATERIAL_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CandidateDiagnosticError("material boundary failed")
        expected[name] = digest
    paths = {
        "models.py": ROOT
        / "shared_lib"
        / "shared_module"
        / "portal_data"
        / "models.py",
        "portal_data_production_bootstrap_diagnostic.py": boundary.ARTIFACT,
    }
    if set(expected) != set(paths) or any(
        expected[name] != _canonical_digest(path) for name, path in paths.items()
    ):
        raise CandidateDiagnosticError("material boundary failed")


def _verify_runtime_git(environ: Mapping[str, str]) -> None:
    _verify_artifacts()
    if (
        Path.cwd().resolve() != ROOT.resolve()
        or Path(sys.executable).resolve() != boundary.RUNTIME_EXECUTABLE.resolve()
        or sys.version_info[:3] != boundary.RUNTIME_VERSION
        or not boundary.RUNTIME_EXECUTABLE.is_file()
    ):
        raise CandidateDiagnosticError("runtime boundary failed")
    if any(
        importlib.metadata.version(name) != version
        for name, version in boundary.REQUIRED_PACKAGES.items()
    ):
        raise CandidateDiagnosticError("runtime boundary failed")
    approved = environ.get(APPROVED_COMMIT_ENV, "")
    if not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise CandidateDiagnosticError("git boundary failed")
    if boundary._run([boundary.GIT, "rev-parse", "HEAD"]) != approved:
        raise CandidateDiagnosticError("git boundary failed")
    if boundary._run([boundary.GIT, "status", "--porcelain"]):
        raise CandidateDiagnosticError("git boundary failed")


def _count(value: int) -> str:
    if value == 0:
        return "zero"
    if value == 1:
        return "one"
    return "other"


def _candidate_state(session: Session, allowlist: set[int]) -> dict[str, str]:
    members = session.execute(
        select(LegacyMemberRecord.id, LegacyMemberRecord.person_id).where(
            LegacyMemberRecord.id.in_(allowlist)
        )
    ).all()
    member_ids = {row.id for row in members}
    person_ids = {row.person_id for row in members if row.person_id is not None}
    person_rows = (
        session.execute(
            select(PersonRecord.id, PersonRecord.portal_status).where(
                PersonRecord.id.in_(person_ids)
            )
        ).all()
        if person_ids
        else []
    )
    if len(members) != 1 or len(person_rows) > 1:
        person_state = "other"
        person_id = None
    elif not person_rows:
        person_state = "absent"
        person_id = None
    else:
        person_id, status = person_rows[0]
        person_state = (
            status if status in ("inactive", "active", "blocked") else "other"
        )

    legacy_rows = session.execute(
        select(LegacyLineUserRecord.line_user_id, LegacyLineUserRecord.member_id).where(
            LegacyLineUserRecord.member_id.in_(member_ids),
            LegacyLineUserRecord.ignored.is_(False),
        )
    ).all()
    subjects = {row.line_user_id for row in legacy_rows}
    linked_identity_rows = (
        session.execute(
            select(
                AuthIdentityRecord.id,
                AuthIdentityRecord.status,
                AuthIdentityRecord.person_id,
            ).where(
                AuthIdentityRecord.provider == "line",
                AuthIdentityRecord.provider_subject.in_(subjects),
            )
        ).all()
        if subjects
        else []
    )
    pending_rows = session.execute(
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
    if (
        len(linked_identity_rows) > 1
        or (linked_identity_rows and pending_rows)
        or len(pending_rows) > 1
    ):
        identity_state = "other"
    elif len(linked_identity_rows) == 1:
        _, identity_status, identity_person_id = linked_identity_rows[0]
        if identity_status == "linked" and person_id is not None:
            identity_state = (
                "linked_same_person"
                if identity_person_id == person_id
                else "linked_other_person"
            )
        else:
            identity_state = "other"
    elif len(pending_rows) == 1:
        identity_state = "pending_unlinked"
    else:
        identity_state = "none"

    pending_thread_count = len(pending_rows)
    team_player_count = (
        int(
            session.scalar(
                select(func.count(PersonQualificationRecord.id)).where(
                    PersonQualificationRecord.person_id.in_(person_ids),
                    PersonQualificationRecord.qualification == "team_player",
                    PersonQualificationRecord.status == "active",
                )
            )
            or 0
        )
        if person_ids
        else 0
    )
    audit_count = int(
        session.scalar(
            select(func.count(AccessAuditRecord.id))
            .select_from(AccessAuditRecord)
            .join(
                AuthIdentityRecord,
                AuthIdentityRecord.id == AccessAuditRecord.auth_identity_id,
            )
            .where(
                AccessAuditRecord.action == "identity_linked",
                AccessAuditRecord.actor_person_id.is_(None),
                AccessAuditRecord.target_person_id.in_(person_ids),
                AuthIdentityRecord.provider == "line",
                AuthIdentityRecord.person_id == AccessAuditRecord.target_person_id,
                AccessAuditRecord.reason == BOOTSTRAP_REASON,
            )
        )
        or 0
    )
    return {
        "allowlisted_member": _count(len(members)),
        "person_state": person_state,
        "reliable_line_identity": identity_state,
        "pending_review_thread": _count(pending_thread_count),
        "legacy_line_link": _count(len(legacy_rows)),
        "active_team_player": _count(team_player_count),
        "bootstrap_audit": _count(audit_count),
    }


def _default_result() -> dict[str, str]:
    return {
        "runtime_artifact_git": "fail",
        "gcloud_metadata": "fail",
        "private_pg": "fail",
        "connection": "fail",
        "schema": "fail",
        "read_logging": "fail",
        "allowlisted_member": "other",
        "person_state": "other",
        "reliable_line_identity": "other",
        "pending_review_thread": "other",
        "legacy_line_link": "other",
        "active_team_player": "other",
        "bootstrap_audit": "other",
    }


def classify(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = os.environ if environ is None else environ
    result = _default_result()
    private_values: dict[str, str] = {}
    allowlist: set[int] = set()
    database_url = ""
    engine: Engine | None = None
    try:
        try:
            _verify_runtime_git(environment)
            result["runtime_artifact_git"] = "pass"
        except Exception:
            return result
        try:
            allowlist = boundary._verify_gcloud_and_load_allowlist()
            result["gcloud_metadata"] = "pass"
        except Exception:
            return result
        try:
            private_values = boundary._load_private_pg_environment(
                boundary.PRIVATE_ENV_PATH
            )
            database_url = boundary._database_url(private_values)
            result["private_pg"] = "pass"
        except Exception:
            return result
        try:
            engine = create_engine(database_url, pool_pre_ping=True)
            with Session(engine) as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                session.execute(text("SET LOCAL statement_timeout = '15s'"))
                session.execute(text("SET LOCAL lock_timeout = '5s'"))
                session.execute(
                    text("SET LOCAL idle_in_transaction_session_timeout = '30s'")
                )
                result["connection"] = "pass"
                try:
                    revision = session.scalar(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    )
                    result["schema"] = (
                        "pass" if revision == boundary.SCHEMA_REVISION else "fail"
                    )
                except Exception:
                    result["schema"] = "fail"
                try:
                    result["read_logging"] = (
                        "pass" if boundary._read_logging_safe(session) else "fail"
                    )
                except Exception:
                    result["read_logging"] = "fail"
                if result["schema"] == "pass" and result["read_logging"] == "pass":
                    try:
                        result.update(_candidate_state(session, allowlist))
                    except Exception:
                        pass
        except Exception:
            result["connection"] = "fail"
        return result
    finally:
        if engine is not None:
            engine.dispose()
        private_values.clear()
        allowlist.clear()
        database_url = ""


def _emit(result: Mapping[str, str]) -> None:
    if tuple(result) != OUTPUT_FIELDS:
        raise CandidateDiagnosticError("output boundary failed")
    if any(result[field] not in ("pass", "fail") for field in OUTPUT_FIELDS[:6]):
        raise CandidateDiagnosticError("output boundary failed")
    if any(result[field] not in ("zero", "one", "other") for field in COUNT_FIELDS):
        raise CandidateDiagnosticError("output boundary failed")
    if result["person_state"] not in PERSON_STATES:
        raise CandidateDiagnosticError("output boundary failed")
    if result["reliable_line_identity"] not in IDENTITY_STATES:
        raise CandidateDiagnosticError("output boundary failed")
    print(json.dumps(result, separators=(",", ":")))


def main() -> None:
    try:
        _emit(classify())
    except Exception:
        _emit(_default_result())


if __name__ == "__main__":
    main()
