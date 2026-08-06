from __future__ import annotations

from .repository import InMemoryTeamPortalRepository


def build_fictional_repository() -> InMemoryTeamPortalRepository:
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
    )
    return repository
