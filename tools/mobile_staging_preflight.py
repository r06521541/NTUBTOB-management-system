"""Read-only inventory and database preflight for isolated mobile staging."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from sqlalchemy import Engine, text

try:
    from .mobile_staging_contract import (REGION, REVISION, SERVICE,
                                          StagingContractError,
                                          validate_database_identity,
                                          validate_target)
except ImportError:  # pragma: no cover - direct script execution
    from mobile_staging_contract import (REGION, REVISION, SERVICE,
                                         StagingContractError,
                                         validate_database_identity,
                                         validate_target)

Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def _json(runner: Runner, command: Sequence[str], root: Path, label: str):
    try:
        value = json.loads(runner(command, root).stdout or "null")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        raise StagingContractError(f"Read-only inventory failed: {label}") from None
    return value


def cloud_inventory(
    root: Path, project: str, max_instances: int, runner: Runner
) -> dict:
    validate_target(project, REGION, SERVICE, max_instances)
    account = runner(
        ["gcloud", "config", "get-value", "account", "--quiet"], root
    ).stdout.strip()
    configured_project = runner(
        ["gcloud", "config", "get-value", "project", "--quiet"], root
    ).stdout.strip()
    if not account or configured_project != project:
        raise StagingContractError("gcloud account/project context is not exact")
    services = _json(
        runner,
        ["gcloud", "run", "services", "list", "--project", project,
         "--region", REGION, "--format=json"],
        root,
        "Cloud Run",
    )
    secrets = _json(
        runner,
        ["gcloud", "secrets", "list", "--project", project,
         "--format=json(name,replication)"],
        root,
        "Secret metadata",
    )
    if not isinstance(services, list) or not isinstance(secrets, list):
        raise StagingContractError("Read-only inventory response is malformed")
    return {
        "account_present": True,
        "project": project,
        "region": REGION,
        "service_exists": any(
            item.get("metadata", {}).get("name") == SERVICE
            for item in services
            if isinstance(item, dict)
        ),
        "secret_metadata_names": sorted(
            item.get("name", "").rsplit("/", 1)[-1]
            for item in secrets
            if isinstance(item, dict) and item.get("name")
        ),
    }


def database_inventory(
    engine: Engine,
    database_url: str,
    approved_staging_hash: str,
    production_hash: str,
) -> dict:
    identity = validate_database_identity(
        database_url, approved_staging_hash, production_hash
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = connection.scalar(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )
            production_fingerprint = connection.scalar(
                text("""
                  SELECT count(*) FROM ntubtob.people
                  WHERE id > 0 AND display_name NOT LIKE '虛構%'
                """)
            )
            fixture_people = connection.scalar(
                text("SELECT count(*) FROM ntubtob.people WHERE id = ANY(:ids)"),
                {"ids": [-112001, -112002, -112003]},
            )
        finally:
            transaction.rollback()
    if revision != REVISION:
        raise StagingContractError("Staging database revision is not exact 0005")
    if production_fingerprint:
        raise StagingContractError("Database contains a production-shaped fingerprint")
    if fixture_people not in {0, 3}:
        raise StagingContractError("Staging fixture state is partial")
    return {
        "database_identity_sha256": identity.fingerprint,
        "revision": revision,
        "production_fingerprint_rows": 0,
        "fixture_state": "clean" if fixture_people == 0 else "seeded",
    }
