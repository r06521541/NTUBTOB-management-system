"""Bounded no-disclosure staging broker state machine."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol, Sequence
from urllib.parse import urlsplit

PUBLIC_OPERATIONS = frozenset({"inspect", "reset", "grant", "restore", "reconcile"})
BOUNDED_STATES = frozenset({"ready_basic", "ready_officer", "reset_required"})
LIFECYCLE_STATES = frozenset(
    {
        "inspected",
        "confirmed",
        "mutation_issued",
        "postcheck_complete",
        "reconcile_required",
    }
)
OPERATION_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_VERSION = re.compile(
    r"^projects/[a-z][a-z0-9-]{4,62}/secrets/[A-Za-z0-9_-]{1,255}/versions/[1-9][0-9]*$"
)
SERVICE_ACCOUNT = re.compile(
    r"^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,62}\.iam\.gserviceaccount\.com$"
)
PRODUCTION_PROJECTS = frozenset({"ntubtob-schedule-405614"})


class BrokerFailure(RuntimeError):
    def __init__(self, reason_code: str, status_code: int = 503):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.status_code = status_code


class BrokerConflict(BrokerFailure):
    def __init__(self, reason_code: str):
        super().__init__(reason_code, 409)


@dataclass(frozen=True)
class BrokerManifest:
    candidate_approval_sha256: str
    project: str
    region: str
    service: str
    runtime_identity: str
    broker_artifact_sha256: str
    operator_artifact_sha256: str
    image_digest: str
    database_secret_version: str
    subject_secret_version: str
    database_identity_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "BrokerManifest":
        if set(value) != set(cls.__dataclass_fields__) or not all(
            isinstance(item, str) for item in value.values()
        ):
            raise BrokerFailure("CONFIG_INVALID")
        result = cls(**value)
        if (
            result.project in PRODUCTION_PROJECTS
            or "production" in result.project
            or not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", result.project)
            or not re.fullmatch(r"[a-z][a-z0-9-]{1,30}[a-z0-9]", result.region)
            or not re.fullmatch(r"[a-z][a-z0-9-]{2,61}[a-z0-9]", result.service)
            or not SERVICE_ACCOUNT.fullmatch(result.runtime_identity)
            or result.runtime_identity.split("@", 1)[1]
            != f"{result.project}.iam.gserviceaccount.com"
            or not IMAGE_DIGEST.fullmatch(result.image_digest)
            or not SECRET_VERSION.fullmatch(result.database_secret_version)
            or result.database_secret_version.split("/")[1] != result.project
            or not SECRET_VERSION.fullmatch(result.subject_secret_version)
            or result.subject_secret_version.split("/")[1] != result.project
            or result.database_secret_version == result.subject_secret_version
        ):
            raise BrokerFailure("CONFIG_INVALID")
        for name in (
            "candidate_approval_sha256",
            "broker_artifact_sha256",
            "operator_artifact_sha256",
            "database_identity_sha256",
        ):
            if not SHA256.fullmatch(getattr(result, name)):
                raise BrokerFailure("CONFIG_INVALID")
        return result


@dataclass(frozen=True)
class JournalRecord:
    operation_id: str
    operation: str
    target_state: str
    inspect_fingerprint: str
    lifecycle_state: str
    reason_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SecretAccessor(Protocol):
    def access(self, resource: str) -> Sequence[str]: ...


class BoundedOperator(Protocol):
    def inspect(self, database_url: str, provider_subject: str) -> str: ...

    def mutate(
        self, operation: str, database_url: str, provider_subject: str
    ) -> None: ...


class Journal(Protocol):
    def get(self, operation_id: str) -> JournalRecord | None: ...

    def create_or_get(
        self,
        operation_id: str,
        operation: str,
        target_state: str,
        inspect_fingerprint: str,
    ) -> JournalRecord: ...

    def compare_and_set(
        self,
        operation_id: str,
        expected_state: str,
        next_state: str,
        reason_code: str | None = None,
    ) -> bool: ...


class InMemoryJournal:
    def __init__(self):
        self._records: dict[str, JournalRecord] = {}
        self._lock = threading.Lock()

    def get(self, operation_id: str) -> JournalRecord | None:
        with self._lock:
            return self._records.get(operation_id)

    def create_or_get(
        self,
        operation_id: str,
        operation: str,
        target_state: str,
        inspect_fingerprint: str,
    ) -> JournalRecord:
        with self._lock:
            existing = self._records.get(operation_id)
            if existing is not None:
                if (
                    existing.operation,
                    existing.target_state,
                    existing.inspect_fingerprint,
                ) != (operation, target_state, inspect_fingerprint):
                    raise BrokerConflict("INTENT_CONFLICT")
                return existing
            now = datetime.now(timezone.utc)
            record = JournalRecord(
                operation_id,
                operation,
                target_state,
                inspect_fingerprint,
                "inspected",
                created_at=now,
                updated_at=now,
            )
            self._records[operation_id] = record
            return record

    def compare_and_set(
        self,
        operation_id: str,
        expected_state: str,
        next_state: str,
        reason_code: str | None = None,
    ) -> bool:
        if next_state not in LIFECYCLE_STATES:
            raise BrokerFailure("JOURNAL_CONFLICT")
        with self._lock:
            current = self._records.get(operation_id)
            if current is None or current.lifecycle_state != expected_state:
                return False
            self._records[operation_id] = JournalRecord(
                **{
                    **asdict(current),
                    "lifecycle_state": next_state,
                    "reason_code": reason_code,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            return True

    def inject(
        self,
        operation_id: str,
        operation: str,
        target_state: str,
        inspect_fingerprint: str,
        lifecycle_state: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._records[operation_id] = JournalRecord(
            operation_id,
            operation,
            target_state,
            inspect_fingerprint,
            lifecycle_state,
            created_at=now,
            updated_at=now,
        )

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [asdict(record) for record in self._records.values()]


class Broker:
    def __init__(self, manifest, secrets, journal, operator):
        self.manifest = manifest
        self.secrets = secrets
        self.journal = journal
        self.operator = operator
        self._gate = threading.Lock()

    def execute(self, operation: str, operation_id: str) -> dict:
        if operation not in PUBLIC_OPERATIONS or not OPERATION_ID.fullmatch(
            operation_id
        ):
            raise BrokerFailure("REQUEST_INVALID", 400)
        if not self._gate.acquire(blocking=False):
            raise BrokerConflict("LOCK_UNAVAILABLE")
        try:
            return self._execute_locked(operation, operation_id)
        finally:
            self._gate.release()

    def _execute_locked(self, requested_operation: str, operation_id: str) -> dict:
        existing = self.journal.get(operation_id)
        if requested_operation == "reconcile":
            if existing is None:
                raise BrokerFailure("OPERATION_NOT_FOUND", 404)
            operation = existing.operation
        else:
            operation = requested_operation
            if existing is not None and existing.operation != operation:
                raise BrokerConflict("INTENT_CONFLICT")
        if existing is not None:
            self._validate_record(existing)
        if existing is not None and existing.lifecycle_state == "postcheck_complete":
            return self._response(existing)

        database_url, provider_subject = self._payloads()
        if existing is not None and existing.lifecycle_state in {
            "mutation_issued",
            "reconcile_required",
        }:
            return self._reconcile(existing, database_url, provider_subject)
        if requested_operation == "reconcile":
            raise BrokerConflict("JOURNAL_CONFLICT")

        inspected = None
        if existing is None:
            inspected = self._inspect(database_url, provider_subject)
            target = self._target(operation, inspected)
            existing = self.journal.create_or_get(
                operation_id,
                operation,
                target,
                self._fingerprint(operation, inspected, target),
            )
        record = existing
        if record.lifecycle_state == "inspected":
            if not self.journal.compare_and_set(
                record.operation_id, "inspected", "confirmed"
            ):
                raise BrokerConflict("OPERATION_IN_PROGRESS")
            record = self._required_record(record.operation_id)
        if record.lifecycle_state != "confirmed":
            raise BrokerConflict("JOURNAL_CONFLICT")
        issued_here = self.journal.compare_and_set(
            record.operation_id, "confirmed", "mutation_issued"
        )
        record = self._required_record(record.operation_id)
        if not issued_here:
            raise BrokerConflict("OPERATION_IN_PROGRESS")

        if operation == "inspect" or inspected == record.target_state:
            self._cas(record.operation_id, "mutation_issued", "postcheck_complete")
            return self._response(self._required_record(record.operation_id))
        try:
            self.operator.mutate(operation, database_url, provider_subject)
        except Exception:
            return self._reconcile_after_unknown(
                record, database_url, provider_subject, "OPERATOR_UNKNOWN"
            )
        try:
            postcheck = self._inspect(database_url, provider_subject)
        except BrokerFailure:
            self._mark_reconcile(record.operation_id, "OPERATOR_UNKNOWN")
            raise BrokerFailure("OPERATOR_UNKNOWN") from None
        if postcheck != record.target_state:
            self._mark_reconcile(record.operation_id, "POSTCHECK_MISMATCH")
            raise BrokerFailure("POSTCHECK_MISMATCH")
        self._cas(record.operation_id, "mutation_issued", "postcheck_complete")
        return self._response(self._required_record(record.operation_id))

    def _payloads(self) -> tuple[str, str]:
        database_url = self._one_payload(self.manifest.database_secret_version)
        provider_subject = self._one_payload(self.manifest.subject_secret_version)
        parsed = urlsplit(database_url)
        if (
            parsed.scheme not in {"postgresql", "postgres"}
            or not parsed.hostname
            or parsed.path in {"", "/"}
            or parsed.username is None
            or parsed.password is None
        ):
            raise BrokerFailure("SECRET_INVALID")
        if (
            not re.fullmatch(r"[A-Za-z0-9._~-]{6,255}", provider_subject)
            or provider_subject.strip() != provider_subject
        ):
            raise BrokerFailure("SECRET_INVALID")
        return database_url, provider_subject

    def _one_payload(self, resource: str) -> str:
        try:
            records = self.secrets.access(resource)
        except Exception:
            raise BrokerFailure("SECRET_UNAVAILABLE") from None
        if (
            not isinstance(records, Sequence)
            or isinstance(records, (str, bytes))
            or len(records) != 1
            or not isinstance(records[0], str)
            or not records[0]
        ):
            raise BrokerFailure("SECRET_INVALID")
        return records[0]

    def _inspect(self, database_url: str, provider_subject: str) -> str:
        try:
            state = self.operator.inspect(database_url, provider_subject)
        except Exception:
            raise BrokerFailure("INSPECT_DRIFT") from None
        if state not in BOUNDED_STATES:
            raise BrokerFailure("INSPECT_DRIFT")
        return state

    @staticmethod
    def _target(operation: str, inspected: str) -> str:
        if operation == "inspect":
            return inspected
        if operation == "grant":
            if inspected == "reset_required":
                raise BrokerFailure("INSPECT_DRIFT")
            return "ready_officer"
        if operation in {"restore", "reset"}:
            return "ready_basic"
        raise BrokerFailure("REQUEST_INVALID", 400)

    def _fingerprint(self, operation: str, inspected: str, target: str) -> str:
        public = {
            "candidate_approval_sha256": self.manifest.candidate_approval_sha256,
            "database_identity_sha256": self.manifest.database_identity_sha256,
            "inspected": inspected,
            "operation": operation,
            "target": target,
        }
        return hashlib.sha256(
            json.dumps(public, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()

    def _reconcile(self, record, database_url: str, provider_subject: str) -> dict:
        state = self._inspect(database_url, provider_subject)
        if state == record.target_state:
            if not self.journal.compare_and_set(
                record.operation_id, record.lifecycle_state, "postcheck_complete"
            ):
                current = self._required_record(record.operation_id)
                if current.lifecycle_state != "postcheck_complete":
                    raise BrokerConflict("JOURNAL_CONFLICT")
            return self._response(self._required_record(record.operation_id))
        if record.lifecycle_state == "mutation_issued":
            self._mark_reconcile(record.operation_id, "RECONCILE_REQUIRED")
        raise BrokerFailure("RECONCILE_REQUIRED")

    def _reconcile_after_unknown(
        self, record, database_url: str, provider_subject: str, reason_code: str
    ) -> dict:
        try:
            state = self._inspect(database_url, provider_subject)
        except BrokerFailure:
            self._mark_reconcile(record.operation_id, reason_code)
            raise BrokerFailure(reason_code) from None
        if state == record.target_state:
            self._cas(record.operation_id, "mutation_issued", "postcheck_complete")
            return self._response(self._required_record(record.operation_id))
        self._mark_reconcile(record.operation_id, reason_code)
        raise BrokerFailure(reason_code)

    def _mark_reconcile(self, operation_id: str, reason_code: str) -> None:
        current = self._required_record(operation_id)
        if current.lifecycle_state == "reconcile_required":
            return
        if not self.journal.compare_and_set(
            operation_id,
            current.lifecycle_state,
            "reconcile_required",
            reason_code,
        ):
            raise BrokerConflict("JOURNAL_CONFLICT")

    def _cas(self, operation_id: str, expected: str, target: str) -> bool:
        changed = self.journal.compare_and_set(operation_id, expected, target)
        if (
            not changed
            and self._required_record(operation_id).lifecycle_state != target
        ):
            raise BrokerConflict("JOURNAL_CONFLICT")
        return changed

    def _required_record(self, operation_id: str) -> JournalRecord:
        record = self.journal.get(operation_id)
        if record is None:
            raise BrokerConflict("JOURNAL_CONFLICT")
        self._validate_record(record)
        return record

    @staticmethod
    def _validate_record(record: JournalRecord) -> None:
        if (
            record.operation not in PUBLIC_OPERATIONS - {"reconcile"}
            or record.target_state not in BOUNDED_STATES
            or not SHA256.fullmatch(record.inspect_fingerprint)
            or record.lifecycle_state not in LIFECYCLE_STATES
        ):
            raise BrokerConflict("JOURNAL_CONFLICT")

    @staticmethod
    def _response(record: JournalRecord) -> dict:
        return {
            "classification": "PASS",
            "lifecycle_state": record.lifecycle_state,
            "operation": record.operation,
            "operation_id": record.operation_id,
            "reason_code": "NONE",
            "target_state": record.target_state,
        }
