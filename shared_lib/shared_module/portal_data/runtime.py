import os
from typing import Iterable

PHASE_C_ENABLED_ENV = "PORTAL_DATA_PHASE_C_ENABLED"


def is_phase_c_enabled() -> bool:
    """Return true only for the exact, explicit Phase C runtime opt-in."""
    return os.environ.get(PHASE_C_ENABLED_ENV) == "true"


def get_identity_lifecycle_repository(admin_member_ids: Iterable[int] = ()):
    """Construct the repository lazily so imports do not connect to the database."""
    from shared_module.models.db import engine

    from .identity_lifecycle import IdentityLifecycleRepository

    return IdentityLifecycleRepository(engine, admin_member_ids)
