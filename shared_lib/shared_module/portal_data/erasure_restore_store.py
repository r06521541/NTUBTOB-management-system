"""Default-unused GCS custody and separately injected exact-version privacy purge.

The trusted caller supplies an already authorized discovery client, bucket and
environment namespace. Construction does no I/O and performs no credential lookup.
No IAM, immutability/retention policy, complete restore inventory, reconciliation,
expiry or runtime enablement is established here. Records remain sensitive
pseudonymous data: never log them, their object names or provider responses.

Reads trust the GCS generation-pinned object contract. One bounded range request
and sink limit accumulated bytes, NOT hostile transport memory: this SDK receives
the HTTP response before sink.write. Trusted transport composition must separately
provide HTTP timeouts/response bounds. A socket timeout is not an overall deadline.
Failures never authorize a resend; even 412 requires separate read-only review.
The purger removes only the exact active version. Neither an acknowledgement nor
a version-specific 404 proves soft-deleted, non-current or other backup copies are
gone. No policy completion follows. Trusted composition separately supplies the
purger's least-privilege client and disables sensitive SDK/transport debug logs;
this module grants no IAM rights or new authority to the ordinary custody writer.
"""

import io
import json
import re
from dataclasses import dataclass
from threading import Lock
from uuid import UUID

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from ..erasure_restore_binding import RestoreBinding
from .erasure_fulfillment import PendingRestoreRecord
from .erasure_person_fulfillment import PersonRestoreRecord

_MAX_BYTES = 4096
_METADATA_FIELDS = "bucket,name,generation,size"
_COMMON = {"job_id", "item_id", "scope_hash", "binding"}
_FIELDS = {
    "pending_identity": _COMMON | {"generation"},
    "person": _COMMON | {"person_generation", "identity_id", "identity_generation"},
}


class RestoreStoreRejected(ValueError):
    """Fixed local shape/configuration rejection before any SDK operation."""


class RestoreStoreUnavailable(RuntimeError):
    """Fixed stage failure; never an absence, successful write or retry signal."""


@dataclass(frozen=True, repr=False)
class RestoreObjectVersion:
    """Private metadata, not approval or a complete backup inventory."""

    bucket: str
    namespace: str
    item_id: str
    generation: str
    size: int


@dataclass(frozen=True, repr=False)
class VersionedRestoreRecord:
    record: PendingRestoreRecord | PersonRestoreRecord
    version: RestoreObjectVersion


@dataclass(frozen=True)
class RestoreVersionOutcome:
    """Fixed diagnostics only; never contains an object path or record payload."""

    stage: str
    classification: str
    delete_dispatched: bool = False
    next_action: str = "read_only_version_review"


def _reject():
    raise RestoreStoreRejected("restore_store_input_rejected") from None


def _unavailable(reason):
    raise RestoreStoreUnavailable(reason) from None


def _uuid(value):
    try:
        if type(value) is str and len(value) == 36 and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    _reject()


def _hex(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _reject()


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            _reject()
        result[key] = value
    return result


def _record(kind, values):
    if type(kind) is not str or kind not in _FIELDS:
        _reject()
    if type(values) is not dict or set(values) != _FIELDS[kind]:
        _reject()
    for field in ("job_id", "item_id"):
        _uuid(values[field])
    _hex(values["scope_hash"])
    binding = values["binding"]
    if (
        type(binding) is not dict
        or set(binding) != {"version", "key_id", "digest"}
        or type(binding["version"]) is not int
        or binding["version"] != 1
        or type(binding["key_id"]) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", binding["key_id"]) is None
    ):
        _reject()
    _hex(binding["digest"])
    parsed = {**values, "binding": RestoreBinding(**binding)}
    if kind == "pending_identity":
        _uuid(values["generation"])
        return PendingRestoreRecord(**parsed)
    _uuid(values["person_generation"])
    _uuid(values["identity_generation"])
    if (
        type(values["identity_id"]) is not int
        or not 0 < values["identity_id"] <= 2**63 - 1
    ):
        _reject()
    return PersonRestoreRecord(**parsed)


def _encode(record, namespace):
    if type(record) is PendingRestoreRecord:
        kind = "pending_identity"
    elif type(record) is PersonRestoreRecord:
        kind = "person"
    else:
        _reject()
    if type(record.binding) is not RestoreBinding:
        _reject()
    values = {**vars(record), "binding": dict(vars(record.binding))}
    _record(kind, values)
    blob = json.dumps(
        {"version": 1, "kind": kind, "namespace": namespace, "record": values},
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    if not 0 < len(blob) <= _MAX_BYTES:
        _reject()
    return blob


def _decode(blob, namespace, identifier):
    data = json.loads(
        blob.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_float=lambda _: _reject(),
        parse_constant=lambda _: _reject(),
    )
    if (
        type(data) is not dict
        or set(data) != {"version", "kind", "namespace", "record"}
        or type(data["version"]) is not int
        or data["version"] != 1
        or data["namespace"] != namespace
    ):
        _reject()
    record = _record(data["kind"], data["record"])
    if record.item_id != identifier:
        _reject()
    return record


def _positive_decimal(value, maximum):
    if (
        type(value) is not str
        or not 1 <= len(value) <= 20
        or re.fullmatch(r"[1-9][0-9]*", value) is None
        or int(value) > maximum
    ):
        _reject()
    return int(value)


class _BoundedSink(io.BytesIO):
    def __init__(self, limit):
        super().__init__()
        self._limit = limit

    def write(self, value):
        if type(value) is not bytes or self.tell() + len(value) > self._limit:
            _reject()
        return super().write(value)


class _RestoreLocation:
    def __init__(self, *, client, bucket, namespace):
        _uuid(namespace)
        if (
            client is None
            or type(bucket) is not str
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket) is None
            or any(not 1 <= len(part) <= 63 for part in bucket.split("."))
        ):
            _reject()
        self._client, self._bucket, self._namespace = client, bucket, namespace

    def _name(self, identifier):
        return (
            "account-erasure-restore/v1/"
            + self._namespace
            + "/"
            + _uuid(identifier)
            + ".json"
        )

    def _metadata(self, metadata, name):
        if (
            type(metadata) is not dict
            or set(metadata) != {"bucket", "name", "generation", "size"}
            or metadata["bucket"] != self._bucket
            or metadata["name"] != name
        ):
            _reject()
        _positive_decimal(metadata["generation"], 2**64 - 1)
        size = _positive_decimal(metadata["size"], _MAX_BYTES)
        return metadata["generation"], size


class GcsErasureRestoreStore(_RestoreLocation):
    """Fixed UUID-addressed put/read. No delete, listing, overwrites or retries.

    A put result is only a create acknowledgement. Existing coordinators must
    still read it and compare the exact DTO before recording confirmed custody.
    read accepts an item UUID, not a bucket, path, generation or arbitrary URL.
    read_versioned returns the same validated DTO with private version metadata.
    """

    def put(self, record):
        blob = _encode(record, self._namespace)
        name = self._name(record.item_id)
        with io.BytesIO(blob) as stream:
            try:
                metadata = (
                    self._client.objects()
                    .insert(
                        bucket=self._bucket,
                        body={"name": name, "contentType": "application/json"},
                        media_body=MediaIoBaseUpload(
                            stream, mimetype="application/json", resumable=False
                        ),
                        ifGenerationMatch=0,
                        fields=_METADATA_FIELDS,
                    )
                    .execute(num_retries=0)
                )
            except HttpError as error:
                if getattr(error.resp, "status", None) == 412:
                    _unavailable("restore_store_create_conflict")
                _unavailable("restore_store_write_outcome_unknown")
            except Exception:
                _unavailable("restore_store_write_outcome_unknown")
        try:
            _, size = self._metadata(metadata, name)
            if size != len(blob):
                _reject()
        except Exception:
            _unavailable("restore_store_write_ack_rejected")
        return record.item_id

    def read(self, identifier):
        return self.read_versioned(identifier).record

    def read_versioned(self, identifier):
        name = self._name(identifier)
        try:
            metadata = (
                self._client.objects()
                .get(bucket=self._bucket, object=name, fields=_METADATA_FIELDS)
                .execute(num_retries=0)
            )
        except Exception:
            _unavailable("restore_store_metadata_unavailable")
        try:
            generation, size = self._metadata(metadata, name)
        except Exception:
            _unavailable("restore_store_metadata_rejected")
        with _BoundedSink(size) as sink:
            try:
                request = self._client.objects().get_media(
                    bucket=self._bucket, object=name, generation=generation
                )
                downloader = MediaIoBaseDownload(sink, request, chunksize=_MAX_BYTES)
                # One small object fits one range. Missing/incorrect totals or
                # incomplete progress reject; never loop or repeat a media read.
                progress, done = downloader.next_chunk(num_retries=0)
            except Exception:
                _unavailable("restore_store_media_unavailable")
            try:
                if (
                    done is not True
                    or progress is None
                    or type(progress.resumable_progress) is not int
                    or progress.resumable_progress != size
                    or type(progress.total_size) is not int
                    or progress.total_size != size
                    or sink.tell() != size
                ):
                    _reject()
                return VersionedRestoreRecord(
                    _decode(sink.getvalue(), self._namespace, identifier),
                    RestoreObjectVersion(
                        self._bucket, self._namespace, identifier, generation, size
                    ),
                )
            except Exception:
                _unavailable("restore_store_media_rejected")


class GcsErasureRestorePurger(_RestoreLocation):
    """Separate, explicit private client for one-shot current-version removal.

    The trusted coordinator must authorize and durably fence each dispatch before
    calling purge. This instance's memoization only prevents local repetition; it
    is NOT a durable fence across restarts/new clients. Preflight and delete are
    not atomic: ifGenerationMatch protects the current object from replacement
    races. Do not select a historical generation for deletion. Readback selects
    only the known generation and cannot authorize resend or establish all-copy
    absence, retention compliance or complete policy fulfillment.
    """

    def __init__(self, *, client, bucket, namespace):
        super().__init__(client=client, bucket=bucket, namespace=namespace)
        self._outcomes = {}
        self._lock = Lock()

    def _validate_version(self, version):
        if (
            type(version) is not RestoreObjectVersion
            or type(version.bucket) is not str
            or version.bucket != self._bucket
            or type(version.namespace) is not str
            or version.namespace != self._namespace
            or type(version.size) is not int
            or not 0 < version.size <= _MAX_BYTES
        ):
            _reject()
        _positive_decimal(version.generation, 2**64 - 1)
        return self._name(version.item_id)

    def _observe(self, version, name, *, stage):
        arguments = dict(bucket=self._bucket, object=name, fields=_METADATA_FIELDS)
        if stage == "presence":
            arguments["generation"] = version.generation
        try:
            metadata = self._client.objects().get(**arguments).execute(num_retries=0)
        except HttpError as error:
            status = getattr(error.resp, "status", None)
            classification = {
                404: (
                    "version_not_found" if stage == "presence" else "current_not_found"
                ),
                412: "version_conflict",
            }.get(status, "metadata_unavailable")
            return RestoreVersionOutcome(stage, classification)
        except Exception:
            return RestoreVersionOutcome(stage, "metadata_unavailable")
        try:
            generation, size = self._metadata(metadata, name)
        except Exception:
            return RestoreVersionOutcome(stage, "metadata_rejected")
        if generation != version.generation or size != version.size:
            return RestoreVersionOutcome(stage, "version_conflict")
        return None

    def read_version_presence(self, version):
        name = self._validate_version(version)
        return self._observe(version, name, stage="presence") or RestoreVersionOutcome(
            "presence", "version_present"
        )

    def purge(self, version):
        name = self._validate_version(version)
        key = (version.item_id, version.generation)
        with self._lock:
            if key in self._outcomes:
                return self._outcomes[key]
            self._outcomes[key] = RestoreVersionOutcome(
                "preflight", "metadata_unavailable"
            )
        outcome = self._observe(version, name, stage="preflight")
        if outcome is None:
            # Preserve this fact before invoking any potentially external SDK
            # operation, including on reentrant/concurrent calls or interruption.
            with self._lock:
                self._outcomes[key] = RestoreVersionOutcome(
                    "delete", "delete_outcome_unknown", True
                )
            try:
                reply = (
                    self._client.objects()
                    .delete(
                        bucket=self._bucket,
                        object=name,
                        ifGenerationMatch=version.generation,
                    )
                    .execute(num_retries=0)
                )
                # Discovery's RawModel maps a successful 204 to this exact value.
                classification = (
                    "active_version_removed"
                    if type(reply) is str and reply == ""
                    else "delete_outcome_unknown"
                )
            except HttpError as error:
                classification = {
                    404: "current_not_found",
                    412: "version_conflict",
                    403: "delete_rejected",
                }.get(getattr(error.resp, "status", None), "delete_outcome_unknown")
            except Exception:
                classification = "delete_outcome_unknown"
            outcome = RestoreVersionOutcome("delete", classification, True)
        with self._lock:
            self._outcomes[key] = outcome
        return outcome
