from __future__ import annotations

from datetime import timedelta

from .repository import InMemoryTeamPortalRepository, utc_now


def build_fictional_repository() -> InMemoryTeamPortalRepository:
    now = utc_now()
    repository = InMemoryTeamPortalRepository()
    repository.add_legacy_member(7001, "虛構校友甲")
    repository.add_legacy_member(7002, "虛構校友乙")
    repository.backfill_members(fake_admin_member_ids=(7001,))
    repository.create_person(
        "虛構親友丙",
        access_level="basic",
        qualifications=("affiliate",),
    )
    repository.create_person(
        "虛構客座球員丁",
        access_level="basic",
        qualifications=("guest_player",),
        guest_valid_from=now - timedelta(days=1),
        guest_valid_until=now + timedelta(days=365),
    )
    return repository
