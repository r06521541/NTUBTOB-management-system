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
REVISION = "0008_mobile_notification_delivery"
FORWARD_REVISIONS = (
    "0005_mobile_auth_api_foundation",
    "0006_staging_broker_operation_journal",
)
RUNTIME_NAMES = (
    "PORTAL_DATA_DATABASE_URL",
    "MOBILE_API_AUDIENCE",
    "MOBILE_API_GOOGLE_AUDIENCES",
    "MOBILE_ACCESS_SIGNING_KEY",
    "MOBILE_REFRESH_REPLAY_KEY",
)
SECRET_NAMES = tuple(
    name
    for name in RUNTIME_NAMES
    if name not in {"MOBILE_API_AUDIENCE", "MOBILE_API_GOOGLE_AUDIENCES"}
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,126}:[1-9][0-9]*$")


class StagingContractError(RuntimeError):
    """Safe, non-sensitive operator failure."""


@dataclass(frozen=True)
class DatabaseIdentity:
    provider: str
    resource_id: str
    host: str
    port: int
    database: str

    @classmethod
    def from_url(
        cls, value: str, provider: str = "local", resource_id: str = "local-rehearsal"
    ) -> "DatabaseIdentity":
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
            or database != database.strip()
            or not 1 <= port <= 65535
            or len(database) > 63
        ):
            raise StagingContractError("Database target is malformed")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", provider or ""):
            raise StagingContractError("Database provider is invalid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{5,127}", resource_id or ""):
            raise StagingContractError("Database resource identity is invalid")
        return cls(provider, resource_id, host, port, database)

    @property
    def fingerprint(self) -> str:
        canonical = (
            f"{self.provider}/{self.resource_id}/"
            f"postgresql://{self.host}:{self.port}/{self.database}"
        )
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
    database_url: str,
    approved_staging_hash: str,
    production_hash: str,
    provider: str = "local",
    resource_id: str = "local-rehearsal",
) -> DatabaseIdentity:
    identity = DatabaseIdentity.from_url(database_url, provider, resource_id)
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
    database_provider: str = "local",
    database_resource_id: str = "local-rehearsal",
    database_alias: str = "local",
    max_instances: int,
    secret_refs: dict[str, str] | None = None,
    commit: str | None = None,
    digest: str | None = None,
) -> dict:
    validate_target(project, REGION, SERVICE, max_instances)
    identity = validate_database_identity(
        database_url,
        approved_staging_hash,
        production_hash,
        database_provider,
        database_resource_id,
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
            "provider": identity.provider,
            "resource_identity_sha256": hashlib.sha256(
                identity.resource_id.encode("utf-8")
            ).hexdigest(),
            "approved_alias": database_alias,
            "credentials": "redacted",
        },
        "runtime_secret_refs": refs
        or {name: "OWNER_DECISION_REQUIRED" for name in SECRET_NAMES},
        "runtime_plain_names": [
            "MOBILE_API_AUDIENCE",
            "MOBILE_API_GOOGLE_AUDIENCES",
        ],
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
        "approval_phase",
        "build_id",
        "image_uri",
        "image_digest",
        "mode",
        "candidate_revision",
        "rollback_revision",
        "database_identity_sha256",
        "production_database_identity_sha256",
        "database_provider",
        "database_resource_id",
        "database_alias",
        "max_instances",
        "service_account",
        "build_service_account",
        "runtime_secret_refs",
        "mobile_api_audience",
        "mobile_api_google_audiences",
    }
    if set(value) != required or value["owner_approved"] is not True:
        raise StagingContractError("Approval artifact fields are not exact")
    validate_target(
        value["project"], value["region"], value["service"], value["max_instances"]
    )
    if not SHA_PATTERN.fullmatch(value["approved_commit"] or ""):
        raise StagingContractError("Approved commit must be a full SHA")
    if value["approval_phase"] not in {"build", "candidate"}:
        raise StagingContractError("Approval phase is invalid")
    if value["mode"] not in {"bootstrap", "update"}:
        raise StagingContractError("Staging service mode is invalid")
    if value["approval_phase"] == "candidate" and not DIGEST_PATTERN.fullmatch(
        value["image_digest"] or ""
    ):
        raise StagingContractError("Approved image digest is invalid")
    if value["approval_phase"] == "build" and value["image_digest"] is not None:
        raise StagingContractError("Build approval cannot pre-approve a digest")
    if value["approval_phase"] == "candidate" and not re.fullmatch(
        r"[a-z0-9][a-z0-9._-]{5,127}", value["build_id"] or ""
    ):
        raise StagingContractError("Candidate approval requires exact build ID")
    if value["approval_phase"] == "build" and value["build_id"] is not None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{5,127}", value["build_id"]):
            raise StagingContractError("Build recovery ID is invalid")
    if not re.fullmatch(
        r"asia-east1-docker\.pkg\.dev/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+",
        value["image_uri"] or "",
    ):
        raise StagingContractError("Exact image URI is invalid")
    if not re.fullmatch(
        r"mobile-api-staging-[a-z0-9-]+", value["candidate_revision"] or ""
    ):
        raise StagingContractError("Candidate revision is invalid")
    rollback = value["rollback_revision"]
    if value["mode"] == "bootstrap" and rollback is not None:
        raise StagingContractError("Bootstrap cannot claim a rollback revision")
    if value["mode"] == "update" and not re.fullmatch(
        r"mobile-api-staging-[a-z0-9-]+", rollback or ""
    ):
        raise StagingContractError("Update requires an exact rollback revision")
    if rollback is not None and value["candidate_revision"] == rollback:
        raise StagingContractError("Candidate and rollback revisions must differ")
    account_pattern = (
        r"[a-z][a-z0-9-]{4,28}@[a-z][a-z0-9-]{4,28}\.iam\.gserviceaccount\.com",
    )[0]
    for field in ("service_account", "build_service_account"):
        account = value[field] or ""
        if not re.fullmatch(account_pattern, account) or account.split("@", 1)[1] != (
            value["project"] + ".iam.gserviceaccount.com"
        ):
            raise StagingContractError(f"Dedicated {field} project is invalid")
    if value["service_account"] == value["build_service_account"]:
        raise StagingContractError("Runtime and build identities must be separate")
    DatabaseIdentity.from_url(
        "postgresql://placeholder.invalid/placeholder",
        value["database_provider"],
        value["database_resource_id"],
    )
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}", value["database_alias"] or ""
    ):
        raise StagingContractError("Database alias is invalid")
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
    google_audiences = value["mobile_api_google_audiences"]
    if (
        not isinstance(google_audiences, str)
        or len(google_audiences) > 512
        or not 1 <= len(google_audiences.split(",")) <= 4
        or any(
            not re.fullmatch(
                r"[0-9A-Za-z][0-9A-Za-z._-]{5,199}\.apps\.googleusercontent\.com",
                audience,
            )
            for audience in google_audiences.split(",")
        )
        or len(set(google_audiences.split(","))) != len(google_audiences.split(","))
    ):
        raise StagingContractError("Google audience allowlist is invalid")
    return value
