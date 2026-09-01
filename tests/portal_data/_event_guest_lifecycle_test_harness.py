"""Test-only rollback of retained TASK-175 evidence in disposable databases."""

from sqlalchemy import inspect, text

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    LOCAL_HOSTS,
)
from tests.portal_data._persistent_admin_authority_test_harness import (
    remove_retained_admin_authority_from_isolated_test_database,
)
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

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


def _require_isolated_test_database(engine) -> None:
    if (
        engine.url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or (engine.url.host or "").lower() not in LOCAL_HOSTS
        or engine.url.database != LOCAL_DATABASE_NAME
    ):
        raise RuntimeError(
            "Event lifecycle cleanup requires the isolated test database"
        )


def _revision_rows(engine) -> tuple[str, ...] | None:
    if not inspect(engine).has_table("alembic_version", schema="ntubtob"):
        return None
    with engine.connect() as connection:
        return tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )


def prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(
    engine,
) -> str | None:
    """Reverse 0011 only so an isolated test may exercise older migrations."""

    _require_isolated_test_database(engine)
    current_rows = _revision_rows(engine)
    if current_rows == ("0012_persistent_admin_authority",):
        remove_retained_admin_authority_from_isolated_test_database(engine)
        current_rows = _revision_rows(engine)
    if current_rows is None:
        return None
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


def reset_pre_0011_schema_for_isolated_test_database(
    engine, upgrade, *, target_revision: str
) -> str:
    """Rebuild a proven pre-0011 test schema at an allowlisted revision."""

    if target_revision not in PRE_0011_NOOP_REVISIONS:
        raise RuntimeError(
            "Event lifecycle reset requires a known pre-0011 target revision"
        )
    _require_isolated_test_database(engine)
    current_rows = _revision_rows(engine)
    if (
        current_rows is None
        or len(current_rows) != 1
        or current_rows[0] not in PRE_0011_NOOP_REVISIONS
    ):
        raise RuntimeError("Event lifecycle reset requires one known pre-0011 revision")
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        connection.execute(text(LEGACY_FIXTURE_SQL))
    upgrade(target_revision)
    return target_revision
