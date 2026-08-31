"""Isolation cleanup for retained TASK-174 evidence in disposable test DBs."""

from sqlalchemy import inspect, text

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    LOCAL_HOSTS,
)


def remove_retained_apple_evidence_from_isolated_test_database(engine) -> None:
    """Remove only 0010 tables after a test deliberately downgrades Alembic."""

    if (
        engine.url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or (engine.url.host or "").lower() not in LOCAL_HOSTS
        or engine.url.database != LOCAL_DATABASE_NAME
    ):
        raise RuntimeError("Apple evidence cleanup requires the isolated test database")
    if inspect(engine).has_table("alembic_version", schema="ntubtob"):
        with engine.connect() as connection:
            current = connection.scalar(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )
        if current == "0010_apple_provider_lifecycle":
            return
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                DROP TABLE IF EXISTS
                  ntubtob.apple_provider_notifications,
                  ntubtob.apple_provider_credentials,
                  ntubtob.apple_provider_code_exchanges
                """
            )
        )
