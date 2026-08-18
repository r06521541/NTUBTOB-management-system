"""Dry-run-first mobile staging deployment operator.

This package never creates projects, databases, service accounts, IAM bindings,
Secrets or LINE channels.  Cloud mutation requires a private exact Owner
approval artifact and an explicit operation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    from .mobile_staging_contract import (REGION, SERVICE,
                                          StagingContractError, load_approval,
                                          redacted_manifest,
                                          validate_database_identity)
except ImportError:  # pragma: no cover - direct script execution
    from mobile_staging_contract import (REGION, SERVICE, StagingContractError,
                                         load_approval, redacted_manifest,
                                         validate_database_identity)


class OperatorError(StagingContractError):
    pass


Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def run_command(arguments: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(arguments[0])
    if executable is None:
        raise OperatorError(f"Required tool is unavailable: {arguments[0]}")
    command = [executable, *arguments[1:]]
    try:
        return subprocess.run(
            command, cwd=cwd, check=True, capture_output=True, text=True, shell=False
        )
    except subprocess.CalledProcessError:
        raise OperatorError(f"Command failed at safe stage: {arguments[0]} {arguments[1]}") from None


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def output(runner: Runner, arguments: Sequence[str], cwd: Path) -> str:
    return runner(arguments, cwd).stdout.strip()


def require_clean_exact_head(root: Path, approved_commit: str, runner: Runner) -> None:
    if output(runner, ["git", "status", "--porcelain"], root):
        raise OperatorError("Repository must be clean")
    if output(runner, ["git", "rev-parse", "HEAD"], root).lower() != approved_commit:
        raise OperatorError("HEAD does not match Owner-approved commit")


def validate_shared_artifact(root: Path, artifact: Path) -> str:
    if artifact.name != "shared_lib-0.0.1.tar.gz" or not artifact.is_file():
        raise OperatorError("Exact shared library artifact is unavailable")
    try:
        with tarfile.open(artifact, "r:gz") as archive:
            names = archive.getnames()
    except (OSError, tarfile.TarError):
        raise OperatorError("Shared library artifact is malformed") from None
    if not any(name.endswith("/shared_module/mobile_api.py") for name in names):
        raise OperatorError("Shared library artifact lacks mobile API application code")
    forbidden = (".env", "credential", "secret", ".pem", ".key")
    if any(any(token in name.lower() for token in forbidden) for name in names):
        raise OperatorError("Shared library artifact contains a forbidden path")
    import hashlib

    return "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()


def validate_build_context(root: Path) -> None:
    service = root / "apps" / "mobile_api"
    ignored = (service / ".dockerignore").read_text(encoding="utf-8").splitlines()
    required_ignores = {
        ".env.yaml", ".env", ".env.*", "*.json", "*.pem", "*.key",
        "*approval*", "*state*", "__pycache__/", "tests/",
    }
    if not required_ignores.issubset(set(ignored)):
        raise OperatorError("Mobile API Docker context exclusions are incomplete")
    for forbidden in (service / ".env.yaml", service / "credentials.json"):
        if forbidden.exists():
            raise OperatorError("Private artifact exists in mobile API build context")


def stage_shared_artifact(root: Path) -> Path:
    source = root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz"
    validate_shared_artifact(root, source)
    target = root / "apps" / "mobile_api" / "dist" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise OperatorError("Refusing to overwrite staged shared artifact")
    shutil.copy2(source, target)
    return target


@dataclass(frozen=True)
class OperatorState:
    approved_commit: str
    image_digest: str
    candidate_revision: str
    rollback_revision: str
    phase: str


def load_state(path: Path) -> OperatorState:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        state = OperatorState(**value)
    except (OSError, json.JSONDecodeError, TypeError):
        raise OperatorError("Operator recovery state is unavailable or malformed") from None
    if state.phase not in {"candidate_ready", "promoted", "rolled_back"}:
        raise OperatorError("Operator recovery phase is invalid")
    return state


def save_state(path: Path, state: OperatorState) -> None:
    if path.exists():
        existing = load_state(path)
        if existing.approved_commit != state.approved_commit:
            raise OperatorError("Refusing to overwrite unrelated recovery state")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(asdict(state), sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _secret_arguments(approval: dict) -> str:
    refs = approval["runtime_secret_refs"]
    return ",".join(f"{name}={refs[name]}" for name in sorted(refs))


def candidate_commands(approval: dict) -> tuple[list[str], list[str]]:
    image = (
        f"{REGION}-docker.pkg.dev/{approval['project']}/mobile-staging/"
        f"mobile-api:{approval['approved_commit']}"
    )
    build = [
        "gcloud", "builds", "submit", "apps/mobile_api",
        "--project", approval["project"], "--region", REGION,
        "--config", "apps/mobile_api/cloudbuild.staging.yaml",
        "--substitutions", f"_IMAGE={image}", "--suppress-logs", "--quiet",
    ]
    deploy = [
        "gcloud", "run", "deploy", SERVICE, "--project", approval["project"],
        "--region", REGION, "--image", f"{image}@{approval['image_digest']}",
        "--revision-suffix", approval["candidate_revision"].removeprefix(SERVICE + "-"),
        "--service-account", approval["service_account"], "--no-traffic",
        "--min", "0", "--max", str(approval["max_instances"]),
        "--set-secrets", _secret_arguments(approval),
        "--set-env-vars", f"MOBILE_API_AUDIENCE={approval['mobile_api_audience']}",
        "--quiet",
    ]
    return build, deploy


def traffic_command(approval: dict, revision: str) -> list[str]:
    if revision not in {approval["candidate_revision"], approval["rollback_revision"]}:
        raise OperatorError("Traffic target is outside approval artifact")
    return [
        "gcloud", "run", "services", "update-traffic", SERVICE,
        "--project", approval["project"], "--region", REGION,
        "--to-revisions", f"{revision}=100", "--quiet",
    ]


def validate_candidate(approval: dict, revision: dict) -> None:
    metadata = revision.get("metadata", {})
    status = revision.get("status", {})
    if metadata.get("name") != approval["candidate_revision"]:
        raise OperatorError("Candidate revision name drifted")
    ready = any(
        item.get("type") == "Ready" and item.get("status") == "True"
        for item in status.get("conditions", [])
        if isinstance(item, dict)
    )
    if not ready or status.get("imageDigest") != approval["image_digest"]:
        raise OperatorError("Candidate revision is not ready at approved digest")
    spec = revision.get("spec", {})
    if spec.get("serviceAccountName") != approval["service_account"]:
        raise OperatorError("Candidate runtime identity drifted")
    if status.get("traffic", 0) not in {0, None}:
        raise OperatorError("Candidate unexpectedly received traffic")
    annotations = metadata.get("annotations", {})
    if annotations.get("autoscaling.knative.dev/minScale", "0") != "0":
        raise OperatorError("Candidate minimum scaling drifted")
    if annotations.get("autoscaling.knative.dev/maxScale") != str(
        approval["max_instances"]
    ):
        raise OperatorError("Candidate maximum scaling drifted")
    containers = spec.get("containers", [])
    if len(containers) != 1 or not isinstance(containers[0], dict):
        raise OperatorError("Candidate container contract is malformed")
    by_name = {
        item.get("name"): item
        for item in containers[0].get("env", [])
        if isinstance(item, dict)
    }
    for name, reference in approval["runtime_secret_refs"].items():
        source = by_name.get(name, {}).get("valueFrom", {}).get("secretKeyRef", {})
        actual = f"{source.get('name')}:{source.get('key')}"
        if actual != reference:
            raise OperatorError(f"Candidate Secret reference drifted for {name}")
    audience = by_name.get("MOBILE_API_AUDIENCE", {})
    if audience.get("value") != approval["mobile_api_audience"] or "valueFrom" in audience:
        raise OperatorError("Candidate LINE audience configuration drifted")


def validate_traffic(service: dict, revision: str) -> None:
    traffic = service.get("status", {}).get("traffic", [])
    if traffic != [{"revisionName": revision, "percent": 100}]:
        raise OperatorError("Cloud Run traffic did not converge exactly")


def dry_run_manifest(approval: dict, database_url: str) -> dict:
    validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
    )
    return redacted_manifest(
        project=approval["project"],
        database_url=database_url,
        approved_staging_hash=approval["database_identity_sha256"],
        production_hash=approval["production_database_identity_sha256"],
        max_instances=approval["max_instances"],
        secret_refs=approval["runtime_secret_refs"],
        commit=approval["approved_commit"],
        digest=approval["image_digest"],
    )


def execute(
    operation: str,
    approval: dict,
    database_url: str,
    state_path: Path,
    root: Path,
    runner: Runner = run_command,
) -> OperatorState:
    dry_run_manifest(approval, database_url)
    require_clean_exact_head(root, approval["approved_commit"], runner)
    validate_build_context(root)
    if operation in {"candidate", "recover"}:
        staged_artifact = stage_shared_artifact(root)
        try:
            if operation == "candidate":
                build, deploy = candidate_commands(approval)
                output(runner, build, root)
                output(runner, deploy, root)
            revision = json.loads(
                output(
                    runner,
                    ["gcloud", "run", "revisions", "describe", approval["candidate_revision"],
                     "--project", approval["project"], "--region", REGION, "--format=json"],
                    root,
                )
            )
            validate_candidate(approval, revision)
        finally:
            staged_artifact.unlink(missing_ok=True)
        state = OperatorState(
            approval["approved_commit"], approval["image_digest"],
            approval["candidate_revision"], approval["rollback_revision"],
            "candidate_ready",
        )
    else:
        current = load_state(state_path)
        if current.approved_commit != approval["approved_commit"]:
            raise OperatorError("Recovery state does not match approval")
        if operation == "promote":
            output(runner, traffic_command(approval, approval["candidate_revision"]), root)
            service = json.loads(
                output(
                    runner,
                    ["gcloud", "run", "services", "describe", SERVICE,
                     "--project", approval["project"], "--region", REGION,
                     "--format=json"],
                    root,
                )
            )
            validate_traffic(service, approval["candidate_revision"])
            phase = "promoted"
        elif operation == "rollback":
            output(runner, traffic_command(approval, approval["rollback_revision"]), root)
            service = json.loads(
                output(
                    runner,
                    ["gcloud", "run", "services", "describe", SERVICE,
                     "--project", approval["project"], "--region", REGION,
                     "--format=json"],
                    root,
                )
            )
            validate_traffic(service, approval["rollback_revision"])
            phase = "rolled_back"
        else:
            raise OperatorError("Unknown staging operation")
        state = OperatorState(
            current.approved_commit, current.image_digest,
            current.candidate_revision, current.rollback_revision, phase,
        )
    save_state(state_path, state)
    return state


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--approval", type=Path)
    value.add_argument("--state-file", type=Path)
    value.add_argument(
        "--execute", choices=("candidate", "recover", "promote", "rollback")
    )
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.approval is None:
            print("Dry-run only: private Owner approval artifact is required for any operation.")
            return 0
        approval = load_approval(args.approval)
        database_url = os.environ.get("MOBILE_STAGING_DATABASE_URL", "")
        manifest = dry_run_manifest(approval, database_url)
        if args.execute is None:
            print(json.dumps(manifest, sort_keys=True))
            return 0
        if args.state_file is None:
            raise OperatorError("Execution requires a private recovery state path")
        state = execute(
            args.execute, approval, database_url, args.state_file,
            repository_root(),
        )
        print(json.dumps(asdict(state), sort_keys=True))
        return 0
    except (OperatorError, StagingContractError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
