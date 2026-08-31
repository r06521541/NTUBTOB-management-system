"""Safe database revision readiness checks for the mobile API runtime."""

import socket

from sqlalchemy import text

EXPECTED_REVISION = "0010_apple_provider_lifecycle"
ACCEPTED_REVISIONS = (EXPECTED_REVISION,)


def _safe_error_category(error: Exception) -> tuple[str, str]:
    original = getattr(error, "orig", error)
    detail = str(original).lower()
    categories = (
        ("authentication", ("password authentication failed", "no password supplied")),
        ("dns", ("could not translate host name", "name or service not known")),
        ("timeout", ("timeout expired", "connection timed out")),
        ("refused", ("connection refused",)),
        ("network", ("network is unreachable", "no route to host")),
        ("ssl", ("ssl", "certificate verify failed")),
    )
    category = next(
        (
            name
            for name, markers in categories
            if any(marker in detail for marker in markers)
        ),
        "operational",
    )
    sqlstate = getattr(original, "pgcode", None)
    if not isinstance(sqlstate, str) or len(sqlstate) != 5 or not sqlstate.isalnum():
        sqlstate = "none"
    return category, sqlstate


def _safe_network_probe(engine) -> str:
    host, port = engine.url.host, engine.url.port or 5432
    if not host:
        return "configuration"
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return "dns_failed"
    try:
        connection = socket.create_connection((host, port), timeout=2)
    except TimeoutError:
        return "tcp_timeout"
    except ConnectionRefusedError:
        return "tcp_refused"
    except OSError:
        return "tcp_failed"
    connection.close()
    return "tcp_ok"


def database_revision_is_current(engine, logger) -> bool:
    try:
        with engine.connect() as connection:
            current = connection.scalar(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )
            if type(current) is not str or current not in ACCEPTED_REVISIONS:
                logger.error("mobile_api_revision_check_mismatch")
                return False
            return True
    except Exception as error:
        # Driver exception text may contain connection details. Emit only the
        # bounded category and SQLSTATE so diagnostics cannot disclose credentials.
        category, sqlstate = _safe_error_category(error)
        network = _safe_network_probe(engine)
        logger.error(
            "mobile_api_revision_check_failed category=%s sqlstate=%s network=%s",
            category,
            sqlstate,
            network,
        )
        return False
