"""Temporary fail-closed boundary for Phase C identity lifecycle features."""


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
