"""Officer publishing contracts with durable in-app history and inert delivery seams."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Callable

from .mobile_api import (
    IdempotencyConflict,
    InvalidArgument,
    MobilePrincipal,
    PermissionDenied,
    canonical_hash,
    mobile_capabilities,
    secret_hash,
    utc_now,
)

PUBLISH_CAPABILITY = "notifications:publish"
PUBLISH_TYPES = {
    "individual": "officer_personal",
    "game": "officer_game_broadcast",
    "team": "officer_team_broadcast",
}
MAX_RECIPIENTS = 500


class RejectingDeliveryAdapter:
    """The only runtime-safe provider seam until a later task provisions one."""

    def deliver(self, _delivery: dict) -> dict:
        return {
            "status": "failed",
            "error_code": "provider_not_configured",
            "retryable": True,
        }


class NotificationPublishingService:
    def __init__(self, repository, *, clock: Callable[[], datetime] = utc_now):
        self.repository, self.clock = repository, clock

    @staticmethod
    def _authorize(principal: MobilePrincipal) -> None:
        if PUBLISH_CAPABILITY not in mobile_capabilities(principal):
            raise PermissionDenied("notification publishing capability required")

    @staticmethod
    def _bounded_text(value, minimum: int, maximum: int, field: str) -> str:
        if not isinstance(value, str) or value != value.strip():
            raise InvalidArgument(f"{field} is malformed")
        if not minimum <= len(value) <= maximum or not value.isprintable():
            raise InvalidArgument(f"{field} is malformed")
        return value

    @staticmethod
    def _positive_identifier(value, prefix: str, field: str) -> int:
        if not isinstance(value, str) or not value.startswith(prefix):
            raise InvalidArgument(f"{field} is malformed")
        suffix = value[len(prefix) :]
        if not suffix.isascii() or not suffix.isdigit() or suffix.startswith("0"):
            raise InvalidArgument(f"{field} is malformed")
        parsed = int(suffix)
        if parsed > 9_223_372_036_854_775_807:
            raise InvalidArgument(f"{field} is malformed")
        return parsed

    @staticmethod
    def _game_identifier(value) -> int:
        if not isinstance(value, str) or not value.startswith("game_"):
            raise InvalidArgument("game_id is malformed")
        suffix = value[5:]
        try:
            parsed = int(suffix)
        except (TypeError, ValueError):
            raise InvalidArgument("game_id is malformed") from None
        if (
            parsed == 0
            or abs(parsed) > 9_223_372_036_854_775_807
            or str(parsed) != suffix
        ):
            raise InvalidArgument("game_id is malformed")
        return parsed

    @classmethod
    def _draft(cls, value: dict) -> dict:
        if not isinstance(value, dict) or set(value) != {
            "type",
            "title",
            "body",
            "audience",
            "destination",
        }:
            raise InvalidArgument("notification draft is malformed")
        audience = value["audience"]
        if not isinstance(audience, dict) or "type" not in audience:
            raise InvalidArgument("audience is malformed")
        audience_type = audience["type"]
        if audience_type not in PUBLISH_TYPES or value["type"] != PUBLISH_TYPES.get(
            audience_type
        ):
            raise InvalidArgument("notification type does not match audience")
        if audience_type == "individual":
            if set(audience) != {"type", "person_id"}:
                raise InvalidArgument("audience is malformed")
            normalized_audience = {
                "type": audience_type,
                "person_id": cls._positive_identifier(
                    audience["person_id"], "person_", "person_id"
                ),
            }
        elif audience_type == "game":
            if set(audience) != {"type", "game_id"}:
                raise InvalidArgument("audience is malformed")
            normalized_audience = {
                "type": audience_type,
                "game_id": cls._game_identifier(audience["game_id"]),
            }
        else:
            if set(audience) != {"type"}:
                raise InvalidArgument("audience is malformed")
            normalized_audience = {"type": audience_type}

        destination = value["destination"]
        if not isinstance(destination, dict) or destination.get("type") not in {
            "notification",
            "game",
        }:
            raise InvalidArgument("destination is malformed")
        if destination["type"] == "notification":
            if set(destination) != {"type"}:
                raise InvalidArgument("destination is malformed")
            normalized_destination = {"type": "notification"}
        else:
            if set(destination) != {"type", "game_id"}:
                raise InvalidArgument("destination is malformed")
            normalized_destination = {
                "type": "game",
                "game_id": cls._game_identifier(destination["game_id"]),
            }
            if audience_type == "game" and (
                normalized_destination["game_id"] != normalized_audience["game_id"]
            ):
                raise InvalidArgument("game destination does not match audience")

        return {
            "type": value["type"],
            "title": cls._bounded_text(value["title"], 1, 120, "title"),
            "body": cls._bounded_text(value["body"], 1, 500, "body"),
            "audience": normalized_audience,
            "destination": normalized_destination,
        }

    def _preview(self, principal: MobilePrincipal, draft: dict) -> tuple[dict, tuple[int, ...]]:
        self._authorize(principal)
        normalized = self._draft(draft)
        if (
            normalized["destination"]["type"] == "game"
            and not self.repository.notification_game_exists(
                normalized["destination"]["game_id"]
            )
        ):
            raise InvalidArgument("game destination is unavailable")
        recipients = tuple(
            sorted(set(self.repository.expand_notification_recipients(
                normalized["audience"], self.clock()
            )))
        )
        if not recipients or len(recipients) > MAX_RECIPIENTS or any(
            type(person_id) is not int or person_id <= 0 for person_id in recipients
        ):
            raise InvalidArgument("recipient expansion is empty or outside bounds")
        revision = canonical_hash(
            {"draft": normalized, "recipient_ids": recipients}
        )
        return (
            {
                "draft": normalized,
                "recipient_count": len(recipients),
                "revision": revision,
                "confirmation_text": f"PUBLISH {len(recipients)}",
            },
            recipients,
        )

    def preview(self, principal: MobilePrincipal, draft: dict) -> dict:
        preview, _recipients = self._preview(principal, draft)
        return preview

    def confirm(
        self,
        principal: MobilePrincipal,
        draft: dict,
        *,
        preview_revision: str,
        typed_confirmation: str,
        idempotency_key: str,
    ) -> dict:
        preview, recipients = self._preview(principal, draft)
        if not isinstance(preview_revision, str) or not hmac.compare_digest(
            preview_revision, preview["revision"]
        ):
            raise IdempotencyConflict("notification preview revision changed")
        if typed_confirmation != preview["confirmation_text"]:
            raise InvalidArgument("typed confirmation does not match preview")
        if not isinstance(idempotency_key, str) or not 16 <= len(idempotency_key) <= 200:
            raise InvalidArgument("Idempotency-Key required")
        now = self.clock()
        result = self.repository.commit_notification_publish(
            session_id=principal.session_id,
            actor_person_id=principal.person_id,
            key_hash=secret_hash(idempotency_key),
            request_hash=canonical_hash(
                {
                    "draft": preview["draft"],
                    "preview_revision": preview_revision,
                    "typed_confirmation": typed_confirmation,
                }
            ),
            draft=preview["draft"],
            preview_revision=preview_revision,
            recipient_ids=recipients,
            now=now,
        )
        return {
            **result,
            "notification_id": f"notification_{result['notification_id']}",
        }

    def register_device(
        self,
        principal: MobilePrincipal,
        *,
        installation_id: str,
        platform: str,
        provider: str,
        token: str,
    ) -> dict:
        if platform not in {"ios", "android"} or provider != "fake":
            raise InvalidArgument("fake device registration required")
        if (
            not isinstance(installation_id, str)
            or not 16 <= len(installation_id) <= 200
            or not isinstance(token, str)
            or not 32 <= len(token) <= 500
            or not token.startswith("fake-device-token-")
        ):
            raise InvalidArgument("fake device registration is malformed")
        result = self.repository.register_fake_device(
            person_id=principal.person_id,
            session_id=principal.session_id,
            installation_id_hash=secret_hash(installation_id),
            platform=platform,
            token_hash=secret_hash(token),
            now=self.clock(),
        )
        return {
            "registration_id": f"device_{result['registration_id']}",
            "status": result["status"],
        }

    def revoke_device(
        self, principal: MobilePrincipal, *, installation_id: str
    ) -> dict:
        if not isinstance(installation_id, str) or not 16 <= len(installation_id) <= 200:
            raise InvalidArgument("installation_id is malformed")
        changed = self.repository.revoke_fake_device(
            person_id=principal.person_id,
            session_id=principal.session_id,
            installation_id_hash=secret_hash(installation_id),
            now=self.clock(),
        )
        return {"status": "revoked", "changed": changed}

    def reject_delivery(self, delivery_id: int) -> dict:
        if type(delivery_id) is not int or delivery_id <= 0:
            raise InvalidArgument("delivery_id is malformed")
        return self.repository.attempt_rejecting_delivery(
            delivery_id=delivery_id,
            adapter=RejectingDeliveryAdapter(),
            now=self.clock(),
        )
