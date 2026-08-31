"""Test-only rollback of retained TASK-175 evidence in disposable databases."""

from sqlalchemy import inspect, text

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    LOCAL_HOSTS,
)

PRE_0011_NOOP_REVISIONS = frozenset(
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
    }
)


def prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(
    engine,
) -> str | None:
    """Reverse 0011 only so an isolated test may exercise older migrations."""

    if (
        engine.url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or (engine.url.host or "").lower() not in LOCAL_HOSTS
        or engine.url.database != LOCAL_DATABASE_NAME
    ):
        raise RuntimeError(
            "Event lifecycle cleanup requires the isolated test database"
        )
    if not inspect(engine).has_table("alembic_version", schema="ntubtob"):
        return None
    with engine.connect() as connection:
        current_rows = tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )
    if len(current_rows) != 1:
        raise RuntimeError("Event lifecycle cleanup requires exact revision 0011")
    current = current_rows[0]
    if current in PRE_0011_NOOP_REVISIONS:
        return current
    if current != "0011_event_notification_guest_lifecycle":
        raise RuntimeError("Event lifecycle cleanup requires exact revision 0011")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                DROP TABLE
                  ntubtob.event_notification_publish_audits,
                  ntubtob.guest_qualification_audits;

                ALTER TABLE ntubtob.mobile_notification_recipients
                  DROP CONSTRAINT ck_mobile_notification_recipient_category,
                  DROP COLUMN participation_category;

                ALTER TABLE ntubtob.mobile_notifications
                  DROP CONSTRAINT ck_mobile_notification_destination,
                  DROP CONSTRAINT ck_mobile_notification_type,
                  ADD CONSTRAINT ck_mobile_notification_type CHECK (
                    notification_type IN (
                      'game_reminder', 'attendance_reminder', 'game_change',
                      'officer_personal', 'officer_game_broadcast',
                      'officer_team_broadcast', 'admin_system_announcement'
                    )
                  ),
                  ADD CONSTRAINT ck_mobile_notification_destination CHECK (
                    (destination_type = 'notification' AND
                      destination_game_id IS NULL) OR
                    (destination_type = 'game' AND
                      destination_game_id IS NOT NULL)
                  ),
                  DROP COLUMN destination_event_id;

                ALTER TABLE ntubtob.person_qualifications
                  DROP CONSTRAINT ck_person_qualification_version,
                  DROP COLUMN version;

                UPDATE ntubtob.alembic_version
                  SET version_num = '0010_apple_provider_lifecycle'
                  WHERE version_num = '0011_event_notification_guest_lifecycle';
                """
            )
        )
    return "0010_apple_provider_lifecycle"
