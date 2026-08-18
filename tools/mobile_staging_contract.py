"""Fail-closed contracts shared by mobile staging operators."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

PRODUCTION_PROJECT = "ntubtob-schedule-405614"
REGION = "asia-east1"
SERVICE = "mobile-api-staging"
REVISION = "0005_mobile_auth_api_foundation"
RUNTIME_NAMES = (
    "PORTAL_DATA_DATABASE_URL",
    "MOBILE_API_AUDIENCE",
    "MOBILE_ACCESS_SIGNING_KEY",
    "MOBILE_REFRESH_REPLAY_KEY",
)
SECRET_NAMES = tuple(name for name in RUNTIME_NAMES if name != "MOBILE_API_AUDIENCE")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,126}:[1-9][0-9]*$")


class StagingContractError(RuntimeError):
    """Safe, non-sensitive operator failure."""


@dataclass(frozen=True)
class DatabaseIdentity:
    host: str
    port: int
    database: str

    @classmethod
    def from_url(cls, value: str) -> "DatabaseIdentity":
        try:
            parsed = urlparse(
                value.replace("postgresql+psycopg2://", "postgresql://", 1)
            )
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port or 5432
            database = unquote(parsed.path.lstrip("/"))
        except (TypeError, ValueError):
            raise StagingContractError("Database target is malformed") from None
        if (
            parsed.scheme != "postgresql"
            or not host
            or not database
            or not 1 <= port <= 65535
            or len(database) > 63
        ):
            raise StagingContractError("Database target is malformed")
        return cls(host, port, database)

    @property
    def fingerprint(self) -> str:
        canonical = f"postgresql://{self.host}:{self.port}/{self.database}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_target(
    project: str, region: str, service: str, max_instances: int
) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project or ""):
        raise StagingContractError("Dedicated staging project ID is invalid")
    if project == PRODUCTION_PROJECT:
        raise StagingContractError("Production project is forbidden")
    if region != REGION or service != SERVICE:
        raise StagingContractError("Staging region or service is not exact")
    if not 1 <= max_instances <= 3:
        raise StagingContractError("Staging max instances must be between 1 and 3")


def validate_database_identity(
    database_url: str, approved_staging_hash: str, production_hash: str
) -> DatabaseIdentity:
    identity = DatabaseIdentity.from_url(database_url)
    hashes = (approved_staging_hash, production_hash)
    if any(not re.fullmatch(r"[0-9a-f]{64}", value or "") for value in hashes):
        raise StagingContractError("Both database identity hashes are required")
    if approved_staging_hash == production_hash:
        raise StagingContractError("Staging and production database identities collide")
    if identity.fingerprint == production_hash:
        raise StagingContractError("Production database is forbidden")
    if identity.fingerprint != approved_staging_hash:
        raise StagingContractError(
            "Database does not match Owner-approved staging identity"
        )
    return identity


def validate_secret_refs(values: dict[str, str]) -> dict[str, str]:
    if set(values) != set(SECRET_NAMES):
        raise StagingContractError("Runtime Secret reference names are not exact")
    for name, value in values.items():
        if not SECRET_REF_PATTERN.fullmatch(value or ""):
            raise StagingContractError(f"Secret reference is invalid for {name}")
    return dict(values)


def redacted_manifest(
    *,
    project: str,
    database_url: str,
    approved_staging_hash: str,
    production_hash: str,
    max_instances: int,
    secret_refs: dict[str, str] | None = None,
    commit: str | None = None,
    digest: str | None = None,
) -> dict:
    validate_target(project, REGION, SERVICE, max_instances)
    identity = validate_database_identity(
        database_url, approved_staging_hash, production_hash
    )
    if commit is not None and not SHA_PATTERN.fullmatch(commit):
        raise StagingContractError("Commit must be a full SHA")
    if digest is not None and not DIGEST_PATTERN.fullmatch(digest):
        raise StagingContractError("Image digest is invalid")
    refs = None if secret_refs is None else validate_secret_refs(secret_refs)
    return {
        "environment": "staging",
        "project": project,
        "region": REGION,
        "service": SERVICE,
        "revision": REVISION,
        "scaling": {"min": 0, "max": max_instances},
        "database": {
            "identity_sha256": identity.fingerprint,
            "credentials": "redacted",
        },
        "runtime_secret_refs": refs
        or {name: "OWNER_DECISION_REQUIRED" for name in SECRET_NAMES},
        "runtime_plain_names": ["MOBILE_API_AUDIENCE"],
        "tester_count": 1,
        "image": {"commit": commit, "digest": digest},
        "traffic": "candidate-no-traffic",
        "external_mutations": "none-dry-run",
        "rollback": "restore exact prior revision traffic; delete rejected candidate",
    }


def load_approval(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise StagingContractError(
            "Approval artifact is unavailable or malformed"
        ) from None
    required = {
        "owner_approved",
        "project",
        "region",
        "service",
        "approved_commit",
        "image_digest",
        "candidate_revision",
        "rollback_revision",
        "database_identity_sha256",
        "production_database_identity_sha256",
        "max_instances",
        "service_account",
        "runtime_secret_refs",
        "mobile_api_audience",
    }
    if set(value) != required or value["owner_approved"] is not True:
        raise StagingContractError("Approval artifact fields are not exact")
    validate_target(
        value["project"], value["region"], value["service"], value["max_instances"]
    )
    if not SHA_PATTERN.fullmatch(value["approved_commit"] or ""):
        raise StagingContractError("Approved commit must be a full SHA")
    if not DIGEST_PATTERN.fullmatch(value["image_digest"] or ""):
        raise StagingContractError("Approved image digest is invalid")
    if not re.fullmatch(
        r"mobile-api-staging-[a-z0-9-]+", value["candidate_revision"] or ""
    ):
        raise StagingContractError("Candidate revision is invalid")
    if not re.fullmatch(
        r"mobile-api-staging-[a-z0-9-]+", value["rollback_revision"] or ""
    ):
        raise StagingContractError("Rollback revision is invalid")
    if value["candidate_revision"] == value["rollback_revision"]:
        raise StagingContractError("Candidate and rollback revisions must differ")
    if not re.fullmatch(
        r"[a-z][a-z0-9-]{4,28}@[a-z][a-z0-9-]{4,28}\.iam\.gserviceaccount\.com",
        value["service_account"] or "",
    ):
        raise StagingContractError("Dedicated service account is invalid")
    hashes = (
        value["database_identity_sha256"],
        value["production_database_identity_sha256"],
    )
    if (
        any(not re.fullmatch(r"[0-9a-f]{64}", item or "") for item in hashes)
        or hashes[0] == hashes[1]
    ):
        raise StagingContractError("Database approval identities are invalid")
    validate_secret_refs(value["runtime_secret_refs"])
    if not re.fullmatch(r"[1-9][0-9]{4,19}", value["mobile_api_audience"] or ""):
        raise StagingContractError("LINE channel ID must be numeric")
    return value
