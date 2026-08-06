from __future__ import annotations

from urllib.parse import urlparse

LOCAL_DATABASE_NAME = "ntubtob_portal_local"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "portal-postgres"}


def require_local_database_url(value: str | None) -> str:
    """Return a local-only PostgreSQL URL or fail closed."""
    if not value:
        raise RuntimeError("PORTAL_DATA_DATABASE_URL is required")

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    database = parsed.path.lstrip("/")
    if parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
        raise RuntimeError("portal data database must use PostgreSQL")
    if host not in LOCAL_HOSTS or database != LOCAL_DATABASE_NAME:
        raise RuntimeError(
            "portal data commands only accept the isolated local database"
        )
    if "supabase" in value.lower():
        raise RuntimeError(
            "Supabase URLs are not accepted by local portal data commands"
        )
    return value
