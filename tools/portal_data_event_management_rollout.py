"""Fail-closed TASK-164 production migration operator.

The operator accepts one caller-owned private PostgreSQL URL in memory.  It
never discovers credentials, logs connection details, or retries execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "tools" / "portal_data_event_management_rollout.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MIGRATIONS = tuple(
    ROOT / "migrations" / "versions" / name
    for name in (
        "0005_mobile_auth_api_foundation.py",
        "0006_staging_broker_operation_journal.py",
        "0007_mobile_notifications.py",
        "0008_mobile_notification_delivery.py",
        "0009_event_management_writes.py",
    )
)
SOURCE_REVISION = "0004_phase_c_identity_lifecycle"
TARGET_REVISION = "0009_event_management_writes"
EXECUTION_ACKNOWLEDGEMENT = "EXECUTE TASK-164 0004 TO 0009"
ADVISORY_LOCK_KEY = 1640009
APPEND_ONLY_BODY_SHA256 = (
    "d24dc1c8bd05ac503ab853c62eab84a4968b79dabd2c535e678ec002af5bdd68"
)
OLD_ACTIONS = ("published", "invitee_included", "invitee_excluded")
NEW_ACTIONS = (
    "published",
    "edited",
    "cancelled",
    "invitee_included",
    "invitee_excluded",
)
EVENT_TABLES = (
    "activities",
    "activity_attendance_replies",
    "event_attendance_replies",
    "event_audit",
    "event_eligibility_rules",
    "event_invitee_overrides",
    "event_invitees",
    "event_managers",
    "events",
)
IDENTITY_TABLE_COLUMNS = {
    "identity_review_messages": frozenset(
        {
            "id",
            "thread_id",
            "sender_role",
            "sender_person_id",
            "body",
            "body_redacted",
            "created_at",
        }
    ),
    "identity_review_threads": frozenset(
        {
            "id",
            "auth_identity_id",
            "status",
            "last_applicant_message_at",
            "last_activity_at",
            "closed_at",
            "redacted_at",
            "created_at",
            "updated_at",
        }
    ),
}
PHASE_C_FINGERPRINTS = (
    "21515e2b449df86d4d31a2789638a3d7",
    "6fb4bde4b853d543d377f8a3b767d01f",
    "b0dacc9d12f7a1114831805d3e56954d",
)
FUTURE_TABLE_COLUMNS = {
    "mobile_sessions": frozenset(
        {
            "id",
            "auth_identity_id",
            "person_id",
            "installation_id_hash",
            "platform",
            "status",
            "access_epoch",
            "refresh_family_expires_at",
            "revoked_at",
            "created_at",
            "updated_at",
        }
    ),
    "mobile_refresh_tokens": frozenset(
        {
            "id",
            "session_id",
            "token_hash",
            "generation",
            "status",
            "successor_token_id",
            "issued_at",
            "expires_at",
            "rotated_at",
            "revoked_at",
        }
    ),
    "mobile_refresh_attempts": frozenset(
        {
            "id",
            "session_id",
            "attempt_id_hash",
            "request_hash",
            "encrypted_successor",
            "expires_at",
            "created_at",
        }
    ),
    "mobile_idempotency_records": frozenset(
        {
            "id",
            "session_id",
            "person_id",
            "method",
            "route",
            "key_hash",
            "request_hash",
            "state",
            "response_status",
            "response_body",
            "expires_at",
            "created_at",
            "updated_at",
        }
    ),
    "mobile_auth_exchanges": frozenset(
        {
            "id",
            "provider",
            "assertion_hash",
            "login_attempt_hash",
            "session_id",
            "expires_at",
            "created_at",
        }
    ),
    "staging_broker_operations": frozenset(
        {
            "operation_id",
            "operation",
            "target_state",
            "inspect_fingerprint",
            "lifecycle_state",
            "reason_code",
            "inspected_at",
            "confirmed_at",
            "mutation_issued_at",
            "completed_at",
            "created_at",
            "updated_at",
        }
    ),
    "mobile_notifications": frozenset(
        {
            "id",
            "notification_type",
            "title",
            "body",
            "created_at",
            "visible_until",
            "destination_type",
            "destination_game_id",
        }
    ),
    "mobile_notification_recipients": frozenset(
        {"id", "notification_id", "person_id", "created_at", "read_at"}
    ),
    "mobile_notification_publish_audits": frozenset(
        {
            "id",
            "notification_id",
            "actor_person_id",
            "audience_type",
            "audience_reference_id",
            "preview_revision",
            "recipient_count",
            "request_hash",
            "created_at",
        }
    ),
    "mobile_notification_deliveries": frozenset(
        {
            "id",
            "notification_id",
            "channel",
            "status",
            "attempt_count",
            "error_code",
            "retryable",
            "created_at",
            "updated_at",
        }
    ),
    "mobile_device_registrations": frozenset(
        {
            "id",
            "person_id",
            "session_id",
            "installation_id_hash",
            "platform",
            "provider",
            "token_hash",
            "status",
            "created_at",
            "updated_at",
            "revoked_at",
        }
    ),
}
FUTURE_FUNCTIONS = frozenset(
    {
        "reject_mobile_notification_mutation",
        "reject_mobile_notification_audit_mutation",
    }
)
FUTURE_TRIGGERS = frozenset(
    {
        ("mobile_notifications", "mobile_notification_content_immutable"),
        (
            "mobile_notification_publish_audits",
            "mobile_notification_audit_immutable",
        ),
    }
)


def _constraint(
    table: str,
    kind: str,
    columns: tuple[str, ...],
    *,
    references: tuple[str, tuple[str, ...], str] | None = None,
    expression: str | None = None,
) -> tuple[object, ...]:
    exact_references = (
        ("ntubtob", *references, "a", "s") if references is not None else None
    )
    return (table, kind, columns, exact_references, expression)


MATERIAL_CONSTRAINTS = {
    "mobile_sessions_pkey": _constraint("mobile_sessions", "p", ("id",)),
    "mobile_sessions_auth_identity_id_fkey": _constraint(
        "mobile_sessions",
        "f",
        ("auth_identity_id",),
        references=("auth_identities", ("id",), "r"),
    ),
    "mobile_sessions_person_id_fkey": _constraint(
        "mobile_sessions",
        "f",
        ("person_id",),
        references=("people", ("id",), "r"),
    ),
    "ck_mobile_sessions_status": _constraint(
        "mobile_sessions", "c", ("status",), expression="status IN ('active','revoked')"
    ),
    "ck_mobile_sessions_platform": _constraint(
        "mobile_sessions",
        "c",
        ("platform",),
        expression="platform IN ('ios','android')",
    ),
    "ck_mobile_sessions_access_epoch": _constraint(
        "mobile_sessions", "c", ("access_epoch",), expression="access_epoch >= 1"
    ),
    "ck_mobile_sessions_expiry": _constraint(
        "mobile_sessions",
        "c",
        ("refresh_family_expires_at", "created_at"),
        expression="refresh_family_expires_at > created_at",
    ),
    "mobile_refresh_tokens_pkey": _constraint("mobile_refresh_tokens", "p", ("id",)),
    "mobile_refresh_tokens_session_id_fkey": _constraint(
        "mobile_refresh_tokens",
        "f",
        ("session_id",),
        references=("mobile_sessions", ("id",), "c"),
    ),
    "mobile_refresh_tokens_successor_token_id_fkey": _constraint(
        "mobile_refresh_tokens",
        "f",
        ("successor_token_id",),
        references=("mobile_refresh_tokens", ("id",), "r"),
    ),
    "uq_mobile_refresh_token_hash": _constraint(
        "mobile_refresh_tokens", "u", ("token_hash",)
    ),
    "uq_mobile_refresh_generation": _constraint(
        "mobile_refresh_tokens", "u", ("session_id", "generation")
    ),
    "ck_mobile_refresh_status": _constraint(
        "mobile_refresh_tokens",
        "c",
        ("status",),
        expression="status IN ('current','rotated','revoked')",
    ),
    "ck_mobile_refresh_generation": _constraint(
        "mobile_refresh_tokens", "c", ("generation",), expression="generation >= 1"
    ),
    "mobile_refresh_attempts_pkey": _constraint(
        "mobile_refresh_attempts", "p", ("id",)
    ),
    "mobile_refresh_attempts_session_id_fkey": _constraint(
        "mobile_refresh_attempts",
        "f",
        ("session_id",),
        references=("mobile_sessions", ("id",), "c"),
    ),
    "uq_mobile_refresh_attempt": _constraint(
        "mobile_refresh_attempts", "u", ("session_id", "attempt_id_hash")
    ),
    "mobile_idempotency_records_pkey": _constraint(
        "mobile_idempotency_records", "p", ("id",)
    ),
    "mobile_idempotency_records_session_id_fkey": _constraint(
        "mobile_idempotency_records",
        "f",
        ("session_id",),
        references=("mobile_sessions", ("id",), "c"),
    ),
    "mobile_idempotency_records_person_id_fkey": _constraint(
        "mobile_idempotency_records",
        "f",
        ("person_id",),
        references=("people", ("id",), "r"),
    ),
    "uq_mobile_idempotency_scope": _constraint(
        "mobile_idempotency_records", "u", ("session_id", "method", "route", "key_hash")
    ),
    "ck_mobile_idempotency_state": _constraint(
        "mobile_idempotency_records",
        "c",
        ("state",),
        expression="state IN ('pending','completed')",
    ),
    "mobile_auth_exchanges_pkey": _constraint("mobile_auth_exchanges", "p", ("id",)),
    "mobile_auth_exchanges_session_id_fkey": _constraint(
        "mobile_auth_exchanges",
        "f",
        ("session_id",),
        references=("mobile_sessions", ("id",), "r"),
    ),
    "uq_mobile_auth_assertion": _constraint(
        "mobile_auth_exchanges", "u", ("provider", "assertion_hash")
    ),
    "uq_mobile_auth_attempt": _constraint(
        "mobile_auth_exchanges", "u", ("provider", "login_attempt_hash")
    ),
    "ck_mobile_auth_provider": _constraint(
        "mobile_auth_exchanges",
        "c",
        ("provider",),
        expression="provider IN ('line','google','apple')",
    ),
    "pk_staging_broker_operations": _constraint(
        "staging_broker_operations", "p", ("operation_id",)
    ),
    "ck_staging_broker_operation_id": _constraint(
        "staging_broker_operations",
        "c",
        ("operation_id",),
        expression="operation_id ~ '^[A-Za-z0-9_-]{16,64}$'",
    ),
    "ck_staging_broker_operation": _constraint(
        "staging_broker_operations",
        "c",
        ("operation",),
        expression="operation IN ('inspect','reset','grant','restore')",
    ),
    "ck_staging_broker_target_state": _constraint(
        "staging_broker_operations",
        "c",
        ("target_state",),
        expression="target_state IN ('ready_basic','ready_officer','reset_required')",
    ),
    "ck_staging_broker_fingerprint": _constraint(
        "staging_broker_operations",
        "c",
        ("inspect_fingerprint",),
        expression="inspect_fingerprint ~ '^[0-9a-f]{64}$'",
    ),
    "ck_staging_broker_lifecycle_state": _constraint(
        "staging_broker_operations",
        "c",
        ("lifecycle_state",),
        expression="lifecycle_state IN ('inspected','confirmed','mutation_issued','postcheck_complete','reconcile_required')",
    ),
    "ck_staging_broker_reason_code": _constraint(
        "staging_broker_operations",
        "c",
        ("reason_code",),
        expression="reason_code IS NULL OR reason_code IN ('OPERATOR_UNKNOWN','POSTCHECK_MISMATCH','RECONCILE_REQUIRED')",
    ),
    "ck_staging_broker_timestamps": _constraint(
        "staging_broker_operations",
        "c",
        (
            "updated_at",
            "created_at",
            "inspected_at",
            "confirmed_at",
            "lifecycle_state",
            "mutation_issued_at",
            "completed_at",
            "reason_code",
        ),
        expression="updated_at >= created_at AND inspected_at >= created_at AND (confirmed_at IS NULL) = (lifecycle_state = 'inspected') AND (mutation_issued_at IS NULL) = (lifecycle_state IN ('inspected','confirmed')) AND (completed_at IS NOT NULL) = (lifecycle_state IN ('postcheck_complete','reconcile_required')) AND (lifecycle_state <> 'reconcile_required' OR reason_code IS NOT NULL) AND (lifecycle_state = 'reconcile_required' OR reason_code IS NULL)",
    ),
    "mobile_notifications_pkey": _constraint("mobile_notifications", "p", ("id",)),
    "mobile_notifications_destination_game_id_fkey": _constraint(
        "mobile_notifications",
        "f",
        ("destination_game_id",),
        references=("games", ("id",), "r"),
    ),
    "ck_mobile_notification_type": _constraint(
        "mobile_notifications",
        "c",
        ("notification_type",),
        expression="notification_type IN ('game_reminder','attendance_reminder','game_change','officer_personal','officer_game_broadcast','officer_team_broadcast','admin_system_announcement')",
    ),
    "ck_mobile_notification_title": _constraint(
        "mobile_notifications",
        "c",
        ("title",),
        expression="length(btrim(title)) BETWEEN 1 AND 120",
    ),
    "ck_mobile_notification_body": _constraint(
        "mobile_notifications",
        "c",
        ("body",),
        expression="length(btrim(body)) BETWEEN 1 AND 500",
    ),
    "ck_mobile_notification_visibility": _constraint(
        "mobile_notifications",
        "c",
        ("visible_until", "created_at"),
        expression="visible_until = created_at + interval '90 days'",
    ),
    "ck_mobile_notification_destination": _constraint(
        "mobile_notifications",
        "c",
        ("destination_type", "destination_game_id"),
        expression="(destination_type = 'notification' AND destination_game_id IS NULL) OR (destination_type = 'game' AND destination_game_id IS NOT NULL)",
    ),
    "mobile_notification_recipients_pkey": _constraint(
        "mobile_notification_recipients", "p", ("id",)
    ),
    "mobile_notification_recipients_notification_id_fkey": _constraint(
        "mobile_notification_recipients",
        "f",
        ("notification_id",),
        references=("mobile_notifications", ("id",), "r"),
    ),
    "mobile_notification_recipients_person_id_fkey": _constraint(
        "mobile_notification_recipients",
        "f",
        ("person_id",),
        references=("people", ("id",), "r"),
    ),
    "uq_mobile_notification_recipient": _constraint(
        "mobile_notification_recipients", "u", ("notification_id", "person_id")
    ),
    "ck_mobile_notification_read_time": _constraint(
        "mobile_notification_recipients",
        "c",
        ("read_at", "created_at"),
        expression="read_at IS NULL OR read_at >= created_at",
    ),
    "mobile_notification_publish_audits_pkey": _constraint(
        "mobile_notification_publish_audits", "p", ("id",)
    ),
    "mobile_notification_publish_audits_notification_id_fkey": _constraint(
        "mobile_notification_publish_audits",
        "f",
        ("notification_id",),
        references=("mobile_notifications", ("id",), "r"),
    ),
    "mobile_notification_publish_audits_actor_person_id_fkey": _constraint(
        "mobile_notification_publish_audits",
        "f",
        ("actor_person_id",),
        references=("people", ("id",), "r"),
    ),
    "uq_mobile_notification_publish_audit": _constraint(
        "mobile_notification_publish_audits", "u", ("notification_id",)
    ),
    "ck_mobile_notification_audit_audience": _constraint(
        "mobile_notification_publish_audits",
        "c",
        ("audience_type",),
        expression="audience_type IN ('individual','game','team')",
    ),
    "ck_mobile_notification_audit_recipient_count": _constraint(
        "mobile_notification_publish_audits",
        "c",
        ("recipient_count",),
        expression="recipient_count BETWEEN 1 AND 500",
    ),
    "mobile_notification_deliveries_pkey": _constraint(
        "mobile_notification_deliveries", "p", ("id",)
    ),
    "mobile_notification_deliveries_notification_id_fkey": _constraint(
        "mobile_notification_deliveries",
        "f",
        ("notification_id",),
        references=("mobile_notifications", ("id",), "r"),
    ),
    "uq_mobile_notification_delivery": _constraint(
        "mobile_notification_deliveries", "u", ("notification_id", "channel")
    ),
    "ck_mobile_notification_delivery_channel": _constraint(
        "mobile_notification_deliveries",
        "c",
        ("channel",),
        expression="channel IN ('in_app','push')",
    ),
    "ck_mobile_notification_delivery_status": _constraint(
        "mobile_notification_deliveries",
        "c",
        ("status",),
        expression="status IN ('pending','succeeded','failed')",
    ),
    "ck_mobile_notification_attempt_count": _constraint(
        "mobile_notification_deliveries",
        "c",
        ("attempt_count",),
        expression="attempt_count >= 0",
    ),
    "mobile_device_registrations_pkey": _constraint(
        "mobile_device_registrations", "p", ("id",)
    ),
    "mobile_device_registrations_person_id_fkey": _constraint(
        "mobile_device_registrations",
        "f",
        ("person_id",),
        references=("people", ("id",), "r"),
    ),
    "mobile_device_registrations_session_id_fkey": _constraint(
        "mobile_device_registrations",
        "f",
        ("session_id",),
        references=("mobile_sessions", ("id",), "r"),
    ),
    "uq_mobile_device_installation": _constraint(
        "mobile_device_registrations", "u", ("person_id", "installation_id_hash")
    ),
    "ck_mobile_device_platform": _constraint(
        "mobile_device_registrations",
        "c",
        ("platform",),
        expression="platform IN ('ios','android')",
    ),
    "ck_mobile_device_provider": _constraint(
        "mobile_device_registrations",
        "c",
        ("provider",),
        expression="provider = 'fake'",
    ),
    "ck_mobile_device_status": _constraint(
        "mobile_device_registrations",
        "c",
        ("status",),
        expression="status IN ('active','revoked')",
    ),
}

EXPLICIT_MATERIAL_INDEXES = {
    "ix_mobile_sessions_person_status": (
        "mobile_sessions",
        False,
        ("person_id", "status"),
        None,
        (0, 0),
    ),
    "ix_mobile_refresh_session_status": (
        "mobile_refresh_tokens",
        False,
        ("session_id", "status"),
        None,
        (0, 0),
    ),
    "ix_mobile_refresh_attempts_expiry": (
        "mobile_refresh_attempts",
        False,
        ("expires_at",),
        None,
        (0,),
    ),
    "ix_mobile_idempotency_expiry": (
        "mobile_idempotency_records",
        False,
        ("expires_at",),
        None,
        (0,),
    ),
    "ix_mobile_auth_exchanges_expiry": (
        "mobile_auth_exchanges",
        False,
        ("expires_at",),
        None,
        (0,),
    ),
    "ix_staging_broker_lifecycle_updated": (
        "staging_broker_operations",
        False,
        ("lifecycle_state", "updated_at"),
        None,
        (0, 0),
    ),
    "ix_mobile_notifications_created": (
        "mobile_notifications",
        False,
        ("created_at", "id"),
        None,
        (3, 3),
    ),
    "ix_mobile_notification_recipient_page": (
        "mobile_notification_recipients",
        False,
        ("person_id", "notification_id"),
        None,
        (0, 3),
    ),
    "ix_mobile_notification_recipient_unread": (
        "mobile_notification_recipients",
        False,
        ("person_id", "notification_id"),
        "read_at IS NULL",
        (0, 0),
    ),
    "ix_mobile_notification_delivery_outbox": (
        "mobile_notification_deliveries",
        False,
        ("status", "channel", "id"),
        "status IN ('pending','failed') AND retryable IS TRUE",
        (0, 0, 0),
    ),
    "uq_mobile_device_active_provider_token": (
        "mobile_device_registrations",
        True,
        ("provider", "token_hash"),
        "status = 'active'",
        (0, 0),
    ),
}


def _column(
    udt: str,
    *,
    length: int | None = None,
    nullable: bool = False,
    identity: bool = False,
    default: bool = False,
) -> tuple[object, ...]:
    return (
        udt,
        length,
        nullable,
        identity,
        "BY DEFAULT" if identity else None,
        default,
    )


V = lambda length, nullable=False: _column("varchar", length=length, nullable=nullable)
C = lambda length, nullable=False: _column("bpchar", length=length, nullable=nullable)
I8 = lambda nullable=False, identity=False: _column(
    "int8", nullable=nullable, identity=identity
)
I4 = lambda nullable=False: _column("int4", nullable=nullable)
TZ = lambda nullable=False: _column("timestamptz", nullable=nullable)
FUTURE_COLUMN_ATTRIBUTES = {
    "mobile_sessions": {
        "id": V(64),
        "auth_identity_id": I8(),
        "person_id": I8(),
        "installation_id_hash": V(64),
        "platform": V(20),
        "status": V(20),
        "access_epoch": I4(),
        "refresh_family_expires_at": TZ(),
        "revoked_at": TZ(True),
        "created_at": TZ(),
        "updated_at": TZ(),
    },
    "mobile_refresh_tokens": {
        "id": I8(identity=True),
        "session_id": V(64),
        "token_hash": V(64),
        "generation": I4(),
        "status": V(20),
        "successor_token_id": I8(True),
        "issued_at": TZ(),
        "expires_at": TZ(),
        "rotated_at": TZ(True),
        "revoked_at": TZ(True),
    },
    "mobile_refresh_attempts": {
        "id": I8(identity=True),
        "session_id": V(64),
        "attempt_id_hash": V(64),
        "request_hash": V(64),
        "encrypted_successor": _column("bytea"),
        "expires_at": TZ(),
        "created_at": TZ(),
    },
    "mobile_idempotency_records": {
        "id": I8(identity=True),
        "session_id": V(64),
        "person_id": I8(),
        "method": V(10),
        "route": V(160),
        "key_hash": V(64),
        "request_hash": V(64),
        "state": V(20),
        "response_status": I4(True),
        "response_body": _column("json", nullable=True),
        "expires_at": TZ(),
        "created_at": TZ(),
        "updated_at": TZ(),
    },
    "mobile_auth_exchanges": {
        "id": I8(identity=True),
        "provider": V(20),
        "assertion_hash": V(64),
        "login_attempt_hash": V(64),
        "session_id": V(64),
        "expires_at": TZ(),
        "created_at": TZ(),
    },
    "staging_broker_operations": {
        "operation_id": V(64),
        "operation": V(16),
        "target_state": V(32),
        "inspect_fingerprint": C(64),
        "lifecycle_state": V(32),
        "reason_code": V(32, True),
        "inspected_at": TZ(),
        "confirmed_at": TZ(True),
        "mutation_issued_at": TZ(True),
        "completed_at": TZ(True),
        "created_at": TZ(),
        "updated_at": TZ(),
    },
    "mobile_notifications": {
        "id": I8(identity=True),
        "notification_type": V(40),
        "title": V(120),
        "body": V(500),
        "created_at": TZ(),
        "visible_until": TZ(),
        "destination_type": V(20),
        "destination_game_id": I8(True),
    },
    "mobile_notification_recipients": {
        "id": I8(identity=True),
        "notification_id": I8(),
        "person_id": I8(),
        "created_at": TZ(),
        "read_at": TZ(True),
    },
    "mobile_notification_publish_audits": {
        "id": I8(identity=True),
        "notification_id": I8(),
        "actor_person_id": I8(),
        "audience_type": V(20),
        "audience_reference_id": I8(True),
        "preview_revision": C(64),
        "recipient_count": I4(),
        "request_hash": C(64),
        "created_at": TZ(),
    },
    "mobile_notification_deliveries": {
        "id": I8(identity=True),
        "notification_id": I8(),
        "channel": V(20),
        "status": V(20),
        "attempt_count": I4(),
        "error_code": V(80, True),
        "retryable": _column("bool"),
        "created_at": TZ(),
        "updated_at": TZ(),
    },
    "mobile_device_registrations": {
        "id": I8(identity=True),
        "person_id": I8(),
        "session_id": V(64),
        "installation_id_hash": C(64),
        "platform": V(20),
        "provider": V(20),
        "token_hash": C(64),
        "status": V(20),
        "created_at": TZ(),
        "updated_at": TZ(),
        "revoked_at": TZ(True),
    },
}


class RolloutError(RuntimeError):
    """Raised when the production migration boundary cannot be proven exact."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_artifact() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != ARTIFACT.name or digest != _canonical_digest(ARTIFACT):
        raise RolloutError("operator checksum boundary is invalid")
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    if scripts.get_heads() != [TARGET_REVISION]:
        raise RolloutError("repository migration graph is divergent")
    revision = scripts.get_revision(TARGET_REVISION)
    observed = []
    while revision is not None and revision.revision != SOURCE_REVISION:
        observed.append(revision.revision)
        if not isinstance(revision.down_revision, str):
            raise RolloutError("repository recovery chain is divergent")
        revision = scripts.get_revision(revision.down_revision)
    if revision is None or observed != [
        "0009_event_management_writes",
        "0008_mobile_notification_delivery",
        "0007_mobile_notifications",
        "0006_staging_broker_operation_journal",
        "0005_mobile_auth_api_foundation",
    ]:
        raise RolloutError("repository recovery chain is not exact")


def _current_revision(connection: Connection) -> str:
    rows = (
        connection.execute(text("SELECT version_num FROM ntubtob.alembic_version"))
        .scalars()
        .all()
    )
    if len(rows) != 1 or not isinstance(rows[0], str):
        raise RolloutError("Alembic revision is ambiguous")
    return rows[0]


def _table_columns(
    connection: Connection, tables: tuple[str, ...]
) -> dict[str, frozenset[str]]:
    rows = connection.execute(
        text(
            "SELECT table_name,column_name FROM information_schema.columns "
            "WHERE table_schema='ntubtob' AND table_name=ANY(:tables) "
            "ORDER BY table_name,ordinal_position"
        ),
        {"tables": list(tables)},
    ).all()
    observed = {table: set() for table in tables}
    for table, column in rows:
        if table not in observed or not isinstance(column, str):
            raise RolloutError("schema column boundary is ambiguous")
        observed[table].add(column)
    return {table: frozenset(columns) for table, columns in observed.items()}


def _phase_c_identity_safe(connection: Connection) -> None:
    fingerprints = connection.execute(
        text(
            "WITH column_fingerprint AS ("
            "SELECT md5(string_agg(c.table_name||'.'||c.column_name||'|'||"
            "c.data_type||'|'||c.udt_name||'|'||c.is_nullable||'|'||"
            "coalesce(c.column_default,'NULL')||'|'||c.is_identity||'|'||"
            "c.is_generated,E'\\n' ORDER BY c.table_name,c.ordinal_position)) value "
            "FROM information_schema.columns c WHERE c.table_schema='ntubtob' "
            "AND ((c.table_name='people' AND c.column_name IN "
            "('formal_name','admin_note')) OR "
            "(c.table_name='game_attendance_replies' AND c.column_name='person_id') "
            "OR c.table_name IN ('identity_review_threads','identity_review_messages'))), "
            "constraint_fingerprint AS ("
            "SELECT md5(string_agg(r.relname||'.'||c.conname||'|'||c.contype::text||"
            "'|'||pg_get_constraintdef(c.oid,true)||'|'||c.convalidated::text,E'\\n' "
            "ORDER BY r.relname,c.conname)) value FROM pg_constraint c "
            "JOIN pg_class r ON r.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=r.relnamespace "
            "WHERE n.nspname='ntubtob' AND "
            "(r.relname IN ('identity_review_threads','identity_review_messages') OR "
            "c.conname IN ('ck_people_formal_name','ck_people_admin_note',"
            "'ck_access_audit_action','ck_guest_player_bounded',"
            "'fk_game_attendance_person'))), index_fingerprint AS ("
            "SELECT md5(string_agg(indexname||'|'||indexdef,E'\\n' ORDER BY indexname)) "
            "value FROM pg_indexes WHERE schemaname='ntubtob' AND indexname IN "
            "('ix_identity_review_threads_status_activity',"
            "'ix_identity_review_messages_thread_created',"
            "'ix_game_attendance_person_game_updated')) "
            "SELECT column_fingerprint.value,constraint_fingerprint.value,"
            "index_fingerprint.value FROM column_fingerprint,constraint_fingerprint,"
            "index_fingerprint"
        )
    ).one()
    if tuple(fingerprints) != PHASE_C_FINGERPRINTS:
        raise RolloutError("Phase C identity catalog fingerprint drifted")
    identity_tables = tuple(sorted(IDENTITY_TABLE_COLUMNS))
    rls_rows = connection.execute(
        text(
            "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='ntubtob' AND relname=ANY(:tables) ORDER BY relname"
        ),
        {"tables": list(identity_tables)},
    ).all()
    if len(rls_rows) != len(identity_tables) or any(
        row.relname != table
        or row.relrowsecurity is not True
        or row.relforcerowsecurity is not False
        for row, table in zip(rls_rows, identity_tables)
    ):
        raise RolloutError("Phase C identity RLS boundary drifted")
    policy_count = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='ntubtob' AND c.relname=ANY(:tables)"
            ),
            {"tables": list(identity_tables)},
        )
        or 0
    )
    if policy_count != 0:
        raise RolloutError("Phase C identity policy boundary drifted")
    attendance_drift = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM ntubtob.game_attendance_replies r "
                "LEFT JOIN ntubtob.members m ON m.id=r.member_id "
                "WHERE r.person_id IS NULL OR m.person_id IS DISTINCT FROM r.person_id"
            )
        )
        or 0
    )
    if attendance_drift != 0:
        raise RolloutError("Phase C attendance identity boundary drifted")


def _future_objects_absent(connection: Connection) -> None:
    tables = tuple(sorted(FUTURE_TABLE_COLUMNS))
    present_tables = set(
        connection.scalars(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' "
                "AND c.relkind IN ('r','p') AND c.relname=ANY(:tables)"
            ),
            {"tables": list(tables)},
        )
    )
    function_count = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid=p.pronamespace WHERE n.nspname='ntubtob' "
                "AND p.proname=ANY(:functions)"
            ),
            {"functions": list(FUTURE_FUNCTIONS)},
        )
        or 0
    )
    trigger_count = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='ntubtob' AND NOT t.tgisinternal "
                "AND t.tgname=ANY(:triggers)"
            ),
            {"triggers": [name for _, name in FUTURE_TRIGGERS]},
        )
        or 0
    )
    if present_tables or function_count != 0 or trigger_count != 0:
        raise RolloutError("future migration objects already exist")


def _expression_tokens(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, str):
        raise RolloutError("unsupported material expression syntax")
    tokens: list[str] = []
    index = 0
    operators = ("!~*", "!~", "~*", "::", "<>", ">=", "<=", "!=")
    while index < len(value):
        character = value[index]
        if character.isspace():
            index += 1
            continue
        if character == "'":
            end = index + 1
            while end < len(value):
                if value[end] == "'":
                    if end + 1 < len(value) and value[end + 1] == "'":
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            else:
                raise RolloutError("unsupported material expression syntax")
            tokens.append(value[index:end])
            index = end
            continue
        if character == '"':
            end = value.find('"', index + 1)
            if end < 0:
                raise RolloutError("unsupported material expression syntax")
            tokens.append(f"identifier:{value[index + 1:end]}")
            index = end + 1
            continue
        operator = next(
            (
                candidate
                for candidate in operators
                if value.startswith(candidate, index)
            ),
            None,
        )
        if operator is not None:
            tokens.append(operator)
            index += len(operator)
            continue
        if character in "=><~+-*/%(),[]":
            tokens.append(character)
            index += 1
            continue
        identifier = re.match(r"[A-Za-z_][A-Za-z0-9_$]*", value[index:])
        if identifier:
            token = identifier.group(0)
            tokens.append(token.lower())
            index += len(token)
            continue
        number = re.match(r"\d+(?:\.\d+)?", value[index:])
        if number:
            token = number.group(0)
            tokens.append(token)
            index += len(token)
            continue
        raise RolloutError("unsupported material expression syntax")

    without_casts: list[str] = []
    index = 0
    cast_types = {
        ("text",),
        ("bpchar",),
        ("cstring",),
        ("interval",),
        ("integer",),
        ("bigint",),
        ("boolean",),
        ("character", "varying"),
        ("timestamp", "with", "time", "zone"),
    }
    while index < len(tokens):
        if tokens[index] != "::":
            without_casts.append(tokens[index])
            index += 1
            continue
        match = next(
            (
                cast_type
                for cast_type in sorted(cast_types, key=len, reverse=True)
                if tuple(tokens[index + 1 : index + 1 + len(cast_type)]) == cast_type
            ),
            None,
        )
        if match is None:
            raise RolloutError("unsupported material expression cast")
        index += 1 + len(match)
        if tuple(tokens[index : index + 2]) == ("[", "]"):
            index += 2

    normalized: list[str] = []
    index = 0
    while index < len(without_casts):
        if (
            without_casts[index] == "interval"
            and index + 1 < len(without_casts)
            and without_casts[index + 1].startswith("'")
        ):
            index += 1
            continue
        if without_casts[index] == "in" and index + 1 < len(without_casts):
            if without_casts[index + 1] != "(":
                raise RolloutError("unsupported material expression syntax")
            depth = 0
            end = index + 1
            while end < len(without_casts):
                if without_casts[end] == "(":
                    depth += 1
                elif without_casts[end] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            if depth != 0:
                raise RolloutError("unsupported material expression syntax")
            normalized.extend(("=", "any", "(", "array", "["))
            normalized.extend(without_casts[index + 2 : end])
            normalized.extend(("]", ")"))
            index = end + 1
            continue
        normalized.append(without_casts[index])
        index += 1
    return tuple(normalized)


def _strip_outer_parentheses(tokens: tuple[str, ...]) -> tuple[str, ...]:
    while len(tokens) >= 2 and tokens[0] == "(" and tokens[-1] == ")":
        depth = 0
        closes_at_end = False
        for index, token in enumerate(tokens):
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(tokens) - 1
                    break
        if not closes_at_end:
            break
        tokens = tokens[1:-1]
    return tokens


def _split_boolean(
    tokens: tuple[str, ...], operator: str
) -> tuple[tuple[str, ...], ...]:
    parts: list[tuple[str, ...]] = []
    start = 0
    depth = 0
    between = 0
    for index, token in enumerate(tokens):
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0 and token == "between":
            between += 1
        elif depth == 0 and token == "and" and between:
            between -= 1
        elif depth == 0 and token == operator:
            parts.append(tokens[start:index])
            start = index + 1
    if parts:
        parts.append(tokens[start:])
    return tuple(parts)


def _expression_fingerprint(value: object) -> tuple[object, ...]:
    def parse(tokens: tuple[str, ...]) -> tuple[object, ...]:
        tokens = _strip_outer_parentheses(tokens)
        for operator in ("or", "and"):
            parts = _split_boolean(tokens, operator)
            if parts:
                return (operator, *(parse(part) for part in parts))
        return ("leaf", *(token for token in tokens if token not in {"(", ")"}))

    tokens = _expression_tokens(value)
    return parse(tokens) if tokens else ()


def _material_columns_safe(connection: Connection) -> None:
    tables = tuple(sorted(FUTURE_COLUMN_ATTRIBUTES))
    rows = connection.execute(
        text(
            "SELECT table_name,column_name,udt_name,character_maximum_length,"
            "is_nullable='YES',is_identity='YES',identity_generation,"
            "column_default IS NOT NULL "
            "FROM information_schema.columns WHERE table_schema='ntubtob' "
            "AND table_name=ANY(:tables)"
        ),
        {"tables": list(tables)},
    ).all()
    observed = {
        (table, column): (
            udt,
            length,
            nullable,
            identity,
            identity_generation,
            has_default,
        )
        for table, column, udt, length, nullable, identity, identity_generation, has_default in rows
    }
    expected = {
        (table, column): attributes
        for table, columns in FUTURE_COLUMN_ATTRIBUTES.items()
        for column, attributes in columns.items()
    }
    if observed != expected:
        raise RolloutError("future migration column fingerprint drifted")


def _material_constraints_safe(connection: Connection) -> None:
    tables = tuple(sorted(FUTURE_TABLE_COLUMNS))
    rows = connection.execute(
        text(
            "SELECT r.relname,c.conname,c.contype,c.convalidated,c.condeferrable,"
            "c.condeferred,ARRAY(SELECT a.attname FROM unnest(c.conkey) "
            "WITH ORDINALITY k(attnum,ord) JOIN pg_attribute a "
            "ON a.attrelid=c.conrelid AND a.attnum=k.attnum ORDER BY k.ord),"
            "rn.nspname,rr.relname,ARRAY(SELECT a.attname FROM unnest(c.confkey) "
            "WITH ORDINALITY k(attnum,ord) JOIN pg_attribute a "
            "ON a.attrelid=c.confrelid AND a.attnum=k.attnum ORDER BY k.ord),"
            "c.confdeltype,c.confupdtype,c.confmatchtype,"
            "pg_get_expr(c.conbin,c.conrelid,true) "
            "FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=r.relnamespace "
            "LEFT JOIN pg_class rr ON rr.oid=c.confrelid "
            "LEFT JOIN pg_namespace rn ON rn.oid=rr.relnamespace "
            "WHERE n.nspname='ntubtob' AND r.relname=ANY(:tables)"
        ),
        {"tables": list(tables)},
    ).all()
    if {row[1] for row in rows} != set(MATERIAL_CONSTRAINTS):
        raise RolloutError("future migration constraint set drifted")
    for row in rows:
        (
            table,
            name,
            kind,
            validated,
            deferrable,
            deferred,
            columns,
            referenced_schema,
            referenced_table,
            referenced_columns,
            delete_action,
            update_action,
            match_type,
            expression,
        ) = row
        expected_table, expected_kind, expected_columns, references, expected_expr = (
            MATERIAL_CONSTRAINTS[name]
        )
        observed_columns = tuple(columns or ())
        columns_match = (
            set(observed_columns) == set(expected_columns)
            if kind == "c"
            else observed_columns == expected_columns
        )
        if (
            table != expected_table
            or kind != expected_kind
            or validated is not True
            or deferrable is not False
            or deferred is not False
            or not columns_match
        ):
            raise RolloutError("future migration constraint fingerprint drifted")
        if references is None:
            if (
                referenced_schema is not None
                or referenced_table is not None
                or tuple(referenced_columns or ())
            ):
                raise RolloutError("future migration constraint reference drifted")
        elif (
            referenced_schema,
            referenced_table,
            tuple(referenced_columns or ()),
            delete_action,
            update_action,
            match_type,
        ) != references:
            raise RolloutError("future migration constraint reference drifted")
        if kind == "c":
            if _expression_fingerprint(expression) != _expression_fingerprint(
                expected_expr
            ):
                raise RolloutError("future migration check definition drifted")
        elif expression is not None:
            raise RolloutError("future migration constraint expression drifted")


def _material_indexes_safe(connection: Connection) -> None:
    expected = {
        name: (table, True, kind == "p", columns, None, (0,) * len(columns))
        for name, (table, kind, columns, _, _) in MATERIAL_CONSTRAINTS.items()
        if kind in {"p", "u"}
    }
    expected.update(
        {
            name: (table, unique, False, columns, predicate, order)
            for name, (
                table,
                unique,
                columns,
                predicate,
                order,
            ) in EXPLICIT_MATERIAL_INDEXES.items()
        }
    )
    rows = connection.execute(
        text(
            "SELECT ci.relname,ct.relname,i.indisunique,i.indisprimary,i.indisvalid,"
            "i.indisready,i.indexprs IS NULL,i.indnatts=i.indnkeyatts,am.amname,"
            "ARRAY(SELECT a.attname "
            "FROM unnest(i.indkey) WITH ORDINALITY k(attnum,ord) "
            "JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum "
            "WHERE k.ord<=i.indnkeyatts ORDER BY k.ord),"
            "ARRAY(SELECT option FROM unnest(i.indoption) WITH ORDINALITY "
            "o(option,ord) WHERE o.ord<=i.indnkeyatts ORDER BY o.ord),"
            "pg_get_expr(i.indpred,i.indrelid,true) FROM pg_index i "
            "JOIN pg_class ci ON ci.oid=i.indexrelid JOIN pg_class ct ON ct.oid=i.indrelid "
            "JOIN pg_am am ON am.oid=ci.relam "
            "JOIN pg_namespace n ON n.oid=ct.relnamespace "
            "WHERE n.nspname='ntubtob' AND ct.relname=ANY(:tables)"
        ),
        {"tables": list(FUTURE_TABLE_COLUMNS)},
    ).all()
    if {row[0] for row in rows} != set(expected):
        raise RolloutError("future migration index set drifted")
    for (
        name,
        table,
        unique,
        primary,
        valid,
        ready,
        plain,
        no_includes,
        access_method,
        columns,
        order,
        predicate,
    ) in rows:
        (
            expected_table,
            expected_unique,
            expected_primary,
            expected_columns,
            expected_predicate,
            expected_order,
        ) = expected[name]
        if (
            table != expected_table
            or unique is not expected_unique
            or primary is not expected_primary
            or valid is not True
            or ready is not True
            or plain is not True
            or no_includes is not True
            or access_method != "btree"
            or tuple(columns or ()) != expected_columns
            or tuple(order or ()) != expected_order
            or _expression_fingerprint(predicate)
            != _expression_fingerprint(expected_predicate)
        ):
            raise RolloutError("future migration index fingerprint drifted")


def _material_routines_safe(connection: Connection) -> None:
    expected_bodies = {
        "reject_mobile_notification_mutation": hashlib.sha256(
            _canonical_sql(
                "BEGIN RAISE EXCEPTION 'mobile notification content is immutable'; END;"
            ).encode("utf-8")
        ).hexdigest(),
        "reject_mobile_notification_audit_mutation": hashlib.sha256(
            _canonical_sql(
                "BEGIN RAISE EXCEPTION 'mobile notification audit is append-only'; END;"
            ).encode("utf-8")
        ).hexdigest(),
    }
    functions = connection.execute(
        text(
            "SELECT p.oid,p.proname,p.pronargs,p.prorettype='trigger'::regtype,l.lanname,"
            "p.prokind,p.proretset,p.prosecdef,p.provolatile,p.proisstrict,"
            "p.proleakproof,p.proparallel,p.proconfig IS NULL,p.pronargdefaults,"
            "p.provariadic=0,p.prosrc "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='ntubtob' "
            "AND p.proname=ANY(:functions)"
        ),
        {"functions": list(FUTURE_FUNCTIONS)},
    ).all()
    if len(functions) != len(expected_bodies) or {row[1] for row in functions} != set(
        expected_bodies
    ):
        raise RolloutError("future migration function identity drifted")
    observed_functions = {}
    for (
        oid,
        name,
        args,
        returns_trigger,
        language,
        kind,
        returns_set,
        security_definer,
        volatility,
        strict,
        leakproof,
        parallel,
        no_config,
        argument_defaults,
        no_variadic,
        body,
    ) in functions:
        if (
            args != 0
            or returns_trigger is not True
            or language != "plpgsql"
            or kind != "f"
            or returns_set is not False
            or security_definer is not False
            or volatility != "v"
            or strict is not False
            or leakproof is not False
            or parallel != "u"
            or no_config is not True
            or argument_defaults != 0
            or no_variadic is not True
        ):
            raise RolloutError("future migration function identity drifted")
        observed_functions[name] = (
            oid,
            hashlib.sha256(
                _canonical_sql(body).encode("utf-8") if isinstance(body, str) else b""
            ).hexdigest(),
        )
    if {
        name: value[1] for name, value in observed_functions.items()
    } != expected_bodies:
        raise RolloutError("future migration function body drifted")
    triggers = connection.execute(
        text(
            "SELECT c.relname,t.tgname,t.tgenabled,t.tgtype,t.tgnargs,t.tgattr::text,"
            "t.tgqual,t.tgconstraint,t.tgoldtable,t.tgnewtable,t.tgdeferrable,"
            "t.tginitdeferred,pn.nspname,p.oid,p.proname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace "
            "WHERE n.nspname='ntubtob' "
            "AND NOT t.tgisinternal AND t.tgname=ANY(:triggers)"
        ),
        {"triggers": [name for _, name in FUTURE_TRIGGERS]},
    ).all()
    observed = set()
    for row in triggers:
        (
            table,
            name,
            enabled,
            kind,
            args,
            attrs,
            qual,
            constraint,
            old,
            new,
            defer,
            initial,
            function_schema,
            function_oid,
            function,
        ) = row
        if (
            enabled != "O"
            or kind != 27
            or args != 0
            or attrs != ""
            or qual is not None
            or constraint != 0
            or old is not None
            or new is not None
            or defer is not False
            or initial is not False
        ):
            raise RolloutError("future migration trigger definition drifted")
        observed.add((table, name, function_schema, function_oid, function))
    expected_triggers = {
        (
            "mobile_notifications",
            "mobile_notification_content_immutable",
            "ntubtob",
            observed_functions["reject_mobile_notification_mutation"][0],
            "reject_mobile_notification_mutation",
        ),
        (
            "mobile_notification_publish_audits",
            "mobile_notification_audit_immutable",
            "ntubtob",
            observed_functions["reject_mobile_notification_audit_mutation"][0],
            "reject_mobile_notification_audit_mutation",
        ),
    }
    if observed != expected_triggers:
        raise RolloutError("future migration trigger identity drifted")


def _future_schema_safe(connection: Connection) -> None:
    tables = tuple(sorted(FUTURE_TABLE_COLUMNS))
    _material_columns_safe(connection)
    rls_rows = connection.execute(
        text(
            "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='ntubtob' AND relname=ANY(:tables) ORDER BY relname"
        ),
        {"tables": list(tables)},
    ).all()
    if len(rls_rows) != len(tables) or any(
        row.relname != table
        or row.relrowsecurity is not True
        or row.relforcerowsecurity is not False
        for row, table in zip(rls_rows, tables)
    ):
        raise RolloutError("future migration RLS boundary drifted")
    policy_count = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='ntubtob' AND c.relname=ANY(:tables)"
            ),
            {"tables": list(tables)},
        )
        or 0
    )
    if policy_count != 0:
        raise RolloutError("future migration policy boundary drifted")
    _material_constraints_safe(connection)
    _material_indexes_safe(connection)
    _material_routines_safe(connection)
    version_length = connection.scalar(
        text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_schema='ntubtob' AND table_name='alembic_version' "
            "AND column_name='version_num'"
        )
    )
    if version_length != 64:
        raise RolloutError("Alembic revision storage boundary drifted")
    if any(
        int(connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}")) or 0) != 0
        for table in tables
    ):
        raise RolloutError("new migration tables are not empty")


def _constraint_actions(connection: Connection) -> tuple[str, ...]:
    row = connection.execute(
        text(
            "SELECT c.contype,c.convalidated,pg_get_constraintdef(c.oid,true) "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace "
            "WHERE n.nspname='ntubtob' AND t.relname='event_audit' "
            "AND c.conname='ck_event_audit_action'"
        )
    ).all()
    if len(row) != 1:
        raise RolloutError("event audit constraint is ambiguous")
    constraint_type, validated, definition = row[0]
    if (
        constraint_type != "c"
        or validated is not True
        or not isinstance(definition, str)
        or not definition.startswith("CHECK (")
        or "action" not in definition
        or " NOT VALID" in definition.upper()
    ):
        raise RolloutError("event audit constraint drifted")
    actions = tuple(re.findall(r"'([^']+)'", definition))
    expression = re.sub(r"'[^']+'", "", definition)
    words = tuple(word.lower() for word in re.findall(r"[A-Za-z_]+", expression))
    allowed_words = {"check", "action", "any", "array", "text", "character", "varying"}
    if (
        any(word not in allowed_words for word in words)
        or words.count("check") != 1
        or words.count("action") != 1
        or words.count("any") != 1
        or words.count("array") != 1
        or definition.count("=") != 1
        or any(token in expression for token in ("<", ">", "!", ";"))
    ):
        raise RolloutError("event audit constraint expression drifted")
    return actions


def _catalog_safe(connection: Connection, expected_actions: tuple[str, ...]) -> None:
    if _constraint_actions(connection) != expected_actions:
        raise RolloutError("event audit action contract drifted")
    rls_rows = connection.execute(
        text(
            "SELECT relname,relrowsecurity,relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='ntubtob' AND relname=ANY(:tables) "
            "ORDER BY relname"
        ),
        {"tables": list(EVENT_TABLES)},
    ).all()
    if len(rls_rows) != len(EVENT_TABLES) or any(
        row.relname != table
        or row.relrowsecurity is not True
        or row.relforcerowsecurity is not False
        for row, table in zip(rls_rows, EVENT_TABLES)
    ):
        raise RolloutError("event RLS contract drifted")
    policy_count = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM pg_policy p "
                "JOIN pg_class c ON c.oid=p.polrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='ntubtob' AND c.relname=ANY(:tables)"
            ),
            {"tables": list(EVENT_TABLES)},
        )
        or 0
    )
    if policy_count != 0:
        raise RolloutError("event policy boundary drifted")
    _validate_append_only(connection)


def _canonical_sql(value: str) -> str:
    return " ".join(value.split())


def _validate_append_only(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "SELECT t.tgenabled,t.tgtype,t.tgnargs,t.tgattr::text,t.tgqual,"
            "t.tgconstraint,t.tgoldtable,t.tgnewtable,t.tgdeferrable,"
            "t.tginitdeferred,fn_ns.nspname,p.pronargs,"
            "p.prorettype='trigger'::regtype,l.lanname,p.prosrc "
            "FROM pg_trigger t "
            "JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_proc p ON p.oid=t.tgfoid "
            "JOIN pg_namespace fn_ns ON fn_ns.oid=p.pronamespace "
            "JOIN pg_language l ON l.oid=p.prolang "
            "WHERE n.nspname='ntubtob' AND c.relname='event_audit' "
            "AND t.tgname='event_audit_append_only' AND NOT t.tgisinternal "
            "AND p.proname='reject_audit_mutation'"
        )
    ).all()
    if len(rows) != 1:
        raise RolloutError("event audit append-only boundary is ambiguous")
    (
        enabled,
        trigger_type,
        trigger_args,
        update_columns,
        when_clause,
        constraint_oid,
        old_transition_table,
        new_transition_table,
        deferrable,
        initially_deferred,
        function_schema,
        function_args,
        returns_trigger,
        language,
        body,
    ) = rows[0]
    body_digest = (
        hashlib.sha256(_canonical_sql(body).encode("utf-8")).hexdigest()
        if isinstance(body, str)
        else ""
    )
    if enabled != "O" or trigger_type != 27 or trigger_args != 0:
        raise RolloutError("event audit append-only mismatch: trigger_core")
    if update_columns != "":
        raise RolloutError("event audit append-only mismatch: trigger_columns")
    if when_clause is not None:
        raise RolloutError("event audit append-only mismatch: trigger_when")
    if constraint_oid != 0:
        raise RolloutError("event audit append-only mismatch: trigger_constraint")
    if old_transition_table is not None or new_transition_table is not None:
        raise RolloutError("event audit append-only mismatch: trigger_transition")
    if deferrable is not False or initially_deferred is not False:
        raise RolloutError("event audit append-only mismatch: trigger_deferrability")
    if (
        function_schema != "ntubtob"
        or function_args != 0
        or returns_trigger is not True
        or language != "plpgsql"
    ):
        raise RolloutError("event audit append-only mismatch: function_identity")
    if body_digest != APPEND_ONLY_BODY_SHA256:
        raise RolloutError("event audit append-only mismatch: function_body")


def _logging_safe(connection: Connection) -> bool:
    row = connection.execute(
        text(
            "SELECT "
            "coalesce(current_setting('log_statement',true),'all') IN ('none','ddl'),"
            "coalesce(current_setting('log_min_duration_statement',true),'0')::integer=-1,"
            "coalesce(current_setting('log_min_duration_sample',true),'0')::integer=-1,"
            "coalesce(current_setting('log_duration',true),'on')='off',"
            "coalesce(current_setting('log_transaction_sample_rate',true),'1')::numeric=0,"
            "coalesce(current_setting('pgaudit.log',true),'none') IN ('none',''),"
            "coalesce(current_setting('log_parameter_max_length_on_error',true),'-1')::integer=0"
        )
    ).one()
    return all(value is True for value in row)


def _application_dml_count(connection: Connection) -> int:
    return int(
        connection.scalar(
            text(
                "SELECT coalesce(sum(n_tup_ins+n_tup_upd+n_tup_del),0) "
                "FROM pg_stat_xact_user_tables "
                "WHERE schemaname='ntubtob' AND relname<>'alembic_version'"
            )
        )
        or 0
    )


def _upgrade(connection: Connection) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, TARGET_REVISION)


def _run_locked(
    connection: Connection,
    *,
    execute: bool,
    fail_after_migration: bool = False,
    migration_runner: Callable[[Connection], None] = _upgrade,
) -> dict[str, object]:
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '45s'"))
    connection.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
    )
    revision = _current_revision(connection)
    if revision != SOURCE_REVISION:
        if revision == TARGET_REVISION:
            raise RolloutError("event migration is already forward; do not retry")
        raise RolloutError("event migration revision drifted")
    if not _logging_safe(connection):
        raise RolloutError("database logging boundary is unsafe")
    _catalog_safe(connection, OLD_ACTIONS)
    _phase_c_identity_safe(connection)
    _future_objects_absent(connection)
    if _application_dml_count(connection) != 0:
        raise RolloutError("transaction contains prior application DML")
    if not execute:
        return {
            "mode": "dry-run",
            "status": "ready",
            "source_revision": SOURCE_REVISION,
            "target_revision": TARGET_REVISION,
            "application_dml_count": 0,
        }

    migration_runner(connection)
    if fail_after_migration:
        raise RolloutError("injected migration failure")
    if _current_revision(connection) != TARGET_REVISION:
        raise RolloutError("event migration postcheck revision failed")
    _catalog_safe(connection, NEW_ACTIONS)
    _phase_c_identity_safe(connection)
    _future_schema_safe(connection)
    dml_count = _application_dml_count(connection)
    if dml_count != 0:
        raise RolloutError("event migration performed application DML")
    return {
        "mode": "execute",
        "status": "applied",
        "source_revision": SOURCE_REVISION,
        "target_revision": TARGET_REVISION,
        "application_dml_count": 0,
    }


def run(
    mode: str,
    database_url: str,
    acknowledgement: str | None = None,
    *,
    engine_factory: Callable[..., Engine] = create_engine,
) -> dict[str, object]:
    verify_artifact()
    if mode not in {"dry-run", "execute"}:
        raise RolloutError("rollout mode is invalid")
    execute = mode == "execute"
    if execute and acknowledgement != EXECUTION_ACKNOWLEDGEMENT:
        raise RolloutError("event migration execution is not acknowledged")
    if not execute and acknowledgement is not None:
        raise RolloutError("dry-run rejects execution acknowledgement")
    engine = engine_factory(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            if not execute:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            result = _run_locked(connection, execute=execute)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return result
    finally:
        engine.dispose()


def main() -> None:
    raise SystemExit("TASK-164 operator requires its reviewed launcher")


if __name__ == "__main__":
    main()
