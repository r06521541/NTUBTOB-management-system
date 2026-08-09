"""Read-only discovery launcher for TASK-087 linked-player activation."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import launch_production_activate_linked_players as execution_boundary
from tools import portal_data_production_activate_linked_players as operator

ARTIFACT = ROOT / "tools" / "launch_production_discover_linked_players.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")


class LinkedPlayerDiscoveryLauncherError(RuntimeError):
    """Raised when read-only discovery cannot prove its boundary."""


def verify_artifacts() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(ARTIFACT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if not separator or name != ARTIFACT.name or digest != actual:
        raise LinkedPlayerDiscoveryLauncherError("discovery checksum is invalid")
    execution_boundary.verify_artifacts()


def run(environ: Mapping[str, str] | None = None) -> None:
    environment = os.environ if environ is None else environ
    verify_artifacts()
    execution_boundary._require_clean_environment()
    execution_boundary._verify_runtime(environment)
    private_values: dict[str, str] = {}
    allowlist = ""
    database_url = ""
    keys = (
        operator.boundary.DATABASE_ENV,
        operator.boundary.ALLOWLIST_ENV,
        operator.EXECUTION_ENV,
    )
    source_boundary = execution_boundary.boundary.boundary
    try:
        private_values = source_boundary._load_private_pg_environment(
            source_boundary.PRIVATE_ENV_PATH
        )
        allowlist = source_boundary._load_allowlist()
        operator.boundary._allowlist(allowlist)
        database_url = source_boundary._database_url(private_values)
        os.environ[operator.boundary.DATABASE_ENV] = database_url
        os.environ[operator.boundary.ALLOWLIST_ENV] = allowlist
        os.environ.pop(operator.EXECUTION_ENV, None)
        operator.run("discovery")
    finally:
        for key in keys:
            os.environ.pop(key, None)
        private_values.clear()
        allowlist = ""
        database_url = ""


def main() -> None:
    try:
        run()
    except Exception:
        raise SystemExit("TASK-087 linked-player discovery stopped") from None


if __name__ == "__main__":
    main()
