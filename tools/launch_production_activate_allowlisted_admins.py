"""Exact no-disclosure launcher for TASK-086 exact-two activation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import launch_production_zero_admin_bootstrap as boundary
from tools import portal_data_production_activate_allowlisted_admins as operator

ARTIFACT = ROOT / "tools" / "launch_production_activate_allowlisted_admins.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MATERIAL_CHECKSUMS = ROOT / "tools" / "TASK-086-exact-two-activation.sha256"
APPROVED_COMMIT_ENV = "TASK086_EXACT_TWO_APPROVED_MERGED_COMMIT"
SEQUENCE = ("preflight", "execute", "post-check")


class ExactTwoLauncherError(RuntimeError):
    """Raised when the exact-two launcher cannot prove its boundary."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _verify_checksum(path: Path, checksum_path: Path) -> None:
    digest, separator, name = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != path.name or digest != _canonical_digest(path):
        raise ExactTwoLauncherError("launcher checksum boundary is invalid")


def verify_artifacts() -> None:
    _verify_checksum(ARTIFACT, CHECKSUM)
    operator.verify_artifact()
    expected = {}
    for line in MATERIAL_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ExactTwoLauncherError("material checksum manifest is invalid")
        expected[name] = digest
    paths = {
        operator.ARTIFACT.name: operator.ARTIFACT,
        "models.py": ROOT
        / "shared_lib"
        / "shared_module"
        / "portal_data"
        / "models.py",
        boundary.ARTIFACT.name: boundary.ARTIFACT,
    }
    if set(expected) != set(paths) or any(
        expected[name] != _canonical_digest(path) for name, path in paths.items()
    ):
        raise ExactTwoLauncherError("material artifact checksum is invalid")


def _verify_runtime(environ: Mapping[str, str]) -> None:
    if Path.cwd().resolve() != ROOT.resolve():
        raise ExactTwoLauncherError("launcher must run from repository root")
    if (
        Path(sys.executable).resolve() != boundary.RUNTIME_EXECUTABLE.resolve()
        or sys.version_info[:3] != boundary.RUNTIME_VERSION
        or not boundary.RUNTIME_EXECUTABLE.is_file()
    ):
        raise ExactTwoLauncherError("approved Python runtime is unavailable")
    if any(
        importlib.metadata.version(name) != version
        for name, version in boundary.REQUIRED_PACKAGES.items()
    ):
        raise ExactTwoLauncherError("dependency boundary failed")
    approved = environ.get(APPROVED_COMMIT_ENV, "")
    if not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise ExactTwoLauncherError("approved merged commit is unavailable")
    if boundary._run([boundary.GIT, "rev-parse", "HEAD"]) != approved:
        raise ExactTwoLauncherError("repository commit is not approved")
    if boundary._run([boundary.GIT, "status", "--porcelain"]):
        raise ExactTwoLauncherError("repository working tree is not clean")
    if not boundary.GCLOUD.is_file():
        raise ExactTwoLauncherError("approved gcloud executable is unavailable")
    account = boundary._run(
        [
            str(boundary.GCLOUD),
            "auth",
            "list",
            "--filter=status:ACTIVE",
            "--format=value(account)",
        ]
    )
    project = boundary._run(
        [str(boundary.GCLOUD), "config", "get-value", "project", "--quiet"]
    )
    if account != boundary.ACCOUNT or project != boundary.PROJECT:
        raise ExactTwoLauncherError("gcloud identity guard failed")


def _require_clean_environment() -> None:
    if any(
        os.environ.get(key) is not None
        for key in (
            operator.DATABASE_ENV,
            operator.ALLOWLIST_ENV,
            operator.EXECUTION_ENV,
        )
    ):
        raise ExactTwoLauncherError("temporary operator environment is not clean")


def run(environ: Mapping[str, str] | None = None) -> None:
    environment = os.environ if environ is None else environ
    verify_artifacts()
    _require_clean_environment()
    _verify_runtime(environment)
    private_values: dict[str, str] = {}
    allowlist = ""
    database_url = ""
    process_keys = (
        operator.DATABASE_ENV,
        operator.ALLOWLIST_ENV,
        operator.EXECUTION_ENV,
    )
    try:
        private_values = boundary._load_private_pg_environment(
            boundary.PRIVATE_ENV_PATH
        )
        allowlist = boundary._load_allowlist()
        operator._allowlist(allowlist)
        database_url = boundary._database_url(private_values)
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
        raise SystemExit("TASK-086 exact-two activation stopped") from None


if __name__ == "__main__":
    main()
