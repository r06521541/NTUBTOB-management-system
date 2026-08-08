"""Offline planner for the canonical Phase C freeze transition path."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from shared_lib.shared_module.portal_data.runtime import (
    ROLLOUT_SERVICES,
    classify_phase_c_transition,
)
from tools import phase_c_rollout_preflight as preflight

FREEZE_ORDER = ("web_portal", "line_webhook", "notify_cron")
PHASE_C_ACTIVATION_ORDER = ("web_portal", "notify_cron", "line_webhook")
UNFREEZE_ORDER = ("web_portal", "line_webhook", "notify_cron")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


class TransitionPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class RolloutVector:
    phase_c: tuple[tuple[str, bool], ...]
    freeze: tuple[tuple[str, bool], ...]
    identity_maintenance: bool

    def phase_flags(self) -> dict[str, bool]:
        return dict(self.phase_c)

    def freeze_flags(self) -> dict[str, bool]:
        return dict(self.freeze)


@dataclass(frozen=True)
class TransitionStep:
    mode: str
    service: str
    flag: str
    value: bool


@dataclass(frozen=True)
class TransitionPlan:
    current_mode: str
    target_mode: str
    direction: str
    next_step: TransitionStep | None
    steps: tuple[TransitionStep, ...]
    source_commit: str
    artifact_fingerprint: str


def _exact_boolean(value: str, label: str) -> bool:
    if value not in {"true", "false"}:
        raise TransitionPlanError(f"{label} must be exactly true or false")
    return value == "true"


def rollout_vector(
    phase_c: Mapping[str, str],
    freeze: Mapping[str, str],
    identity_maintenance: str,
) -> RolloutVector:
    if set(phase_c) != set(ROLLOUT_SERVICES) or set(freeze) != set(ROLLOUT_SERVICES):
        raise TransitionPlanError("state must name every exact rollout service")
    phase_values = tuple(
        (service, _exact_boolean(phase_c[service], f"{service} Phase C flag"))
        for service in ROLLOUT_SERVICES
    )
    freeze_values = tuple(
        (service, _exact_boolean(freeze[service], f"{service} freeze flag"))
        for service in ROLLOUT_SERVICES
    )
    return RolloutVector(
        phase_values,
        freeze_values,
        _exact_boolean(identity_maintenance, "identity maintenance flag"),
    )


def _vector(
    phase_services=(), freeze_services=(), *, maintenance: bool = False
) -> RolloutVector:
    return RolloutVector(
        tuple((service, service in phase_services) for service in ROLLOUT_SERVICES),
        tuple((service, service in freeze_services) for service in ROLLOUT_SERVICES),
        maintenance,
    )


def canonical_transition_path() -> tuple[RolloutVector, ...]:
    states = [_vector()]
    frozen = []
    for service in FREEZE_ORDER:
        frozen.append(service)
        states.append(_vector(freeze_services=frozen))
    enabled = []
    for service in PHASE_C_ACTIVATION_ORDER:
        enabled.append(service)
        states.append(_vector(enabled, ROLLOUT_SERVICES))
    remaining_frozen = list(ROLLOUT_SERVICES)
    for service in UNFREEZE_ORDER:
        remaining_frozen.remove(service)
        states.append(_vector(ROLLOUT_SERVICES, remaining_frozen))
    states.append(_vector(ROLLOUT_SERVICES, maintenance=True))
    return tuple(states)


def repository_head_commit(root: Path) -> str:
    """Read the current Git HEAD without executing Git or another process."""
    git_path = root / ".git"
    if git_path.is_file():
        marker = git_path.read_text(encoding="utf-8").strip()
        if not marker.startswith("gitdir: "):
            raise TransitionPlanError("repository Git metadata is invalid")
        git_path = (root / marker.removeprefix("gitdir: ")).resolve()
    head_path = git_path / "HEAD"
    if not head_path.is_file():
        raise TransitionPlanError("repository Git HEAD is unavailable")
    head = head_path.read_text(encoding="utf-8").strip()
    if SHA_PATTERN.fullmatch(head):
        return head
    if not head.startswith("ref: "):
        raise TransitionPlanError("repository Git HEAD is invalid")
    reference = head.removeprefix("ref: ")
    reference_path = git_path / reference
    if reference_path.is_file():
        value = reference_path.read_text(encoding="utf-8").strip()
        if SHA_PATTERN.fullmatch(value):
            return value
    packed_refs = git_path / "packed-refs"
    if packed_refs.is_file():
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            commit, separator, name = line.partition(" ")
            if separator and name == reference and SHA_PATTERN.fullmatch(commit):
                return commit
    raise TransitionPlanError("repository Git HEAD reference is unavailable")


def _mode(vector: RolloutVector) -> str:
    state = classify_phase_c_transition(
        vector.phase_flags(),
        vector.freeze_flags(),
        identity_maintenance=vector.identity_maintenance,
    )
    if not state.safe:
        raise TransitionPlanError("rollout state is unsafe")
    return state.mode


def _transition_step(before: RolloutVector, after: RolloutVector) -> TransitionStep:
    changes = []
    for flag, before_values, after_values in (
        ("phase_c", before.phase_flags(), after.phase_flags()),
        ("freeze", before.freeze_flags(), after.freeze_flags()),
    ):
        for service in ROLLOUT_SERVICES:
            if before_values[service] != after_values[service]:
                changes.append((service, flag, after_values[service]))
    if before.identity_maintenance != after.identity_maintenance:
        changes.append(
            ("web_portal", "identity_maintenance", after.identity_maintenance)
        )
    if len(changes) != 1:
        raise TransitionPlanError("canonical transition must change exactly one flag")
    service, flag, value = changes[0]
    return TransitionStep(_mode(after), service, flag, value)


def plan_transition(
    current: RolloutVector,
    target: RolloutVector,
    *,
    source_commit: str,
    expected_source_commit: str,
    artifact_fingerprint: str,
    expected_artifact_fingerprint: str,
) -> TransitionPlan:
    for value, pattern, label in (
        (source_commit, SHA_PATTERN, "source commit"),
        (expected_source_commit, SHA_PATTERN, "expected source commit"),
        (artifact_fingerprint, FINGERPRINT_PATTERN, "artifact fingerprint"),
        (
            expected_artifact_fingerprint,
            FINGERPRINT_PATTERN,
            "expected artifact fingerprint",
        ),
    ):
        if pattern.fullmatch(value) is None:
            raise TransitionPlanError(f"{label} has an invalid format")
    if source_commit != expected_source_commit:
        raise TransitionPlanError("source commit does not match the expected commit")
    if artifact_fingerprint != expected_artifact_fingerprint:
        raise TransitionPlanError(
            "artifact fingerprint does not match the expected fingerprint"
        )

    path = canonical_transition_path()
    try:
        current_index = path.index(current)
        target_index = path.index(target)
    except ValueError as error:
        raise TransitionPlanError(
            "current and target must be canonical unambiguous states"
        ) from error
    direction = (
        "forward"
        if target_index > current_index
        else "rollback" if target_index < current_index else "complete"
    )
    increment = 1 if target_index > current_index else -1
    steps = []
    index = current_index
    while index != target_index:
        next_index = index + increment
        steps.append(_transition_step(path[index], path[next_index]))
        index = next_index
    return TransitionPlan(
        _mode(current),
        _mode(target),
        direction,
        steps[0] if steps else None,
        tuple(steps),
        source_commit,
        artifact_fingerprint,
    )


def _state_arguments(parser: argparse.ArgumentParser, prefix: str) -> None:
    for service in ROLLOUT_SERVICES:
        option = service.replace("_", "-")
        parser.add_argument(
            f"--{prefix}-{option}-phase-c", required=True, choices=("true", "false")
        )
        parser.add_argument(
            f"--{prefix}-{option}-freeze", required=True, choices=("true", "false")
        )
    parser.add_argument(
        f"--{prefix}-identity-maintenance",
        required=True,
        choices=("true", "false"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _state_arguments(parser, "current")
    _state_arguments(parser, "target")
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-artifact-fingerprint", required=True)
    parser.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def _arguments_vector(arguments, prefix: str) -> RolloutVector:
    return rollout_vector(
        {
            service: getattr(arguments, f"{prefix}_{service}_phase_c")
            for service in ROLLOUT_SERVICES
        },
        {
            service: getattr(arguments, f"{prefix}_{service}_freeze")
            for service in ROLLOUT_SERVICES
        },
        getattr(arguments, f"{prefix}_identity_maintenance"),
    )


def _step_dict(step: TransitionStep | None):
    if step is None:
        return None
    return {
        "mode": step.mode,
        "service": step.service,
        "flag": step.flag,
        "value": step.value,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        root = preflight.repository_root()
        preflight.verify_environment_examples(root)
        preflight.verify_build_contexts(root)
        preflight.verify_service_requirements(root)
        fingerprint, _ = preflight.verify_artifacts(root)
        plan = plan_transition(
            _arguments_vector(arguments, "current"),
            _arguments_vector(arguments, "target"),
            source_commit=repository_head_commit(root),
            expected_source_commit=arguments.expected_source_commit,
            artifact_fingerprint=fingerprint,
            expected_artifact_fingerprint=arguments.expected_artifact_fingerprint,
        )
    except (TransitionPlanError, preflight.RolloutPreflightError) as error:
        print(f"Phase C transition plan failed: {error}")
        return 2
    output = {
        "status": "valid",
        "current_mode": plan.current_mode,
        "target_mode": plan.target_mode,
        "direction": plan.direction,
        "next_step": _step_dict(plan.next_step),
        "step_count": len(plan.steps),
        "source_commit": plan.source_commit,
        "artifact_fingerprint": plan.artifact_fingerprint,
    }
    if arguments.output == "json":
        print(json.dumps(output, sort_keys=True))
    else:
        print(
            "Phase C transition plan passed: "
            f"{plan.current_mode}->{plan.target_mode} direction={plan.direction}"
        )
        if plan.next_step is not None:
            print(
                "Next step: "
                f"service={plan.next_step.service} flag={plan.next_step.flag} "
                f"value={str(plan.next_step.value).lower()}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
