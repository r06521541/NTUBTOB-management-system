"""Test-only cleanup of retained TASK-176 evidence on the isolated database."""

from sqlalchemy import inspect, text

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    LOCAL_HOSTS,
)

PRE_0012_REVISIONS = frozenset(
    {
        "0001_legacy_baseline",
        "0002_portal_data_foundation",
        "0003_legacy_bigint_activity_game",
        "0004_phase_c_identity_lifecycle",
        "0005_mobile_auth_api_foundation",
        "0006_staging_broker_operation_journal",
        "0007_mobile_notifications",
        "0008_mobile_notification_delivery",
        "0009_event_management_writes",
        "0010_apple_provider_lifecycle",
        "0011_event_notification_guest_lifecycle",
    }
)


def remove_retained_admin_authority_from_isolated_test_database(engine) -> None:
    if (
        engine.url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or (engine.url.host or "").lower() not in LOCAL_HOSTS
        or engine.url.database != LOCAL_DATABASE_NAME
    ):
        raise RuntimeError(
            "Admin authority cleanup requires the isolated test database"
        )
    if not inspect(engine).has_table("alembic_version", schema="ntubtob"):
        return
    with engine.connect() as connection:
        revisions = tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )
    if len(revisions) != 1:
        raise RuntimeError("Admin authority cleanup requires one known revision")
    if revisions[0] in PRE_0012_REVISIONS:
        return
    if revisions[0] != "0012_persistent_admin_authority":
        raise RuntimeError("Admin authority cleanup rejects unknown/future revision")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE ntubtob.portal_authority_state"))
        connection.execute(
            text(
                "UPDATE ntubtob.alembic_version "
                "SET version_num = '0011_event_notification_guest_lifecycle' "
                "WHERE version_num = '0012_persistent_admin_authority'"
            )
        )
