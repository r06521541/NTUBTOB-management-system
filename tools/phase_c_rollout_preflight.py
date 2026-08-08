"""Offline, secret-free preflight for a coordinated Phase C rollout package."""

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from shared_lib.shared_module.portal_data.runtime import (
    ROLLOUT_SERVICES,
    classify_phase_c_transition,
)

ARTIFACT_NAME = "shared_lib-0.0.1.tar.gz"
ARTIFACT_ROOT = "shared_lib-0.0.1"
ARTIFACT_TARGETS = {
    "web_portal": Path("apps/web_portal/dist") / ARTIFACT_NAME,
    "line_webhook": Path("functions/line_webhook_handler/dist") / ARTIFACT_NAME,
    "notify_cron": Path("apps/notify_cronjob_service/dist") / ARTIFACT_NAME,
}
ENV_EXAMPLES = {
    "web_portal": Path("envs/web_portal/.env_example.yaml"),
    "line_webhook": Path("envs/line_webhook_handler/.env_example.yaml"),
    "notify_cron": Path("envs/notify_cronjob_service/.env_example.yaml"),
}
CONTEXT_IGNORE_FILES = {
    "web_portal": Path("apps/web_portal/.dockerignore"),
    "notify_cron": Path("apps/notify_cronjob_service/.dockerignore"),
    "line_webhook": Path("functions/line_webhook_handler/.gcloudignore"),
}
SERVICE_REQUIREMENTS = {
    "web_portal": Path("apps/web_portal/requirements.txt"),
    "line_webhook": Path("functions/line_webhook_handler/requirements.txt"),
    "notify_cron": Path("apps/notify_cronjob_service/requirements.txt"),
}
REQUIRED_CONTEXT_RULES = frozenset(
    {
        ".env.yaml",
        ".env*",
        "credentials*.json",
        "service-account*.json",
        "*.pem",
        "*.key",
        "*.dump",
        "*.backup",
        "*.sqlite*",
        "dist/*",
        f"!dist/{ARTIFACT_NAME}",
    }
)
ENV_LINE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*):\s*(?P<value>.*)\s*$")


class RolloutPreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class RolloutPreflightResult:
    mode: str
    source_fingerprint: str
    artifact_fingerprints: tuple[tuple[str, str], ...]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _boolean(value: str, label: str) -> bool:
    if value not in {"true", "false"}:
        raise RolloutPreflightError(f"{label} must be exactly true or false")
    return value == "true"


def _example_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RolloutPreflightError("required environment example is unavailable")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE.fullmatch(line.strip())
        if match:
            key = match.group("key")
            if key in values:
                raise RolloutPreflightError("environment example has a duplicate key")
            values[key] = match.group("value").strip().strip('"').strip("'")
    return values


def verify_environment_examples(root: Path) -> None:
    for service, relative in ENV_EXAMPLES.items():
        values = _example_values(root / relative)
        if values.get("PORTAL_DATA_PHASE_C_ENABLED") != "false":
            raise RolloutPreflightError(
                f"{service} Phase C example must remain explicitly false"
            )
        if values.get("PORTAL_DATA_ROLLOUT_FREEZE_ENABLED") != "false":
            raise RolloutPreflightError(
                f"{service} rollout freeze example must remain explicitly false"
            )
    web_values = _example_values(root / ENV_EXAMPLES["web_portal"])
    if web_values.get("WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED") != "false":
        raise RolloutPreflightError(
            "web_portal identity maintenance example must remain explicitly false"
        )


def verify_build_contexts(root: Path) -> None:
    for service, relative in CONTEXT_IGNORE_FILES.items():
        path = root / relative
        if not path.is_file():
            raise RolloutPreflightError(
                f"{service} build-context ignore file is missing"
            )
        rules = {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        missing = REQUIRED_CONTEXT_RULES - rules
        if missing or rules.intersection({"*", "**", ".", "dist/"}):
            raise RolloutPreflightError(
                f"{service} build context does not satisfy the rollout boundary"
            )


def verify_service_requirements(root: Path) -> None:
    expected = f"dist/{ARTIFACT_NAME}"
    for service, relative in SERVICE_REQUIREMENTS.items():
        path = root / relative
        if not path.is_file():
            raise RolloutPreflightError(f"{service} requirements file is missing")
        references = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if "shared_lib" in line and not line.lstrip().startswith("#")
        ]
        if references != [expected]:
            raise RolloutPreflightError(
                f"{service} does not reference the exact shared library artifact"
            )


def _source_files(root: Path) -> dict[str, bytes]:
    shared_root = root / "shared_lib"
    files = {
        "setup.py": (shared_root / "setup.py").read_bytes(),
    }
    for path in sorted((shared_root / "shared_module").rglob("*.py")):
        relative = path.relative_to(shared_root).as_posix()
        files[relative] = path.read_bytes()
    return files


def _fingerprint(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _artifact_files(path: Path) -> dict[str, bytes]:
    if not path.is_file():
        raise RolloutPreflightError("required shared library artifact is unavailable")
    try:
        with tarfile.open(path, "r:gz") as archive:
            names = archive.getnames()
            if not names or names[0].rstrip("/") != ARTIFACT_ROOT:
                raise RolloutPreflightError("shared library artifact root is invalid")
            files = {}
            prefix = f"{ARTIFACT_ROOT}/"
            for member in archive.getmembers():
                if not member.isfile() or not member.name.startswith(prefix):
                    continue
                relative = member.name[len(prefix) :]
                if relative == "setup.py" or (
                    relative.startswith("shared_module/") and relative.endswith(".py")
                ):
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise RolloutPreflightError(
                            "shared library artifact is unreadable"
                        )
                    files[relative] = extracted.read()
    except (tarfile.TarError, OSError) as error:
        raise RolloutPreflightError("shared library artifact is unreadable") from error
    return files


def verify_artifacts(root: Path) -> tuple[str, tuple[tuple[str, str], ...]]:
    expected_files = _source_files(root)
    expected_fingerprint = _fingerprint(expected_files)
    artifact_paths = {
        "shared_source": Path("shared_lib/dist") / ARTIFACT_NAME,
        **ARTIFACT_TARGETS,
    }
    fingerprints = []
    for service, relative in artifact_paths.items():
        files = _artifact_files(root / relative)
        if files != expected_files:
            raise RolloutPreflightError(
                f"{service} shared library artifact does not match source"
            )
        fingerprints.append((service, _fingerprint(files)))
    return expected_fingerprint, tuple(fingerprints)


def verify_rollout(
    root: Path,
    flag_values: Mapping[str, str],
    identity_maintenance: str,
    *,
    freeze_values: Mapping[str, str] | None = None,
    require_artifacts: bool = True,
) -> RolloutPreflightResult:
    if set(flag_values) != set(ROLLOUT_SERVICES):
        raise RolloutPreflightError("the rollout plan must name every runtime service")
    flags = {
        service: _boolean(flag_values[service], f"{service} Phase C flag")
        for service in ROLLOUT_SERVICES
    }
    freeze_input = (
        {service: "false" for service in ROLLOUT_SERVICES}
        if freeze_values is None
        else freeze_values
    )
    if set(freeze_input) != set(ROLLOUT_SERVICES):
        raise RolloutPreflightError("the freeze plan must name every runtime service")
    freezes = {
        service: _boolean(freeze_input[service], f"{service} freeze flag")
        for service in ROLLOUT_SERVICES
    }
    maintenance = _boolean(identity_maintenance, "identity maintenance flag")
    state = classify_phase_c_transition(
        flags, freezes, identity_maintenance=maintenance
    )
    if not state.safe:
        raise RolloutPreflightError(
            "mixed Phase C is allowed only while every service is frozen"
        )
    verify_environment_examples(root)
    verify_build_contexts(root)
    verify_service_requirements(root)
    fingerprint = "not-checked"
    artifacts: tuple[tuple[str, str], ...] = ()
    if require_artifacts:
        fingerprint, artifacts = verify_artifacts(root)
    return RolloutPreflightResult(state.mode, fingerprint, artifacts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-portal", required=True, choices=("true", "false"))
    parser.add_argument("--line-webhook", required=True, choices=("true", "false"))
    parser.add_argument("--notify-cron", required=True, choices=("true", "false"))
    parser.add_argument("--web-portal-freeze", required=True, choices=("true", "false"))
    parser.add_argument(
        "--line-webhook-freeze", required=True, choices=("true", "false")
    )
    parser.add_argument(
        "--notify-cron-freeze", required=True, choices=("true", "false")
    )
    parser.add_argument(
        "--identity-maintenance", required=True, choices=("true", "false")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        result = verify_rollout(
            repository_root(),
            {
                "web_portal": arguments.web_portal,
                "line_webhook": arguments.line_webhook,
                "notify_cron": arguments.notify_cron,
            },
            arguments.identity_maintenance,
            freeze_values={
                "web_portal": arguments.web_portal_freeze,
                "line_webhook": arguments.line_webhook_freeze,
                "notify_cron": arguments.notify_cron_freeze,
            },
        )
    except RolloutPreflightError as error:
        print(f"Phase C rollout preflight failed: {error}")
        return 2
    print(f"Phase C rollout preflight passed: mode={result.mode}")
    print(f"Shared library source fingerprint: {result.source_fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
