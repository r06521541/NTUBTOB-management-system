from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "ntubtob"


class PortalDataBase(DeclarativeBase):
    pass


class PersonRecord(PortalDataBase):
    __tablename__ = "people"
    __table_args__ = (
        CheckConstraint(
            "portal_access_level IN ('basic', 'officer', 'admin')",
            name="ck_people_access_level",
        ),
        CheckConstraint(
            "portal_status IN ('pending', 'active', 'disabled', 'inactive', 'blocked')",
            name="ck_people_status",
        ),
        CheckConstraint(
            "formal_name IS NULL OR length(btrim(formal_name)) BETWEEN 1 AND 120",
            name="ck_people_formal_name",
        ),
        CheckConstraint(
            "admin_note IS NULL OR length(btrim(admin_note)) BETWEEN 1 AND 1000",
            name="ck_people_admin_note",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    formal_name: Mapped[Optional[str]] = mapped_column(String(120))
    admin_note: Mapped[Optional[str]] = mapped_column(String(1000))
    portal_access_level: Mapped[str] = mapped_column(String(20), nullable=False)
    portal_status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class LegacyMemberRecord(PortalDataBase):
    __tablename__ = "members"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    enroll_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    major: Mapped[Optional[str]] = mapped_column(String)
    number: Mapped[Optional[int]] = mapped_column(SmallInteger)
    positions: Mapped[Optional[str]] = mapped_column(String)
    person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )


class LegacyGameRecord(PortalDataBase):
    __tablename__ = "games"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    season: Mapped[Optional[int]] = mapped_column(SmallInteger)
    start_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration: Mapped[Optional[int]] = mapped_column(SmallInteger)
    location: Mapped[Optional[str]] = mapped_column(String)
    home_team: Mapped[Optional[str]] = mapped_column(String)
    away_team: Mapped[Optional[str]] = mapped_column(String)
    invitation_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    cancellation_announcement_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )


class LegacyLineUserRecord(PortalDataBase):
    __tablename__ = "line_users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nickname: Mapped[str] = mapped_column(String, nullable=False)
    line_user_id: Mapped[str] = mapped_column(String, nullable=False)
    member_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.members.id")
    )
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    has_replied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False)


class LegacyAttendanceReplyTypeRecord(PortalDataBase):
    __tablename__ = "attendance_reply_types"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    description: Mapped[str] = mapped_column(String, nullable=False)


class LegacyGameAttendanceReplyRecord(PortalDataBase):
    __tablename__ = "game_attendance_replies"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.games.id"), nullable=False
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.line_users.id")
    )
    member_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.members.id")
    )
    person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    reply: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey(f"{SCHEMA}.attendance_reply_types.id"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_game_attendance_person_game_updated",
    LegacyGameAttendanceReplyRecord.person_id,
    LegacyGameAttendanceReplyRecord.game_id,
    LegacyGameAttendanceReplyRecord.updated_at.desc(),
    LegacyGameAttendanceReplyRecord.id.desc(),
)


class AuthIdentityRecord(PortalDataBase):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_auth_provider_subject"
        ),
        CheckConstraint(
            "provider IN ('line', 'google', 'apple')", name="ck_auth_provider"
        ),
        CheckConstraint(
            "status IN ('pending', 'linked', 'disabled', 'blocked')",
            name="ck_auth_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND person_id IS NULL) OR "
            "(status = 'linked' AND person_id IS NOT NULL) OR "
            "status IN ('disabled', 'blocked')",
            name="ck_auth_link_state",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_auth_identities_person", AuthIdentityRecord.person_id)


class PersonQualificationRecord(PortalDataBase):
    __tablename__ = "person_qualifications"
    __table_args__ = (
        UniqueConstraint("person_id", "qualification", name="uq_person_qualification"),
        CheckConstraint(
            "qualification IN ('team_player', 'guest_player', 'affiliate', 'staff')",
            name="ck_qualification_value",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')", name="ck_qualification_status"
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_qualification_dates",
        ),
        CheckConstraint(
            "qualification <> 'guest_player' OR "
            "(valid_from IS NOT NULL AND valid_until IS NOT NULL AND "
            "valid_until > valid_from AND "
            "valid_until <= valid_from + interval '5 years')",
            name="ck_guest_player_bounded",
        ),
        CheckConstraint("version > 0", name="ck_person_qualification_version"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qualification: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    granted_by_person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Added by 0011 and intentionally deferred so the additive migration can
    # be applied before the new runtime without breaking 0010 read paths.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), deferred=True
    )


Index(
    "ix_person_qualifications_active",
    PersonQualificationRecord.qualification,
    PersonQualificationRecord.person_id,
    postgresql_where=text("status = 'active'"),
)


class AccessAuditRecord(PortalDataBase):
    __tablename__ = "access_audit"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_access_audit_request"),
        CheckConstraint(
            "action IN ('identity_pending', 'identity_linked', 'identity_ignored', "
            "'identity_unignored', 'identity_unlinked', 'identity_remapped', "
            "'identity_disabled', 'identity_enabled', 'identity_rejected', "
            "'identity_unblocked', 'identity_blocked', 'person_approved', "
            "'person_profile_updated', 'access_changed', 'status_changed', "
            "'qualification_granted', 'qualification_revoked', "
            "'qualification_restored', 'review_message_sent', 'review_closed', "
            "'review_redacted', 'member_backfilled')",
            name="ck_access_audit_action",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 3 AND 300", name="ck_access_audit_reason"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    target_person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    auth_identity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT")
    )
    before_state: Mapped[Optional[dict]] = mapped_column(JSON)
    after_state: Mapped[Optional[dict]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IdentityReviewThreadRecord(PortalDataBase):
    __tablename__ = "identity_review_threads"
    __table_args__ = (
        UniqueConstraint("auth_identity_id", name="uq_identity_review_thread"),
        CheckConstraint(
            "status IN ('open', 'closed')", name="ck_identity_review_thread_status"
        ),
        CheckConstraint(
            "(status = 'open' AND closed_at IS NULL) OR "
            "(status = 'closed' AND closed_at IS NOT NULL)",
            name="ck_identity_review_thread_closed",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    auth_identity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_applicant_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    redacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_identity_review_threads_status_activity",
    IdentityReviewThreadRecord.status,
    IdentityReviewThreadRecord.last_activity_at,
)


class IdentityReviewMessageRecord(PortalDataBase):
    __tablename__ = "identity_review_messages"
    __table_args__ = (
        CheckConstraint(
            "(sender_role = 'applicant' AND sender_person_id IS NULL) OR "
            "(sender_role = 'admin' AND sender_person_id IS NOT NULL)",
            name="ck_identity_review_sender",
        ),
        CheckConstraint(
            "(body_redacted IS FALSE AND length(body) BETWEEN 1 AND 1000) OR "
            "(body_redacted IS TRUE AND body IS NULL)",
            name="ck_identity_review_body",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.identity_review_threads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    body: Mapped[Optional[str]] = mapped_column(Text)
    body_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_identity_review_messages_thread_created",
    IdentityReviewMessageRecord.thread_id,
    IdentityReviewMessageRecord.created_at,
    IdentityReviewMessageRecord.id,
)


class MobileSessionRecord(PortalDataBase):
    __tablename__ = "mobile_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')", name="ck_mobile_sessions_status"
        ),
        CheckConstraint(
            "platform IN ('ios', 'android')", name="ck_mobile_sessions_platform"
        ),
        CheckConstraint("access_epoch >= 1", name="ck_mobile_sessions_access_epoch"),
        CheckConstraint(
            "refresh_family_expires_at > created_at", name="ck_mobile_sessions_expiry"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    auth_identity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    installation_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    access_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    refresh_family_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_mobile_sessions_person_status",
    MobileSessionRecord.person_id,
    MobileSessionRecord.status,
)


class MobileRefreshTokenRecord(PortalDataBase):
    __tablename__ = "mobile_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_mobile_refresh_token_hash"),
        UniqueConstraint(
            "session_id", "generation", name="uq_mobile_refresh_generation"
        ),
        CheckConstraint(
            "status IN ('current', 'rotated', 'revoked')",
            name="ck_mobile_refresh_status",
        ),
        CheckConstraint("generation >= 1", name="ck_mobile_refresh_generation"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHEMA}.mobile_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    successor_token_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.mobile_refresh_tokens.id", ondelete="RESTRICT"),
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


Index(
    "ix_mobile_refresh_session_status",
    MobileRefreshTokenRecord.session_id,
    MobileRefreshTokenRecord.status,
)


class MobileRefreshAttemptRecord(PortalDataBase):
    __tablename__ = "mobile_refresh_attempts"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "attempt_id_hash", name="uq_mobile_refresh_attempt"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHEMA}.mobile_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_successor: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_mobile_refresh_attempts_expiry", MobileRefreshAttemptRecord.expires_at)


class MobileIdempotencyRecord(PortalDataBase):
    __tablename__ = "mobile_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "method",
            "route",
            "key_hash",
            name="uq_mobile_idempotency_scope",
        ),
        CheckConstraint(
            "state IN ('pending', 'completed')", name="ck_mobile_idempotency_state"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHEMA}.mobile_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str] = mapped_column(String(160), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    response_status: Mapped[Optional[int]] = mapped_column(Integer)
    response_body: Mapped[Optional[dict]] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_mobile_idempotency_expiry", MobileIdempotencyRecord.expires_at)


class MobileNotificationRecord(PortalDataBase):
    __tablename__ = "mobile_notifications"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ("
            "'game_reminder', 'attendance_reminder', 'game_change', "
            "'officer_personal', 'officer_game_broadcast', "
            "'officer_team_broadcast', 'admin_system_announcement', "
            "'event_published', 'event_updated', 'event_cancelled')",
            name="ck_mobile_notification_type",
        ),
        CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 120",
            name="ck_mobile_notification_title",
        ),
        CheckConstraint(
            "length(btrim(body)) BETWEEN 1 AND 500",
            name="ck_mobile_notification_body",
        ),
        CheckConstraint(
            "visible_until = created_at + interval '90 days'",
            name="ck_mobile_notification_visibility",
        ),
        CheckConstraint(
            "(destination_type = 'notification' AND destination_game_id IS NULL "
            "AND destination_event_id IS NULL) OR "
            "(destination_type = 'game' AND destination_game_id IS NOT NULL "
            "AND destination_event_id IS NULL) OR "
            "(destination_type = 'event' AND destination_game_id IS NULL "
            "AND destination_event_id IS NOT NULL)",
            name="ck_mobile_notification_destination",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_game_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.games.id", ondelete="RESTRICT")
    )
    destination_event_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="RESTRICT"),
        server_default=text("NULL"),
        deferred=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    visible_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_mobile_notifications_created",
    MobileNotificationRecord.created_at.desc(),
    MobileNotificationRecord.id.desc(),
)


class MobileNotificationPublishAuditRecord(PortalDataBase):
    __tablename__ = "mobile_notification_publish_audits"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", name="uq_mobile_notification_publish_audit"
        ),
        CheckConstraint(
            "audience_type IN ('individual', 'game', 'team')",
            name="ck_mobile_notification_audit_audience",
        ),
        CheckConstraint(
            "recipient_count BETWEEN 1 AND 500",
            name="ck_mobile_notification_audit_recipient_count",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.mobile_notifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    audience_type: Mapped[str] = mapped_column(String(20), nullable=False)
    audience_reference_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    preview_revision: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MobileNotificationDeliveryRecord(PortalDataBase):
    __tablename__ = "mobile_notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "channel", name="uq_mobile_notification_delivery"
        ),
        CheckConstraint(
            "channel IN ('in_app', 'push')",
            name="ck_mobile_notification_delivery_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="ck_mobile_notification_delivery_status",
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_mobile_notification_attempt_count"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.mobile_notifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(80))
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_mobile_notification_delivery_outbox",
    MobileNotificationDeliveryRecord.status,
    MobileNotificationDeliveryRecord.channel,
    MobileNotificationDeliveryRecord.id,
    postgresql_where=text("status IN ('pending', 'failed') AND retryable IS TRUE"),
)


class MobileDeviceRegistrationRecord(PortalDataBase):
    __tablename__ = "mobile_device_registrations"
    __table_args__ = (
        UniqueConstraint(
            "person_id", "installation_id_hash", name="uq_mobile_device_installation"
        ),
        CheckConstraint(
            "platform IN ('ios', 'android')", name="ck_mobile_device_platform"
        ),
        CheckConstraint("provider = 'fake'", name="ck_mobile_device_provider"),
        CheckConstraint(
            "status IN ('active', 'revoked')", name="ck_mobile_device_status"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHEMA}.mobile_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    installation_id_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


Index(
    "uq_mobile_device_active_provider_token",
    MobileDeviceRegistrationRecord.provider,
    MobileDeviceRegistrationRecord.token_hash,
    unique=True,
    postgresql_where=text("status = 'active'"),
)


class MobileNotificationRecipientRecord(PortalDataBase):
    __tablename__ = "mobile_notification_recipients"
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "person_id",
            name="uq_mobile_notification_recipient",
        ),
        CheckConstraint(
            "read_at IS NULL OR read_at >= created_at",
            name="ck_mobile_notification_read_time",
        ),
        CheckConstraint(
            "participation_category IS NULL OR participation_category IN "
            "('team_player', 'guest_player', 'affiliate', 'staff', 'other')",
            name="ck_mobile_notification_recipient_category",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.mobile_notifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    participation_category: Mapped[Optional[str]] = mapped_column(
        String(30), server_default=text("NULL"), deferred=True
    )


Index(
    "ix_mobile_notification_recipient_page",
    MobileNotificationRecipientRecord.person_id,
    MobileNotificationRecipientRecord.notification_id.desc(),
)
Index(
    "ix_mobile_notification_recipient_unread",
    MobileNotificationRecipientRecord.person_id,
    MobileNotificationRecipientRecord.notification_id,
    postgresql_where=text("read_at IS NULL"),
)


class EventNotificationPublishAuditRecord(PortalDataBase):
    __tablename__ = "event_notification_publish_audits"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", name="uq_event_notification_audit_notification"
        ),
        UniqueConstraint("request_id", name="uq_event_notification_audit_request"),
        CheckConstraint(
            "notification_type IN "
            "('event_published', 'event_updated', 'event_cancelled')",
            name="ck_event_notification_audit_type",
        ),
        CheckConstraint(
            "event_version > 0", name="ck_event_notification_audit_version"
        ),
        CheckConstraint(
            "recipient_count BETWEEN 1 AND 500",
            name="ck_event_notification_audit_recipients",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.mobile_notifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_audit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.event_audit.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_revision: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_event_notification_audits_event",
    EventNotificationPublishAuditRecord.event_id,
    EventNotificationPublishAuditRecord.id,
)


class GuestQualificationAuditRecord(PortalDataBase):
    __tablename__ = "guest_qualification_audits"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_guest_qualification_audit_request"),
        CheckConstraint(
            "action IN ('granted', 'extended', 'revoked')",
            name="ck_guest_qualification_audit_action",
        ),
        CheckConstraint(
            "expected_version >= 0 AND resulting_version > 0",
            name="ck_guest_qualification_audit_versions",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 3 AND 300",
            name="ck_guest_qualification_audit_reason",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    qualification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.person_qualifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    before_state: Mapped[Optional[dict]] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_guest_qualification_audits_target",
    GuestQualificationAuditRecord.target_person_id,
    GuestQualificationAuditRecord.id,
)


class MobileAuthExchangeRecord(PortalDataBase):
    __tablename__ = "mobile_auth_exchanges"
    __table_args__ = (
        UniqueConstraint("provider", "assertion_hash", name="uq_mobile_auth_assertion"),
        UniqueConstraint(
            "provider", "login_attempt_hash", name="uq_mobile_auth_attempt"
        ),
        CheckConstraint(
            "provider IN ('line', 'google', 'apple')", name="ck_mobile_auth_provider"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    assertion_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    login_attempt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHEMA}.mobile_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_mobile_auth_exchanges_expiry", MobileAuthExchangeRecord.expires_at)


class AppleProviderCodeExchangeRecord(PortalDataBase):
    __tablename__ = "apple_provider_code_exchanges"
    __table_args__ = (
        UniqueConstraint("code_hash", name="uq_apple_provider_code_hash"),
        UniqueConstraint(
            "login_attempt_hash", name="uq_apple_provider_login_attempt_hash"
        ),
        CheckConstraint(
            "state IN ('pending', 'completed', 'rejected', 'unknown')",
            name="ck_apple_provider_code_state",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    login_attempt_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    auth_identity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AppleProviderCredentialRecord(PortalDataBase):
    __tablename__ = "apple_provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "auth_identity_id", name="uq_apple_provider_credential_identity"
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_apple_provider_credential_status",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    auth_identity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encrypted_refresh_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AppleProviderNotificationRecord(PortalDataBase):
    __tablename__ = "apple_provider_notifications"
    __table_args__ = (
        UniqueConstraint("jti_hash", name="uq_apple_provider_notification_jti"),
        CheckConstraint(
            "event_type IN ('consent-revoked', 'account-deleted', "
            "'email-disabled', 'email-enabled')",
            name="ck_apple_provider_notification_type",
        ),
        CheckConstraint(
            "disposition IN ('revoked', 'receipt_only')",
            name="ck_apple_provider_notification_disposition",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    jti_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    auth_identity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT"),
    )
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StagingBrokerOperationRecord(PortalDataBase):
    __tablename__ = "staging_broker_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_id ~ '^[A-Za-z0-9_-]{16,64}$'",
            name="ck_staging_broker_operation_id",
        ),
        CheckConstraint(
            "operation IN ('inspect', 'reset', 'grant', 'restore')",
            name="ck_staging_broker_operation",
        ),
        CheckConstraint(
            "target_state IN ('ready_basic', 'ready_officer', 'reset_required')",
            name="ck_staging_broker_target_state",
        ),
        CheckConstraint(
            "inspect_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_staging_broker_fingerprint",
        ),
        CheckConstraint(
            "lifecycle_state IN ('inspected', 'confirmed', 'mutation_issued', "
            "'postcheck_complete', 'reconcile_required')",
            name="ck_staging_broker_lifecycle_state",
        ),
        CheckConstraint(
            "reason_code IS NULL OR reason_code IN "
            "('OPERATOR_UNKNOWN', 'POSTCHECK_MISMATCH', 'RECONCILE_REQUIRED')",
            name="ck_staging_broker_reason_code",
        ),
        CheckConstraint(
            "updated_at >= created_at AND inspected_at >= created_at "
            "AND (confirmed_at IS NULL) = (lifecycle_state = 'inspected') "
            "AND (mutation_issued_at IS NULL) = "
            "(lifecycle_state IN ('inspected', 'confirmed')) "
            "AND (completed_at IS NOT NULL) = "
            "(lifecycle_state IN ('postcheck_complete', 'reconcile_required')) "
            "AND (lifecycle_state <> 'reconcile_required' OR reason_code IS NOT NULL) "
            "AND (lifecycle_state = 'reconcile_required' OR reason_code IS NULL)",
            name="ck_staging_broker_timestamps",
        ),
        {"schema": SCHEMA},
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_state: Mapped[str] = mapped_column(String(32), nullable=False)
    inspect_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[Optional[str]] = mapped_column(String(32))
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    mutation_issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_staging_broker_lifecycle_updated",
    StagingBrokerOperationRecord.lifecycle_state,
    StagingBrokerOperationRecord.updated_at,
)


class EventRecord(PortalDataBase):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('game', 'meal', 'trip', 'practice', 'social', 'other')",
            name="ck_event_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'cancelled')", name="ck_event_status"
        ),
        CheckConstraint("end_at IS NULL OR end_at > start_at", name="ck_event_dates"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ActivityRecord(PortalDataBase):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("event_id", "position", name="uq_activity_position"),
        CheckConstraint(
            "activity_type IN ('game', 'meal', 'transport', 'lodging', 'gathering', 'other')",
            name="ck_activity_type",
        ),
        CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_activity_dates"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    game_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.games.id", ondelete="RESTRICT")
    )


class EventEligibilityRuleRecord(PortalDataBase):
    __tablename__ = "event_eligibility_rules"
    __table_args__ = (
        UniqueConstraint("event_id", "qualification", name="uq_event_eligibility"),
        CheckConstraint(
            "qualification IN ('team_player', 'guest_player', 'affiliate', 'staff')",
            name="ck_event_eligibility_value",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    qualification: Mapped[str] = mapped_column(String(30), nullable=False)


class EventInviteeOverrideRecord(PortalDataBase):
    __tablename__ = "event_invitee_overrides"
    __table_args__ = (
        UniqueConstraint("event_id", "person_id", name="uq_event_invitee_override"),
        CheckConstraint(
            "action IN ('include', 'exclude')", name="ck_invitee_override_action"
        ),
        CheckConstraint(
            "participation_category IN ('team_player', 'guest_player', 'affiliate', 'staff', 'other')",
            name="ck_invitee_override_category",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 3 AND 300", name="ck_invitee_override_reason"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    participation_category: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EventInviteeRecord(PortalDataBase):
    __tablename__ = "event_invitees"
    __table_args__ = (
        UniqueConstraint("event_id", "person_id", name="uq_event_invitee"),
        CheckConstraint(
            "source IN ('qualification', 'manual_include', 'manual_exclude')",
            name="ck_event_invitee_source",
        ),
        CheckConstraint(
            "participation_category IN ('team_player', 'guest_player', 'affiliate', 'staff', 'other')",
            name="ck_event_participation_category",
        ),
        CheckConstraint(
            "(source = 'qualification' AND source_qualification IS NOT NULL "
            "AND actor_person_id IS NULL) OR "
            "(source IN ('manual_include', 'manual_exclude') AND actor_person_id IS NOT NULL "
            "AND length(reason) BETWEEN 3 AND 300)",
            name="ck_event_invitee_source_fields",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_qualification: Mapped[Optional[str]] = mapped_column(String(30))
    participation_category: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    snapshotted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "ix_event_invitees_event_included",
    EventInviteeRecord.event_id,
    EventInviteeRecord.included,
    EventInviteeRecord.participation_category,
)


class EventAttendanceReplyRecord(PortalDataBase):
    __tablename__ = "event_attendance_replies"
    __table_args__ = (
        UniqueConstraint("event_id", "person_id", name="uq_event_attendance_reply"),
        CheckConstraint(
            "reply IN ('attending', 'not_attending', 'maybe')",
            name="ck_event_attendance_reply",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reply: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ActivityAttendanceReplyRecord(PortalDataBase):
    __tablename__ = "activity_attendance_replies"
    __table_args__ = (
        UniqueConstraint(
            "activity_id", "person_id", name="uq_activity_attendance_reply"
        ),
        CheckConstraint(
            "reply IN ('attending', 'not_attending', 'maybe')",
            name="ck_activity_attendance_reply",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.activities.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reply: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EventManagerRecord(PortalDataBase):
    __tablename__ = "event_managers"
    __table_args__ = (
        UniqueConstraint("event_id", "person_id", name="uq_event_manager"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_by_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EventAuditRecord(PortalDataBase):
    __tablename__ = "event_audit"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_event_audit_request"),
        CheckConstraint(
            "action IN ('published', 'edited', 'cancelled', "
            "'invitee_included', 'invitee_excluded')",
            name="ck_event_audit_action",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 3 AND 300", name="ck_event_audit_reason"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
