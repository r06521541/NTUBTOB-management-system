from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .domain import AuthIdentity, BackfillSummary, Invitee, Person
from .repository import TeamPortalRepository


class PortalDataService:
    """Application-facing domain boundary, deliberately independent of Flask."""

    def __init__(self, repository: TeamPortalRepository):
        self.repository = repository

    def approve_existing_person(
        self,
        actor_id: int,
        identity_id: int,
        person_id: int,
        reason: str,
        request_id: str,
    ) -> Person:
        return self.repository.approve_identity(
            actor_id,
            identity_id,
            reason,
            request_id,
            person_id=person_id,
        )

    def approve_new_non_member(
        self,
        actor_id: int,
        identity_id: int,
        display_name: str,
        qualifications: Iterable[str],
        reason: str,
        request_id: str,
    ) -> Person:
        return self.repository.approve_identity(
            actor_id,
            identity_id,
            reason,
            request_id,
            display_name=display_name,
            qualifications=qualifications,
        )

    def block_pending_identity(
        self, actor_id: int, identity_id: int, reason: str, request_id: str
    ) -> AuthIdentity:
        return self.repository.block_identity(actor_id, identity_id, reason, request_id)

    def publish_event(
        self, actor_id: int, event_id: int, request_id: str
    ) -> list[Invitee]:
        return self.repository.publish_event(actor_id, event_id, request_id)

    def rehearse_member_backfill(
        self, fake_admin_member_ids: Iterable[int] = ()
    ) -> BackfillSummary:
        return self.repository.backfill_members(fake_admin_member_ids)

    def create_event(
        self,
        actor_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        eligibility: Iterable[str],
    ) -> int:
        return self.repository.create_event(
            actor_id, title, event_type, start_at, eligibility
        )
