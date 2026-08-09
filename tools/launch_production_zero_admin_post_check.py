"""Read-only TASK-086 recovery launcher for one production post-check."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import launch_production_zero_admin_bootstrap as production_launcher

operator = production_launcher.operator
ARTIFACT = ROOT / "tools" / "launch_production_zero_admin_post_check.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MODE = "post-check"


class RecoveryLauncherError(RuntimeError):
    """Raised when the read-only recovery boundary cannot be proven safe."""


def verify_artifacts() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    actual = hashlib.sha256(ARTIFACT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if not separator or name != ARTIFACT.name or digest != actual:
        raise RecoveryLauncherError("recovery launcher checksum boundary is invalid")
    production_launcher.verify_artifacts()


def run(environ: Mapping[str, str] | None = None) -> None:
    environment = os.environ if environ is None else environ
    verify_artifacts()
    production_launcher._require_clean_process_environment()
    production_launcher._verify_runtime(environment)
    private_values = production_launcher._load_private_pg_environment(
        production_launcher.PRIVATE_ENV_PATH
    )
    allowlist = production_launcher._load_allowlist()
    database_url = production_launcher._database_url(private_values)
    process_keys = (
        operator.DATABASE_ENV,
        operator.ALLOWLIST_ENV,
        operator.EXECUTION_ENV,
    )
    try:
        os.environ[operator.DATABASE_ENV] = database_url
        os.environ[operator.ALLOWLIST_ENV] = allowlist
        os.environ.pop(operator.EXECUTION_ENV, None)
        operator.run(MODE)
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
        raise SystemExit("TASK-086 production post-check stopped") from None


if __name__ == "__main__":
    main()
