"""Isolation cleanup for retained TASK-174 evidence in disposable test DBs."""

from sqlalchemy import inspect, text

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    LOCAL_HOSTS,
)

PRE_0010_CLEANUP_REVISIONS = frozenset(
    {
        "0001_legacy_baseline",
        "0003_legacy_bigint_activity_game",
        "0004_phase_c_identity_lifecycle",
    }
)


def remove_retained_apple_evidence_from_isolated_test_database(engine) -> None:
    """Remove only 0010 tables after a test deliberately downgrades Alembic."""

    if (
        engine.url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or (engine.url.host or "").lower() not in LOCAL_HOSTS
        or engine.url.database != LOCAL_DATABASE_NAME
    ):
        raise RuntimeError("Apple evidence cleanup requires the isolated test database")
    if not inspect(engine).has_table("alembic_version", schema="ntubtob"):
        return
    with engine.connect() as connection:
        current_rows = tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )
    if len(current_rows) != 1:
        raise RuntimeError("Apple evidence cleanup requires an exact known revision")
    current = current_rows[0]
    if current == "0010_apple_provider_lifecycle":
        return
    if current not in PRE_0010_CLEANUP_REVISIONS:
        raise RuntimeError("Apple evidence cleanup requires an exact known revision")
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
