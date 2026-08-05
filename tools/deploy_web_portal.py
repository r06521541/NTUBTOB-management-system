"""Fail-closed, cross-platform deployment wrapper for the Web Portal.

The default command performs repository-local preflight only. Cloud mutation
requires ``--execute`` plus every exact approval input documented by TASK-028.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence


PROJECT_ID = "ntubtob-schedule-405614"
REGION = "asia-east1"
SERVICE = "web-portal"
SERVICE_DIRECTORY = "web_portal"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SECRET_REF_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*$"
)
EXCLUDED_ENV_KEYS = frozenset(
    {"DSN_PASSWORD", "LINE_LOGIN_CHANNEL_SECRET", "SECRET_KEY"}
)
REQUIRED_PLAIN_KEYS = frozenset(
    {
        "DSN_DATABASE",
        "DSN_HOSTNAME",
        "DSN_PORT",
        "DSN_UID",
        "LINE_LOGIN_CHANNEL_ID",
        "WEB_PORTAL_ADMIN_MEMBER_IDS",
    }
)
TERMINAL_BUILD_STATUSES = frozenset(
    {"SUCCESS", "FAILURE", "CANCELLED", "EXPIRED", "TIMEOUT", "INTERNAL_ERROR"}
)


class DeploymentError(RuntimeError):
    """A safely reportable deployment contract failure."""


class DeploymentStageError(DeploymentError):
    """A deployment failure with a safe, non-sensitive stage label."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]
HttpGet = Callable[[str, float], int]


def run_command(arguments: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
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


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def http_status(url: str, timeout: float) -> int:
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise DeploymentError("Web Portal HTTP verification could not complete") from error


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


def validate_revision(value: str) -> str:
    if not re.fullmatch(r"web-portal-[a-z0-9-]+", value):
        raise DeploymentError("Rollback revision does not belong to web-portal")
    return value


def validate_secret_ref(value: str, label: str) -> str:
    if not SECRET_REF_PATTERN.fullmatch(value):
        raise DeploymentError(f"{label} must be a resource:version reference")
    return value


def parse_env_key(line: str) -> Optional[str]:
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#") or ":" not in stripped:
        return None
    key = stripped.split(":", 1)[0].strip()
    return key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) else None


def write_filtered_env(source: Path, destination: Path) -> None:
    if destination.exists():
        raise DeploymentError("Refusing to overwrite an existing service .env.yaml")
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [line for line in lines if parse_env_key(line) not in EXCLUDED_ENV_KEYS]
    destination.write_text("".join(filtered), encoding="utf-8")


def parse_json(output: str, context: str) -> dict:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise DeploymentError(f"Invalid JSON returned for {context}") from error
    if not isinstance(value, dict):
        raise DeploymentError(f"Unexpected JSON returned for {context}")
    return value


def normalize_digest(value: object) -> str:
    if not isinstance(value, str):
        raise DeploymentError("Image digest is missing or invalid")
    digest = value.rsplit("@", 1)[-1].lower()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise DeploymentError("Image digest is missing or invalid")
    return digest


def preflight(
    root: Path,
    approved_commit: Optional[str] = None,
    rollback_revision: Optional[str] = None,
    line_secret_ref: Optional[str] = None,
    session_secret_ref: Optional[str] = None,
    runner: Runner = run_command,
    check_tools: bool = True,
) -> str:
    if check_tools:
        require_tool("git")
    status = command_output(runner, ["git", "status", "--porcelain"], root)
    if status:
        raise DeploymentError("Repository working tree must be clean")
    head = command_output(runner, ["git", "rev-parse", "HEAD"], root).lower()

    if approved_commit is not None and head != validate_sha(approved_commit):
        raise DeploymentError("HEAD does not match the approved commit")
    if rollback_revision is not None:
        validate_revision(rollback_revision)
    if line_secret_ref is not None:
        validate_secret_ref(line_secret_ref, "LINE Login Secret reference")
    if session_secret_ref is not None:
        validate_secret_ref(session_secret_ref, "Session Secret reference")

    service_root = root / "apps" / SERVICE_DIRECTORY
    required_files = (
        service_root / "cloudbuild.yaml",
        service_root / "Dockerfile",
        root / "shared_lib" / "setup.py",
        root / "envs" / SERVICE_DIRECTORY / ".env.yaml",
    )
    if not all(path.is_file() for path in required_files):
        raise DeploymentError("Required deployment source is unavailable")
    if (service_root / ".env.yaml").exists():
        raise DeploymentError("Refusing to overwrite an existing service .env.yaml")
    return head


def poll_build(
    root: Path,
    build_id: str,
    runner: Runner,
    timeout: float,
    interval: float,
    clock: Clock,
    sleeper: Sleeper,
) -> dict:
    deadline = clock() + timeout
    while True:
        build = parse_json(
            command_output(
                runner,
                [
                    "gcloud",
                    "builds",
                    "describe",
                    build_id,
                    "--project",
                    PROJECT_ID,
                    "--region",
                    REGION,
                    "--format=json",
                ],
                root,
            ),
            "Cloud Build status",
        )
        status = build.get("status")
        if status in TERMINAL_BUILD_STATUSES:
            if status != "SUCCESS":
                raise DeploymentError(f"Cloud Build ended with status {status}")
            return build
        if not isinstance(status, str):
            raise DeploymentError("Cloud Build status is missing or malformed")
        if clock() >= deadline:
            raise DeploymentError("Cloud Build polling timed out")
        sleeper(interval)


def revision_ready(revision: dict) -> bool:
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in revision.get("status", {}).get("conditions", [])
        if isinstance(condition, dict)
    )


def secret_reference(entry: dict) -> Optional[str]:
    source = entry.get("valueFrom", {}).get("secretKeyRef", {})
    resource = source.get("name") or source.get("secret")
    version = source.get("key") or source.get("version")
    if isinstance(resource, str) and isinstance(version, str):
        return f"{resource}:{version}"
    return None


def validate_revision_contract(
    revision: dict,
    approved_digest: str,
    expected_identity: str,
    line_secret_ref: str,
    session_secret_ref: str,
) -> None:
    if not revision_ready(revision):
        raise DeploymentError("New revision is not ready")
    if normalize_digest(revision.get("status", {}).get("imageDigest")) != approved_digest:
        raise DeploymentError("New revision digest does not match the approved image")
    spec = revision.get("spec", {})
    if spec.get("serviceAccountName") != expected_identity:
        raise DeploymentError("Runtime identity changed unexpectedly")
    containers = spec.get("containers", [])
    if len(containers) != 1 or not isinstance(containers[0], dict):
        raise DeploymentError("Revision container contract is malformed")
    entries = containers[0].get("env", [])
    by_name = {entry.get("name"): entry for entry in entries if isinstance(entry, dict)}
    expected_secrets = {
        "DSN_PASSWORD": "supabase-database-password:latest",
        "LINE_LOGIN_CHANNEL_SECRET": line_secret_ref,
        "SECRET_KEY": session_secret_ref,
    }
    for name, reference in expected_secrets.items():
        if secret_reference(by_name.get(name, {})) != reference:
            raise DeploymentError(f"Runtime Secret classification is invalid for {name}")
    for name in REQUIRED_PLAIN_KEYS:
        entry = by_name.get(name, {})
        if "value" not in entry or secret_reference(entry) is not None:
            raise DeploymentError(f"Runtime plain configuration is missing: {name}")
    for forbidden in ("WEB_PORTAL_DEMO_MODE", "WEB_PORTAL_ENV"):
        if forbidden in by_name:
            raise DeploymentError("Production demo configuration must remain absent")


def revision_converged(
    root: Path,
    baseline_revision: str,
    approved_digest: str,
    expected_identity: str,
    line_secret_ref: str,
    session_secret_ref: str,
    runner: Runner,
) -> Optional[tuple[dict, str]]:
    """Return a distinct Ready revision with an approved runtime contract."""
    service = parse_json(
        command_output(
            runner,
            [
                "gcloud", "run", "services", "describe", SERVICE,
                "--project", PROJECT_ID, "--region", REGION, "--format=json",
            ],
            root,
        ),
        "Cloud Run service",
    )
    revision_name = service.get("status", {}).get("latestCreatedRevisionName")
    if (
        not isinstance(revision_name, str)
        or not revision_name
        or revision_name == baseline_revision
    ):
        return None
    revision = parse_json(
        command_output(
            runner,
            [
                "gcloud",
                "run",
                "revisions",
                "describe",
                revision_name,
                "--project",
                PROJECT_ID,
                "--region",
                REGION,
                "--format=json",
            ],
            root,
        ),
        "Cloud Run revision",
    )
    if not revision_ready(revision):
        return None
    # Once Ready=True, contract differences are hard drift, not convergence delay.
    validate_revision_contract(
        revision,
        approved_digest,
        expected_identity,
        line_secret_ref,
        session_secret_ref,
    )
    return service, revision_name


def poll_revision(
    root: Path,
    baseline_revision: str,
    approved_digest: str,
    expected_identity: str,
    line_secret_ref: str,
    session_secret_ref: str,
    runner: Runner,
    timeout: float,
    interval: float,
    clock: Clock,
    sleeper: Sleeper,
) -> tuple[dict, str]:
    deadline = clock() + timeout
    while True:
        result = revision_converged(
            root,
            baseline_revision,
            approved_digest,
            expected_identity,
            line_secret_ref,
            session_secret_ref,
            runner,
        )
        if result is not None:
            return result
        if clock() >= deadline:
            raise DeploymentError("Cloud Run revision convergence timed out")
        sleeper(interval)


def has_exact_traffic(service: dict, revision_name: str) -> bool:
    traffic = service.get("status", {}).get("traffic", [])
    return any(
        item.get("revisionName") == revision_name and item.get("percent") == 100
        for item in traffic
        if isinstance(item, dict)
    )


def poll_traffic(
    root: Path,
    revision_name: str,
    runner: Runner,
    timeout: float,
    interval: float,
    clock: Clock,
    sleeper: Sleeper,
) -> dict:
    deadline = clock() + timeout
    while True:
        service = parse_json(
            command_output(
                runner,
                [
                    "gcloud", "run", "services", "describe", SERVICE,
                    "--project", PROJECT_ID, "--region", REGION, "--format=json",
                ],
                root,
            ),
            "Cloud Run traffic",
        )
        if has_exact_traffic(service, revision_name):
            return service
        if clock() >= deadline:
            raise DeploymentError("Cloud Run traffic convergence timed out")
        sleeper(interval)


def public_invoker_enabled(policy: dict) -> bool:
    return any(
        binding.get("role") == "roles/run.invoker"
        and "allUsers" in binding.get("members", [])
        for binding in policy.get("bindings", [])
        if isinstance(binding, dict)
    )


def rollback_command(revision: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "update-traffic",
        SERVICE,
        "--project",
        PROJECT_ID,
        "--region",
        REGION,
        "--to-revisions",
        f"{revision}=100",
        "--quiet",
    ]


def promotion_command(revision: str) -> list[str]:
    return rollback_command(revision)


def execute_deployment(
    root: Path,
    approved_commit: str,
    rollback_revision: str,
    line_secret_ref: str,
    session_secret_ref: str,
    runner: Runner = run_command,
    http_get: HttpGet = http_status,
    clock: Clock = time.monotonic,
    sleeper: Sleeper = time.sleep,
    poll_timeout: float = 900.0,
    poll_interval: float = 10.0,
    http_timeout: float = 10.0,
    check_tools: bool = True,
) -> dict:
    preflight(
        root,
        approved_commit,
        rollback_revision,
        line_secret_ref,
        session_secret_ref,
        runner,
        check_tools,
    )
    approved_commit = validate_sha(approved_commit)
    rollback_revision = validate_revision(rollback_revision)
    line_secret_ref = validate_secret_ref(line_secret_ref, "LINE Login Secret reference")
    session_secret_ref = validate_secret_ref(session_secret_ref, "Session Secret reference")
    if check_tools:
        require_tool("gcloud")

    service_root = root / "apps" / SERVICE_DIRECTORY
    env_source = root / "envs" / SERVICE_DIRECTORY / ".env.yaml"
    temporary_env = service_root / ".env.yaml"
    artifact_source = root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz"
    artifact_target = service_root / "dist" / artifact_source.name
    traffic_may_have_changed = False
    failure_stage = "build"
    try:
        baseline = parse_json(
            command_output(
                runner,
                ["gcloud", "run", "services", "describe", SERVICE, "--project", PROJECT_ID, "--region", REGION, "--format=json"],
                root,
            ),
            "Cloud Run baseline",
        )
        baseline_identity = baseline.get("spec", {}).get("template", {}).get("spec", {}).get("serviceAccountName")
        baseline_revision = baseline.get("status", {}).get("latestCreatedRevisionName")
        if not isinstance(baseline_identity, str) or not baseline_identity or not baseline_revision:
            raise DeploymentError("Cloud Run baseline contract is incomplete")

        command_output(runner, [sys.executable, "setup.py", "sdist", "--dist-dir", "dist"], root / "shared_lib")
        if not artifact_source.is_file():
            raise DeploymentError("Shared library build did not produce the expected artifact")
        artifact_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact_source, artifact_target)
        write_filtered_env(env_source, temporary_env)

        substitutions = ",".join(
            (
                f"_SERVICE_NAME={SERVICE}",
                f"_REGION={REGION}",
                f"_IMAGE_TAG={approved_commit}",
                f"_WEB_PORTAL_LINE_LOGIN_SECRET_REF={line_secret_ref}",
                f"_WEB_PORTAL_SESSION_SECRET_REF={session_secret_ref}",
            )
        )
        build_id = command_output(
            runner,
            ["gcloud", "builds", "submit", ".", "--async", "--project", PROJECT_ID, "--region", REGION, "--config", "cloudbuild.yaml", "--substitutions", substitutions, "--format=value(id)", "--quiet"],
            service_root,
        )
        if not re.fullmatch(r"[A-Za-z0-9-]+", build_id):
            raise DeploymentError("Cloud Build ID is missing or malformed")
        poll_build(root, build_id, runner, poll_timeout, poll_interval, clock, sleeper)
        failure_stage = "revision_convergence"

        image_reference = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/management-system-docker-repo/{SERVICE}-image:{approved_commit}"
        approved_digest = normalize_digest(
            command_output(runner, ["gcloud", "artifacts", "docker", "images", "describe", image_reference, "--project", PROJECT_ID, "--format=value(image_summary.digest)"], root)
        )
        service, revision_name = poll_revision(
            root,
            baseline_revision,
            approved_digest,
            baseline_identity,
            line_secret_ref,
            session_secret_ref,
            runner,
            poll_timeout,
            poll_interval,
            clock,
            sleeper,
        )
        if has_exact_traffic(service, revision_name):
            # Cloud Run may have promoted automatically; later checks still need rollback safety.
            traffic_may_have_changed = True
        else:
            failure_stage = "traffic_promotion"
            traffic_may_have_changed = True
            command_output(runner, promotion_command(revision_name), root)
            failure_stage = "traffic_convergence"
            service = poll_traffic(
                root,
                revision_name,
                runner,
                poll_timeout,
                poll_interval,
                clock,
                sleeper,
            )
        failure_stage = "iam"
        policy = parse_json(
            command_output(runner, ["gcloud", "run", "services", "get-iam-policy", SERVICE, "--project", PROJECT_ID, "--region", REGION, "--format=json"], root),
            "Cloud Run IAM policy",
        )
        if not public_invoker_enabled(policy):
            raise DeploymentError("Public invoker boundary is missing")
        failure_stage = "http"
        service_url = service.get("status", {}).get("url")
        if not isinstance(service_url, str) or not service_url.startswith("https://"):
            raise DeploymentError("Cloud Run service URL is missing or invalid")
        root_status = http_get(service_url.rstrip("/") + "/", http_timeout)
        demo_status = http_get(service_url.rstrip("/") + "/demo/", http_timeout)
        if root_status != 200 or demo_status != 404:
            raise DeploymentError("Web Portal HTTP verification failed")
        return {
            "build_id": build_id,
            "revision": revision_name,
            "image_tag": approved_commit,
            "image_digest": approved_digest,
            "http_status": {"/": root_status, "/demo/": demo_status},
            "rollback": "not_required",
        }
    except (DeploymentError, subprocess.CalledProcessError) as deployment_error:
        if traffic_may_have_changed:
            try:
                command_output(runner, rollback_command(rollback_revision), root)
            except DeploymentError as rollback_error:
                raise DeploymentStageError(
                    "rollback",
                    f"Deployment failed at stage {failure_stage}; rollback failed",
                ) from rollback_error
            raise DeploymentStageError(
                failure_stage,
                f"Deployment failed at stage {failure_stage}; rollback succeeded",
            ) from deployment_error
        if isinstance(deployment_error, DeploymentError):
            raise DeploymentStageError(
                failure_stage, f"Deployment failed at stage {failure_stage}"
            ) from deployment_error
        raise DeploymentStageError(
            failure_stage, f"Deployment failed at stage {failure_stage}"
        ) from deployment_error
    finally:
        if temporary_env.exists():
            temporary_env.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-commit")
    parser.add_argument("--rollback-revision")
    parser.add_argument("--line-login-secret-ref")
    parser.add_argument("--session-secret-ref")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    execution_values = (
        args.approved_commit,
        args.rollback_revision,
        args.line_login_secret_ref,
        args.session_secret_ref,
    )
    try:
        if args.execute:
            if not all(execution_values):
                raise DeploymentError("--execute requires every exact approval input")
            result = execute_deployment(
                repository_root(),
                args.approved_commit,
                args.rollback_revision,
                args.line_login_secret_ref,
                args.session_secret_ref,
            )
            print(json.dumps(result, sort_keys=True))
        else:
            if any(execution_values):
                raise DeploymentError("Execution-only arguments require --execute")
            preflight(repository_root())
            print("Preflight passed for web-portal; no cloud or HTTP commands were run.")
        return 0
    except DeploymentError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
