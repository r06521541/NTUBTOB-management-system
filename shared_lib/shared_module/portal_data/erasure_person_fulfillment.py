"""Default-unused, reviewed linked-Person fulfillment over existing executors.

The trusted caller captures before requesting and retains this sealed snapshot.
Reviews are explicit whole-free-content decisions, not inferred authorship or a
public permission API. No raw credentials are projected; full SQL row digests
include ciphertext/token versions. Unknown custody/provider effects permit local
cleanup but retain roots and credentials. No backup completion/runtime wiring.
This is not a free-text mention scanner. The trusted upstream inventory must add
reviewed rows without account FKs explicitly; lack of an FK is not a review.
Exact reviewed shared-game text patches preserve the game and its schedule.
Persistent administrators may submit an intake without a survivor; execution
requires another reachable administrator or the exact durable0019 suspension
for this verified job/generation/scope. This never resumes management or grants
legacy-runtime allowlist authority.
"""

import hmac
import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..erasure_restore_binding import RestoreBindingCodec
from ..mobile_api import utc_now
from . import erasure_item_models, erasure_models  # Register the retained FK graph.
from .domain import AuthorizationError
from .erasure_fulfillment import (
    FulfillmentResult,
    PendingIdentityFulfillment,
    _confirmed,
    _connection,
    _digest,
    _hash,
    _rows,
)
from .erasure_legacy_execution import (
    LegacyErasureExecutor,
    _locked_scope,
    legacy_item_binding,
)
from .erasure_management_guard import (
    ManagementGuardUnavailable,
    read_applied_admin_suspension,
)
from .erasure_privacy_execution import PrivacyDispositionExecutor
from .erasure_provider_execution import (
    PreparedProviderEffect,
    ProviderErasureExecutor,
    _Rejected,
    _uuid,
)
from .erasure_structured_execution import (
    DELETE_ORDER,
    StructuredErasureExecutor,
    _locked_inventory,
    structured_item_binding,
)
from .identity_lifecycle import IdentityLifecycleRepository
from .models import PortalDataBase

# Every known free-content field of these related rows must be explicitly reviewed.
# Empty tuples are structural-only decisions; they still require exact row binding.
CONTENT_FIELDS = {
    "identity_review_messages": ("body",),
    "access_audit": ("reason", "before_state", "after_state"),
    "guest_qualification_audits": ("reason", "before_state", "after_state"),
    "events": ("title",),
    "activities": ("title",),
    "games": ("location", "home_team", "away_team"),
    "event_audit": ("reason", "details"),
    "mobile_notifications": ("title", "body"),
    "mobile_notification_publish_audits": (),
    "event_notification_publish_audits": (),
    "person_qualifications": ("reason",),
    "event_invitee_overrides": ("reason",),
    "event_invitees": ("reason",),
    "event_managers": (),
    "identity_review_threads": (),
}
LEGACY_TABLES = ("game_attendance_replies", "line_users", "members")
LOCAL_TABLES = (
    "apple_provider_notifications",
    "apple_provider_code_exchanges",
    "account_deletion_requests",
    "event_managers",
    "event_invitee_overrides",
    "event_invitees",
    "person_qualifications",
)
ROW_TABLES = tuple(
    dict.fromkeys(
        (
            *LEGACY_TABLES,
            *DELETE_ORDER,
            *LOCAL_TABLES,
            *CONTENT_FIELDS,
            "apple_provider_credentials",
        )
    )
)
LOCK_TABLES = (
    "people",
    "auth_identities",
    "portal_authority_state",
    *ROW_TABLES,
    "account_erasure_jobs",
    "account_erasure_items",
    "account_erasure_item_events",
    "account_erasure_steps",
)
ROOT_DELETE_TABLES = (
    "people",
    "auth_identities",
    *LEGACY_TABLES,
    *DELETE_ORDER,
    *LOCAL_TABLES,
    "access_audit",
    "guest_qualification_audits",
    "identity_review_messages",
    "apple_provider_credentials",
)


@dataclass(frozen=True, repr=False)
class ReviewedPersonDisposition:
    table: str
    row_id: int
    old_digest: str
    action: str
    patch_json: str
    post_digest: str
    reviewed_fields: tuple
    decision: str


@dataclass(frozen=True, repr=False)
class PersonIdentitySnapshot:
    identity_id: int
    provider: str
    generation: str
    digest: str
    restore_binding: object


@dataclass(frozen=True, repr=False)
class SessionVerificationBaseline:
    session_id: str
    status: str
    revoked_at: object
    updated_at: object
    access_epoch: int


@dataclass(frozen=True, repr=False)
class PersonSnapshot:
    person_id: int
    generation: str
    person_digest: str
    identities: tuple
    rows: tuple
    sessions: tuple
    legacy: object
    structured: object
    local_ids: tuple
    reviews: tuple

    @property
    def scope_hash(self):
        return _digest(
            [
                "person_fulfillment_v1",
                self.person_id,
                self.generation,
                self.person_digest,
                [
                    (
                        i.identity_id,
                        i.provider,
                        i.generation,
                        i.digest,
                        i.restore_binding.version,
                        i.restore_binding.key_id,
                        i.restore_binding.digest,
                    )
                    for i in self.identities
                ],
                self.rows,
                [
                    (
                        s.session_id,
                        s.status,
                        s.revoked_at.isoformat() if s.revoked_at else None,
                        s.updated_at.isoformat(),
                        s.access_epoch,
                    )
                    for s in self.sessions
                ],
                (
                    self.legacy.member_ids,
                    self.legacy.line_user_ids,
                    self.legacy.reply_ids,
                ),
                (
                    self.structured.person_id,
                    self.structured.identities,
                    self.structured.rows,
                    self.structured.delivery_proofs,
                ),
                self.local_ids,
                [
                    (
                        r.table,
                        r.row_id,
                        r.old_digest,
                        r.action,
                        r.patch_json,
                        r.post_digest,
                        r.reviewed_fields,
                        r.decision,
                    )
                    for r in self.reviews
                ],
            ]
        )


@dataclass(frozen=True, repr=False)
class PersonRestoreRecord:
    job_id: str
    item_id: str
    scope_hash: str
    person_generation: str
    identity_id: int
    identity_generation: str
    binding: object


def seal_reviewed_person_disposition(
    connection, *, table, row_id, action, patch, reviewed_fields, decision
):
    """Seal an ALREADY reviewed decision; calling this does not perform review.

    reviewed_fields must cover every listed free field, including content retained
    unchanged by a partial patch. The trusted reviewer asserts no target content
    remains after a shared update/retain. A client or classifier cannot supply it.
    """
    if (
        type(table) is not str
        or table not in CONTENT_FIELDS
        or type(row_id) is not int
        or row_id <= 0
        or type(action) is not str
        or action not in {"update", "delete", "retain"}
        or type(patch) is not dict
        or type(reviewed_fields) is not tuple
        or reviewed_fields != CONTENT_FIELDS[table]
        or type(decision) is not str
        or decision
        != (
            "own_content_delete"
            if action == "delete"
            else "no_target_content_after_disposition"
        )
        or (action != "update" and patch)
        or (action == "update" and not patch)
    ):
        raise _Rejected("reviewed_dispositions_required")
    if table == "games" and (
        action == "delete"
        or any(
            type(field) is not str
            or field not in CONTENT_FIELDS["games"]
            or (value is not None and type(value) is not str)
            for field, value in patch.items()
        )
    ):
        raise _Rejected("invalid_game_disposition")
    serialized = json.dumps(
        patch, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    )
    if len(serialized) > 65536:
        raise _Rejected("invalid_disposition")
    row = connection.execute(
        text(
            f"SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),"
            "encode(sha256(convert_to((to_jsonb(t)||CAST(:patch AS jsonb))::text,'UTF8')),'hex') "
            f"FROM ntubtob.{table} t WHERE id=:id"
        ),
        {"id": row_id, "patch": serialized},
    ).first()
    if row is None:
        raise _Rejected("reviewed_row_missing")
    return ReviewedPersonDisposition(
        table, row_id, row[0], action, serialized, row[1], reviewed_fields, decision
    )


def _lock(connection):
    if tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) not in (
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
        ("0022_erasure_retention",),
        ("0023_erasure_minimal_retention",),
    ):
        raise _Rejected("schema_not_ready")
    connection.execute(
        text(
            "LOCK TABLE "
            + ",".join("ntubtob." + name for name in LOCK_TABLES)
            + " IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for name in LOCK_TABLES:
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{name}'::regclass)"
                )
            )
            is not False
        ):
            raise _Rejected("unfiltered_tables_required")
    # No newly introduced FK, cascade or cross-schema store may be silently lost.
    actual = _rows(
        connection,
        "SELECT ns.nspname,src.relname,dst.relname,c.confdeltype,"
        "ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(n,o) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.n ORDER BY k.o),"
        "ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY k(n,o) JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.n ORDER BY k.o) "
        "FROM pg_constraint c JOIN pg_class src ON src.oid=c.conrelid JOIN pg_namespace ns ON ns.oid=src.relnamespace "
        "JOIN pg_class dst ON dst.oid=c.confrelid JOIN pg_namespace nd ON nd.oid=dst.relnamespace "
        "WHERE c.contype='f' AND nd.nspname='ntubtob' AND dst.relname=ANY(:tables)",
        tables=list(ROOT_DELETE_TABLES),
    )
    expected = set()
    codes = {
        None: "a",
        "NO ACTION": "a",
        "RESTRICT": "r",
        "CASCADE": "c",
        "SET NULL": "n",
        "SET DEFAULT": "d",
    }
    intake_schema = tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) in {
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
        ("0022_erasure_retention",),
        ("0023_erasure_minimal_retention",),
    }
    for table in PortalDataBase.metadata.tables.values():
        if table.name == "account_erasure_intakes" and not intake_schema:
            continue
        for fk in table.foreign_key_constraints:
            if fk.referred_table.name in ROOT_DELETE_TABLES:
                expected.add(
                    (
                        table.schema,
                        table.name,
                        fk.referred_table.name,
                        codes[fk.ondelete],
                        tuple(c.name for c in fk.columns),
                        tuple(e.column.name for e in fk.elements),
                    )
                )
    actual = tuple(row[:4] + (tuple(row[4]), tuple(row[5])) for row in actual)
    if len(actual) != len(expected) or set(actual) != expected:
        raise _Rejected("schema_changed")


def _require_persistent_authority(connection, person_id):
    """Validate authority metadata even during read-only intake; grant nothing."""
    if (
        connection.scalar(
            text(
                "SELECT pg_catalog.row_security_active('ntubtob.portal_authority_state'::regclass)"
            )
        )
        is not False
    ):
        raise _Rejected("admin_authority_unavailable")
    states = connection.execute(
        text(
            "SELECT singleton_id,mode,epoch FROM ntubtob.portal_authority_state ORDER BY singleton_id FOR UPDATE"
        )
    ).all()
    if (
        len(states) != 1
        or type(states[0][0]) is not int
        or states[0][0] != 1
        or states[0][1] != "persistent"
        or type(states[0][2]) is not int
        or states[0][2] < 1
    ):
        raise _Rejected("admin_authority_unavailable")


def _require_admin_survivor(connection, person_id, *, job_id, generation, scope_hash):
    """Execution-only survivor check under the caller's canonical/root locks."""
    _require_persistent_authority(connection, person_id)
    lifecycle = IdentityLifecycleRepository(
        connection.engine,
        authority_mode="persistent",
        erasure_checks_enabled=True,
    )
    try:
        with (
            Session(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            remaining = lifecycle._reachable_persistent_admin_count(
                session,
                excluding_person_id=person_id,
            )
    except AuthorizationError:
        raise _Rejected("admin_authority_unavailable") from None
    if type(remaining) is not int or remaining < 0:
        raise _Rejected("admin_authority_unavailable")
    if remaining == 0:
        # Read the native immutable operation anew on this exact transaction.
        # A count failure, callback audit or client flag is never a substitute.
        try:
            read_applied_admin_suspension(
                connection,
                job_id=job_id,
                generation=generation,
                scope_hash=scope_hash,
            )
        except ManagementGuardUnavailable:
            raise _Rejected("admin_recovery_required") from None


def _roots(connection, person_id, *, job_id, generation, scope_hash):
    def check_admin(checked_connection, checked_person):
        _require_admin_survivor(
            checked_connection,
            checked_person,
            job_id=job_id,
            generation=generation,
            scope_hash=scope_hash,
        )

    return _load_roots(connection, person_id, check_admin)


def _capture_roots(connection, person_id):
    """Intake is not permission to execute or to bypass recovery afterward."""
    return _load_roots(connection, person_id, _require_persistent_authority)


def _load_roots(connection, person_id, admin_check):
    person = connection.execute(
        text(
            "SELECT account_generation::text,encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),portal_access_level "
            "FROM ntubtob.people t WHERE id=:id FOR UPDATE"
        ),
        {"id": person_id},
    ).first()
    if person is None:
        raise _Rejected("person_missing")
    if person[2] == "admin":
        admin_check(connection, person_id)
    identities = _rows(
        connection,
        "SELECT id,provider,account_generation::text,encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') "
        "FROM ntubtob.auth_identities t WHERE person_id=:person ORDER BY id FOR UPDATE",
        person=person_id,
    )
    if not identities or any(
        row[1] not in {"apple", "line", "google"} for row in identities
    ):
        raise _Rejected("linked_identities_required")
    return person[:2], identities


def _inventory(
    connection, person, identities, *, anchors=(), baselines=(), verified_at=None
):
    """Fixed ownership joins; raw content/credentials stay in SQL digests."""
    _lock(connection)
    legacy = _locked_scope(connection, person)
    structured = _locked_inventory(connection, person)
    parameters = dict(person=person, identities=[i[0] for i in identities])
    anchor = dict(anchors)
    result = {}

    def collect(table, predicate, **extra):
        values = dict(
            parameters, **extra, anchors=[row[0] for row in anchor.get(table, ())]
        )
        identifier_sql = (
            "t.id::text" if table == "account_deletion_requests" else "t.id"
        )
        result[table] = _rows(
            connection,
            f"SELECT {identifier_sql},encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM ntubtob.{table} t "
            f"WHERE ({predicate}) OR {identifier_sql}=ANY(:anchors) ORDER BY t.id",
            **values,
        )
        return [row[0] for row in result[table]]

    for table, ids in zip(
        LEGACY_TABLES, (legacy.reply_ids, legacy.line_user_ids, legacy.member_ids)
    ):
        collect(table, "t.id=ANY(:ids)", ids=list(ids))
    for table, rows in structured.rows:
        collect(table, "t.id=ANY(:ids)", ids=[row[0] for row in rows])
    local = {}
    for table in LOCAL_TABLES:
        predicate = (
            "t.auth_identity_id=ANY(:identities)"
            if table.startswith("apple_")
            else "t.person_id=:person"
        )
        identifier_sql = (
            "t.id::text" if table == "account_deletion_requests" else "t.id"
        )
        local[table] = tuple(
            connection.scalars(
                text(
                    f"SELECT {identifier_sql} FROM ntubtob.{table} t WHERE {predicate} ORDER BY t.id"
                ),
                parameters,
            )
        )
        actor = {
            "person_qualifications": "granted_by_person_id",
            "event_invitee_overrides": "actor_person_id",
            "event_invitees": "actor_person_id",
            "event_managers": "assigned_by_person_id",
        }.get(table)
        collect(table, predicate + (f" OR t.{actor}=:person" if actor else ""))
    collect("apple_provider_credentials", "t.auth_identity_id=ANY(:identities)")
    collect(
        "access_audit",
        "t.actor_person_id=:person OR t.target_person_id=:person OR t.auth_identity_id=ANY(:identities)",
    )
    collect(
        "guest_qualification_audits",
        "t.actor_person_id=:person OR t.target_person_id=:person OR t.qualification_id=ANY(:ids)",
        ids=list(local["person_qualifications"]),
    )
    event_ids = collect(
        "events",
        "t.created_by_person_id=:person OR t.id IN (SELECT event_id FROM ntubtob.event_attendance_replies WHERE person_id=:person UNION SELECT event_id FROM ntubtob.event_invitees WHERE person_id=:person UNION SELECT event_id FROM ntubtob.event_invitee_overrides WHERE person_id=:person UNION SELECT event_id FROM ntubtob.event_managers WHERE person_id=:person UNION SELECT a.event_id FROM ntubtob.activities a JOIN ntubtob.activity_attendance_replies r ON r.activity_id=a.id WHERE r.person_id=:person)",
    )
    collect("activities", "t.event_id=ANY(:events)", events=event_ids)
    collect(
        "event_audit",
        "t.actor_person_id=:person OR t.event_id=ANY(:events)",
        events=event_ids,
    )
    threads = collect(
        "identity_review_threads",
        "t.auth_identity_id=ANY(:identities) OR t.id IN (SELECT thread_id FROM ntubtob.identity_review_messages WHERE sender_person_id=:person)",
    )
    collect(
        "identity_review_messages",
        "t.sender_person_id=:person OR t.thread_id=ANY(:threads)",
        threads=threads,
    )
    notifications = collect(
        "mobile_notifications",
        "t.id IN (SELECT notification_id FROM ntubtob.mobile_notification_recipients WHERE person_id=:person UNION SELECT notification_id FROM ntubtob.mobile_notification_publish_audits WHERE actor_person_id=:person OR (audience_type='individual' AND audience_reference_id=:person) UNION SELECT notification_id FROM ntubtob.event_notification_publish_audits WHERE actor_person_id=:person OR event_id=ANY(:events))",
        events=event_ids,
    )
    collect(
        "mobile_notification_publish_audits",
        "t.notification_id=ANY(:notifications) OR t.actor_person_id=:person",
        notifications=notifications,
    )
    collect(
        "event_notification_publish_audits",
        "t.notification_id=ANY(:notifications) OR t.actor_person_id=:person",
        notifications=notifications,
    )
    collect(
        "games",
        "t.id IN (SELECT game_id FROM ntubtob.game_attendance_replies WHERE id=ANY(:replies) UNION SELECT game_id FROM ntubtob.activities WHERE event_id=ANY(:events) UNION SELECT destination_game_id FROM ntubtob.mobile_notifications WHERE id=ANY(:notifications))",
        replies=list(legacy.reply_ids),
        events=event_ids,
        notifications=notifications,
    )
    if baselines:
        current = dict(result["mobile_sessions"])
        for baseline in baselines:
            if baseline.session_id not in current or baseline.status != "active":
                continue  # Already-revoked sessions retain their entire original hash.
            row = connection.execute(
                text(
                    "SELECT status,revoked_at,updated_at,access_epoch,"
                    "encode(sha256(convert_to((to_jsonb(t)||jsonb_build_object('status',CAST(:status AS text),"
                    "'revoked_at',CAST(:revoked AS timestamptz),'updated_at',CAST(:updated AS timestamptz),'access_epoch',CAST(:epoch AS integer)))::text,'UTF8')),'hex') "
                    "FROM ntubtob.mobile_sessions t WHERE id=:id"
                ),
                dict(
                    id=baseline.session_id,
                    status=baseline.status,
                    revoked=baseline.revoked_at,
                    updated=baseline.updated_at,
                    epoch=baseline.access_epoch,
                ),
            ).one()
            if tuple(row[:4]) != (
                "revoked",
                verified_at,
                verified_at,
                baseline.access_epoch + 1,
            ):
                raise _Rejected("verification_transform_changed")
            current[baseline.session_id] = row[4]
        result["mobile_sessions"] = tuple(sorted(current.items()))
    return (
        tuple((name, result[name]) for name in ROW_TABLES),
        legacy,
        structured,
        tuple((name, local[name]) for name in LOCAL_TABLES),
    )


def _check_reviews(connection, person, identities, rows, local_ids, reviews):
    if type(reviews) is not tuple or any(
        type(r) is not ReviewedPersonDisposition for r in reviews
    ):
        raise _Rejected("reviewed_dispositions_required")
    required = {
        (table, row[0]): row[1]
        for table, values in rows
        if table in CONTENT_FIELDS
        for row in values
    }
    if (
        len(reviews) != len(required)
        or {(r.table, r.row_id): r.old_digest for r in reviews} != required
    ):
        raise _Rejected("reviewed_dispositions_required")
    local = dict(local_ids)
    identity_ids = [row[0] for row in identities]
    for review in reviews:
        # Re-seal against the same locked pre-request image to reject fabricated hashes.
        actual = seal_reviewed_person_disposition(
            connection,
            table=review.table,
            row_id=review.row_id,
            action=review.action,
            patch=json.loads(review.patch_json),
            reviewed_fields=review.reviewed_fields,
            decision=review.decision,
        )
        if actual != review:
            raise _Rejected("reviewed_dispositions_required")
        own = False
        if review.table in local:
            own = review.row_id in local[review.table]
        elif review.table == "identity_review_messages":
            own = (
                connection.scalar(
                    text(
                        "SELECT m.sender_person_id=:person OR (m.sender_role='applicant' AND t.auth_identity_id=ANY(:identities)) FROM ntubtob.identity_review_messages m JOIN ntubtob.identity_review_threads t ON t.id=m.thread_id WHERE m.id=:id"
                    ),
                    dict(person=person, identities=identity_ids, id=review.row_id),
                )
                is True
            )
        elif review.table in {"access_audit", "guest_qualification_audits"}:
            extra = (
                " OR (target_person_id IS NULL AND auth_identity_id=ANY(:identities))"
                if review.table == "access_audit"
                else ""
            )
            own = (
                connection.scalar(
                    text(
                        f"SELECT target_person_id=:person{extra} FROM ntubtob.{review.table} WHERE id=:id"
                    ),
                    dict(person=person, identities=identity_ids, id=review.row_id),
                )
                is True
            )
        if (own and review.action != "delete") or (
            not own and review.action == "delete"
        ):
            raise _Rejected("content_ownership_changed")


def capture_person_snapshot(
    session, person_id, *, reviewed_dispositions, restore_codec, provider_audiences
):
    if (
        type(person_id) is not int
        or person_id <= 0
        or type(restore_codec) is not RestoreBindingCodec
        or type(provider_audiences) is not dict
    ):
        raise _Rejected("invalid_snapshot")
    if type(reviewed_dispositions) is not tuple or any(
        type(review) is not ReviewedPersonDisposition
        for review in reviewed_dispositions
    ):
        raise _Rejected("reviewed_dispositions_required")
    # Additional exact reviewed rows can be found by the authorized content
    # inventory even without an account FK. They never override relationship
    # discovery or establish that another person's content is ours to delete.
    anchors = {table: [] for table in CONTENT_FIELDS}
    for review in reviewed_dispositions:
        if (
            type(review.table) is not str
            or review.table not in CONTENT_FIELDS
            or type(review.row_id) is not int
            or review.row_id <= 0
        ):
            raise _Rejected("reviewed_dispositions_required")
        _hash(review.old_digest)
        anchors[review.table].append((review.row_id, review.old_digest))
    connection = _connection(session)
    person, identities = _capture_roots(connection, person_id)
    rows, legacy, structured, local = _inventory(
        connection,
        person_id,
        identities,
        anchors=tuple((table, tuple(values)) for table, values in anchors.items()),
    )
    if _capture_roots(connection, person_id) != (person, identities):
        raise _Rejected("inventory_changed")
    _check_reviews(
        connection, person_id, identities, rows, local, reviewed_dispositions
    )
    captured = []
    for identifier, provider, generation, digest in identities:
        subject = connection.scalar(
            text("SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": identifier},
        )
        binding = restore_codec.bind(
            provider=provider,
            audience=provider_audiences.get(provider),
            subject=subject,
            generation=generation,
        )
        captured.append(
            PersonIdentitySnapshot(identifier, provider, generation, digest, binding)
        )
    sessions = tuple(
        SessionVerificationBaseline(*row)
        for row in connection.execute(
            text(
                "SELECT id,status,revoked_at,updated_at,access_epoch FROM ntubtob.mobile_sessions WHERE person_id=:person ORDER BY id"
            ),
            {"person": person_id},
        )
    )
    return PersonSnapshot(
        person_id,
        person[0],
        person[1],
        tuple(captured),
        rows,
        sessions,
        legacy,
        structured,
        local,
        tuple(
            sorted(
                reviewed_dispositions,
                key=lambda r: (list(CONTENT_FIELDS).index(r.table), r.row_id),
            )
        ),
    )


def _review_label(review):
    return "review:" + review.table + ":" + str(review.row_id)


def _specs(connection, job_id, snapshot):
    result = {
        label: (stage, _digest(["person_item_v1", job_id, snapshot.scope_hash, label]))
        for label, stage in (
            ("local", "manual_redaction"),
            ("final", "online_erasure"),
            *(
                ("provider:" + str(i.identity_id), "provider_revocation")
                for i in snapshot.identities
            ),
            *(
                ("restore:" + str(i.identity_id), "restore_suppression")
                for i in snapshot.identities
            ),
        )
    }
    if (
        snapshot.legacy.member_ids
        or snapshot.legacy.line_user_ids
        or snapshot.legacy.reply_ids
    ):
        result["legacy"] = (
            "online_erasure",
            legacy_item_binding(job_id, snapshot.generation, snapshot.legacy),
        )
    if any(values for _, values in snapshot.structured.rows):
        result["structured"] = (
            "online_erasure",
            structured_item_binding(job_id, snapshot.generation, snapshot.structured),
        )
    local = dict(snapshot.local_ids)
    for review in snapshot.reviews:
        if review.action == "retain" or (
            review.action == "delete" and review.row_id in local.get(review.table, ())
        ):
            continue
        binding = connection.scalar(
            text(
                "SELECT encode(sha256(convert_to(jsonb_build_array('privacy_mutation_v1',CAST(:job AS uuid),CAST(:generation AS uuid),CAST(:table AS text),CAST(:row AS bigint),CAST(:old AS text),CAST(:patch AS jsonb),CAST(:action AS text))::text,'UTF8')),'hex')"
            ),
            dict(
                job=job_id,
                generation=snapshot.generation,
                table=review.table,
                row=review.row_id,
                old=review.old_digest,
                patch=review.patch_json,
                action=review.action,
            ),
        )
        result[_review_label(review)] = ("manual_redaction", binding)
    return result


class PersonFulfillment:
    _now = PendingIdentityFulfillment._now
    _event = staticmethod(PendingIdentityFulfillment._event)
    _fence = staticmethod(PendingIdentityFulfillment._fence)
    _failure = staticmethod(PendingIdentityFulfillment._failure)

    @staticmethod
    def _delete(connection, table, rows):
        if table != "account_deletion_requests":
            return PendingIdentityFulfillment._delete(connection, table, rows)
        identifiers = [row[0] for row in rows]
        changed = connection.execute(
            text(
                "DELETE FROM ntubtob.account_deletion_requests WHERE id::text=ANY(:ids)"
            ),
            {"ids": identifiers},
        )
        if changed.rowcount != len(identifiers) or connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM ntubtob.account_deletion_requests WHERE id::text=ANY(:ids))"
            ),
            {"ids": identifiers},
        ):
            raise _Rejected("deletion_not_verified")

    def __init__(self, engine, prepare_provider, restore_store, *, clock=utc_now):
        if (
            not isinstance(engine, Engine)
            or not callable(prepare_provider)
            or not callable(clock)
            or not callable(getattr(restore_store, "put", None))
            or not callable(getattr(restore_store, "read", None))
        ):
            raise ValueError("invalid_configuration")
        self.engine, self.prepare_provider, self.restore_store, self.clock = (
            engine,
            prepare_provider,
            restore_store,
            clock,
        )

    def _context(self, session, job_id, snapshot, *, create=False):
        return self._context_on(_connection(session), job_id, snapshot, create=create)

    def _context_on(self, connection, job_id, snapshot, *, create=False):
        _uuid(job_id)
        if type(snapshot) is not PersonSnapshot:
            raise _Rejected("invalid_snapshot")
        job = (
            connection.execute(
                text(
                    "SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE"
                ),
                {"id": job_id},
            )
            .mappings()
            .first()
        )
        if job and job["status"] in {"online_completed", "completed"}:
            raise _Rejected("receipt_read_required")
        if job is None or job["status"] not in {
            "verified",
            "processing",
            "needs_attention",
        }:
            raise _Rejected("verified_job_required")
        if (
            job["target_kind"] != "person"
            or job["person_id"] != snapshot.person_id
            or job["auth_identity_id"] is not None
            or str(job["expected_generation"]) != snapshot.generation
            or job["scope_version"] != 1
            or not hmac.compare_digest(job["scope_hash"], snapshot.scope_hash)
        ):
            raise _Rejected("scope_changed")
        binding = dict(
            job_id=job_id,
            generation=snapshot.generation,
            scope_hash=snapshot.scope_hash,
        )
        person, identities = _roots(connection, snapshot.person_id, **binding)
        if tuple(person) != (
            snapshot.generation,
            snapshot.person_digest,
        ) or identities != tuple(
            (i.identity_id, i.provider, i.generation, i.digest)
            for i in snapshot.identities
        ):
            raise _Rejected("scope_changed")
        items = (
            connection.execute(
                text(
                    "SELECT * FROM ntubtob.account_erasure_items WHERE job_id=:job ORDER BY id FOR UPDATE"
                ),
                {"job": job_id},
            )
            .mappings()
            .all()
        )
        current, legacy, structured, local = _inventory(
            connection,
            snapshot.person_id,
            identities,
            anchors=snapshot.rows,
            baselines=snapshot.sessions,
            verified_at=job["verified_at"],
        )
        if _roots(connection, snapshot.person_id, **binding) != (person, identities):
            raise _Rejected("inventory_changed")
        if connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs WHERE id<>:job AND (person_id=:person OR auth_identity_id=ANY(:identities)))"
            ),
            dict(
                job=job_id,
                person=snapshot.person_id,
                identities=[i.identity_id for i in snapshot.identities],
            ),
        ):
            raise _Rejected("ownership_conflict")
        specs = _specs(connection, job_id, snapshot)
        if create and not items:
            if (
                current != snapshot.rows
                or legacy != snapshot.legacy
                or structured != snapshot.structured
                or local != snapshot.local_ids
            ):
                raise _Rejected("inventory_changed")
            now = self._now(job)
            for stage, binding in specs.values():
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_items (id,job_id,stage,binding_hash,expected_generation,created_at) VALUES (:id,:job,:stage,:binding,:generation,:now)"
                    ),
                    dict(
                        id=str(uuid4()),
                        job=job_id,
                        stage=stage,
                        binding=binding,
                        generation=snapshot.generation,
                        now=now,
                    ),
                )
            items = (
                connection.execute(
                    text(
                        "SELECT * FROM ntubtob.account_erasure_items WHERE job_id=:job ORDER BY id FOR UPDATE"
                    ),
                    {"job": job_id},
                )
                .mappings()
                .all()
            )
        inverse = {value: label for label, value in specs.items()}
        if (
            len(items) != len(inverse)
            or {(i["stage"], i["binding_hash"]) for i in items} != set(inverse)
            or any(str(i["expected_generation"]) != snapshot.generation for i in items)
        ):
            raise _Rejected("workset_changed")
        mapped = {inverse[(i["stage"], i["binding_hash"])]: i for i in items}
        events = {}
        for label, item in mapped.items():
            row = connection.execute(
                text(
                    "SELECT event_sequence,event_kind,result_code FROM ntubtob.account_erasure_item_events WHERE item_id=:id ORDER BY event_sequence DESC LIMIT 1"
                ),
                {"id": item["id"]},
            ).first()
            if row:
                events[label] = tuple(row)
        expected = {table: dict(values) for table, values in snapshot.rows}
        for label, tables in (("legacy", LEGACY_TABLES), ("structured", DELETE_ORDER)):
            if _confirmed(events, label):
                for table in tables:
                    expected[table] = {}
        if _confirmed(events, "local"):
            for table, ids in snapshot.local_ids:
                for identifier in ids:
                    expected[table].pop(identifier, None)
        for review in snapshot.reviews:
            if _confirmed(events, _review_label(review)):
                if review.action == "delete":
                    expected[review.table].pop(review.row_id, None)
                else:
                    expected[review.table][review.row_id] = review.post_digest
        if current != tuple(
            (table, tuple(sorted(expected[table].items()))) for table in ROW_TABLES
        ):
            raise _Rejected("inventory_changed")
        if (
            "legacy" in mapped
            and not _confirmed(events, "legacy")
            and legacy != snapshot.legacy
        ) or (
            "structured" in mapped
            and not _confirmed(events, "structured")
            and structured != snapshot.structured
        ):
            raise _Rejected("ownership_changed")
        return connection, job, mapped, events

    def prepare(self, *, job_id, snapshot):
        stage = "preparation"
        try:
            with Session(self.engine) as session, session.begin():
                self._context(session, job_id, snapshot, create=True)
                stage = "commit"
        except Exception as error:
            return self._failure(error, stage)
        return FulfillmentResult(
            "confirmed", "preparation", "exact_workset_ready", "execute"
        )

    def execute(self, *, job_id, snapshot):
        result = self.prepare(job_id=job_id, snapshot=snapshot)
        if result.classification != "confirmed":
            return result
        stage = "provider"
        try:

            def validate(connection, job, item):
                self._context_on(connection, job_id, snapshot)

            for identity in snapshot.identities:
                label = "provider:" + str(identity.identity_id)
                with Session(self.engine) as session, session.begin():
                    _, _, items, events = self._context(session, job_id, snapshot)
                if label in events:
                    continue

                def prepare(connection, job, item, identity=identity):
                    validate(connection, job, item)
                    prepared = self.prepare_provider(connection, job, item, identity)
                    if type(prepared) is not PreparedProviderEffect:
                        raise _Rejected("invalid_provider_preparation")
                    return prepared

                result = ProviderErasureExecutor(
                    self.engine, prepare, clock=self.clock
                ).execute(job_id=job_id, item_id=str(items[label]["id"]))
                if result.classification == "not_dispatched":
                    return FulfillmentResult(
                        (
                            "outcome_unknown"
                            if result.reason == "fence_unconfirmed"
                            else "not_applied"
                        ),
                        stage,
                        result.reason,
                    )
            for label, executor in (
                ("legacy", LegacyErasureExecutor),
                ("structured", StructuredErasureExecutor),
            ):
                stage = label
                with Session(self.engine) as session, session.begin():
                    _, _, items, events = self._context(session, job_id, snapshot)
                if label not in items or _confirmed(events, label):
                    continue
                if label in events:
                    raise _Rejected("local_outcome_requires_review")
                result = executor(
                    self.engine, clock=self.clock, scope_validator=validate
                ).execute(job_id=job_id, item_id=str(items[label]["id"]))
                if result.classification != "confirmed":
                    return result
            stage = "reviewed_disposition"
            for review in snapshot.reviews:
                label = _review_label(review)
                with Session(self.engine) as session, session.begin():
                    _, _, items, events = self._context(session, job_id, snapshot)
                if label not in items or _confirmed(events, label):
                    continue
                if label in events:
                    raise _Rejected("local_outcome_requires_review")
                result = PrivacyDispositionExecutor(
                    self.engine, clock=self.clock, scope_validator=validate
                ).execute(
                    job_id=job_id,
                    item_id=str(items[label]["id"]),
                    table=review.table,
                    row_id=review.row_id,
                    old_digest=review.old_digest,
                    patch=json.loads(review.patch_json),
                    action=review.action,
                )
                if result.classification != "confirmed":
                    return result
            result = self._local(job_id, snapshot)
            if result.classification != "confirmed":
                return result
            for identity in snapshot.identities:
                result = self._restore(job_id, snapshot, identity)
                if result.classification not in {"confirmed", "needs_attention"}:
                    return result
            return self._finalize(job_id, snapshot)
        except Exception as error:
            return self._failure(error, stage)

    def _local(self, job_id, snapshot):
        stage = "local_cleanup"
        try:
            with Session(self.engine) as session, session.begin():
                connection, job, items, events = self._context(
                    session, job_id, snapshot
                )
                if _confirmed(events, "local"):
                    return FulfillmentResult("confirmed", stage, "local_data_removed")
                if "local" in events:
                    raise _Rejected("local_outcome_requires_review")
                now = self._now(job, items.values())
                self._fence(connection, job, now)
                self._event(
                    connection, items["local"], 1, "started", "in_progress", now
                )
                for table, ids in snapshot.local_ids:
                    self._delete(
                        connection, table, tuple((identifier,) for identifier in ids)
                    )
                self._event(
                    connection, items["local"], 2, "confirmed", "succeeded", now
                )
                stage = "commit"
        except Exception as error:
            return self._failure(error, stage)
        return FulfillmentResult("confirmed", "local_cleanup", "local_data_removed")

    def _restore(self, job_id, snapshot, identity):
        stage = "restore_start"
        label = "restore:" + str(identity.identity_id)
        try:
            with Session(self.engine) as session, session.begin():
                connection, job, items, events = self._context(
                    session, job_id, snapshot
                )
                if label in events:
                    return FulfillmentResult(
                        "confirmed" if _confirmed(events, label) else "needs_attention",
                        "restore",
                        "existing_restore_evidence",
                    )
                now = self._now(job, items.values())
                self._fence(connection, job, now)
                self._event(connection, items[label], 1, "started", "in_progress", now)
                record = PersonRestoreRecord(
                    job_id,
                    str(items[label]["id"]),
                    snapshot.scope_hash,
                    snapshot.generation,
                    identity.identity_id,
                    identity.generation,
                    identity.restore_binding,
                )
                stage = "commit"
            confirmed = False
            try:
                identifier = self.restore_store.put(record)
                _uuid(identifier)
                stored = self.restore_store.read(identifier)
                confirmed = type(stored) is PersonRestoreRecord and stored == record
            except Exception:
                pass
            stage = "restore_result"
            with Session(self.engine) as session, session.begin():
                connection, job, items, events = self._context(
                    session, job_id, snapshot
                )
                if events.get(label) != (1, "started", "in_progress"):
                    raise _Rejected("restore_outcome_requires_review")
                now = self._now(job, items.values())
                self._event(
                    connection,
                    items[label],
                    2,
                    "confirmed" if confirmed else "unknown",
                    "succeeded" if confirmed else "response_unknown",
                    now,
                )
                if not confirmed:
                    connection.execute(
                        text(
                            "UPDATE ntubtob.account_erasure_jobs SET status='needs_attention',updated_at=:now WHERE id=:id"
                        ),
                        {"id": job_id, "now": now},
                    )
                stage = "commit"
        except Exception as error:
            return self._failure(error, stage)
        return FulfillmentResult(
            "confirmed" if confirmed else "needs_attention",
            "restore",
            "custody_recorded" if confirmed else "custody_unconfirmed",
        )

    def _finalize(self, job_id, snapshot):
        stage = "finalization"
        try:
            with Session(self.engine) as session, session.begin():
                connection, job, items, events = self._context(
                    session, job_id, snapshot
                )
                provider_ok = True
                for identity in snapshot.identities:
                    outcome = events.get("provider:" + str(identity.identity_id), ())[
                        -2:
                    ]
                    missing = not connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM ntubtob.apple_provider_credentials WHERE auth_identity_id=:id)"
                        ),
                        {"id": identity.identity_id},
                    )
                    provider_ok &= outcome == ("confirmed", "succeeded") or (
                        outcome == ("confirmed", "credential_missing") and missing
                    )
                if not provider_ok or any(
                    not _confirmed(events, label)
                    for label in items
                    if label != "final" and not label.startswith("provider:")
                ):
                    connection.execute(
                        text(
                            "UPDATE ntubtob.account_erasure_jobs SET status='needs_attention',updated_at=:now WHERE id=:id"
                        ),
                        {"id": job_id, "now": self._now(job, items.values())},
                    )
                    stage = "commit"
                    return FulfillmentResult(
                        "needs_attention",
                        "finalization",
                        "required_outcome_unconfirmed",
                    )
                if "final" in events:
                    raise _Rejected("final_outcome_requires_review")
                now = self._now(job, items.values())
                self._fence(connection, job, now)
                self._event(
                    connection, items["final"], 1, "started", "in_progress", now
                )
                self._delete(
                    connection,
                    "apple_provider_credentials",
                    dict(snapshot.rows)["apple_provider_credentials"],
                )
                # RESTRICT is a final fail-closed backstop, not implicit cascade.
                # Earlier full graph validation excludes unknown CASCADE/SET NULL.
                self._event(
                    connection, items["final"], 2, "confirmed", "succeeded", now
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_steps (job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at) VALUES (:job,'online_verification',1,1,'confirmed','succeeded',:now)"
                    ),
                    {"job": job_id, "now": now},
                )
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_jobs SET status='online_completed',person_id=NULL,online_completed_at=:now,updated_at=:now WHERE id=:id"
                    ),
                    {"id": job_id, "now": now},
                )
                self._delete(
                    connection,
                    "auth_identities",
                    tuple((i.identity_id,) for i in snapshot.identities),
                )
                self._delete(connection, "people", ((snapshot.person_id,),))
                session.info["person_fulfillment_final"] = True
                stage = "commit"
        except Exception as error:
            return self._failure(error, stage)
        return FulfillmentResult(
            "confirmed", "finalization", "online_completed", "read_receipt"
        )
