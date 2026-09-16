"""Optional persistence for self-service deletion intents; no fulfillment path."""

from datetime import datetime
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..account_deletion import AccountDeletionRequest, AccountDeletionUnavailable
from ..mobile_api import (
    AccountUnavailable,
    AuthenticationError,
    MobilePrincipal,
    utc_now,
)
from .models import (
    AccountDeletionRequestRecord,
    AuthIdentityRecord,
    MobileSessionRecord,
    PersonRecord,
)
from .runtime import acquire_admin_event_locks


class AccountDeletionRepository:
    def __init__(self, engine: Engine, *, clock: Callable[[], datetime] = utc_now):
        self.engine, self.clock = engine, clock

    def status(self, principal: MobilePrincipal) -> AccountDeletionRequest | None:
        return self._current_request(principal, create=False)

    def request(self, principal: MobilePrincipal) -> AccountDeletionRequest:
        result = self._current_request(principal, create=True)
        assert result is not None
        return result

    def _current_request(
        self, principal: MobilePrincipal, *, create: bool
    ) -> AccountDeletionRequest | None:
        try:
            with Session(self.engine) as session, session.begin():
                # The canonical advisory locks precede rows, matching identity
                # status/admin/Apple writers despite their differing row order.
                acquire_admin_event_locks(session)
                now = self._lock_principal(session, principal)
                row = session.scalar(
                    select(AccountDeletionRequestRecord).where(
                        AccountDeletionRequestRecord.person_id == principal.person_id
                    )
                )
                if row is None and create:
                    row = AccountDeletionRequestRecord(
                        id=str(uuid4()),
                        person_id=principal.person_id,
                        status="requested",
                        requested_at=now,
                    )
                    session.add(row)
                    session.flush()
                result = (
                    None
                    if row is None
                    else AccountDeletionRequest(row.id, row.requested_at)
                )
            return result
        except SQLAlchemyError:
            # A commit response can be lost after persistence; callers reconcile
            # with GET. Never expose driver text or imply a POST can be retried.
            raise AccountDeletionUnavailable() from None

    def _lock_principal(self, session: Session, principal: MobilePrincipal) -> datetime:
        identity = session.scalar(
            select(AuthIdentityRecord)
            .where(AuthIdentityRecord.id == principal.identity_id)
            .with_for_update()
        )
        person = session.scalar(
            select(PersonRecord)
            .where(PersonRecord.id == principal.person_id)
            .with_for_update()
        )
        device = session.scalar(
            select(MobileSessionRecord)
            .where(MobileSessionRecord.id == principal.session_id)
            .with_for_update()
        )
        now = self.clock()
        if (
            identity is None
            or identity.status != "linked"
            or identity.person_id != principal.person_id
        ):
            raise AuthenticationError("current linked identity required")
        if person is None or person.portal_status != "active":
            raise AccountUnavailable("active account required")
        if (
            device is None
            or device.status != "active"
            or device.person_id != principal.person_id
            or device.auth_identity_id != principal.identity_id
            or device.access_epoch != principal.access_epoch
            or device.refresh_family_expires_at <= now
        ):
            raise AuthenticationError("current active session required")
        return now
