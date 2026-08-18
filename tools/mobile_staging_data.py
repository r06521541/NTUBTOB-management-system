"""Approved remote staging migration/fixture operation; dry-run by default."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from sqlalchemy import create_engine, text

try:
    from .mobile_staging_contract import (
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from .mobile_staging_seed import StagingSeedError, seed
except ImportError:  # pragma: no cover
    from mobile_staging_contract import (
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from mobile_staging_seed import StagingSeedError, seed

Runner = Callable[
    [Sequence[str], Path, dict[str, str]], subprocess.CompletedProcess[str]
]


def plan(approval: dict, database_url: str) -> dict:
    validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    return {
        "operation": "migration-seed-postcheck",
        "revision": REVISION,
        "database_alias": approval["database_alias"],
        "database_provider": approval["database_provider"],
        "database_identity_sha256": approval["database_identity_sha256"],
        "provider_subject": "private-input-redacted",
        "mutation": "none-dry-run",
    }


def inventory(approval: dict, database_url: str) -> dict:
    identity = validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                revision = connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                )
                fixture_people = connection.scalar(
                    text("SELECT count(*) FROM ntubtob.people " "WHERE id = ANY(:ids)"),
                    {"ids": [-112001, -112002, -112003]},
                )
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
    if revision not in {"0004_phase_c_identity_lifecycle", REVISION}:
        raise StagingContractError("Remote staging revision is outside approved path")
    if fixture_people not in {0, 3}:
        raise StagingContractError("Remote staging fixture is partial")
    return {
        "database_identity_sha256": identity.fingerprint,
        "revision": revision,
        "fixture_state": "clean" if fixture_people == 0 else "seeded",
    }


def recover(approval: dict, database_url: str) -> dict:
    state = inventory(approval, database_url)
    if state["revision"] == REVISION and state["fixture_state"] == "seeded":
        return {"outcome": "completed", **state}
    if (
        state["revision"] in {"0004_phase_c_identity_lifecycle", REVISION}
        and state["fixture_state"] == "clean"
    ):
        return {"outcome": "not_started", **state}
    raise StagingContractError("Remote data operation is ambiguous; do not retry")


def execute(
    approval: dict,
    database_url: str,
    private_subject: str,
    root: Path,
    runner: Runner,
) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError("Remote data mutation requires candidate approval")
    before = recover(approval, database_url)
    if before["outcome"] != "not_started":
        raise StagingContractError("Remote data operation already completed")
    environment = {"PORTAL_DATA_DATABASE_URL": database_url}
    runner(
        [sys.executable, "-m", "alembic", "upgrade", REVISION],
        root,
        environment,
    )
    engine = create_engine(database_url)
    try:
        seed(engine, private_subject)
    finally:
        engine.dispose()
    return recover(approval, database_url)


def _runner(arguments: Sequence[str], cwd: Path, environment: dict[str, str]):
    merged = dict(os.environ)
    merged.update(environment)
    return subprocess.run(
        list(arguments), cwd=cwd, env=merged, check=True, capture_output=True, text=True
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)
    try:
        approval = load_approval(args.approval)
        database_url = os.environ.get("MOBILE_STAGING_DATABASE_URL", "")
        if args.recover:
            result = recover(approval, database_url)
        elif args.execute:
            result = execute(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
                Path(__file__).resolve().parents[1],
                _runner,
            )
        else:
            result = plan(approval, database_url)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (
        StagingContractError,
        StagingSeedError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
