"""Fixed-schema, read-only TASK-086 production outcome classifier."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, Engine
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
    PersonRecord,
)

ARTIFACT = ROOT / "tools" / "portal_data_production_bootstrap_diagnostic.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MATERIAL_CHECKSUMS = ROOT / "tools" / "TASK-086-readonly-diagnostic.sha256"
RUNTIME_EXECUTABLE = Path(
    r"C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
RUNTIME_VERSION = (3, 12, 13)
REQUIRED_PACKAGES = {
    "SQLAlchemy": "2.0.23",
    "alembic": "1.13.1",
    "psycopg2-binary": "2.9.9",
}
PRIVATE_ENV_PATH = Path(r"C:\Users\USER\.ntubtob-private\backup.env")
GCLOUD = Path(
    r"C:\Users\USER\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)
GIT = "git"
ACCOUNT = "yces3108@gmail.com"
PROJECT = "ntubtob-schedule-405614"
SERVICE = "web-portal"
REGION = "asia-east1"
APPROVED_COMMIT_ENV = "TASK086_DIAGNOSTIC_APPROVED_MERGED_COMMIT"
ALLOWLIST_NAME = "WEB_PORTAL_ADMIN_MEMBER_IDS"
METADATA_FORMAT = "json(spec.template.spec.containers[0].env)"
PG_KEYS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
SCHEMA_REVISION = "0004_phase_c_identity_lifecycle"
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
    "active_admin",
    "completed_relationship",
)


class DiagnosticError(RuntimeError):
    """Internal fixed-boundary failure; its text is never emitted."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _verify_checksum(path: Path, checksum_path: Path) -> None:
    digest, separator, name = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != path.name or digest != _canonical_digest(path):
        raise DiagnosticError("artifact boundary failed")


def _verify_artifacts() -> None:
    _verify_checksum(ARTIFACT, CHECKSUM)
    expected = {}
    for line in MATERIAL_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DiagnosticError("material boundary failed")
        expected[name] = digest
    paths = {
        "models.py": ROOT
        / "shared_lib"
        / "shared_module"
        / "portal_data"
        / "models.py",
    }
    if set(expected) != set(paths):
        raise DiagnosticError("material boundary failed")
    if any(expected[name] != _canonical_digest(path) for name, path in paths.items()):
        raise DiagnosticError("material boundary failed")


def _run(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _verify_runtime_git(environ: Mapping[str, str]) -> None:
    _verify_artifacts()
    if (
        Path.cwd().resolve() != ROOT.resolve()
        or Path(sys.executable).resolve() != RUNTIME_EXECUTABLE.resolve()
        or sys.version_info[:3] != RUNTIME_VERSION
        or not RUNTIME_EXECUTABLE.is_file()
    ):
        raise DiagnosticError("runtime boundary failed")
    if any(
        importlib.metadata.version(name) != version
        for name, version in REQUIRED_PACKAGES.items()
    ):
        raise DiagnosticError("runtime boundary failed")
    approved = environ.get(APPROVED_COMMIT_ENV, "")
    if not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise DiagnosticError("git boundary failed")
    if _run([GIT, "rev-parse", "HEAD"]) != approved:
        raise DiagnosticError("git boundary failed")
    if _run([GIT, "status", "--porcelain"]):
        raise DiagnosticError("git boundary failed")


def _allowlist(value: str) -> set[int]:
    parts = value.split(",")
    if not parts or any(not re.fullmatch(r"[1-9]\d*", part) for part in parts):
        raise DiagnosticError("metadata boundary failed")
    values = {int(part) for part in parts}
    if len(values) != len(parts):
        raise DiagnosticError("metadata boundary failed")
    return values


def _clear_metadata(value: object) -> None:
    if isinstance(value, dict):
        for child in tuple(value.values()):
            _clear_metadata(child)
        value.clear()
    elif isinstance(value, list):
        for child in tuple(value):
            _clear_metadata(child)
        value.clear()
    elif isinstance(value, bytearray):
        value.clear()


def _extract_plain_allowlist(metadata: object) -> set[int]:
    if not isinstance(metadata, dict) or set(metadata) != {"spec"}:
        raise DiagnosticError("metadata boundary failed")
    template = metadata["spec"]
    if not isinstance(template, dict) or set(template) != {"template"}:
        raise DiagnosticError("metadata boundary failed")
    spec = template["template"]
    if not isinstance(spec, dict) or set(spec) != {"spec"}:
        raise DiagnosticError("metadata boundary failed")
    container_spec = spec["spec"]
    if not isinstance(container_spec, dict) or set(container_spec) != {"containers"}:
        raise DiagnosticError("metadata boundary failed")
    containers = container_spec["containers"]
    if not isinstance(containers, list) or len(containers) != 1:
        raise DiagnosticError("metadata boundary failed")
    container = containers[0]
    if not isinstance(container, dict) or set(container) != {"env"}:
        raise DiagnosticError("metadata boundary failed")
    entries = container["env"]
    if not isinstance(entries, list):
        raise DiagnosticError("metadata boundary failed")
    matches = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DiagnosticError("metadata boundary failed")
        keys = set(entry)
        if keys not in ({"name", "value"}, {"name", "valueFrom"}):
            raise DiagnosticError("metadata boundary failed")
        if not isinstance(entry["name"], str) or not entry["name"]:
            raise DiagnosticError("metadata boundary failed")
        if keys == {"name", "value"} and not isinstance(entry["value"], str):
            raise DiagnosticError("metadata boundary failed")
        if keys == {"name", "valueFrom"}:
            value_from = entry["valueFrom"]
            if not isinstance(value_from, dict) or set(value_from) != {"secretKeyRef"}:
                raise DiagnosticError("metadata boundary failed")
            secret_ref = value_from["secretKeyRef"]
            if (
                not isinstance(secret_ref, dict)
                or set(secret_ref) != {"secret", "version"}
                or not all(
                    isinstance(secret_ref[field], str) and secret_ref[field]
                    for field in ("secret", "version")
                )
            ):
                raise DiagnosticError("metadata boundary failed")
        if entry["name"] == ALLOWLIST_NAME:
            if keys != {"name", "value"} or not isinstance(entry["value"], str):
                raise DiagnosticError("metadata boundary failed")
            matches.append(entry["value"])
    if len(matches) != 1:
        raise DiagnosticError("metadata boundary failed")
    return _allowlist(matches[0])


def _load_env_metadata() -> tuple[bytearray, bytearray]:
    result = subprocess.run(
        [
            str(GCLOUD),
            "run",
            "services",
            "describe",
            SERVICE,
            "--account",
            ACCOUNT,
            "--project",
            PROJECT,
            "--region",
            REGION,
            f"--format={METADATA_FORMAT}",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=False,
        timeout=30,
    )
    response = bytearray(result.stdout or b"")
    error = bytearray(result.stderr or b"")
    if result.returncode != 0:
        response.clear()
        error.clear()
        raise DiagnosticError("metadata boundary failed")
    return response, error


def _verify_gcloud_and_load_allowlist() -> set[int]:
    if not GCLOUD.is_file():
        raise DiagnosticError("gcloud boundary failed")
    account = _run(
        [
            str(GCLOUD),
            "auth",
            "list",
            "--filter=status:ACTIVE",
            "--format=value(account)",
        ]
    )
    project = _run([str(GCLOUD), "config", "get-value", "project", "--quiet"])
    if account != ACCOUNT or project != PROJECT:
        raise DiagnosticError("gcloud boundary failed")
    response = bytearray()
    error = bytearray()
    metadata: object = {}
    try:
        response, error = _load_env_metadata()
        metadata = json.loads(response)
        return _extract_plain_allowlist(metadata)
    except Exception:
        raise DiagnosticError("metadata boundary failed") from None
    finally:
        _clear_metadata(metadata)
        response.clear()
        error.clear()


def _load_private_pg_environment(path: Path) -> dict[str, str]:
    if path != PRIVATE_ENV_PATH or not path.is_file():
        raise DiagnosticError("private PG boundary failed")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        key, separator, value = raw_line.partition("=")
        if not separator or key not in PG_KEYS or not value or key in values:
            raise DiagnosticError("private PG boundary failed")
        values[key] = value
    if set(values) != set(PG_KEYS) or not re.fullmatch(
        r"[1-9]\d{0,4}", values["PGPORT"]
    ):
        raise DiagnosticError("private PG boundary failed")
    return values


def _database_url(values: Mapping[str, str]) -> str:
    return URL.create(
        "postgresql+psycopg2",
        username=values["PGUSER"],
        password=values["PGPASSWORD"],
        host=values["PGHOST"],
        port=int(values["PGPORT"]),
        database=values["PGDATABASE"],
    ).render_as_string(hide_password=False)


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


def _active_admin_count(session: Session, allowlist: set[int]) -> int:
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


def _completed_relationship_count(session: Session, allowlist: set[int]) -> int:
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
                AccessAuditRecord.reason == BOOTSTRAP_REASON,
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


def _count_classification(value: int) -> str:
    if value == 0:
        return "zero"
    if value == 1:
        return "one"
    return "other"


def _default_result() -> dict[str, str]:
    return {
        "runtime_artifact_git": "fail",
        "gcloud_metadata": "fail",
        "private_pg": "fail",
        "connection": "fail",
        "schema": "fail",
        "read_logging": "fail",
        "active_admin": "other",
        "completed_relationship": "other",
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
            allowlist = _verify_gcloud_and_load_allowlist()
            result["gcloud_metadata"] = "pass"
        except Exception:
            return result
        try:
            private_values = _load_private_pg_environment(PRIVATE_ENV_PATH)
            database_url = _database_url(private_values)
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
                    schema = session.scalar(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    )
                    result["schema"] = "pass" if schema == SCHEMA_REVISION else "fail"
                except Exception:
                    result["schema"] = "fail"
                try:
                    result["read_logging"] = (
                        "pass" if _read_logging_safe(session) else "fail"
                    )
                except Exception:
                    result["read_logging"] = "fail"
                try:
                    result["active_admin"] = _count_classification(
                        _active_admin_count(session, allowlist)
                    )
                except Exception:
                    result["active_admin"] = "other"
                try:
                    result["completed_relationship"] = _count_classification(
                        _completed_relationship_count(session, allowlist)
                    )
                except Exception:
                    result["completed_relationship"] = "other"
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
        raise DiagnosticError("output boundary failed")
    if any(result[field] not in ("pass", "fail") for field in OUTPUT_FIELDS[:6]):
        raise DiagnosticError("output boundary failed")
    if any(
        result[field] not in ("zero", "one", "other") for field in OUTPUT_FIELDS[6:]
    ):
        raise DiagnosticError("output boundary failed")
    print(json.dumps(result, separators=(",", ":")))


def main() -> None:
    try:
        _emit(classify())
    except Exception:
        _emit(_default_result())


if __name__ == "__main__":
    main()
