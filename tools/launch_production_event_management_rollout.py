"""No-disclosure launcher for the TASK-164 production 0008-to-0009 rollout."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import portal_data_event_management_rollout as operator

ARTIFACT = ROOT / "tools" / "launch_production_event_management_rollout.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MATERIAL_CHECKSUMS = ROOT / "tools" / "TASK-164-event-rollout-materials.sha256"
PROJECT = "ntubtob-schedule-405614"
REGION = "asia-east1"
SERVICE = "web-portal"
EXPECTED_READY_REVISION = "web-portal-00051-p4z"
REQUIRED_RUNTIME_VALUES = {
    "PORTAL_DATA_PHASE_C_ENABLED": "true",
    "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "false",
    "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED": "true",
}
REQUIRED_SECRET_KEYS = frozenset(
    {
        "DSN_PASSWORD",
        "LINE_LOGIN_CHANNEL_SECRET",
        "SECRET_KEY",
        "WEATHER_API_KEY",
    }
)
IDENTITY_LINK_KEYS = frozenset(
    {
        "WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID",
        "WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET",
        "WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI",
        "WEB_IDENTITY_LINK_LINE_CLIENT_ID",
        "WEB_IDENTITY_LINK_LINE_CLIENT_SECRET",
        "WEB_IDENTITY_LINK_LINE_REDIRECT_URI",
    }
)
REQUIRED_PACKAGES = {
    "SQLAlchemy": "2.0.23",
    "alembic": "1.13.1",
    "psycopg2-binary": "2.9.9",
}


class LauncherError(RuntimeError):
    """Raised when target identity or private-input boundaries fail closed."""


@dataclass(frozen=True)
class DatabaseTarget:
    hostname: str
    port: str
    database: str
    username: str


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _verify_checksum(path: Path, checksum_path: Path) -> None:
    digest, separator, name = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != path.name or digest != _canonical_digest(path):
        raise LauncherError("artifact checksum boundary is invalid")


def verify_artifacts() -> None:
    _verify_checksum(ARTIFACT, CHECKSUM)
    operator.verify_artifact()
    expected: dict[str, str] = {}
    for line in MATERIAL_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or name in expected
        ):
            raise LauncherError("material checksum manifest is invalid")
        expected[name] = digest
    paths = {
        ARTIFACT.name: ARTIFACT,
        operator.ARTIFACT.name: operator.ARTIFACT,
        operator.MIGRATION.name: operator.MIGRATION,
        "env.py": ROOT / "migrations" / "env.py",
        "alembic.ini": ROOT / "alembic.ini",
    }
    if set(expected) != set(paths) or any(
        expected[name] != _canonical_digest(path) for name, path in paths.items()
    ):
        raise LauncherError("material artifact checksum is invalid")


def _run_text(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise LauncherError("repository or cloud command failed") from None
    return result.stdout.strip()


def _verify_repository(execute: bool, approved_commit: str | None) -> None:
    if Path.cwd().resolve() != ROOT.resolve():
        raise LauncherError("launcher must run from repository root")
    if sys.version_info[:2] != (3, 10):
        raise LauncherError("Python 3.10 runtime is required")
    if any(
        importlib.metadata.version(name) != version
        for name, version in REQUIRED_PACKAGES.items()
    ):
        raise LauncherError("dependency boundary failed")
    git = shutil.which("git")
    if git is None:
        raise LauncherError("Git executable is unavailable")
    if _run_text([git, "status", "--porcelain"]):
        raise LauncherError("repository working tree is not clean")
    branch = _run_text([git, "branch", "--show-current"])
    head = _run_text([git, "rev-parse", "HEAD"])
    origin = _run_text([git, "rev-parse", "origin/main"])
    if branch != "main" or head != origin:
        raise LauncherError("repository is not exact merged main")
    if not execute:
        if approved_commit is not None:
            raise LauncherError("dry-run rejects execution approval")
        return
    if not isinstance(approved_commit, str) or not re.fullmatch(
        r"[0-9a-f]{40}", approved_commit
    ):
        raise LauncherError("approved merged commit is invalid")
    if head != approved_commit:
        raise LauncherError("repository is not exact approved merged main")


def _gcloud() -> str:
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if executable is None:
        raise LauncherError("gcloud executable is unavailable")
    return executable


def _clear(value: object) -> None:
    if isinstance(value, dict):
        for child in tuple(value.values()):
            _clear(child)
        value.clear()
    elif isinstance(value, list):
        for child in tuple(value):
            _clear(child)
        value.clear()
    elif isinstance(value, bytearray):
        value.clear()


def _json_document(command: Sequence[str], label: str) -> dict:
    response = bytearray()
    error = bytearray()
    document: object = {}
    try:
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=False,
            timeout=30,
        )
        response = bytearray(result.stdout or b"")
        error = bytearray(result.stderr or b"")
        if result.returncode != 0 or not response:
            raise LauncherError(f"{label} inventory failed")
        document = json.loads(response)
        if not isinstance(document, dict):
            raise LauncherError(f"{label} inventory is malformed")
        return document
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        raise LauncherError(f"{label} inventory failed") from None
    finally:
        response.clear()
        error.clear()


def _active_account_present(gcloud: str) -> bool:
    response = bytearray()
    error = bytearray()
    try:
        result = subprocess.run(
            [
                gcloud,
                "auth",
                "list",
                "--filter=status:ACTIVE",
                "--format=value(account)",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=False,
            timeout=30,
        )
        response = bytearray(result.stdout or b"")
        error = bytearray(result.stderr or b"")
        values = response.splitlines()
        return result.returncode == 0 and len(values) == 1 and bool(values[0].strip())
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        response.clear()
        error.clear()


def _plain_or_secret_entries(revision: dict) -> dict[str, dict]:
    containers = revision.get("spec", {}).get("containers", [])
    if len(containers) != 1 or not isinstance(containers[0], dict):
        raise LauncherError("Ready revision container contract is malformed")
    entries = containers[0].get("env", [])
    if not isinstance(entries, list) or any(
        not isinstance(item, dict) for item in entries
    ):
        raise LauncherError("Ready revision environment contract is malformed")
    by_name: dict[str, dict] = {}
    for entry in entries:
        name = entry.get("name")
        if not isinstance(name, str) or not name or name in by_name:
            raise LauncherError("Ready revision environment contract is ambiguous")
        by_name[name] = entry
    return by_name


def _plain_value(entries: dict[str, dict], name: str) -> str:
    entry = entries.get(name)
    if not isinstance(entry, dict) or set(entry) != {"name", "value"}:
        raise LauncherError("production database metadata is not plain and exact")
    value = entry.get("value")
    if not isinstance(value, str) or not value:
        raise LauncherError("production database metadata is unavailable")
    return value


def _secret_backed(entries: dict[str, dict], name: str) -> bool:
    entry = entries.get(name)
    if not isinstance(entry, dict) or set(entry) != {"name", "valueFrom"}:
        return False
    secret = entry.get("valueFrom", {}).get("secretKeyRef", {})
    return (
        isinstance(secret, dict)
        and set(secret) == {"name", "key"}
        and all(
            isinstance(secret.get(key), str) and secret[key] for key in ("name", "key")
        )
    )


def _validate_cloud_contract(
    service: dict, revision: dict, policy: dict
) -> DatabaseTarget:
    metadata = service.get("metadata", {})
    latest_ready = service.get("status", {}).get("latestReadyRevisionName")
    traffic = service.get("status", {}).get("traffic", [])
    service_identity = (
        service.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("serviceAccountName")
    )
    revision_identity = revision.get("spec", {}).get("serviceAccountName")
    conditions = revision.get("status", {}).get("conditions", [])
    traffic_exact = (
        isinstance(traffic, list)
        and len(traffic) == 1
        and isinstance(traffic[0], dict)
        and traffic[0].get("revisionName") == latest_ready
        and traffic[0].get("percent") == 100
    )
    if (
        metadata.get("name") != SERVICE
        or metadata.get("labels", {}).get("cloud.googleapis.com/location") != REGION
        or metadata.get("annotations", {}).get("run.googleapis.com/ingress") != "all"
        or not isinstance(latest_ready, str)
        or latest_ready != EXPECTED_READY_REVISION
        or revision.get("metadata", {}).get("name") != latest_ready
        or not traffic_exact
        or not isinstance(service_identity, str)
        or not service_identity
        or revision_identity != service_identity
        or not any(
            item.get("type") == "Ready" and item.get("status") == "True"
            for item in conditions
            if isinstance(item, dict)
        )
    ):
        raise LauncherError("Cloud Run production identity contract drifted")
    if not any(
        binding.get("role") == "roles/run.invoker"
        and "allUsers" in binding.get("members", [])
        for binding in policy.get("bindings", [])
        if isinstance(binding, dict)
    ):
        raise LauncherError("Cloud Run public boundary drifted")
    entries = _plain_or_secret_entries(revision)
    if any(name in entries for name in IDENTITY_LINK_KEYS):
        raise LauncherError("production identity-link contract drifted")
    if any(
        _plain_value(entries, name) != value
        for name, value in REQUIRED_RUNTIME_VALUES.items()
    ):
        raise LauncherError("production runtime flag contract drifted")
    if any(not _secret_backed(entries, name) for name in REQUIRED_SECRET_KEYS):
        raise LauncherError("production Secret reference categories drifted")
    port = _plain_value(entries, "DSN_PORT")
    if not re.fullmatch(r"[1-9]\d{0,4}", port):
        raise LauncherError("production database port category is invalid")
    return DatabaseTarget(
        hostname=_plain_value(entries, "DSN_HOSTNAME"),
        port=port,
        database=_plain_value(entries, "DSN_DATABASE"),
        username=_plain_value(entries, "DSN_UID"),
    )


def _load_cloud_target() -> DatabaseTarget:
    gcloud = _gcloud()
    if not _active_account_present(gcloud):
        raise LauncherError("active gcloud account is unavailable")
    if _run_text([gcloud, "config", "get-value", "project", "--quiet"]) != PROJECT:
        raise LauncherError("active gcloud project is not production")
    service: dict = {}
    revision: dict = {}
    policy: dict = {}
    try:
        service = _json_document(
            [
                gcloud,
                "run",
                "services",
                "describe",
                SERVICE,
                "--project",
                PROJECT,
                "--region",
                REGION,
                "--format=json",
            ],
            "Cloud Run service",
        )
        latest_ready = service.get("status", {}).get("latestReadyRevisionName")
        if not isinstance(latest_ready, str) or not re.fullmatch(
            r"web-portal-[a-z0-9-]+", latest_ready
        ):
            raise LauncherError("Cloud Run Ready revision is unavailable")
        revision = _json_document(
            [
                gcloud,
                "run",
                "revisions",
                "describe",
                latest_ready,
                "--project",
                PROJECT,
                "--region",
                REGION,
                "--format=json",
            ],
            "Cloud Run revision",
        )
        policy = _json_document(
            [
                gcloud,
                "run",
                "services",
                "get-iam-policy",
                SERVICE,
                "--project",
                PROJECT,
                "--region",
                REGION,
                "--format=json",
            ],
            "Cloud Run IAM",
        )
        return _validate_cloud_contract(service, revision, policy)
    finally:
        _clear(service)
        _clear(revision)
        _clear(policy)


def _database_target(database_url: str) -> DatabaseTarget:
    try:
        value = make_url(database_url)
    except Exception:
        raise LauncherError("private database input format is invalid") from None
    if (
        value.drivername not in {"postgresql", "postgresql+psycopg2"}
        or not value.host
        or value.port is None
        or not value.database
        or not value.username
        or not value.password
        or set(value.query) != {"sslmode"}
        or not isinstance(value.query["sslmode"], str)
        or value.query["sslmode"] not in {"require", "verify-ca", "verify-full"}
    ):
        raise LauncherError("private database input contract is invalid")
    return DatabaseTarget(
        hostname=value.host,
        port=str(value.port),
        database=value.database,
        username=value.username,
    )


def _require_target_match(database_url: str, target: DatabaseTarget) -> None:
    if _database_target(database_url) != target:
        raise LauncherError("private database target does not match production runtime")


def run(*, execute: bool, approved_commit: str | None = None) -> dict[str, object]:
    verify_artifacts()
    _verify_repository(execute, approved_commit)
    target = _load_cloud_target()
    database_url = ""
    acknowledgement: str | None = None
    try:
        database_url = getpass.getpass("Production database URL: ")
        _require_target_match(database_url, target)
        if execute:
            acknowledgement = getpass.getpass("Execution acknowledgement: ")
        return operator.run(
            "execute" if execute else "dry-run",
            database_url,
            acknowledgement,
        )
    finally:
        database_url = ""
        acknowledgement = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-commit")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        run(execute=args.execute, approved_commit=args.approved_commit)
    except Exception:
        raise SystemExit("TASK-164 production rollout stopped safely") from None


if __name__ == "__main__":
    main()
