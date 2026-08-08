import os
from dataclasses import dataclass
from typing import Iterable, Mapping

PHASE_C_ENABLED_ENV = "PORTAL_DATA_PHASE_C_ENABLED"
IDENTITY_MAINTENANCE_ENV = "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED"
ROLLOUT_SERVICES = ("web_portal", "line_webhook", "notify_cron")


@dataclass(frozen=True)
class PhaseCRuntimeState:
    """Effective runtime flags after applying the fail-closed relationship."""

    phase_c_enabled: bool
    identity_maintenance_enabled: bool
    maintenance_requested: bool
    valid: bool
    mode: str


@dataclass(frozen=True)
class PhaseCRolloutState:
    """Cross-service rollout classification used by tests and preflight."""

    mode: str
    safe: bool
    enabled_services: tuple[str, ...]


def phase_c_runtime_state(
    environment: Mapping[str, str] | None = None,
    *,
    demo_mode: bool = False,
) -> PhaseCRuntimeState:
    values = os.environ if environment is None else environment
    phase_c_requested = values.get(PHASE_C_ENABLED_ENV) == "true"
    maintenance_requested = values.get(IDENTITY_MAINTENANCE_ENV) == "true"
    if demo_mode:
        return PhaseCRuntimeState(False, False, maintenance_requested, True, "demo")
    if maintenance_requested and not phase_c_requested:
        return PhaseCRuntimeState(False, False, True, False, "invalid")
    if phase_c_requested and maintenance_requested:
        return PhaseCRuntimeState(True, True, True, True, "phase_c_maintenance")
    if phase_c_requested:
        return PhaseCRuntimeState(True, False, False, True, "phase_c")
    return PhaseCRuntimeState(False, False, False, True, "legacy")


def classify_phase_c_rollout(
    service_flags: Mapping[str, bool], *, identity_maintenance: bool = False
) -> PhaseCRolloutState:
    """Accept only coordinated all-off or all-on service flag vectors."""
    if set(service_flags) != set(ROLLOUT_SERVICES):
        return PhaseCRolloutState("invalid_service_set", False, ())
    enabled = tuple(name for name in ROLLOUT_SERVICES if service_flags[name])
    if not enabled and not identity_maintenance:
        return PhaseCRolloutState("legacy", True, enabled)
    if len(enabled) == len(ROLLOUT_SERVICES):
        mode = "phase_c_maintenance" if identity_maintenance else "phase_c"
        return PhaseCRolloutState(mode, True, enabled)
    if identity_maintenance and "web_portal" not in enabled:
        return PhaseCRolloutState("invalid_maintenance", False, enabled)
    return PhaseCRolloutState("forbidden_mixed_mode", False, enabled)


def is_phase_c_enabled(
    environment: Mapping[str, str] | None = None, *, demo_mode: bool = False
) -> bool:
    """Return true only for the exact, explicit Phase C runtime opt-in."""
    return phase_c_runtime_state(environment, demo_mode=demo_mode).phase_c_enabled


def is_identity_maintenance_enabled(
    environment: Mapping[str, str] | None = None, *, demo_mode: bool = False
) -> bool:
    """Permit maintenance only as an exact opt-in under an enabled Phase C."""
    return phase_c_runtime_state(
        environment, demo_mode=demo_mode
    ).identity_maintenance_enabled


def get_identity_lifecycle_repository(admin_member_ids: Iterable[int] = ()):
    """Construct the repository lazily so imports do not connect to the database."""
    from shared_module.models.db import engine

    from .identity_lifecycle import IdentityLifecycleRepository

    return IdentityLifecycleRepository(engine, admin_member_ids)
