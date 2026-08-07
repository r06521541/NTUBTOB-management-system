"""Temporary fail-closed boundary for legacy identity maintenance."""

import os

IDENTITY_MAINTENANCE_ENV = "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED"


def is_identity_maintenance_enabled() -> bool:
    """Only the exact, explicit opt-in value can permit legacy writes."""
    return os.environ.get(IDENTITY_MAINTENANCE_ENV) == "true"
