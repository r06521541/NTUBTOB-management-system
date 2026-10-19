"""Private encrypted snapshot serialization, not persistence or purge authority.

Only explicit existing DTOs are encoded; never pickle, dynamic imports or object
hooks supplied by stored data. Inject the reviewed key and namespace in trusted
composition. Key custody/rotation and durable storage are separate responsibilities.
Decode requires the ORIGINAL job binding supplied from the ledger, not from the
blob. Executors still recheck scope, current rows, proof and item evidence.
"""

import hmac
import json
import re
import secrets
from dataclasses import fields
from datetime import datetime
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..account_erasure_scope import LegacyErasureScope
from ..erasure_restore_binding import RestoreBinding
from .erasure_fulfillment import PendingIdentitySnapshot
from .erasure_person_fulfillment import (
    PersonIdentitySnapshot,
    PersonSnapshot,
    ReviewedPersonDisposition,
    SessionVerificationBaseline,
)
from .erasure_structured_execution import StructuredInventory

_TYPES = {
    cls.__name__: cls
    for cls in (
        PendingIdentitySnapshot,
        PersonSnapshot,
        PersonIdentitySnapshot,
        SessionVerificationBaseline,
        ReviewedPersonDisposition,
        RestoreBinding,
        LegacyErasureScope,
        StructuredInventory,
    )
}
_PREFIX = b"NTUBTOB-ERASURE-PLAN-1\x00"
_MAX_DEPTH = 24
_MAX_NODES = 100000


class PlanCodecRejected(ValueError):
    """Fixed safe input/integrity rejection; no private object representation."""


def _reject():
    raise PlanCodecRejected("sealed_plan_rejected") from None


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _reject()
    return value


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _reject()
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _visit(counter, depth):
    counter[0] += 1
    if counter[0] > _MAX_NODES or depth > _MAX_DEPTH:
        _reject()


def _pack(value, counter, depth=0):
    _visit(counter, depth)
    kind = type(value)
    if value is None:
        return None
    if kind is str:
        if len(value) > 65536:
            _reject()
        return value
    if kind is int:
        if not -(2**63) <= value < 2**63:
            _reject()
        return value
    if kind is datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            _reject()
        return {"type": "datetime", "value": value.isoformat()}
    if kind is tuple:
        return {"type": "tuple", "value": [_pack(v, counter, depth + 1) for v in value]}
    if kind in _TYPES.values():
        return {
            "type": kind.__name__,
            "value": [
                _pack(getattr(value, f.name), counter, depth + 1) for f in fields(kind)
            ],
        }
    _reject()


def _unpack(value, counter, depth=0):
    _visit(counter, depth)
    if value is None or type(value) in (str, int):
        # Reuse scalar bounds; bool and floating point are never snapshot scalars.
        return _pack(value, [0])
    if type(value) is not dict or set(value) != {"type", "value"}:
        _reject()
    tag, data = value["type"], value["value"]
    if type(tag) is not str:
        _reject()
    if tag == "datetime":
        if type(data) is not str or len(data) > 40:
            _reject()
        result = datetime.fromisoformat(data)
        if (
            result.tzinfo is None
            or result.utcoffset() is None
            or result.isoformat() != data
        ):
            _reject()
        return result
    if type(data) is not list:
        _reject()
    if tag == "tuple":
        return tuple(_unpack(v, counter, depth + 1) for v in data)
    cls = _TYPES.get(tag)
    if cls is None or len(data) != len(fields(cls)):
        _reject()
    return cls(*(_unpack(v, counter, depth + 1) for v in data))


def _binding(snapshot):
    if type(snapshot) is PendingIdentitySnapshot:
        kind, identifier = "pending_identity", snapshot.identity_id
        if type(snapshot.restore_binding) is not RestoreBinding:
            _reject()
        _hash(snapshot.identity_digest)
    elif type(snapshot) is PersonSnapshot:
        kind, identifier = "person", snapshot.person_id
        if (
            type(snapshot.identities) is not tuple
            or not snapshot.identities
            or any(type(v) is not PersonIdentitySnapshot for v in snapshot.identities)
            or type(snapshot.sessions) is not tuple
            or any(
                type(v) is not SessionVerificationBaseline for v in snapshot.sessions
            )
            or type(snapshot.reviews) is not tuple
            or any(type(v) is not ReviewedPersonDisposition for v in snapshot.reviews)
            or type(snapshot.legacy) is not LegacyErasureScope
            or type(snapshot.structured) is not StructuredInventory
            or type(snapshot.local_ids) is not tuple
        ):
            _reject()
        _hash(snapshot.person_digest)
    else:
        _reject()
    if (
        type(identifier) is not int
        or identifier <= 0
        or type(snapshot.rows) is not tuple
    ):
        _reject()
    return kind, _uuid(snapshot.generation), _hash(snapshot.scope_hash)


class ErasurePlanCodec:
    MAX_BYTES = 4 * 1024 * 1024

    def __init__(self, *, namespace, key):
        try:
            self._namespace = _uuid(namespace)
            if type(key) is not bytes or len(key) != 32:
                _reject()
            self._cipher = AESGCM(key)
        except Exception:
            _reject()

    def _aad(self, job_id, kind, generation, scope_hash):
        if type(kind) is not str or kind not in {"person", "pending_identity"}:
            _reject()
        return json.dumps(
            [
                "ntubtob-erasure-plan",
                1,
                self._namespace,
                _uuid(job_id),
                kind,
                _uuid(generation),
                _hash(scope_hash),
            ],
            separators=(",", ":"),
        ).encode("ascii")

    def encode(self, snapshot, *, job_id):
        try:
            kind, generation, scope_hash = _binding(snapshot)
            payload = json.dumps(
                _pack(snapshot, [0]),
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("ascii")
            if len(payload) > self.MAX_BYTES:
                _reject()
            nonce = secrets.token_bytes(12)
            return (
                _PREFIX
                + nonce
                + self._cipher.encrypt(
                    nonce, payload, self._aad(job_id, kind, generation, scope_hash)
                )
            )
        except Exception:
            _reject()

    def decode(self, blob, *, job_id, target_kind, generation, scope_hash):
        try:
            if (
                type(blob) is not bytes
                or not len(_PREFIX) + 28
                < len(blob)
                <= self.MAX_BYTES + len(_PREFIX) + 28
                or not blob.startswith(_PREFIX)
            ):
                _reject()
            nonce = blob[len(_PREFIX) : len(_PREFIX) + 12]
            plain = self._cipher.decrypt(
                nonce,
                blob[len(_PREFIX) + 12 :],
                self._aad(job_id, target_kind, generation, scope_hash),
            )
            data = json.loads(
                plain.decode("ascii"),
                object_pairs_hook=_pairs,
                parse_constant=lambda _: _reject(),
            )
            result = _unpack(data, [0])
            kind, actual_generation, actual_hash = _binding(result)
            if (
                kind != target_kind
                or actual_generation != generation
                or not hmac.compare_digest(actual_hash, scope_hash)
            ):
                _reject()
            return result
        except Exception:
            _reject()
