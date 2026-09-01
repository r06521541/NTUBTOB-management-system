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
        end_at: datetime | None = None,
    ) -> int:
        return self.repository.create_event(
            actor_id, title, event_type, start_at, eligibility, end_at
        )

    def managed_events(self, actor_id: int) -> tuple[dict, ...]:
        return self.repository.managed_events(actor_id)

    def managed_event(self, actor_id: int, event_id: int) -> dict:
        return self.repository.managed_event(actor_id, event_id)

    def eligibility_preview(self, actor_id: int, event_id: int) -> dict:
        return self.repository.eligibility_preview(actor_id, event_id)

    def update_event(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        end_at: datetime | None,
        eligibility: Iterable[str],
        expected_version: int,
        request_id: str,
    ) -> dict:
        return self.repository.update_event(
            actor_id,
            event_id,
            title,
            event_type,
            start_at,
            end_at,
            eligibility,
            expected_version,
            request_id,
        )

    def add_activity(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str | None = None,
    ) -> int:
        return self.repository.add_activity(
            actor_id,
            event_id,
            title,
            activity_type,
            start_at,
            end_at,
            request_id,
        )

    def update_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str,
    ) -> None:
        self.repository.update_activity(
            actor_id,
            event_id,
            activity_id,
            title,
            activity_type,
            start_at,
            end_at,
            request_id,
        )

    def delete_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        request_id: str | None = None,
    ) -> None:
        self.repository.delete_activity(
            actor_id, event_id, activity_id, request_id=request_id
        )

    def move_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        direction: str,
        request_id: str | None = None,
    ) -> None:
        self.repository.move_activity(
            actor_id,
            event_id,
            activity_id,
            direction,
            request_id=request_id,
        )

    def set_invitee_override(
        self,
        actor_id: int,
        event_id: int,
        person_id: int,
        action: str,
        participation_category: str,
        reason: str,
        request_id: str,
    ) -> None:
        self.repository.set_invitee_override(
            actor_id,
            event_id,
            person_id,
            action,
            participation_category,
            reason,
            request_id,
        )

    def cancel_event(self, actor_id: int, event_id: int, request_id: str) -> dict:
        return self.repository.cancel_event(actor_id, event_id, request_id)

    def preview_event_notification(self, actor_id: int, event_id: int) -> dict:
        return self.repository.preview_event_notification(actor_id, event_id)

    def confirm_event_notification(
        self,
        actor_id: int,
        event_id: int,
        *,
        notification_type: str,
        preview_revision: str,
        typed_confirmation: str,
        request_id: str,
    ) -> dict:
        return self.repository.confirm_event_notification(
            actor_id,
            event_id,
            notification_type=notification_type,
            preview_revision=preview_revision,
            typed_confirmation=typed_confirmation,
            request_id=request_id,
        )

    def managed_guests(self, actor_id: int, state: str = "active") -> tuple[dict, ...]:
        return self.repository.managed_guests(actor_id, state)

    def guest_candidates(self, actor_id: int) -> tuple[dict, ...]:
        return self.repository.guest_candidates(actor_id)

    def mutate_guest_qualification(
        self,
        actor_id: int,
        target_person_id: int,
        action: str,
        *,
        expected_version: int,
        reason: str,
        request_id: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> dict:
        return self.repository.mutate_guest_qualification(
            actor_id,
            target_person_id,
            action,
            expected_version=expected_version,
            reason=reason,
            request_id=request_id,
            valid_from=valid_from,
            valid_until=valid_until,
        )
