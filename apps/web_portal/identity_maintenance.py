"""Temporary fail-closed boundary for Phase C identity lifecycle features."""

import os


def validate_erasure_checks_configuration(*, demo_mode: bool = False) -> None:
    """Validate before routes; offline demo must not import the shared package."""
    if demo_mode:
        if os.environ.get("PORTAL_DATA_ERASURE_CHECKS_ENABLED", "false") != "false":
            raise RuntimeError("erasure checks cannot run in demo mode")
        return
    from shared_module.portal_data.runtime import phase_c_runtime_state

    phase_c_runtime_state()


def is_phase_c_enabled(*, demo_mode: bool = False) -> bool:
    """Keep the offline demo independent from the deployed shared package."""
    if demo_mode:
        return False
    from shared_module.portal_data.runtime import is_phase_c_enabled as enabled

    return enabled()


def is_identity_maintenance_enabled(*, demo_mode: bool = False) -> bool:
    """Maintenance requires both exact Phase C and maintenance opt-ins."""
    if demo_mode:
        return False
    from shared_module.portal_data.runtime import (
        is_identity_maintenance_enabled as enabled,
    )

    return enabled()


def is_rollout_freeze_enabled(*, demo_mode: bool = False) -> bool:
    """Keep production transition freeze disabled in the offline demo."""
    if demo_mode:
        return False
    from shared_module.portal_data.runtime import is_rollout_freeze_enabled as enabled

    return enabled()
