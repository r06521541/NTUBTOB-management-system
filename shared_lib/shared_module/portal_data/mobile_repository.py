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
from shared_module.identity_linking import (
    IdentityLinkConflict,
    IdentityLinkResult,
    InternalWebPrincipal,
)
from sqlalchemy import Engine, and_, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .identity_lifecycle import ADMIN_LOCK_KEY, IdentityLifecycleRepository
from .models import (
    AuthIdentityRecord,
    AccessAuditRecord,
    LegacyGameRecord,
    MobileAuthExchangeRecord,
    MobileDeviceRegistrationRecord,
    MobileIdempotencyRecord,
    MobileNotificationDeliveryRecord,
    MobileNotificationPublishAuditRecord,
    MobileNotificationRecipientRecord,
    MobileNotificationRecord,
    MobileRefreshAttemptRecord,
    MobileRefreshTokenRecord,
    MobileSessionRecord,
    LegacyLineUserRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
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
                raise IdentityPending("identity approval is pending", identity.id)
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

    def identity_link_candidate(self, provider: str, subject: str, now: datetime):
        with Session(self.engine) as session:
            row = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.provider == provider,
                    AuthIdentityRecord.provider_subject == subject,
                )
            )
            if row is None:
                return None
            return {
                "identity_id": row.id,
                "provider": row.provider,
                "status": row.status,
                "person_id": row.person_id,
                "updated_at": row.updated_at,
            }

    def ensure_google_link_candidate(
        self, subject: str, request_id: str, now: datetime
    ) -> dict:
        try:
            with Session(self.engine) as session, session.begin():
                row = session.scalar(
                    select(AuthIdentityRecord)
                    .where(
                        AuthIdentityRecord.provider == "google",
                        AuthIdentityRecord.provider_subject == subject,
                    )
                    .with_for_update()
                )
                if row is None:
                    row = AuthIdentityRecord(
                        provider="google",
                        provider_subject=subject,
                        person_id=None,
                        status="pending",
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    session.flush()
                    self.lifecycle._thread(session, row.id, now)
                    session.add(
                        AccessAuditRecord(
                            action="identity_pending",
                            actor_person_id=None,
                            target_person_id=None,
                            auth_identity_id=row.id,
                            before_state=None,
                            after_state={"status": "pending"},
                            reason="Google identity awaiting self-link confirmation",
                            request_id=request_id,
                            created_at=now,
                        )
                    )
                return {
                    "identity_id": row.id,
                    "provider": row.provider,
                    "status": row.status,
                    "person_id": row.person_id,
                    "updated_at": row.updated_at,
                }
        except IntegrityError:
            raise Conflict("identity-link candidate conflict") from None

    def ensure_line_link_candidate(
        self, subject: str, display_name: str, request_id: str, now: datetime
    ) -> dict:
        self.lifecycle.ensure_pending_line_identity(subject, display_name, request_id)
        snapshot = self.identity_link_candidate("line", subject, now)
        if snapshot is None:
            raise Conflict("LINE identity-link candidate is unavailable")
        return snapshot

    def linked_identity_for_proof(self, provider: str, subject: str, now: datetime):
        principal = self.lifecycle.resolve_principal(provider, subject, now)
        if principal is None:
            raise AuthenticationError("fresh linked identity required")
        return {
            "identity_id": principal.identity.id,
            "person_id": principal.person.id,
            "provider": principal.identity.provider,
            "updated_at": principal.identity.updated_at,
            "display_name": principal.person.display_name,
        }

    def linked_identity_labels(self, person_id: int) -> tuple[dict, ...]:
        with Session(self.engine) as session:
            identities = session.scalars(
                select(AuthIdentityRecord)
                .where(
                    AuthIdentityRecord.person_id == person_id,
                    AuthIdentityRecord.status == "linked",
                    AuthIdentityRecord.provider.in_(("line", "google")),
                )
                .order_by(AuthIdentityRecord.provider)
            ).all()
            return tuple(
                {
                    "provider": row.provider,
                    "label": "LINE" if row.provider == "line" else "Google",
                    "linked_at": session.scalar(
                        select(func.max(AccessAuditRecord.created_at)).where(
                            AccessAuditRecord.auth_identity_id == row.id,
                            AccessAuditRecord.action == "identity_linked",
                        )
                    )
                    or row.updated_at,
                }
                for row in identities
            )

    def confirm_identity_link(self, **values) -> dict:
        candidate, proof, codec = values["candidate"], values["proof"], values["codec"]
        now = values["now"]
        request_id = codec.audit_request_id(candidate.jti)
        with Session(self.engine) as session, session.begin():
            # Identity lifecycle admin mutations acquire this advisory lock,
            # then the target Person, then identity rows. Linking must use the
            # same global order to avoid Person/identity lock inversion.
            proof_snapshot = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.id == proof.identity_id
                )
            )
            if (
                proof_snapshot is None
                or proof_snapshot.person_id is None
                or proof_snapshot.person_id != proof.person_id
            ):
                raise IdentityLinkConflict("identity-link state changed")
            lock_boundary = values.get("lock_boundary")
            if lock_boundary is not None:
                lock_boundary()
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": ADMIN_LOCK_KEY},
            )
            person = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == proof.person_id)
                .with_for_update()
            )
            rows = session.scalars(
                select(AuthIdentityRecord)
                .where(
                    AuthIdentityRecord.id.in_(
                        sorted((candidate.identity_id, proof.identity_id))
                    )
                )
                .order_by(AuthIdentityRecord.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).all()
            by_id = {row.id: row for row in rows}
            candidate_row, proof_row = by_id.get(candidate.identity_id), by_id.get(
                proof.identity_id
            )
            audit = session.scalar(
                select(AccessAuditRecord).where(
                    AccessAuditRecord.request_id == request_id
                )
            )
            expected_after = {
                "status": "linked",
                "source_provider": proof.provider,
                "target_provider": candidate.provider,
                "outcome": values["outcome"],
            }
            if candidate_row is not None and candidate_row.status == "linked":
                if (
                    candidate_row.person_id == proof.person_id
                    and proof_row is not None
                    and proof_row.status == "linked"
                    and proof_row.person_id == proof.person_id
                    and proof_row.provider == proof.provider
                    and codec.identity_version_hash(proof_row.id, proof_row.updated_at)
                    == proof.version_hash
                    and audit is not None
                    and audit.action == "identity_linked"
                    and audit.auth_identity_id == candidate.identity_id
                    and audit.target_person_id == proof.person_id
                    and audit.before_state == {"status": "pending"}
                    and audit.after_state == expected_after
                ):
                    return IdentityLinkResult(
                        "already_linked",
                        web_principal=(
                            self._web_principal(session, proof_row)
                            if values["session_mode"] == "web"
                            else None
                        ),
                    )
                raise IdentityLinkConflict("identity is already linked")
            if (
                candidate_row is None
                or candidate_row.status != "pending"
                or candidate_row.person_id is not None
                or candidate_row.provider != candidate.provider
                or codec.identity_version_hash(
                    candidate_row.id, candidate_row.updated_at
                )
                != candidate.version_hash
                or proof_row is None
                or proof_row.status != "linked"
                or proof_row.person_id != proof.person_id
                or proof_row.provider != proof.provider
                or codec.identity_version_hash(proof_row.id, proof_row.updated_at)
                != proof.version_hash
                or audit is not None
            ):
                raise IdentityLinkConflict("identity-link state changed")
            if person is None or person.portal_status != "active":
                raise IdentityLinkConflict("active target Person required")
            if values.get("current_person_id") not in {None, person.id}:
                raise IdentityLinkConflict(
                    "current session Person does not match proof"
                )
            if candidate_row.provider == "line":
                legacy = session.scalar(
                    select(LegacyLineUserRecord)
                    .where(
                        LegacyLineUserRecord.line_user_id
                        == candidate_row.provider_subject
                    )
                    .with_for_update()
                )
                if legacy is None or legacy.ignored or legacy.member_id is not None:
                    raise IdentityLinkConflict("eligible LINE candidate required")
                member = session.scalar(
                    select(LegacyMemberRecord).where(
                        LegacyMemberRecord.person_id == person.id
                    )
                )
                if member is not None:
                    legacy.member_id = member.id
            candidate_row.person_id = person.id
            candidate_row.status = "linked"
            candidate_row.updated_at = now
            thread = self.lifecycle._thread(session, candidate_row.id, now)
            thread.status = "closed"
            thread.closed_at = now
            thread.last_activity_at = now
            thread.updated_at = now
            session.add(
                AccessAuditRecord(
                    action="identity_linked",
                    actor_person_id=person.id,
                    target_person_id=person.id,
                    auth_identity_id=candidate_row.id,
                    before_state={"status": "pending"},
                    after_state=expected_after,
                    reason="Self-service cross-provider identity link",
                    request_id=request_id,
                    created_at=now,
                )
            )
            pair = None
            recovery = values.get("recovery")
            if recovery is not None:
                session_id = secrets.token_urlsafe(24)
                session.add(
                    MobileSessionRecord(
                        id=session_id,
                        auth_identity_id=proof_row.id,
                        person_id=person.id,
                        installation_id_hash=recovery["installation_id_hash"],
                        platform=recovery["platform"],
                        status="active",
                        access_epoch=1,
                        refresh_family_expires_at=now + timedelta(days=30),
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.flush()
                session.add(
                    MobileRefreshTokenRecord(
                        session_id=session_id,
                        token_hash=recovery["refresh_hash"],
                        generation=1,
                        status="current",
                        issued_at=now,
                        expires_at=now + timedelta(days=30),
                    )
                )
                session.add(
                    MobileAuthExchangeRecord(
                        provider=candidate.provider,
                        assertion_hash=candidate.assertion_hash,
                        login_attempt_hash=candidate.attempt_hash,
                        session_id=session_id,
                        expires_at=now + timedelta(minutes=10),
                        created_at=now,
                    )
                )
                principal = MobilePrincipal(
                    session_id,
                    person.id,
                    proof_row.id,
                    person.portal_access_level,
                    person.display_name,
                    1,
                )
                access, expires = recovery["token_codec"].issue(principal, now)
                pair = TokenPair(
                    access, recovery["refresh"], session_id, expires
                ).__dict__
            return IdentityLinkResult(
                "linked",
                mobile_session=pair,
                web_principal=(
                    self._web_principal(session, proof_row)
                    if values["session_mode"] == "web"
                    else None
                ),
            )

    @staticmethod
    def _web_principal(
        session: Session, identity: AuthIdentityRecord
    ) -> InternalWebPrincipal:
        member_id = session.scalar(
            select(LegacyMemberRecord.id).where(
                LegacyMemberRecord.person_id == identity.person_id
            )
        )
        return InternalWebPrincipal(identity.person_id, identity.id, member_id)

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

    @staticmethod
    def _notification_row(notification, read_at, cursor_created_at) -> dict:
        return {
            "id": notification.id,
            "type": notification.notification_type,
            "title": notification.title,
            "body": notification.body,
            "created_at": notification.created_at,
            "visible_until": notification.visible_until,
            "read_at": read_at,
            "destination_type": notification.destination_type,
            "destination_game_id": notification.destination_game_id,
            "_cursor_created_at": cursor_created_at,
        }

    @staticmethod
    def _visible_notification(now: datetime):
        return and_(
            MobileNotificationRecord.created_at <= now,
            MobileNotificationRecord.visible_until > now,
        )

    def notification_page(
        self,
        person_id: int,
        now: datetime,
        cursor: tuple[datetime, int] | None,
        limit: int,
        unread_only: bool,
    ) -> list[dict]:
        statement = (
            select(
                MobileNotificationRecord,
                MobileNotificationRecipientRecord.read_at,
                MobileNotificationRecord.created_at,
            )
            .join(
                MobileNotificationRecipientRecord,
                MobileNotificationRecipientRecord.notification_id
                == MobileNotificationRecord.id,
            )
            .where(
                MobileNotificationRecipientRecord.person_id == person_id,
                MobileNotificationRecipientRecord.created_at <= now,
                self._visible_notification(now),
            )
            .order_by(
                MobileNotificationRecord.created_at.desc(),
                MobileNotificationRecord.id.desc(),
            )
            .limit(limit)
        )
        if unread_only:
            statement = statement.where(
                MobileNotificationRecipientRecord.read_at.is_(None)
            )
        if cursor is not None:
            created_at, notification_id = cursor
            statement = statement.where(
                or_(
                    MobileNotificationRecord.created_at < created_at,
                    and_(
                        MobileNotificationRecord.created_at == created_at,
                        MobileNotificationRecord.id < notification_id,
                    ),
                )
            )
        with Session(self.engine) as session:
            rows = session.execute(statement).all()
        return [self._notification_row(*row) for row in rows]

    def notification_detail(
        self, person_id: int, notification_id: int, now: datetime
    ) -> dict | None:
        statement = (
            select(
                MobileNotificationRecord,
                MobileNotificationRecipientRecord.read_at,
                MobileNotificationRecord.created_at,
            )
            .join(
                MobileNotificationRecipientRecord,
                MobileNotificationRecipientRecord.notification_id
                == MobileNotificationRecord.id,
            )
            .where(
                MobileNotificationRecord.id == notification_id,
                MobileNotificationRecipientRecord.person_id == person_id,
                MobileNotificationRecipientRecord.created_at <= now,
                self._visible_notification(now),
            )
        )
        with Session(self.engine) as session:
            row = session.execute(statement).one_or_none()
        return None if row is None else self._notification_row(*row)

    def notification_unread_count(self, person_id: int, now: datetime) -> int:
        statement = (
            select(func.count())
            .select_from(MobileNotificationRecipientRecord)
            .join(
                MobileNotificationRecord,
                MobileNotificationRecord.id
                == MobileNotificationRecipientRecord.notification_id,
            )
            .where(
                MobileNotificationRecipientRecord.person_id == person_id,
                MobileNotificationRecipientRecord.read_at.is_(None),
                MobileNotificationRecipientRecord.created_at <= now,
                self._visible_notification(now),
            )
        )
        with Session(self.engine) as session:
            return int(session.scalar(statement) or 0)

    def mark_notification_read(
        self, person_id: int, notification_id: int, now: datetime
    ) -> tuple[datetime, bool] | None:
        visible_ids = select(MobileNotificationRecord.id).where(
            MobileNotificationRecord.id == notification_id,
            self._visible_notification(now),
        )
        with Session(self.engine) as session, session.begin():
            read_at = session.scalar(
                update(MobileNotificationRecipientRecord)
                .where(
                    MobileNotificationRecipientRecord.person_id == person_id,
                    MobileNotificationRecipientRecord.notification_id.in_(visible_ids),
                    MobileNotificationRecipientRecord.created_at <= now,
                    MobileNotificationRecipientRecord.read_at.is_(None),
                )
                .values(read_at=now)
                .returning(MobileNotificationRecipientRecord.read_at)
            )
            if read_at is not None:
                return read_at, True
            existing = session.scalar(
                select(MobileNotificationRecipientRecord.read_at).where(
                    MobileNotificationRecipientRecord.person_id == person_id,
                    MobileNotificationRecipientRecord.notification_id.in_(visible_ids),
                    MobileNotificationRecipientRecord.created_at <= now,
                )
            )
            return None if existing is None else (existing, False)

    def mark_all_notifications_read(
        self, person_id: int, now: datetime
    ) -> tuple[int, int]:
        visible_ids = select(MobileNotificationRecord.id).where(
            self._visible_notification(now)
        )
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(MobileNotificationRecipientRecord)
                .where(
                    MobileNotificationRecipientRecord.person_id == person_id,
                    MobileNotificationRecipientRecord.notification_id.in_(visible_ids),
                    MobileNotificationRecipientRecord.created_at <= now,
                    MobileNotificationRecipientRecord.read_at.is_(None),
                )
                .values(read_at=now)
            )
            unread = session.scalar(
                select(func.count())
                .select_from(MobileNotificationRecipientRecord)
                .join(
                    MobileNotificationRecord,
                    MobileNotificationRecord.id
                    == MobileNotificationRecipientRecord.notification_id,
                )
                .where(
                    MobileNotificationRecipientRecord.person_id == person_id,
                    MobileNotificationRecipientRecord.read_at.is_(None),
                    MobileNotificationRecipientRecord.created_at <= now,
                    self._visible_notification(now),
                )
            )
            return result.rowcount, int(unread or 0)

    @staticmethod
    def _active_team_recipient_ids(session: Session, now: datetime) -> tuple[int, ...]:
        return tuple(
            session.scalars(
                select(PersonRecord.id)
                .join(
                    PersonQualificationRecord,
                    PersonQualificationRecord.person_id == PersonRecord.id,
                )
                .where(
                    PersonRecord.portal_status == "active",
                    PersonQualificationRecord.qualification == "team_player",
                    PersonQualificationRecord.status == "active",
                    or_(
                        PersonQualificationRecord.valid_from.is_(None),
                        PersonQualificationRecord.valid_from <= now,
                    ),
                    or_(
                        PersonQualificationRecord.valid_until.is_(None),
                        PersonQualificationRecord.valid_until > now,
                    ),
                )
                .order_by(PersonRecord.id)
            )
        )

    @classmethod
    def _expand_notification_recipients(
        cls, session: Session, audience: dict, now: datetime
    ) -> tuple[int, ...]:
        if audience["type"] == "individual":
            person_id = session.scalar(
                select(PersonRecord.id).where(
                    PersonRecord.id == audience["person_id"],
                    PersonRecord.portal_status == "active",
                )
            )
            return () if person_id is None else (person_id,)
        if (
            audience["type"] == "game"
            and session.get(LegacyGameRecord, audience["game_id"]) is None
        ):
            return ()
        return cls._active_team_recipient_ids(session, now)

    def expand_notification_recipients(
        self, audience: dict, now: datetime
    ) -> tuple[int, ...]:
        with Session(self.engine) as session:
            return self._expand_notification_recipients(session, audience, now)

    def notification_game_exists(self, game_id: int) -> bool:
        with Session(self.engine) as session:
            return session.get(LegacyGameRecord, game_id) is not None

    def commit_notification_publish(self, **values) -> dict:
        route = "/api/v1/officer/notifications/confirm"
        try:
            with Session(self.engine) as session, session.begin():
                existing = session.scalar(
                    select(MobileIdempotencyRecord)
                    .where(
                        MobileIdempotencyRecord.session_id == values["session_id"],
                        MobileIdempotencyRecord.method == "POST",
                        MobileIdempotencyRecord.route == route,
                        MobileIdempotencyRecord.key_hash == values["key_hash"],
                    )
                    .with_for_update()
                )
                if existing is not None:
                    return self._published_replay(existing, values["request_hash"])

                draft, now = values["draft"], values["now"]
                current_recipients = self._expand_notification_recipients(
                    session, draft["audience"], now
                )
                if current_recipients != values["recipient_ids"]:
                    raise IdempotencyConflict("notification preview revision changed")
                destination = draft["destination"]
                notification = MobileNotificationRecord(
                    notification_type=draft["type"],
                    title=draft["title"],
                    body=draft["body"],
                    destination_type=destination["type"],
                    destination_game_id=destination.get("game_id"),
                    created_at=now,
                    visible_until=now + timedelta(days=90),
                )
                session.add(notification)
                session.flush()
                session.add_all(
                    MobileNotificationRecipientRecord(
                        notification_id=notification.id,
                        person_id=person_id,
                        created_at=now,
                    )
                    for person_id in values["recipient_ids"]
                )
                audience = draft["audience"]
                session.add(
                    MobileNotificationPublishAuditRecord(
                        notification_id=notification.id,
                        actor_person_id=values["actor_person_id"],
                        audience_type=audience["type"],
                        audience_reference_id=audience.get(
                            "person_id", audience.get("game_id")
                        ),
                        preview_revision=values["preview_revision"],
                        recipient_count=len(values["recipient_ids"]),
                        request_hash=values["request_hash"],
                        created_at=now,
                    )
                )
                deliveries = (
                    {
                        "channel": "in_app",
                        "status": "succeeded",
                        "retryable": False,
                    },
                    {"channel": "push", "status": "pending", "retryable": True},
                )
                session.add_all(
                    MobileNotificationDeliveryRecord(
                        notification_id=notification.id,
                        channel=delivery["channel"],
                        status=delivery["status"],
                        attempt_count=0,
                        retryable=delivery["retryable"],
                        created_at=now,
                        updated_at=now,
                    )
                    for delivery in deliveries
                )
                response = {
                    "notification_id": notification.id,
                    "recipient_count": len(values["recipient_ids"]),
                    "deliveries": list(deliveries),
                    "idempotent_replay": False,
                }
                session.add(
                    MobileIdempotencyRecord(
                        session_id=values["session_id"],
                        person_id=values["actor_person_id"],
                        method="POST",
                        route=route,
                        key_hash=values["key_hash"],
                        request_hash=values["request_hash"],
                        state="completed",
                        response_status=201,
                        response_body=response,
                        expires_at=now + timedelta(hours=24),
                        created_at=now,
                        updated_at=now,
                    )
                )
                return response
        except IntegrityError:
            with Session(self.engine) as session:
                existing = session.scalar(
                    select(MobileIdempotencyRecord).where(
                        MobileIdempotencyRecord.session_id == values["session_id"],
                        MobileIdempotencyRecord.method == "POST",
                        MobileIdempotencyRecord.route == route,
                        MobileIdempotencyRecord.key_hash == values["key_hash"],
                    )
                )
                if existing is None:
                    raise
                return self._published_replay(existing, values["request_hash"])

    @staticmethod
    def _published_replay(record, request_hash: str) -> dict:
        if record.request_hash != request_hash or record.state != "completed":
            raise IdempotencyConflict("idempotency key body mismatch")
        return {**record.response_body, "idempotent_replay": True}

    @staticmethod
    def _lock_current_device_session(
        session: Session, values: dict, *, verify_platform: bool
    ) -> MobileSessionRecord:
        device = session.scalar(
            select(MobileSessionRecord)
            .where(MobileSessionRecord.id == values["session_id"])
            .with_for_update()
        )
        if (
            device is None
            or device.status != "active"
            or device.person_id != values["person_id"]
            or device.installation_id_hash != values["installation_id_hash"]
            or device.refresh_family_expires_at <= values["now"]
            or (verify_platform and device.platform != values["platform"])
        ):
            raise Conflict("device registration is unavailable")
        return device

    def register_fake_device(self, **values) -> dict:
        try:
            with Session(self.engine) as session, session.begin():
                self._lock_current_device_session(session, values, verify_platform=True)
                registration = session.scalar(
                    select(MobileDeviceRegistrationRecord)
                    .where(
                        MobileDeviceRegistrationRecord.person_id == values["person_id"],
                        MobileDeviceRegistrationRecord.installation_id_hash
                        == values["installation_id_hash"],
                    )
                    .with_for_update()
                )
                token_owner = session.scalar(
                    select(MobileDeviceRegistrationRecord)
                    .where(
                        MobileDeviceRegistrationRecord.provider == "fake",
                        MobileDeviceRegistrationRecord.token_hash
                        == values["token_hash"],
                        MobileDeviceRegistrationRecord.status == "active",
                    )
                    .with_for_update()
                )
                if token_owner is not None and token_owner is not registration:
                    raise Conflict("device registration is unavailable")
                if registration is None:
                    registration = MobileDeviceRegistrationRecord(
                        person_id=values["person_id"],
                        session_id=values["session_id"],
                        installation_id_hash=values["installation_id_hash"],
                        platform=values["platform"],
                        provider="fake",
                        token_hash=values["token_hash"],
                        status="active",
                        created_at=values["now"],
                        updated_at=values["now"],
                    )
                    session.add(registration)
                else:
                    registration.session_id = values["session_id"]
                    registration.platform = values["platform"]
                    registration.token_hash = values["token_hash"]
                    registration.status = "active"
                    registration.revoked_at = None
                    registration.updated_at = values["now"]
                session.flush()
                return {
                    "registration_id": registration.id,
                    "status": registration.status,
                }
        except IntegrityError:
            raise Conflict("device registration is unavailable") from None

    def revoke_fake_device(self, **values) -> bool:
        with Session(self.engine) as session, session.begin():
            self._lock_current_device_session(session, values, verify_platform=False)
            registration = session.scalar(
                select(MobileDeviceRegistrationRecord)
                .where(
                    MobileDeviceRegistrationRecord.person_id == values["person_id"],
                    MobileDeviceRegistrationRecord.session_id == values["session_id"],
                    MobileDeviceRegistrationRecord.installation_id_hash
                    == values["installation_id_hash"],
                )
                .with_for_update()
            )
            if registration is None or registration.status == "revoked":
                return False
            registration.status = "revoked"
            registration.revoked_at = values["now"]
            registration.updated_at = values["now"]
            return True

    def attempt_rejecting_delivery(self, **values) -> dict:
        with Session(self.engine) as session, session.begin():
            delivery = session.scalar(
                select(MobileNotificationDeliveryRecord)
                .where(
                    MobileNotificationDeliveryRecord.id == values["delivery_id"],
                    MobileNotificationDeliveryRecord.channel == "push",
                    MobileNotificationDeliveryRecord.retryable.is_(True),
                )
                .with_for_update()
            )
            if delivery is None:
                raise Conflict("retryable push delivery is unavailable")
            outcome = values["adapter"].deliver({"delivery_id": delivery.id})
            if outcome != {
                "status": "failed",
                "error_code": "provider_not_configured",
                "retryable": True,
            }:
                raise Conflict("rejecting provider returned an invalid result")
            delivery.status = outcome["status"]
            delivery.error_code = outcome["error_code"]
            delivery.retryable = outcome["retryable"]
            delivery.attempt_count += 1
            delivery.updated_at = values["now"]
            return {
                "delivery_id": delivery.id,
                "channel": delivery.channel,
                **outcome,
                "attempt_count": delivery.attempt_count,
            }

    def idempotent(self, **values) -> tuple[int, dict, bool]:
        """Claim durably, serialize execution, and reconcile a saved mutation.

        The claim commits before the independently committing attendance service
        runs.  A retry of a pending claim first reads the authoritative state;
        it never repeats a mutation whose requested state is already visible.
        """
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
                    if existing.state == "completed":
                        return existing.response_status, existing.response_body, True
                else:
                    session.add(
                        MobileIdempotencyRecord(
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
                    )
        except IntegrityError:
            pass

        mutation_result = None
        mutation_started = False
        try:
            with Session(self.engine) as session, session.begin():
                record = self._locked_idempotency(session, values)
                if record.state == "completed":
                    return record.response_status, record.response_body, True
                reconciled = values.get("reconcile", lambda: None)()
                replayed = reconciled is not None
                if reconciled is not None:
                    mutation_result = reconciled
                else:
                    mutation_started = True
                    mutation_result = values["mutation"]()
                self._complete_idempotency(record, mutation_result, values["now"])
            return mutation_result[0], mutation_result[1], replayed
        except Exception:
            if not mutation_started:
                raise
            # The attendance transaction may already have committed.  Prove the
            # requested readback before returning instead of reporting failure.
            with Session(self.engine) as session, session.begin():
                record = self._locked_idempotency(session, values)
                if record.state == "completed":
                    return record.response_status, record.response_body, True
                reconciled = values.get("reconcile", lambda: None)()
                if reconciled is None:
                    raise
                recovered = mutation_result or reconciled
                self._complete_idempotency(record, recovered, values["now"])
                return recovered[0], recovered[1], True

    @staticmethod
    def _locked_idempotency(session: Session, values) -> MobileIdempotencyRecord:
        record = session.scalar(
            select(MobileIdempotencyRecord)
            .where(
                MobileIdempotencyRecord.session_id == values["session_id"],
                MobileIdempotencyRecord.method == values["method"],
                MobileIdempotencyRecord.route == values["route"],
                MobileIdempotencyRecord.key_hash == values["key_hash"],
            )
            .with_for_update()
        )
        if record is None or record.request_hash != values["request_hash"]:
            raise IdempotencyConflict("idempotency key body mismatch")
        return record

    @staticmethod
    def _complete_idempotency(record, result, now) -> None:
        record.state = "completed"
        record.response_status, record.response_body = result
        record.updated_at = now

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
        session.execute(
            update(MobileDeviceRegistrationRecord)
            .where(
                MobileDeviceRegistrationRecord.session_id == device.id,
                MobileDeviceRegistrationRecord.status == "active",
            )
            .values(status="revoked", revoked_at=now, updated_at=now)
        )
