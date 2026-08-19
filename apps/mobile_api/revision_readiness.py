"""Safe database revision readiness checks for the mobile API runtime."""

from sqlalchemy import text

EXPECTED_REVISION = "0005_mobile_auth_api_foundation"


def database_revision_is_current(engine, logger) -> bool:
    try:
        with engine.connect() as connection:
            current = connection.scalar(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )
            if current != EXPECTED_REVISION:
                logger.error("mobile_api_revision_check_mismatch")
                return False
            return True
    except Exception as error:
        # Driver exception text may contain connection details. Emit only the
        # exception class so staging diagnostics cannot disclose credentials.
        logger.error(
            "mobile_api_revision_check_failed error_type=%s",
            type(error).__name__,
        )
        return False
