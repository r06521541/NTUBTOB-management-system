"""PostgreSQL transactions for native mobile sessions and exact replay."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

from shared_module.mobile_api import (
    AccountUnavailable,
    AuthenticationError,
    Conflict,
    IdempotencyConflict,
    IdentityPending,
    MobilePrincipal,
    TokenPair,
)
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .identity_lifecycle import IdentityLifecycleRepository
from .models import (
    AuthIdentityRecord,
    MobileAuthExchangeRecord,
    MobileIdempotencyRecord,
    MobileRefreshAttemptRecord,
    MobileRefreshTokenRecord,
    MobileSessionRecord,
)


class MobileRepository:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.lifecycle = IdentityLifecycleRepository(engine)

    def exchange(self, **values) -> MobilePrincipal:
        principal = self.lifecycle.resolve_principal(
            values["provider"], values["subject"], values["now"]
        )
        if principal is None:
            with Session(self.engine) as session:
                identity = session.scalar(
                    select(AuthIdentityRecord).where(
                        AuthIdentityRecord.provider == values["provider"],
                        AuthIdentityRecord.provider_subject == values["subject"],
                    )
                )
            if identity is not None and identity.status == "pending":
                raise IdentityPending("identity approval is pending")
            raise AccountUnavailable("linked active account is unavailable")
        now, session_id = values["now"], secrets.token_urlsafe(24)
        session_row = MobileSessionRecord(
            id=session_id,
            auth_identity_id=principal.identity.id,
            person_id=principal.person.id,
            installation_id_hash=values["installation_id_hash"],
            platform=values["platform"],
            status="active",
            access_epoch=1,
            refresh_family_expires_at=now + timedelta(days=30),
            created_at=now,
            updated_at=now,
        )
        try:
            with Session(self.engine) as session, session.begin():
                session.add(session_row)
                session.flush()
                session.add(
                    MobileRefreshTokenRecord(
                        session_id=session_id,
                        token_hash=values["refresh_hash"],
                        generation=1,
                        status="current",
                        issued_at=now,
                        expires_at=now + timedelta(days=30),
                    )
                )
                session.add(
                    MobileAuthExchangeRecord(
                        provider=values["provider"],
                        assertion_hash=values["assertion_hash"],
                        login_attempt_hash=values["login_attempt_hash"],
                        session_id=session_id,
                        expires_at=now + timedelta(minutes=10),
                        created_at=now,
                    )
                )
        except IntegrityError:
            raise Conflict(
                "provider assertion or login attempt was already used"
            ) from None
        return MobilePrincipal(
            session_id,
            principal.person.id,
            principal.identity.id,
            principal.person.access_level,
            principal.person.display_name,
            1,
        )

    def principal(
        self,
        session_id: str,
        person_id: int,
        identity_id: int,
        access_epoch: int,
        now: datetime,
    ) -> MobilePrincipal | None:
        with Session(self.engine) as session:
            row = session.get(MobileSessionRecord, session_id)
            if (
                row is None
                or row.status != "active"
                or row.person_id != person_id
                or row.auth_identity_id != identity_id
                or row.access_epoch != access_epoch
                or row.refresh_family_expires_at <= now
            ):
                return None
        lifecycle = (
            self.lifecycle.resolve_principal_by_ids(identity_id, person_id, now)
            if hasattr(self.lifecycle, "resolve_principal_by_ids")
            else None
        )
        if lifecycle is None:
            return None
        return MobilePrincipal(
            row.id,
            person_id,
            identity_id,
            lifecycle.person.access_level,
            lifecycle.person.display_name,
            row.access_epoch,
        )

    def rotate(self, **values) -> tuple[TokenPair, bool]:
        now = values["now"]
        conflict = None
        result = None
        with Session(self.engine) as session, session.begin():
            token = session.scalar(
                select(MobileRefreshTokenRecord)
                .where(MobileRefreshTokenRecord.token_hash == values["refresh_hash"])
                .with_for_update()
            )
            if token is None:
                raise AuthenticationError("invalid refresh token")
            device = session.scalar(
                select(MobileSessionRecord)
                .where(MobileSessionRecord.id == token.session_id)
                .with_for_update()
            )
            if (
                device is None
                or device.status != "active"
                or device.installation_id_hash != values["installation_id_hash"]
                or device.refresh_family_expires_at <= now
                or token.expires_at <= now
            ):
                raise AuthenticationError("inactive refresh family")
            attempt = session.scalar(
                select(MobileRefreshAttemptRecord)
                .where(
                    MobileRefreshAttemptRecord.session_id == device.id,
                    MobileRefreshAttemptRecord.attempt_id_hash
                    == values["attempt_id_hash"],
                )
                .with_for_update()
            )
            if attempt is not None:
                if (
                    attempt.request_hash != values["request_hash"]
                    or attempt.expires_at <= now
                ):
                    self._revoke_family(session, device, now)
                    conflict = "refresh attempt mismatch"
                else:
                    payload = json.loads(
                        values["cipher"].open(attempt.encrypted_successor)
                    )
                    result = TokenPair(**payload), True
            elif token.status != "current":
                self._revoke_family(session, device, now)
                conflict = "refresh token replay revoked the family"
            else:
                successor = MobileRefreshTokenRecord(
                    session_id=device.id,
                    token_hash=values["successor_hash"],
                    generation=token.generation + 1,
                    status="current",
                    issued_at=now,
                    expires_at=min(
                        device.refresh_family_expires_at, now + timedelta(days=30)
                    ),
                )
                session.add(successor)
                session.flush()
                token.status, token.successor_token_id, token.rotated_at = (
                    "rotated",
                    successor.id,
                    now,
                )
                session.add(
                    MobileRefreshAttemptRecord(
                        session_id=device.id,
                        attempt_id_hash=values["attempt_id_hash"],
                        request_hash=values["request_hash"],
                        encrypted_successor=b"pending",
                        expires_at=now + timedelta(minutes=5),
                        created_at=now,
                    )
                )
                device.updated_at = now
                principal = self._principal_from_device(device)
                access_token, expires_in = values["token_codec"].issue(principal, now)
                pair = TokenPair(
                    access_token,
                    values["successor"],
                    device.id,
                    expires_in,
                )
                attempt_row = session.scalar(
                    select(MobileRefreshAttemptRecord).where(
                        MobileRefreshAttemptRecord.session_id == device.id,
                        MobileRefreshAttemptRecord.attempt_id_hash
                        == values["attempt_id_hash"],
                    )
                )
                attempt_row.encrypted_successor = values["cipher"].seal(
                    json.dumps(pair.__dict__, sort_keys=True).encode("utf-8")
                )
                result = pair, False
        if conflict is not None:
            raise Conflict(conflict)
        assert result is not None
        return result

    def logout(self, session_id: str, now: datetime) -> None:
        with Session(self.engine) as session, session.begin():
            device = session.scalar(
                select(MobileSessionRecord)
                .where(MobileSessionRecord.id == session_id)
                .with_for_update()
            )
            if device is not None:
                self._revoke_family(session, device, now)

    def idempotent(self, **values) -> tuple[int, dict, bool]:
        try:
            with Session(self.engine) as session, session.begin():
                existing = session.scalar(
                    select(MobileIdempotencyRecord)
                    .where(
                        MobileIdempotencyRecord.session_id == values["session_id"],
                        MobileIdempotencyRecord.method == values["method"],
                        MobileIdempotencyRecord.route == values["route"],
                        MobileIdempotencyRecord.key_hash == values["key_hash"],
                    )
                    .with_for_update()
                )
                if existing is not None:
                    if existing.request_hash != values["request_hash"]:
                        raise IdempotencyConflict("idempotency key body mismatch")
                    if existing.state != "completed":
                        raise Conflict("request is in progress")
                    return existing.response_status, existing.response_body, True
                record = MobileIdempotencyRecord(
                    session_id=values["session_id"],
                    person_id=values["person_id"],
                    method=values["method"],
                    route=values["route"],
                    key_hash=values["key_hash"],
                    request_hash=values["request_hash"],
                    state="pending",
                    expires_at=values["now"] + timedelta(hours=24),
                    created_at=values["now"],
                    updated_at=values["now"],
                )
                session.add(record)
                session.flush()
                status, body = values["mutation"]()
                record.state, record.response_status, record.response_body = (
                    "completed",
                    status,
                    body,
                )
                return status, body, False
        except IntegrityError:
            with Session(self.engine) as session:
                existing = session.scalar(
                    select(MobileIdempotencyRecord).where(
                        MobileIdempotencyRecord.session_id == values["session_id"],
                        MobileIdempotencyRecord.method == values["method"],
                        MobileIdempotencyRecord.route == values["route"],
                        MobileIdempotencyRecord.key_hash == values["key_hash"],
                    )
                )
                if (
                    existing is not None
                    and existing.request_hash == values["request_hash"]
                    and existing.state == "completed"
                ):
                    return existing.response_status, existing.response_body, True
            raise IdempotencyConflict("concurrent idempotent request") from None

    @staticmethod
    def _principal_from_device(device: MobileSessionRecord) -> MobilePrincipal:
        # Refresh revalidates lifecycle when the access token is next used.
        return MobilePrincipal(
            device.id,
            device.person_id,
            device.auth_identity_id,
            "basic",
            "",
            device.access_epoch,
        )

    @staticmethod
    def _revoke_family(
        session: Session, device: MobileSessionRecord, now: datetime
    ) -> None:
        device.status, device.revoked_at, device.updated_at = "revoked", now, now
        session.execute(
            update(MobileRefreshTokenRecord)
            .where(
                MobileRefreshTokenRecord.session_id == device.id,
                MobileRefreshTokenRecord.status != "revoked",
            )
            .values(status="revoked", revoked_at=now)
        )
