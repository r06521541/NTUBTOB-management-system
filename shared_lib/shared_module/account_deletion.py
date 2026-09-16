"""An account deletion request is a durable intent, never deletion fulfillment."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from .mobile_api import InvalidArgument, MobileApiError, MobilePrincipal


class AccountDeletionUnavailable(MobileApiError):
    retryable = False

    def __init__(self):
        super().__init__("account deletion request service is unavailable")


@dataclass(frozen=True)
class AccountDeletionRequest:
    id: str
    requested_at: datetime

    def public(self) -> dict:
        return {
            "id": self.id,
            "status": "requested",
            "requested_at": self.requested_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }


class AccountDeletionStore(Protocol):
    def status(self, principal: MobilePrincipal) -> AccountDeletionRequest | None: ...

    def request(self, principal: MobilePrincipal) -> AccountDeletionRequest: ...


class AccountDeletionService:
    def __init__(self, repository: AccountDeletionStore):
        self.repository = repository

    def status(self, principal: MobilePrincipal) -> dict:
        record = self.repository.status(principal)
        return {"request": None if record is None else record.public()}

    def request(
        self, principal: MobilePrincipal, confirmed: object, idempotency_key: object
    ) -> dict:
        if confirmed is not True:
            raise InvalidArgument("explicit confirmation required")
        try:
            if (
                not isinstance(idempotency_key, str)
                or len(idempotency_key) != 36
                or str(UUID(idempotency_key)) != idempotency_key
            ):
                raise ValueError
        except (ValueError, AttributeError, TypeError):
            raise InvalidArgument("canonical UUID Idempotency-Key required") from None
        # The only valid command has a constant body. One durable request per
        # Person therefore deduplicates every key and every device, without
        # retaining keys or depending on short-lived session replay records.
        return {"request": self.repository.request(principal).public()}
