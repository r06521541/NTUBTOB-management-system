"""Runtime attestation for immutable nonsecret broker inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .broker import BrokerFailure, BrokerManifest

APPROVAL_PATH = Path("apps/mobile_staging_broker/artifacts/candidate-approval.json")
OPERATOR_PATH = Path("tools/mobile_staging_data.py")
BROKER_PATHS = (
    Path("apps/mobile_staging_broker/app.py"),
    Path("apps/mobile_staging_broker/artifacts.py"),
    Path("apps/mobile_staging_broker/bootstrap.py"),
    Path("apps/mobile_staging_broker/broker.py"),
    Path("apps/mobile_staging_broker/Dockerfile"),
    Path("apps/mobile_staging_broker/Dockerfile.dockerignore"),
    Path("apps/mobile_staging_broker/journal.py"),
    Path("apps/mobile_staging_broker/operator.py"),
    Path("apps/mobile_staging_broker/requirements.txt"),
    Path("apps/mobile_staging_broker/runtime.py"),
    Path("migrations/versions/0006_staging_broker_operation_journal.py"),
)


def normalized_text_bytes(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError:
        raise BrokerFailure("ARTIFACT_INVALID") from None
    if b"\x00" in raw:
        raise BrokerFailure("ARTIFACT_INVALID")
    return raw.replace(b"\r\n", b"\n")


def normalized_text_sha256(path: Path) -> str:
    return hashlib.sha256(normalized_text_bytes(path)).hexdigest()


def broker_bundle_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in BROKER_PATHS:
        digest.update(relative.as_posix().encode("ascii"))
        digest.update(b"\x00")
        digest.update(normalized_text_bytes(root / relative))
        digest.update(b"\x00")
    return digest.hexdigest()


def artifact_hashes(root: Path) -> dict[str, str]:
    return {
        "candidate_approval_sha256": normalized_text_sha256(root / APPROVAL_PATH),
        "operator_artifact_sha256": normalized_text_sha256(root / OPERATOR_PATH),
        "broker_artifact_sha256": broker_bundle_sha256(root),
    }


def load_attested_approval(manifest: BrokerManifest, root: Path) -> dict:
    actual = artifact_hashes(root)
    if any(getattr(manifest, name) != value for name, value in actual.items()):
        raise BrokerFailure("ARTIFACT_INVALID")
    try:
        from tools.mobile_staging_contract import StagingContractError, load_approval

        approval = load_approval(root / APPROVAL_PATH)
    except (ImportError, StagingContractError):
        raise BrokerFailure("ARTIFACT_INVALID") from None
    if (
        approval["approval_phase"] != "candidate"
        or approval["project"] != manifest.project
        or approval["region"] != manifest.region
        or approval["database_identity_sha256"] != manifest.database_identity_sha256
    ):
        raise BrokerFailure("ARTIFACT_INVALID")
    return approval
