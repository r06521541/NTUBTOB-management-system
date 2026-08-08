"""Temporary fail-closed boundary for identity lifecycle maintenance."""

from shared_module.portal_data.runtime import is_identity_maintenance_enabled as enabled


def is_identity_maintenance_enabled() -> bool:
    """Maintenance requires both exact Phase C and maintenance opt-ins."""
    return enabled()
