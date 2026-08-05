"""Fail-closed deployment orchestration for the two scheduled Cloud Run services.

Without ``--execute`` this command performs repository-only checks and never runs
gcloud. Production execution always requires an exact commit and rollback
revision supplied by an approved deployment work package.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence


PROJECT_ID = "ntubtob-schedule-405614"
REGION = "asia-east1"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ServiceConfig:
    directory: str
    cloud_run_name: str
    secret_env_keys: frozenset[str]


SERVICES: Dict[str, ServiceConfig] = {
    "game-broadcast-service": ServiceConfig(
        directory="game_broadcast_service",
        cloud_run_name="game-broadcast-service",
        secret_env_keys=frozenset(
            {
                "DSN_PASSWORD",
                "CHANNEL_ACCESS_TOKEN",
                "CHANNEL_SECRET",
                "WEATHER_API_KEY",
            }
        ),
    ),
    "notify-cronjob-service": ServiceConfig(
        directory="notify_cronjob_service",
        cloud_run_name="notify-cronjob-service",
        secret_env_keys=frozenset(
            {"DSN_PASSWORD", "CHANNEL_ACCESS_TOKEN", "CHANNEL_SECRET"}
        ),
    ),
}


class DeploymentError(RuntimeError):
    """An expected, safely reportable deployment contract failure."""


Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def run_command(
    arguments: Sequence[str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    command = list(arguments)
    if not command:
        raise DeploymentError("Refusing to run an empty command")
    executable = shutil.which(command[0])
    if executable is None:
        raise DeploymentError(f"Required tool is unavailable: {command[0]}")
    command[0] = executable
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def command_output(runner: Runner, arguments: Sequence[str], cwd: Path) -> str:
    try:
        return runner(arguments, cwd).stdout.strip()
    except subprocess.CalledProcessError as error:
        command_name = " ".join(arguments[:2])
        raise DeploymentError(f"Command failed: {command_name}") from error


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise DeploymentError(f"Required tool is unavailable: {name}")


def validate_sha(value: str) -> str:
    normalized = value.lower()
    if not SHA_PATTERN.fullmatch(normalized):
        raise DeploymentError("Approved commit must be a full 40-character Git SHA")
    return normalized


def validate_rollback_revision(service: ServiceConfig, revision: str) -> str:
    pattern = rf"^{re.escape(service.cloud_run_name)}-[a-z0-9-]+$"
    if not re.fullmatch(pattern, revision):
        raise DeploymentError("Rollback revision does not belong to the target service")
    return revision


def parse_env_key(line: str) -> Optional[str]:
    stripped = line.lstrip()
    if (
        not stripped
        or stripped.startswith("#")
        or ":" not in stripped
    ):
        return None
    key = stripped.split(":", 1)[0].strip()
    return key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) else None


def write_filtered_env(
    source: Path, destination: Path, excluded: frozenset[str]
) -> None:
    if destination.exists():
        raise DeploymentError(
            f"Temporary environment file already exists: {destination}"
        )
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [line for line in lines if parse_env_key(line) not in excluded]
    destination.write_text("".join(filtered), encoding="utf-8")


def preflight(
    root: Path,
    service_name: str,
    approved_commit: Optional[str],
    rollback_revision: Optional[str],
    runner: Runner = run_command,
    check_tools: bool = True,
) -> ServiceConfig:
    service = SERVICES[service_name]
    if check_tools:
        require_tool("git")
    status = command_output(runner, ["git", "status", "--porcelain"], root)
    if status:
        raise DeploymentError("Repository working tree must be clean")

    head = command_output(runner, ["git", "rev-parse", "HEAD"], root).lower()
    if approved_commit is not None and head != validate_sha(approved_commit):
        raise DeploymentError("HEAD does not match the approved commit")
    if rollback_revision is not None:
        validate_rollback_revision(service, rollback_revision)

    service_root = root / "apps" / service.directory
    env_source = root / "envs" / service.directory / ".env.yaml"
    temporary_env = service_root / ".env.yaml"
    if temporary_env.exists():
        raise DeploymentError("Refusing to overwrite an existing service .env.yaml")
    if not env_source.is_file():
        raise DeploymentError("Service environment source is unavailable")
    if not (service_root / "cloudbuild.yaml").is_file():
        raise DeploymentError("Service Cloud Build configuration is unavailable")
    return service


def parse_json_output(output: str, context: str) -> dict:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise DeploymentError(f"Invalid JSON returned for {context}") from error
    if not isinstance(value, dict):
        raise DeploymentError(f"Unexpected JSON returned for {context}")
    return value


def normalize_image_digest(value: object) -> str:
    if not isinstance(value, str):
        raise DeploymentError("Image digest is missing or invalid")
    candidate = value.rsplit("@", 1)[-1].lower()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate):
        raise DeploymentError("Image digest is missing or invalid")
    return candidate


def revision_is_ready(revision: dict) -> bool:
    conditions = revision.get("status", {}).get("conditions", [])
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in conditions
        if isinstance(condition, dict)
    )


def rollback_command(service: ServiceConfig, revision: str) -> List[str]:
    return [
        "gcloud", "run", "services", "update-traffic", service.cloud_run_name,
        "--project", PROJECT_ID, "--region", REGION,
        "--to-revisions", f"{revision}=100", "--quiet",
    ]


def execute_deployment(
    root: Path,
    service_name: str,
    approved_commit: str,
    rollback_revision: str,
    runner: Runner = run_command,
    check_tools: bool = True,
) -> dict:
    service = preflight(
        root, service_name, approved_commit, rollback_revision, runner, check_tools
    )
    approved_commit = validate_sha(approved_commit)
    rollback_revision = validate_rollback_revision(service, rollback_revision)
    if check_tools:
        require_tool("gcloud")

    service_root = root / "apps" / service.directory
    env_source = root / "envs" / service.directory / ".env.yaml"
    temporary_env = service_root / ".env.yaml"
    artifact_source = root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz"
    artifact_target = service_root / "dist" / artifact_source.name
    traffic_may_have_changed = False

    try:
        baseline = parse_json_output(
            command_output(
                runner,
                [
                    "gcloud", "run", "services", "describe",
                    service.cloud_run_name, "--project", PROJECT_ID,
                    "--region", REGION, "--format=json",
                ],
                root,
            ),
            "Cloud Run baseline",
        )
        baseline_revision = baseline.get("status", {}).get(
            "latestCreatedRevisionName"
        )
        if not baseline_revision:
            raise DeploymentError("Cloud Run baseline has no latest revision")

        command_output(
            runner,
            [sys.executable, "setup.py", "sdist", "--dist-dir", "dist"],
            root / "shared_lib",
        )
        if not artifact_source.is_file():
            raise DeploymentError(
                "Shared library build did not produce the expected artifact"
            )
        artifact_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact_source, artifact_target)
        write_filtered_env(env_source, temporary_env, service.secret_env_keys)

        substitutions = (
            f"_SERVICE_NAME={service.cloud_run_name},_REGION={REGION},"
            f"_IMAGE_TAG={approved_commit}"
        )
        build = parse_json_output(
            command_output(
                runner,
                [
                    "gcloud", "builds", "submit", ".", "--project", PROJECT_ID,
                    "--region", REGION, "--config", "cloudbuild.yaml",
                    "--substitutions", substitutions, "--format=json", "--quiet",
                ],
                service_root,
            ),
            "Cloud Build",
        )
        if build.get("status") != "SUCCESS" or not build.get("id"):
            raise DeploymentError("Cloud Build did not report SUCCESS with a build ID")
        traffic_may_have_changed = True

        image_reference = (
            f"{REGION}-docker.pkg.dev/{PROJECT_ID}/"
            "management-system-docker-repo/"
            f"{service.cloud_run_name}-image:{approved_commit}"
        )
        approved_digest = command_output(
            runner,
            [
                "gcloud", "artifacts", "docker", "images", "describe",
                image_reference, "--project", PROJECT_ID, "--format",
                "value(image_summary.digest)",
            ],
            root,
        )
        approved_digest = normalize_image_digest(approved_digest)

        deployed = parse_json_output(
            command_output(
                runner,
                [
                    "gcloud", "run", "services", "describe", service.cloud_run_name,
                    "--project", PROJECT_ID, "--region", REGION, "--format=json",
                ],
                root,
            ),
            "Cloud Run service",
        )
        status = deployed.get("status", {})
        revision = status.get("latestCreatedRevisionName")
        if not revision or revision == baseline_revision:
            raise DeploymentError("Deployment did not create a new revision")
        revision_state = parse_json_output(
            command_output(
                runner,
                [
                    "gcloud", "run", "revisions", "describe", revision,
                    "--project", PROJECT_ID, "--region", REGION, "--format=json",
                ],
                root,
            ),
            "Cloud Run revision",
        )
        if not revision_is_ready(revision_state):
            raise DeploymentError("New revision is not ready")
        image_digest = normalize_image_digest(
            revision_state.get("status", {}).get("imageDigest")
        )
        if image_digest != approved_digest:
            raise DeploymentError(
                "New revision digest does not match the approved image tag"
            )

        command_output(
            runner,
            [
                "gcloud", "run", "services", "update-traffic", service.cloud_run_name,
                "--project", PROJECT_ID, "--region", REGION,
                "--to-revisions", f"{revision}=100", "--quiet",
            ],
            root,
        )
        verified = parse_json_output(
            command_output(
                runner,
                [
                    "gcloud", "run", "services", "describe", service.cloud_run_name,
                    "--project", PROJECT_ID, "--region", REGION, "--format=json",
                ],
                root,
            ),
            "Cloud Run verification",
        )
        traffic = verified.get("status", {}).get("traffic", [])
        if verified.get("status", {}).get("latestReadyRevisionName") != revision:
            raise DeploymentError("New revision is not the latest ready revision")
        if not any(
            item.get("revisionName") == revision and item.get("percent") == 100
            for item in traffic
        ):
            raise DeploymentError("New revision does not have 100% traffic")
        return {
            "build_id": build["id"],
            "revision": revision,
            "image_tag": approved_commit,
            "image_digest": image_digest,
        }
    except (DeploymentError, subprocess.CalledProcessError):
        if traffic_may_have_changed:
            try:
                command_output(
                    runner, rollback_command(service, rollback_revision), root
                )
            except DeploymentError as rollback_error:
                raise DeploymentError(
                    f"Deployment failed and rollback also failed: {rollback_error}"
                ) from rollback_error
        raise
    finally:
        if temporary_env.exists():
            temporary_env.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=sorted(SERVICES))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-commit")
    parser.add_argument("--rollback-revision")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.execute:
            if not args.approved_commit or not args.rollback_revision:
                raise DeploymentError(
                    "--execute requires --approved-commit and --rollback-revision"
                )
            result = execute_deployment(
                repository_root(),
                args.service,
                args.approved_commit,
                args.rollback_revision,
            )
            print(json.dumps(result, sort_keys=True))
        else:
            if args.approved_commit or args.rollback_revision:
                raise DeploymentError("Execution-only arguments require --execute")
            preflight(repository_root(), args.service, None, None)
            print(f"Preflight passed for {args.service}; no cloud commands were run.")
        return 0
    except DeploymentError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
