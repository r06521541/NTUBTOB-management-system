from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import AuthIdentityRecord
from shared_lib.shared_module.portal_data.repository import PostgresTeamPortalRepository

FAKE_IDENTITIES = (
    ("fake-line-affiliate", "虛構親友丙", ("affiliate",)),
    ("fake-line-guest-player", "虛構客座球員丁", ("guest_player",)),
)


def seed_fake_data(engine: Engine) -> dict[str, int]:
    repository = PostgresTeamPortalRepository(engine)
    backfill = repository.backfill_members(fake_admin_member_ids=(7001,))

    with engine.connect() as connection:
        admin_person_id = connection.exec_driver_sql(
            "SELECT person_id FROM ntubtob.members WHERE id = 7001"
        ).scalar_one()

    created = 0
    reused = 0
    for subject, display_name, qualifications in FAKE_IDENTITIES:
        with Session(engine) as session:
            identity = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.provider == "line",
                    AuthIdentityRecord.provider_subject == subject,
                )
            )
            identity_id = identity.id if identity is not None else None
            identity_status = identity.status if identity is not None else None
        if identity_id is None:
            identity_id = repository.create_pending_identity("line", subject).id
            identity_status = "pending"
        if identity_status == "pending":
            repository.approve_identity(
                admin_person_id,
                identity_id,
                "建立 TASK-048 虛構 local fixture",
                f"seed-{subject}",
                display_name=display_name,
                qualifications=qualifications,
            )
            created += 1
        elif identity_status == "linked":
            reused += 1
        else:
            raise RuntimeError("fake seed identity is not pending or linked")

    return {
        "backfilled_members": backfill.scanned_members,
        "created_fake_people": created,
        "reused_fake_people": reused,
    }


def main() -> None:
    database_url = require_local_database_url(
        os.environ.get("PORTAL_DATA_DATABASE_URL")
    )
    engine = create_engine(database_url)
    try:
        summary = seed_fake_data(engine)
    finally:
        engine.dispose()
    print(
        "local fake seed ready: "
        f"members={summary['backfilled_members']} "
        f"created={summary['created_fake_people']} "
        f"reused={summary['reused_fake_people']}"
    )


if __name__ == "__main__":
    main()
