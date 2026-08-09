"""Exact no-disclosure launcher for the reviewed TASK-086 production sequence."""

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

from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import portal_data_production_zero_admin_bootstrap as operator

ARTIFACT = ROOT / "tools" / "launch_production_zero_admin_bootstrap.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MATERIAL_CHECKSUMS = ROOT / "tools" / "TASK-086-production-bootstrap.sha256"
RUNTIME_EXECUTABLE = Path(
    r"C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
RUNTIME_VERSION = (3, 12, 13)
PRIVATE_ENV_PATH = Path(r"C:\Users\USER\.ntubtob-private\backup.env")
GCLOUD = Path(
    r"C:\Users\USER\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)
GIT = "git"
ACCOUNT = "yces3108@gmail.com"
PROJECT = "ntubtob-schedule-405614"
SERVICE = "web-portal"
REGION = "asia-east1"
APPROVED_COMMIT_ENV = "TASK086_APPROVED_MERGED_COMMIT"
ALLOWLIST_NAME = "WEB_PORTAL_ADMIN_MEMBER_IDS"
METADATA_FORMAT = "json(spec.template.spec.containers[0].env)"
REQUIRED_PACKAGES = {
    "SQLAlchemy": "2.0.23",
    "alembic": "1.13.1",
    "psycopg2-binary": "2.9.9",
}
PG_KEYS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
SEQUENCE = ("discovery", "preflight", "dry-run", "execute", "post-check")


class LauncherError(RuntimeError):
    """Raised when the exact production launcher cannot prove its boundary."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _verify_checksum(path: Path, checksum_path: Path) -> None:
    digest, separator, name = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != path.name or digest != _canonical_digest(path):
        raise LauncherError("launcher checksum boundary is invalid")


def verify_artifacts() -> None:
    _verify_checksum(ARTIFACT, CHECKSUM)
    operator.verify_artifact()
    expected = {}
    for line in MATERIAL_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LauncherError("material checksum manifest is invalid")
        expected[name] = digest
    paths = {
        "portal_data_production_zero_admin_bootstrap.py": operator.ARTIFACT,
        "identity_lifecycle.py": ROOT
        / "shared_lib"
        / "shared_module"
        / "portal_data"
        / "identity_lifecycle.py",
        "models.py": ROOT
        / "shared_lib"
        / "shared_module"
        / "portal_data"
        / "models.py",
    }
    if set(expected) != set(paths):
        raise LauncherError("material checksum set is invalid")
    if any(expected[name] != _canonical_digest(path) for name, path in paths.items()):
        raise LauncherError("material artifact checksum is invalid")


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


def _verify_runtime(environ: Mapping[str, str]) -> None:
    if Path.cwd().resolve() != ROOT.resolve():
        raise LauncherError("launcher must run from the repository root")
    if (
        Path(sys.executable).resolve() != RUNTIME_EXECUTABLE.resolve()
        or sys.version_info[:3] != RUNTIME_VERSION
        or not RUNTIME_EXECUTABLE.is_file()
    ):
        raise LauncherError("approved Python runtime is unavailable")
    if any(
        importlib.metadata.version(name) != version
        for name, version in REQUIRED_PACKAGES.items()
    ):
        raise LauncherError("Python dependency versions are invalid")
    approved = environ.get(APPROVED_COMMIT_ENV, "")
    if not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise LauncherError("approved merged commit is unavailable")
    if _run([GIT, "rev-parse", "HEAD"]) != approved:
        raise LauncherError("repository commit is not approved")
    if _run([GIT, "status", "--porcelain"]):
        raise LauncherError("repository working tree is not clean")
    if not GCLOUD.is_file():
        raise LauncherError("approved gcloud executable is unavailable")
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
        raise LauncherError("gcloud identity guard failed")


def _load_private_pg_environment(path: Path) -> dict[str, str]:
    if path != PRIVATE_ENV_PATH or not path.is_file():
        raise LauncherError("approved private environment file is unavailable")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        key, separator, value = raw_line.partition("=")
        if not separator or key not in PG_KEYS or not value or key in values:
            raise LauncherError("private environment contract is invalid")
        values[key] = value
    if set(values) != set(PG_KEYS) or not re.fullmatch(
        r"[1-9]\d{0,4}", values["PGPORT"]
    ):
        raise LauncherError("private environment contract is incomplete")
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


def _extract_plain_allowlist(metadata: object) -> str:
    if not isinstance(metadata, dict) or set(metadata) != {"spec"}:
        raise LauncherError("metadata boundary failed")
    template = metadata["spec"]
    if not isinstance(template, dict) or set(template) != {"template"}:
        raise LauncherError("metadata boundary failed")
    spec = template["template"]
    if not isinstance(spec, dict) or set(spec) != {"spec"}:
        raise LauncherError("metadata boundary failed")
    container_spec = spec["spec"]
    if not isinstance(container_spec, dict) or set(container_spec) != {"containers"}:
        raise LauncherError("metadata boundary failed")
    containers = container_spec["containers"]
    if not isinstance(containers, list) or len(containers) != 1:
        raise LauncherError("metadata boundary failed")
    container = containers[0]
    if not isinstance(container, dict) or set(container) != {"env"}:
        raise LauncherError("metadata boundary failed")
    entries = container["env"]
    if not isinstance(entries, list):
        raise LauncherError("metadata boundary failed")
    matches = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise LauncherError("metadata boundary failed")
        keys = set(entry)
        if keys not in ({"name", "value"}, {"name", "valueFrom"}):
            raise LauncherError("metadata boundary failed")
        if not isinstance(entry["name"], str) or not entry["name"]:
            raise LauncherError("metadata boundary failed")
        if keys == {"name", "value"} and not isinstance(entry["value"], str):
            raise LauncherError("metadata boundary failed")
        if keys == {"name", "valueFrom"}:
            value_from = entry["valueFrom"]
            if not isinstance(value_from, dict) or set(value_from) != {"secretKeyRef"}:
                raise LauncherError("metadata boundary failed")
            secret_ref = value_from["secretKeyRef"]
            if (
                not isinstance(secret_ref, dict)
                or set(secret_ref) != {"key", "name"}
                or not all(
                    isinstance(secret_ref[field], str) and secret_ref[field]
                    for field in ("key", "name")
                )
            ):
                raise LauncherError("metadata boundary failed")
        if entry["name"] == ALLOWLIST_NAME:
            if keys != {"name", "value"} or not isinstance(entry["value"], str):
                raise LauncherError("metadata boundary failed")
            matches.append(entry["value"])
    if len(matches) != 1:
        raise LauncherError("metadata boundary failed")
    try:
        operator._allowlist(matches[0])
    except Exception:
        raise LauncherError("metadata boundary failed") from None
    return matches[0]


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
        raise LauncherError("metadata boundary failed")
    return response, error


def _load_allowlist() -> str:
    response = bytearray()
    error = bytearray()
    metadata: object = {}
    try:
        response, error = _load_env_metadata()
        metadata = json.loads(response)
        return _extract_plain_allowlist(metadata)
    except Exception:
        raise LauncherError("metadata boundary failed") from None
    finally:
        _clear_metadata(metadata)
        response.clear()
        error.clear()


def _require_clean_process_environment() -> None:
    sensitive_keys = (
        operator.DATABASE_ENV,
        operator.ALLOWLIST_ENV,
        operator.EXECUTION_ENV,
    )
    if any(os.environ.get(key) is not None for key in sensitive_keys):
        raise LauncherError("temporary operator environment is not clean")


def run(environ: Mapping[str, str] | None = None) -> None:
    environment = os.environ if environ is None else environ
    verify_artifacts()
    _require_clean_process_environment()
    _verify_runtime(environment)
    private_values = _load_private_pg_environment(PRIVATE_ENV_PATH)
    allowlist = _load_allowlist()
    database_url = _database_url(private_values)
    process_keys = (
        operator.DATABASE_ENV,
        operator.ALLOWLIST_ENV,
        operator.EXECUTION_ENV,
    )
    try:
        os.environ[operator.DATABASE_ENV] = database_url
        os.environ[operator.ALLOWLIST_ENV] = allowlist
        for mode in SEQUENCE:
            if mode == "execute":
                os.environ[operator.EXECUTION_ENV] = operator.EXECUTION_ACKNOWLEDGEMENT
            else:
                os.environ.pop(operator.EXECUTION_ENV, None)
            operator.run(mode)
    finally:
        for key in process_keys:
            os.environ.pop(key, None)
        private_values.clear()
        allowlist = ""
        database_url = ""


def main() -> None:
    try:
        run()
    except Exception:
        raise SystemExit("TASK-086 production launcher stopped") from None


if __name__ == "__main__":
    main()
