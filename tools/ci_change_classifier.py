from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Optional, Sequence

SCOPES = (
    "flutter",
    "portal_data",
    "web_portal",
    "game_broadcast",
    "notify_cron",
    "deployment_tools",
    "update_schedule",
    "line_webhook",
)
OUTPUTS = ("docs_only", "quick_only", *SCOPES, "full")
QUALITY_JOB = "quality"
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")


@dataclass(frozen=True)
class Classification:
    docs_only: bool = False
    quick_only: bool = False
    flutter: bool = False
    portal_data: bool = False
    web_portal: bool = False
    game_broadcast: bool = False
    notify_cron: bool = False
    deployment_tools: bool = False
    update_schedule: bool = False
    line_webhook: bool = False
    full: bool = False

    def outputs(self) -> dict[str, str]:
        return {name: "true" if getattr(self, name) else "false" for name in OUTPUTS}


def _full() -> Classification:
    return Classification(full=True)


def _normalize_path(raw_path: str) -> Optional[str]:
    if not raw_path or any(character in raw_path for character in ("\0", "\n", "\r")):
        return None
    path = raw_path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return None
    parts = PurePosixPath(path).parts
    if any(part in ("", ".", "..") for part in parts):
        return None
    return "/".join(parts)


def _path_scope(path: str) -> Optional[str]:
    lower = path.lower()
    name = PurePosixPath(lower).name

    if lower.endswith(".py") and lower.startswith("docs/"):
        return "full"
    if lower.startswith("clients/flutter_app/") or lower == (
        ".github/workflows/flutter-tests.yml"
    ):
        return "flutter"
    if lower == ".gitattributes" or lower.startswith(".github/workflows/"):
        return "full"
    if lower in (
        "tools/ci_change_classifier.py",
        "tools/repository_quality.py",
        "tools/artifact_digest.py",
        "tools/tests/test_ci_change_classifier.py",
        "tools/tests/test_ci_workflow_contract.py",
        "tools/tests/test_repository_quality.py",
        "tools/tests/test_artifact_digest.py",
    ):
        return "full"
    if lower in (
        "tools/invoke-fluttertoolchain.ps1",
        "tools/tests/test_ci_flutter_toolchain_contract.py",
    ):
        return "quick"
    if lower in (
        "tests/portal_data/test_phase_c_rollout_state.py",
        "tools/phase_c_rollout_preflight.py",
        "tools/phase_c_transition_controller.py",
        "docs/operations/data/portal_data_phase_c_application_rollout.md",
        "envs/web_portal/.env_example.yaml",
        "envs/line_webhook_handler/.env_example.yaml",
        "envs/notify_cronjob_service/.env_example.yaml",
    ):
        return "deployment_tools"
    if (
        name.startswith("requirements")
        or name
        in (
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "tox.ini",
            "pipfile",
            "pipfile.lock",
            "poetry.lock",
        )
        or lower.startswith("shared_lib/")
        or lower.startswith("envs/")
    ):
        return "full"
    if (
        lower.startswith("docs/operations/sql/")
        or lower.startswith("docs/operations/data/")
        or lower == "docs/development/local_portal_data.md"
        or lower.startswith("migrations/")
        or lower.startswith("tests/portal_data/")
        or lower.startswith("tests/fixtures/")
        or lower.startswith("tools/portal_data_")
        or lower
        in (
            "alembic.ini",
            "docker-compose.portal-data.yml",
            "tools/setup_portal_data_legacy.py",
            "tools/seed_portal_data_fake.py",
            "tools/supabase_access_inventory.py",
        )
    ):
        return "portal_data"
    if lower.startswith("apps/web_portal/"):
        return "web_portal"
    if lower.startswith("apps/game_broadcast_service/"):
        return "game_broadcast"
    if lower.startswith("apps/notify_cronjob_service/"):
        return "notify_cron"
    if lower.startswith("functions/update_game_schedule/"):
        return "update_schedule"
    if lower.startswith("functions/line_webhook_handler/"):
        return "line_webhook"
    if (
        lower.startswith("makes/")
        or lower.startswith("tools/deploy_")
        or lower.startswith("tools/tests/test_deploy_")
    ):
        return "deployment_tools"
    if "dockerfile" in name or name.startswith("cloudbuild") or name == ".dockerignore":
        return "full"
    if lower.startswith("docs/") or lower in (
        "agents.md",
        "readme.md",
        "license",
        "license.md",
    ):
        return "docs"
    return None


def classify_paths(paths: Iterable[str]) -> Classification:
    normalized_paths = set()
    for raw_path in paths:
        normalized = _normalize_path(raw_path)
        if normalized is None:
            return _full()
        normalized_paths.add(normalized)
    if not normalized_paths:
        return _full()

    scopes = set()
    for path in normalized_paths:
        if path.lower() == "shared_lib/shared_module/portal_data/runtime.py":
            scopes.update(
                {
                    "deployment_tools",
                    "web_portal",
                    "line_webhook",
                    "notify_cron",
                }
            )
            continue
        scope = _path_scope(path)
        if scope is None or scope == "full":
            return _full()
        scopes.add(scope)

    if scopes == {"docs"}:
        return Classification(docs_only=True)
    if scopes.issubset({"docs", "quick"}):
        return Classification(quick_only=True)
    values = {scope: True for scope in scopes if scope in SCOPES}
    return Classification(**values)


def _valid_sha(value: str) -> bool:
    return bool(SHA_PATTERN.fullmatch(value)) and value != "0" * 40


def classify_git_diff(
    base: str, head: str, *, merge_base: bool = False
) -> tuple[Classification, str, str]:
    if not _valid_sha(base) or not _valid_sha(head):
        return _full(), "", ""
    command = ["git", "diff", "--name-only", "-z", "--no-renames"]
    if merge_base:
        command.append("--merge-base")
    completed = subprocess.run(
        [*command, base, head],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        return _full(), "", ""
    paths = [os.fsdecode(path) for path in completed.stdout.split(b"\0") if path]
    return classify_paths(paths), base.lower(), head.lower()


def final_gate_failures(
    classification: Mapping[str, str], results: Mapping[str, str]
) -> list[str]:
    failures = []
    if set(classification) != set(OUTPUTS) or any(
        value not in ("true", "false") for value in classification.values()
    ):
        failures.append("classification outputs are missing or invalid")
        return failures

    enabled = {name for name, value in classification.items() if value == "true"}
    if "full" in enabled and len(enabled) != 1:
        failures.append("full classification must be exclusive")
    if "docs_only" in enabled and len(enabled) != 1:
        failures.append("docs-only classification must be exclusive")
    if "quick_only" in enabled and len(enabled) != 1:
        failures.append("quick-only classification must be exclusive")
    if not enabled:
        failures.append("classification selected no execution path")

    for job in ("classify", "quick"):
        if results.get(job) != "success":
            failures.append(f"required job did not succeed: {job}")

    if enabled.intersection({"docs_only", "quick_only"}):
        if results.get(QUALITY_JOB) != "skipped":
            failures.append("unselected job was not skipped: quality")
    elif results.get(QUALITY_JOB) != "success":
        failures.append("required job did not succeed: quality")

    required_scopes = set(SCOPES) if "full" in enabled else enabled.intersection(SCOPES)
    for scope in SCOPES:
        result = results.get(scope)
        if scope in required_scopes:
            if result != "success":
                failures.append(f"required job did not succeed: {scope}")
        elif result != "skipped":
            failures.append(f"unselected job was not skipped: {scope}")
    return failures


def _emit(classification: Classification, base: str = "", head: str = "") -> None:
    for name, value in classification.outputs().items():
        print(f"{name}={value}")
    print(f"base_sha={base}")
    print(f"head_sha={head}")


def _classification_from_environment() -> dict[str, str]:
    return {name: os.environ.get(f"CI_SCOPE_{name.upper()}", "") for name in OUTPUTS}


def _results_from_environment() -> dict[str, str]:
    return {
        name: os.environ.get(f"CI_RESULT_{name.upper()}", "")
        for name in ("classify", "quick", QUALITY_JOB, *SCOPES)
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    classify_parser = subparsers.add_parser("classify")
    source = classify_parser.add_mutually_exclusive_group()
    source.add_argument("--full", action="store_true")
    source.add_argument("--git-diff", nargs=2, metavar=("BASE", "HEAD"))
    classify_parser.add_argument("--merge-base", action="store_true")
    subparsers.add_parser("final-gate")
    args = parser.parse_args(argv)

    if args.command == "final-gate":
        failures = final_gate_failures(
            _classification_from_environment(), _results_from_environment()
        )
        if failures:
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print("all selected CI jobs passed")
        return 0

    if args.full:
        _emit(_full())
        return 0
    if args.git_diff:
        classification, base, head = classify_git_diff(
            *args.git_diff, merge_base=args.merge_base
        )
        _emit(classification, base, head)
        return 0
    if args.merge_base:
        parser.error("--merge-base requires --git-diff")
    paths = [os.fsdecode(path) for path in sys.stdin.buffer.read().split(b"\0") if path]
    _emit(classify_paths(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
