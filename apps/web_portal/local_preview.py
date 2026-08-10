"""Fail-closed gates for the localhost production-shaped Portal preview."""

from __future__ import annotations

from urllib.parse import urlparse

PREVIEW_FLAG = "WEB_PORTAL_LOCAL_PREVIEW_MODE"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_local_preview_enabled(environ) -> bool:
    return (
        environ.get("WEB_PORTAL_ENV") == "development"
        and environ.get(PREVIEW_FLAG) == "true"
    )


def require_local_preview_startup(environ) -> bool:
    requested = environ.get(PREVIEW_FLAG)
    if requested is None:
        return False
    if requested != "true" or environ.get("WEB_PORTAL_ENV") != "development":
        raise RuntimeError("local preview requires exact development gates")
    if environ.get("WEB_PORTAL_DEMO_MODE") == "true":
        raise RuntimeError("local preview and demo mode are mutually exclusive")
    bind_host = (environ.get("WEB_PORTAL_BIND_HOST") or "127.0.0.1").lower()
    if bind_host not in LOOPBACK_HOSTS:
        raise RuntimeError("local preview must bind to a loopback host")
    from shared_module.portal_data.local_database import require_local_database_url

    safe_url = require_local_database_url(environ.get("PORTAL_DATA_DATABASE_URL"))
    parsed = urlparse(safe_url)
    dsn_host = (environ.get("DSN_HOSTNAME") or "").lower()
    if (
        dsn_host not in LOOPBACK_HOSTS
        or dsn_host != (parsed.hostname or "").lower()
        or environ.get("DSN_DATABASE") != "ntubtob_portal_local"
        or str(environ.get("DSN_PORT") or "") != str(parsed.port or 5432)
    ):
        raise RuntimeError("local preview database settings do not match")
    return True


def require_loopback_request(host: str) -> None:
    parsed = urlparse(f"//{host}")
    if (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
        raise RuntimeError("local preview request host must be loopback")
