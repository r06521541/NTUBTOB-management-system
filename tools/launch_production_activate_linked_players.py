"""No-disclosure launcher for TASK-087 linked-player activation."""

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

from tools import launch_production_activate_allowlisted_admins as boundary
from tools import portal_data_production_activate_linked_players as operator

ARTIFACT = ROOT / "tools" / "launch_production_activate_linked_players.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MATERIAL_CHECKSUMS = ROOT / "tools" / "TASK-087-linked-player-activation.sha256"
APPROVED_COMMIT_ENV = "TASK087_APPROVED_MERGED_COMMIT"
SEQUENCE = ("preflight", "execute", "post-check")


class LinkedPlayerLauncherError(RuntimeError):
    """Raised when the batch launcher cannot prove its exact boundary."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _verify_checksum(path: Path, checksum_path: Path) -> None:
    digest, separator, name = (
        checksum_path.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != path.name or digest != _canonical_digest(path):
        raise LinkedPlayerLauncherError("launcher checksum boundary is invalid")


def verify_artifacts() -> None:
    _verify_checksum(ARTIFACT, CHECKSUM)
    operator.verify_artifact()
    expected = {}
    for line in MATERIAL_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LinkedPlayerLauncherError("material checksum manifest is invalid")
        expected[name] = digest
    paths = {
        operator.ARTIFACT.name: operator.ARTIFACT,
        "models.py": ROOT
        / "shared_lib"
        / "shared_module"
        / "portal_data"
        / "models.py",
        boundary.ARTIFACT.name: boundary.ARTIFACT,
        boundary.operator.ARTIFACT.name: boundary.operator.ARTIFACT,
        boundary.boundary.ARTIFACT.name: boundary.boundary.ARTIFACT,
    }
    if set(expected) != set(paths) or any(
        expected[name] != _canonical_digest(path) for name, path in paths.items()
    ):
        raise LinkedPlayerLauncherError("material artifact checksum is invalid")


def _verify_runtime(environ: Mapping[str, str]) -> None:
    if Path.cwd().resolve() != ROOT.resolve():
        raise LinkedPlayerLauncherError("launcher must run from repository root")
    runtime = boundary.boundary.RUNTIME_EXECUTABLE
    if (
        Path(sys.executable).resolve() != runtime.resolve()
        or sys.version_info[:3] != boundary.boundary.RUNTIME_VERSION
        or not runtime.is_file()
    ):
        raise LinkedPlayerLauncherError("approved Python runtime is unavailable")
    if any(
        importlib.metadata.version(name) != version
        for name, version in boundary.boundary.REQUIRED_PACKAGES.items()
    ):
        raise LinkedPlayerLauncherError("dependency boundary failed")
    approved = environ.get(APPROVED_COMMIT_ENV, "")
    if not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise LinkedPlayerLauncherError("approved merged commit is unavailable")
    command_boundary = boundary.boundary
    if command_boundary._run([command_boundary.GIT, "rev-parse", "HEAD"]) != approved:
        raise LinkedPlayerLauncherError("repository commit is not approved")
    if command_boundary._run([command_boundary.GIT, "status", "--porcelain"]):
        raise LinkedPlayerLauncherError("repository working tree is not clean")
    if not command_boundary.GCLOUD.is_file():
        raise LinkedPlayerLauncherError("approved gcloud executable is unavailable")
    account = command_boundary._run(
        [
            str(command_boundary.GCLOUD),
            "auth",
            "list",
            "--filter=status:ACTIVE",
            "--format=value(account)",
        ]
    )
    project = command_boundary._run(
        [
            str(command_boundary.GCLOUD),
            "config",
            "get-value",
            "project",
            "--quiet",
        ]
    )
    if account != command_boundary.ACCOUNT or project != command_boundary.PROJECT:
        raise LinkedPlayerLauncherError("gcloud identity guard failed")


def _require_clean_environment() -> None:
    if any(
        os.environ.get(key) is not None
        for key in (
            operator.boundary.DATABASE_ENV,
            operator.boundary.ALLOWLIST_ENV,
            operator.EXECUTION_ENV,
        )
    ):
        raise LinkedPlayerLauncherError("temporary operator environment is not clean")


def run(approved_cohort_count: int, environ: Mapping[str, str] | None = None) -> None:
    if (
        not isinstance(approved_cohort_count, int)
        or isinstance(approved_cohort_count, bool)
        or approved_cohort_count <= 0
    ):
        raise LinkedPlayerLauncherError("approved cohort count is invalid")
    environment = os.environ if environ is None else environ
    verify_artifacts()
    _require_clean_environment()
    _verify_runtime(environment)
    private_values: dict[str, str] = {}
    allowlist = ""
    database_url = ""
    keys = (
        operator.boundary.DATABASE_ENV,
        operator.boundary.ALLOWLIST_ENV,
        operator.EXECUTION_ENV,
    )
    source_boundary = boundary.boundary
    try:
        private_values = source_boundary._load_private_pg_environment(
            source_boundary.PRIVATE_ENV_PATH
        )
        allowlist = source_boundary._load_allowlist()
        operator.boundary._allowlist(allowlist)
        database_url = source_boundary._database_url(private_values)
        os.environ[operator.boundary.DATABASE_ENV] = database_url
        os.environ[operator.boundary.ALLOWLIST_ENV] = allowlist
        for mode in SEQUENCE:
            if mode == "execute":
                os.environ[operator.EXECUTION_ENV] = operator.EXECUTION_ACKNOWLEDGEMENT
            else:
                os.environ.pop(operator.EXECUTION_ENV, None)
            operator.run(mode, approved_cohort_count=approved_cohort_count)
    finally:
        for key in keys:
            os.environ.pop(key, None)
        private_values.clear()
        allowlist = ""
        database_url = ""


def _approved_count_from_argv(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--approved-cohort-count":
        raise LinkedPlayerLauncherError("approved cohort count arguments are invalid")
    try:
        count = int(argv[1])
    except ValueError as error:
        raise LinkedPlayerLauncherError(
            "approved cohort count arguments are invalid"
        ) from error
    if count <= 0:
        raise LinkedPlayerLauncherError("approved cohort count arguments are invalid")
    return count


def main() -> None:
    try:
        run(_approved_count_from_argv(sys.argv[1:]))
    except Exception:
        raise SystemExit("TASK-087 linked-player activation stopped") from None


if __name__ == "__main__":
    main()
