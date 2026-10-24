"""Default-unused supported pending-identity fulfillment; no live composition.

Capture precedes request creation: its sealed digest is supplied by the existing
trusted plan builder, never written back over a requested job's scope. The caller
retains the immutable snapshot, reviewed audit dispositions and restore binding.
Provider preparation is trusted local read-only code; dispatch uses the existing
commit-before-I/O executor. Restore custody is a separately injected record/read
port, not a boolean or successful HMAC. Only fictional ports are tested here.
Apple, Google and LINE pending identities require their own reviewed provider
preparation; absence of an Apple credential is not non-Apple provider evidence.

Unknown provider/custody outcomes do not prevent owned local cleanup, but retain
the identity/credential and needs_attention. This avoids pretending the current
item schema/reconciler supports post-online evidence. Person, LINE legacy stores,
shared/admin content, backup completion, and runtime enablement are not supported.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from ..erasure_restore_binding import RestoreBinding
from ..mobile_api import utc_now
from .erasure_provider_execution import (
    PreparedProviderEffect,
    ProviderErasureExecutor,
    _Rejected,
    _time,
    _uuid,
)
from .runtime import acquire_admin_event_locks

LOCAL_TABLES = (
    "identity_review_messages",
    "identity_review_threads",
    "apple_provider_code_exchanges",
    "apple_provider_notifications",
)
ROW_TABLES = (*LOCAL_TABLES, "access_audit", "apple_provider_credentials")
LOCK_TABLES = (
    "auth_identities",
    *ROW_TABLES,
    "mobile_sessions",
    "account_erasure_jobs",
)
SCOPE_VERSION = 1


@dataclass(frozen=True, repr=False)
class PendingIdentitySnapshot:
    identity_id: int
    generation: str
    identity_digest: str
    rows: tuple
    restore_binding: RestoreBinding

    @property
    def scope_hash(self):
        # Historical wire/domain stays fixed. The complete identity digest and
        # restore binding already bind the exact provider; no new snapshot format.
        return _digest(
            [
                "pending_apple_fulfillment_v1",
                self.identity_id,
                self.generation,
                self.identity_digest,
                self.rows,
                [
                    self.restore_binding.version,
                    self.restore_binding.key_id,
                    self.restore_binding.digest,
                ],
            ]
        )


@dataclass(frozen=True, repr=False)
class PendingRestoreRecord:
    job_id: str
    item_id: str
    scope_hash: str
    generation: str
    binding: RestoreBinding


@dataclass(frozen=True)
class FulfillmentResult:
    """Classification is stage-local; earlier committed stages are never undone.

    not_applied describes this stage only, not the entire multi-transaction run.
    Always read durable item/receipt evidence before any operator recovery.
    """

    classification: str
    stage: str
    reason: str
    next_action: str = "read_only_review"


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, allow_nan=False, separators=(",", ":")
        ).encode("ascii")
    ).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise _Rejected("invalid_snapshot")


def _rows(connection, sql, **parameters):
    return tuple(tuple(row) for row in connection.execute(text(sql), parameters))


def _connection(session):
    # Request capture must reuse its caller's exact checked Connection. Never
    # create a second Session/transaction, or commit a capture independently.
    if isinstance(session, Connection):
        transaction = session.get_transaction()
        if (
            session.in_transaction() is not True
            or transaction is None
            or transaction.is_active is not True
        ):
            raise _Rejected("clean_transaction_required")
        connection = session
    else:
        if (
            not session.in_transaction()
            or session.new
            or session.dirty
            or session.deleted
        ):
            raise _Rejected("clean_transaction_required")
        connection = session.connection()
    if (
        connection.get_isolation_level() != "READ COMMITTED"
        or getattr(connection.connection.dbapi_connection, "autocommit", None)
        is not False
    ):
        raise _Rejected("read_committed_required")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '5s'"))
    acquire_admin_event_locks(connection)
    if tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) not in (
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
    ):
        raise _Rejected("schema_not_ready")
    for table in (
        *LOCK_TABLES,
        "account_erasure_items",
        "account_erasure_item_events",
        "account_erasure_steps",
    ):
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                )
            )
            is not False
        ):
            raise _Rejected("unfiltered_tables_required")
    return connection


def _identity(connection, identity_id):
    row = (
        connection.execute(
            text(
                "SELECT id,provider,person_id,status,account_generation::text AS generation,"
                "encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS digest "
                "FROM ntubtob.auth_identities t WHERE id=:id FOR UPDATE"
            ),
            {"id": identity_id},
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["provider"] not in {"apple", "google", "line"}
        or row["person_id"] is not None
        or row["status"] not in {"pending", "disabled", "blocked"}
    ):
        raise _Rejected("pending_identity_required")
    return row


def _inventory(connection, identity_id):
    # Relation locks also exclude direct DML/DDL not using advisory fences.
    connection.execute(
        text(
            "LOCK TABLE "
            + ",".join("ntubtob." + name for name in LOCK_TABLES)
            + " IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    # Recheck here as provider preparation uses its own fixed connection/TX.
    # A previous preparation transaction's visibility is not current authority.
    for table in LOCK_TABLES:
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                )
            )
            is not False
        ):
            raise _Rejected("unfiltered_tables_required")
    edges = _rows(
        connection,
        "SELECT ns.nspname,src.relname,dst.relname,c.confdeltype,"
        "ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(attnum,ord) "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum ORDER BY k.ord),"
        "ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY k(attnum,ord) "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.attnum ORDER BY k.ord) "
        "FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class src ON src.oid=c.conrelid "
        "JOIN pg_catalog.pg_namespace ns ON ns.oid=src.relnamespace "
        "JOIN pg_catalog.pg_class dst ON dst.oid=c.confrelid "
        "JOIN pg_catalog.pg_namespace nd ON nd.oid=dst.relnamespace "
        "WHERE c.contype='f' AND nd.nspname='ntubtob' AND dst.relname=ANY(:tables)",
        tables=["auth_identities", *ROW_TABLES],
    )
    edges = tuple(edge[:4] + (tuple(edge[4]), tuple(edge[5])) for edge in edges)
    expected = {
        ("ntubtob", table, "auth_identities", "r", ("auth_identity_id",), ("id",))
        for table in (
            "identity_review_threads",
            "access_audit",
            "mobile_sessions",
            "account_erasure_jobs",
            "apple_provider_credentials",
            "apple_provider_notifications",
            "apple_provider_code_exchanges",
        )
    }
    expected.add(
        (
            "ntubtob",
            "identity_review_messages",
            "identity_review_threads",
            "r",
            ("thread_id",),
            ("id",),
        )
    )
    if tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) in {("0020_erasure_intake",), ("0021_erasure_continuity",)}:
        expected.add(
            (
                "ntubtob",
                "account_erasure_intakes",
                "auth_identities",
                "r",
                ("auth_identity_id",),
                ("id",),
            )
        )
    if len(edges) != len(expected) or set(edges) != expected:
        raise _Rejected("schema_changed")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM ntubtob.mobile_sessions WHERE auth_identity_id=:id)"
        ),
        {"id": identity_id},
    ):
        raise _Rejected("ownership_conflict")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM ntubtob.identity_review_messages m JOIN ntubtob.identity_review_threads t ON t.id=m.thread_id WHERE t.auth_identity_id=:id AND (m.sender_role<>'applicant' OR m.sender_person_id IS NOT NULL))"
        ),
        {"id": identity_id},
    ):
        raise _Rejected("shared_content_requires_review")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM ntubtob.access_audit WHERE auth_identity_id=:id AND (target_person_id IS NOT NULL OR actor_person_id IS NOT NULL))"
        ),
        {"id": identity_id},
    ):
        raise _Rejected("shared_content_requires_review")
    rows = []
    for table in ROW_TABLES:
        predicate = (
            "t.thread_id IN (SELECT id FROM ntubtob.identity_review_threads WHERE auth_identity_id=:id)"
            if table == "identity_review_messages"
            else "t.auth_identity_id=:id"
        )
        rows.append(
            (
                table,
                _rows(
                    connection,
                    f"SELECT id,encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM ntubtob.{table} t WHERE {predicate} ORDER BY id",
                    id=identity_id,
                ),
            )
        )
    return tuple(rows)


def capture_pending_snapshot(session, identity_id, *, reviewed_audits, restore_binding):
    """Trusted pre-request capture; exact reviewed audit digests, not raw text.

    restore_binding must come from the separately reviewed namespace/key codec.
    This function cannot prove custody or authorize an unreviewed disposition.
    Its SQL hashes entire credentials; encrypted bytes/token hashes never leave SQL.
    """
    if (
        type(identity_id) is not int
        or identity_id <= 0
        or type(reviewed_audits) is not tuple
    ):
        raise _Rejected("invalid_snapshot")
    if (
        type(restore_binding) is not RestoreBinding
        or type(restore_binding.version) is not int
        or restore_binding.version != 1
        or type(restore_binding.key_id) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", restore_binding.key_id) is None
    ):
        raise _Rejected("invalid_restore_binding")
    _hash(restore_binding.digest)
    connection = _connection(session)
    identity = _identity(connection, identity_id)
    rows = _inventory(connection, identity_id)
    if reviewed_audits != dict(rows)["access_audit"]:
        raise _Rejected("reviewed_dispositions_required")
    return PendingIdentitySnapshot(
        identity_id, identity["generation"], identity["digest"], rows, restore_binding
    )


def _specs(connection, job_id, snapshot):
    specs = {}
    for label, stage in (
        ("provider", "provider_revocation"),
        ("restore", "restore_suppression"),
        ("local", "online_erasure"),
        ("final", "online_erasure"),
    ):
        specs[label] = (
            stage,
            _digest(["pending_item_v1", job_id, snapshot.scope_hash, label]),
        )
    for identifier, digest in dict(snapshot.rows)["access_audit"]:
        binding = connection.scalar(
            text(
                "SELECT encode(sha256(convert_to(jsonb_build_array('privacy_mutation_v1',CAST(:job AS uuid),"
                "CAST(:generation AS uuid),'access_audit'::text,CAST(:row AS bigint),CAST(:old AS text),"
                "'{}'::jsonb,'delete'::text)::text,'UTF8')),'hex')"
            ),
            dict(
                job=job_id, generation=snapshot.generation, row=identifier, old=digest
            ),
        )
        specs["audit:" + str(identifier)] = ("manual_redaction", binding)
    return specs


def _confirmed(events, label):
    return events.get(label, ())[-2:] == ("confirmed", "succeeded")


class PendingIdentityFulfillment:
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
        if type(snapshot) is not PendingIdentitySnapshot:
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
        if job is not None and job["status"] in {"online_completed", "completed"}:
            raise _Rejected("receipt_read_required")
        if job is None or job["status"] not in {
            "verified",
            "processing",
            "needs_attention",
        }:
            raise _Rejected("verified_job_required")
        if (
            job["target_kind"] != "pending_identity"
            or job["person_id"] is not None
            or job["auth_identity_id"] != snapshot.identity_id
            or str(job["expected_generation"]) != snapshot.generation
            or job["scope_version"] != SCOPE_VERSION
            or not hmac.compare_digest(job["scope_hash"], snapshot.scope_hash)
        ):
            raise _Rejected("scope_changed")
        identity = _identity(connection, snapshot.identity_id)
        if identity["generation"] != snapshot.generation or not hmac.compare_digest(
            identity["digest"], snapshot.identity_digest
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
        current = _inventory(connection, snapshot.identity_id)
        if connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs WHERE auth_identity_id=:identity AND id<>:job)"
            ),
            {"identity": snapshot.identity_id, "job": job_id},
        ):
            raise _Rejected("ownership_conflict")
        specs = _specs(connection, job_id, snapshot)
        if not items and create:
            if current != snapshot.rows:
                raise _Rejected("inventory_changed")
            now = self._now(job)
            for label, (stage, binding) in specs.items():
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
        expected = {spec: label for label, spec in specs.items()}
        if (
            len(items) != len(expected)
            or {(item["stage"], item["binding_hash"]) for item in items}
            != set(expected)
            or any(
                str(item["expected_generation"]) != snapshot.generation
                for item in items
            )
        ):
            raise _Rejected("workset_changed")
        mapped = {
            expected[(item["stage"], item["binding_hash"])]: item for item in items
        }
        events = {}
        for label, item in mapped.items():
            rows = _rows(
                connection,
                "SELECT event_sequence,event_kind,result_code FROM ntubtob.account_erasure_item_events WHERE item_id=:id ORDER BY event_sequence DESC LIMIT 1",
                id=item["id"],
            )
            if rows:
                events[label] = rows[0]
        remaining = []
        for table, rows in snapshot.rows:
            if table in LOCAL_TABLES and _confirmed(events, "local"):
                rows = ()
            if table == "access_audit":
                rows = tuple(
                    row
                    for row in rows
                    if not _confirmed(events, "audit:" + str(row[0]))
                )
            remaining.append((table, rows))
        if current != tuple(remaining):
            raise _Rejected("inventory_changed")
        return connection, job, mapped, events

    def _now(self, job, items=()):
        now = _time(self.clock())
        if now < max([job["updated_at"], *(item["created_at"] for item in items)]):
            raise _Rejected("clock_regressed")
        return now

    @staticmethod
    def _event(connection, item, sequence, kind, code, now):
        connection.execute(
            text(
                "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:item,:seq,:kind,:code,:now)"
            ),
            dict(item=item["id"], seq=sequence, kind=kind, code=code, now=now),
        )

    @staticmethod
    def _fence(connection, job, now):
        connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET status='processing',irreversible_started_at=COALESCE(irreversible_started_at,:now),updated_at=:now WHERE id=:id"
            ),
            {"id": job["id"], "now": now},
        )

    @staticmethod
    def _failure(error, stage):
        if isinstance(error, _Rejected):
            return FulfillmentResult("not_applied", stage, str(error))
        original = getattr(error, "orig", None)
        message = getattr(getattr(original, "diag", None), "message_primary", None)
        for check in (
            "input",
            "job_binding",
            "item_binding",
            "row_version",
            "disposition",
            "storage_mutation",
            "storage_verification",
        ):
            if message == "privacy mutation rejected at " + check:
                return FulfillmentResult(
                    "not_applied", stage, "privacy_" + check + "_rejected"
                )
        reason = {
            "23503": "foreign_key_conflict",
            "23514": "constraint_rejected",
            "23505": "evidence_conflict",
            "55P03": "lock_unavailable",
            "57014": "statement_unavailable",
        }.get(getattr(original, "pgcode", None), "transaction_failed")
        return FulfillmentResult(
            "outcome_unknown" if stage == "commit" else "not_applied",
            stage,
            "commit_unconfirmed" if stage == "commit" else reason,
        )

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
        prepared = self.prepare(job_id=job_id, snapshot=snapshot)
        if prepared.classification != "confirmed":
            return prepared
        stage = "provider"
        try:
            with Session(self.engine) as session, session.begin():
                _, _, items, events = self._context(session, job_id, snapshot)
                provider_id = str(items["provider"]["id"])
            if "provider" not in events:

                def prepare(connection, job, item):
                    # Existing executor already owns canonical/job/target/item locks.
                    # Use its fixed connection, not a separately routed transaction.
                    if tuple(
                        connection.scalars(
                            text("SELECT version_num FROM ntubtob.alembic_version")
                        )
                    ) not in (
                        ("0018_erasure_privacy_mutation",),
                        ("0019_erasure_admin_recovery",),
                        ("0020_erasure_intake",),
                        ("0021_erasure_continuity",),
                    ):
                        raise _Rejected("schema_not_ready")
                    self._context_on(connection, job_id, snapshot)
                    effect = self.prepare_provider(connection, job, item)
                    if type(effect) is not PreparedProviderEffect:
                        raise _Rejected("invalid_provider_preparation")
                    return effect

                result = ProviderErasureExecutor(
                    self.engine, prepare, clock=self.clock
                ).execute(job_id=job_id, item_id=provider_id)
                if result.classification == "not_dispatched":
                    return FulfillmentResult(
                        (
                            "outcome_unknown"
                            if result.reason == "fence_unconfirmed"
                            else "not_applied"
                        ),
                        "provider",
                        result.reason,
                    )
            local = self._local(job_id, snapshot)
            if local.classification != "confirmed":
                return local
            restore = self._restore(job_id, snapshot)
            if restore.classification == "outcome_unknown":
                return restore
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
                labels = [
                    "local",
                    *(
                        "audit:" + str(row[0])
                        for row in dict(snapshot.rows)["access_audit"]
                    ),
                ]
                if any(
                    label in events and not _confirmed(events, label)
                    for label in labels
                ):
                    raise _Rejected("local_outcome_requires_review")
                if all(_confirmed(events, label) for label in labels):
                    return FulfillmentResult(
                        "confirmed", "local_cleanup", "local_data_removed"
                    )
                now = self._now(job, items.values())
                self._fence(connection, job, now)
                for identifier, digest in dict(snapshot.rows)["access_audit"]:
                    label = "audit:" + str(identifier)
                    if _confirmed(events, label):
                        continue
                    self._event(
                        connection, items[label], 1, "started", "in_progress", now
                    )
                    connection.execute(
                        text(
                            "SELECT ntubtob.apply_erasure_privacy_mutation(CAST(:job AS uuid),CAST(:item AS uuid),'access_audit',:row,:old,'{}'::jsonb,'delete')"
                        ),
                        dict(
                            job=job_id,
                            item=items[label]["id"],
                            row=identifier,
                            old=digest,
                        ),
                    )
                    self._event(
                        connection, items[label], 2, "confirmed", "succeeded", now
                    )
                if not _confirmed(events, "local"):
                    self._event(
                        connection, items["local"], 1, "started", "in_progress", now
                    )
                    for table in LOCAL_TABLES:
                        self._delete(connection, table, dict(snapshot.rows)[table])
                    self._event(
                        connection, items["local"], 2, "confirmed", "succeeded", now
                    )
                stage = "commit"
        except Exception as error:
            return self._failure(error, stage)
        return FulfillmentResult("confirmed", "local_cleanup", "local_data_removed")

    @staticmethod
    def _delete(connection, table, rows):
        identifiers = [row[0] for row in rows]
        changed = connection.execute(
            text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
            {"ids": identifiers},
        )
        if changed.rowcount != len(identifiers) or connection.scalar(
            text(f"SELECT EXISTS(SELECT 1 FROM ntubtob.{table} WHERE id=ANY(:ids))"),
            {"ids": identifiers},
        ):
            raise _Rejected("deletion_not_verified")

    def _restore(self, job_id, snapshot):
        stage = "restore_start"
        try:
            with Session(self.engine) as session, session.begin():
                connection, job, items, events = self._context(
                    session, job_id, snapshot
                )
                if "restore" in events:
                    return FulfillmentResult(
                        (
                            "confirmed"
                            if _confirmed(events, "restore")
                            else "needs_attention"
                        ),
                        "restore",
                        "existing_restore_evidence",
                    )
                now = self._now(job, items.values())
                self._fence(connection, job, now)
                self._event(
                    connection, items["restore"], 1, "started", "in_progress", now
                )
                record = PendingRestoreRecord(
                    job_id,
                    str(items["restore"]["id"]),
                    snapshot.scope_hash,
                    snapshot.generation,
                    snapshot.restore_binding,
                )
                stage = "commit"
            confirmed = False
            try:
                identifier = self.restore_store.put(record)
                _uuid(identifier)
                stored = self.restore_store.read(identifier)
                confirmed = type(stored) is PendingRestoreRecord and stored == record
            except Exception:
                pass
            stage = "restore_result"
            with Session(self.engine) as session, session.begin():
                connection, job, items, events = self._context(
                    session, job_id, snapshot
                )
                if events.get("restore") != (1, "started", "in_progress"):
                    raise _Rejected("restore_outcome_requires_review")
                now = self._now(job, items.values())
                self._event(
                    connection,
                    items["restore"],
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
                provider = events.get("provider", ())[-2:]
                provider_ok = provider == ("confirmed", "succeeded") or (
                    provider == ("confirmed", "credential_missing")
                    and not dict(snapshot.rows)["apple_provider_credentials"]
                    and _identity(connection, snapshot.identity_id)["provider"]
                    == "apple"
                )
                if not provider_ok or any(
                    not _confirmed(events, label)
                    for label in items
                    if label not in {"provider", "final"}
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
                if any(
                    rows for _, rows in _inventory(connection, snapshot.identity_id)
                ):
                    raise _Rejected("deletion_not_verified")
                self._event(
                    connection, items["final"], 2, "confirmed", "succeeded", now
                )
                stage = "online_evidence"
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_steps (job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at) VALUES (:job,'online_verification',1,1,'confirmed','succeeded',:now)"
                    ),
                    {"job": job_id, "now": now},
                )
                stage = "target_detachment"
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_jobs SET status='online_completed',auth_identity_id=NULL,online_completed_at=:now,updated_at=:now WHERE id=:id"
                    ),
                    {"id": job_id, "now": now},
                )
                self._delete(
                    connection,
                    "auth_identities",
                    ((snapshot.identity_id, snapshot.identity_digest),),
                )
                session.info["pending_fulfillment_final"] = True
                stage = "commit"
        except Exception as error:
            return self._failure(error, stage)
        return FulfillmentResult(
            "confirmed", "finalization", "online_completed", "read_receipt"
        )
