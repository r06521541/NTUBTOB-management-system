"""Two-approval, dry-run-first mobile staging operator."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    from .mobile_staging_contract import (
        REGION,
        SERVICE,
        StagingContractError,
        load_approval,
        redacted_manifest,
    )
except ImportError:  # pragma: no cover
    from mobile_staging_contract import (
        REGION,
        SERVICE,
        StagingContractError,
        load_approval,
        redacted_manifest,
    )


class OperatorError(StagingContractError):
    pass


Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def run_command(
    arguments: Sequence[str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(arguments[0])
    if executable is None:
        raise OperatorError(f"Required tool is unavailable: {arguments[0]}")
    try:
        return subprocess.run(
            [executable, *arguments[1:]],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
    except subprocess.CalledProcessError:
        raise OperatorError(f"Command failed at safe stage: {arguments[0]}") from None


def output(runner: Runner, arguments: Sequence[str], cwd: Path) -> str:
    return runner(arguments, cwd).stdout.strip()


def normalize_digest(value: object) -> str:
    if not isinstance(value, str):
        raise OperatorError("Image digest is missing or invalid")
    digest = value.rsplit("@", 1)[-1].lower()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise OperatorError("Image digest is missing or invalid")
    return digest


def require_clean_exact_head(root: Path, commit: str, runner: Runner) -> None:
    if output(runner, ["git", "status", "--porcelain"], root):
        raise OperatorError("Repository must be clean")
    if output(runner, ["git", "rev-parse", "HEAD"], root).lower() != commit:
        raise OperatorError("HEAD does not match Owner-approved commit")


def validate_shared_artifact(artifact: Path) -> str:
    if artifact.name != "shared_lib-0.0.1.tar.gz" or not artifact.is_file():
        raise OperatorError("Fresh shared library artifact is unavailable")
    try:
        with tarfile.open(artifact, "r:gz") as archive:
            names = archive.getnames()
    except (OSError, tarfile.TarError):
        raise OperatorError("Fresh shared library artifact is malformed") from None
    if not any(name.endswith("/shared_module/mobile_api.py") for name in names):
        raise OperatorError("Fresh shared artifact lacks mobile API code")
    if any(
        any(
            token in name.lower()
            for token in (".env", "credential", "secret", ".pem", ".key")
        )
        for name in names
    ):
        raise OperatorError("Fresh shared artifact contains a forbidden path")
    import hashlib

    return "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()


def fresh_shared_artifact(root: Path, runner: Runner, output_dir: Path) -> Path:
    output(
        runner,
        [sys.executable, "setup.py", "sdist", "--dist-dir", str(output_dir)],
        root / "shared_lib",
    )
    artifact = output_dir / "shared_lib-0.0.1.tar.gz"
    validate_shared_artifact(artifact)
    return artifact


def validate_build_context(root: Path) -> None:
    service = root / "apps" / "mobile_api"
    ignored = set((service / ".dockerignore").read_text(encoding="utf-8").splitlines())
    required = {
        ".env.yaml",
        ".env",
        ".env.*",
        "*.json",
        "*.pem",
        "*.key",
        "*approval*",
        "*state*",
        "__pycache__/",
        "tests/",
    }
    if not required.issubset(ignored):
        raise OperatorError("Mobile API Docker context exclusions are incomplete")
    if (service / "dist" / "shared_lib-0.0.1.tar.gz").exists():
        raise OperatorError("Stale shared artifact exists in Docker context")


@dataclass(frozen=True)
class OperatorState:
    approved_commit: str
    build_id: str
    image_uri: str
    image_digest: str | None
    candidate_revision: str
    rollback_revision: str | None
    mode: str
    phase: str


def load_state(path: Path) -> OperatorState:
    try:
        state = OperatorState(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        raise OperatorError(
            "Operator recovery state is unavailable or malformed"
        ) from None
    if state.phase not in {"built", "candidate_ready", "promoted", "rolled_back"}:
        raise OperatorError("Operator recovery phase is invalid")
    return state


def save_state(path: Path, state: OperatorState) -> None:
    if path.exists() and load_state(path).approved_commit != state.approved_commit:
        raise OperatorError("Refusing to overwrite unrelated recovery state")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(state), sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def build_command(approval: dict) -> list[str]:
    return [
        "gcloud",
        "builds",
        "submit",
        "apps/mobile_api",
        "--project",
        approval["project"],
        "--region",
        REGION,
        "--config",
        "apps/mobile_api/cloudbuild.staging.yaml",
        "--substitutions",
        f"_IMAGE={approval['image_uri']}",
        "--service-account",
        (
            f"projects/{approval['project']}/serviceAccounts/"
            f"{approval['build_service_account']}"
        ),
        "--format=json",
        "--quiet",
    ]


def deploy_command(approval: dict) -> list[str]:
    arguments = [
        "gcloud",
        "run",
        "deploy",
        SERVICE,
        "--project",
        approval["project"],
        "--region",
        REGION,
        "--image",
        f"{approval['image_uri']}@{approval['image_digest']}",
        "--revision-suffix",
        approval["candidate_revision"].removeprefix(SERVICE + "-"),
        "--service-account",
        approval["service_account"],
        "--ingress",
        "all",
        "--min-instances",
        "0",
        "--max-instances",
        str(approval["max_instances"]),
        "--set-secrets",
        ",".join(
            f"{k}={v}" for k, v in sorted(approval["runtime_secret_refs"].items())
        ),
        "--set-env-vars",
        f"MOBILE_API_AUDIENCE={approval['mobile_api_audience']}",
        "--quiet",
    ]
    if approval["mode"] == "update":
        arguments.insert(arguments.index("--ingress"), "--no-traffic")
    else:
        arguments.insert(
            arguments.index("--ingress"), "--no-allow-unauthenticated"
        )
    return arguments


def _build_result(value: dict, approval: dict) -> str:
    build_id = value.get("id")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{5,127}", build_id or ""):
        raise OperatorError("Cloud Build ID is malformed")
    if approval["build_id"] is not None and build_id != approval["build_id"]:
        raise OperatorError("Cloud Build ID drifted")
    images = value.get("results", {}).get("images", [])
    matches = [item for item in images if item.get("name") == approval["image_uri"]]
    if len(matches) != 1:
        raise OperatorError("Cloud Build image result is not exact")
    return normalize_digest(matches[0].get("digest"))


def build_inventory_command(approval: dict) -> list[str]:
    if approval["build_id"] is None:
        raise OperatorError("Lost-response recovery requires exact build ID")
    return [
        "gcloud",
        "builds",
        "describe",
        approval["build_id"],
        "--project",
        approval["project"],
        "--region",
        REGION,
        "--format=json",
    ]


def service_inventory_command(approval: dict) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "describe",
        SERVICE,
        "--project",
        approval["project"],
        "--region",
        REGION,
        "--format=json",
    ]


def _traffic_is_exact(
    traffic: object, active_revision: str, allowed_zero_revisions: set[str]
) -> bool:
    if not isinstance(traffic, list):
        return False
    targets: dict[str, int] = {}
    for item in traffic:
        if not isinstance(item, dict):
            return False
        revision = item.get("revisionName")
        percent = item.get("percent")
        if (
            type(revision) is not str
            or not revision
            or type(percent) is not int
            or revision in targets
        ):
            return False
        targets[revision] = percent
    if targets.get(active_revision) != 100:
        return False
    return all(
        revision == active_revision
        or (revision in allowed_zero_revisions and percent == 0)
        for revision, percent in targets.items()
    )


def validate_candidate(approval: dict, revision: dict, service: dict) -> None:
    metadata, status, spec = (
        revision.get("metadata", {}),
        revision.get("status", {}),
        revision.get("spec", {}),
    )
    ready = any(
        item.get("type") == "Ready" and item.get("status") == "True"
        for item in status.get("conditions", [])
        if isinstance(item, dict)
    )
    if metadata.get("name") != approval["candidate_revision"] or not ready:
        raise OperatorError("Candidate revision is not exact and ready")
    if normalize_digest(status.get("imageDigest")) != approval["image_digest"]:
        raise OperatorError("Candidate image digest drifted")
    annotations = metadata.get("annotations", {})
    if (
        spec.get("serviceAccountName") != approval["service_account"]
        or annotations.get("autoscaling.knative.dev/minScale", "0") != "0"
        or annotations.get("autoscaling.knative.dev/maxScale")
        != str(approval["max_instances"])
    ):
        raise OperatorError("Candidate runtime identity or scaling drifted")
    containers = spec.get("containers", [])
    if len(containers) != 1:
        raise OperatorError("Candidate container contract is malformed")
    environment = {
        item.get("name"): item
        for item in containers[0].get("env", [])
        if isinstance(item, dict)
    }
    for name, reference in approval["runtime_secret_refs"].items():
        secret = environment.get(name, {}).get("valueFrom", {}).get("secretKeyRef", {})
        if f"{secret.get('name')}:{secret.get('key')}" != reference:
            raise OperatorError(f"Candidate Secret reference drifted for {name}")
    audience = environment.get("MOBILE_API_AUDIENCE", {})
    if (
        audience.get("value") != approval["mobile_api_audience"]
        or "valueFrom" in audience
    ):
        raise OperatorError("Candidate audience configuration drifted")
    service_annotations = service.get("metadata", {}).get("annotations", {})
    if service_annotations.get("run.googleapis.com/ingress") != "all":
        raise OperatorError("Cloud Run ingress drifted")
    template = service.get("spec", {}).get("template", {})
    template_annotations = template.get("metadata", {}).get("annotations", {})
    if (
        template.get("spec", {}).get("serviceAccountName")
        != approval["service_account"]
        or template_annotations.get("autoscaling.knative.dev/minScale", "0") != "0"
        or template_annotations.get("autoscaling.knative.dev/maxScale")
        != str(approval["max_instances"])
    ):
        raise OperatorError("Cloud Run service runtime or scaling drifted")
    traffic = service.get("status", {}).get("traffic", [])
    if approval["mode"] == "bootstrap" and not _traffic_is_exact(
        traffic, approval["candidate_revision"], set()
    ):
        raise OperatorError("Bootstrap candidate traffic topology drifted")
    if approval["mode"] == "update" and not _traffic_is_exact(
        traffic,
        approval["rollback_revision"],
        {approval["candidate_revision"]},
    ):
        raise OperatorError("Update baseline traffic topology drifted")


def dry_run_manifest(approval: dict, database_url: str) -> dict:
    return redacted_manifest(
        project=approval["project"],
        database_url=database_url,
        approved_staging_hash=approval["database_identity_sha256"],
        production_hash=approval["production_database_identity_sha256"],
        database_provider=approval["database_provider"],
        database_resource_id=approval["database_resource_id"],
        database_alias=approval["database_alias"],
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
    if operation in {"build", "recover-build"}:
        if approval["approval_phase"] != "build":
            raise OperatorError("Build operation requires build approval")
        with tempfile.TemporaryDirectory(prefix="task112-shared-") as directory:
            artifact = fresh_shared_artifact(root, runner, Path(directory))
            target = root / "apps" / "mobile_api" / "dist" / artifact.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(artifact, target)
            try:
                raw = (
                    output(runner, build_command(approval), root)
                    if operation == "build"
                    else output(runner, build_inventory_command(approval), root)
                )
                digest = _build_result(json.loads(raw), approval)
            finally:
                target.unlink(missing_ok=True)
        build_id = json.loads(raw)["id"]
        state = OperatorState(
            approval["approved_commit"],
            build_id,
            approval["image_uri"],
            digest,
            approval["candidate_revision"],
            approval["rollback_revision"],
            approval["mode"],
            "built",
        )
    elif operation in {"candidate", "recover-candidate"}:
        if approval["approval_phase"] != "candidate":
            raise OperatorError("Candidate operation requires candidate approval")
        if operation == "candidate":
            output(runner, deploy_command(approval), root)
        revision = json.loads(
            output(
                runner,
                [
                    "gcloud",
                    "run",
                    "revisions",
                    "describe",
                    approval["candidate_revision"],
                    "--project",
                    approval["project"],
                    "--region",
                    REGION,
                    "--format=json",
                ],
                root,
            )
        )
        service = json.loads(output(runner, service_inventory_command(approval), root))
        validate_candidate(approval, revision, service)
        state = OperatorState(
            approval["approved_commit"],
            approval["build_id"],
            approval["image_uri"],
            approval["image_digest"],
            approval["candidate_revision"],
            approval["rollback_revision"],
            approval["mode"],
            "candidate_ready",
        )
    else:
        current = load_state(state_path)
        if operation == "rollback" and approval["mode"] == "bootstrap":
            raise OperatorError(
                "Bootstrap has no rollback revision; cleanup needs separate approval"
            )
        revision = (
            approval["candidate_revision"]
            if operation == "promote"
            else approval["rollback_revision"]
        )
        output(
            runner,
            [
                "gcloud",
                "run",
                "services",
                "update-traffic",
                SERVICE,
                "--project",
                approval["project"],
                "--region",
                REGION,
                "--to-revisions",
                f"{revision}=100",
                "--quiet",
            ],
            root,
        )
        service = json.loads(output(runner, service_inventory_command(approval), root))
        zero_revision = (
            current.rollback_revision
            if operation == "promote"
            else current.candidate_revision
        )
        if not _traffic_is_exact(
            service.get("status", {}).get("traffic", []),
            revision,
            {zero_revision},
        ):
            raise OperatorError("Cloud Run traffic did not converge exactly")
        state = OperatorState(
            current.approved_commit,
            current.build_id,
            current.image_uri,
            current.image_digest,
            current.candidate_revision,
            current.rollback_revision,
            current.mode,
            "promoted" if operation == "promote" else "rolled_back",
        )
    save_state(state_path, state)
    return state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument(
        "--execute",
        choices=(
            "build",
            "recover-build",
            "candidate",
            "recover-candidate",
            "promote",
            "rollback",
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.approval is None:
            print("Dry-run only: private Owner approval artifact is required.")
            return 0
        approval = load_approval(args.approval)
        manifest = dry_run_manifest(
            approval, os.environ.get("MOBILE_STAGING_DATABASE_URL", "")
        )
        if args.execute is None:
            print(json.dumps(manifest, sort_keys=True))
            return 0
        if args.state_file is None:
            raise OperatorError("Execution requires private recovery state")
        state = execute(
            args.execute,
            approval,
            os.environ.get("MOBILE_STAGING_DATABASE_URL", ""),
            args.state_file,
            Path(__file__).resolve().parents[1],
        )
        print(json.dumps(asdict(state), sort_keys=True))
        return 0
    except (OperatorError, StagingContractError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
