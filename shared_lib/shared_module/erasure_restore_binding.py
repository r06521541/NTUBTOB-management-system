"""Pure pseudonymous restore binding, not retention or deletion authority.

Use only on a complete, authorized restore inventory BEFORE exposing restored
data. A mismatch does not authorize login, account creation or notification.
Records and keys need separately approved bounded custody covering every backup
and export horizon; this helper never expires evidence merely by elapsed time.
No raw provider subject or generation is stored in the returned binding. The
digest is still sensitive pseudonymous data, not anonymous/public evidence.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from uuid import UUID


class RestoreBindingUnavailable(ValueError):
    """Fixed configuration/input failure; never interpret it as no-match."""


def _reject():
    raise RestoreBindingUnavailable("restore_binding_unavailable")


def _uuid(value):
    try:
        if type(value) is str and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    _reject()


def _name(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        _reject()
    return value


@dataclass(frozen=True, repr=False)
class RestoreBinding:
    version: int
    key_id: str
    digest: str


class RestoreBindingCodec:
    """Explicit namespace/keyring injected by trusted composition, never env I/O.

    Keep old keys only under that composition's approved horizon; removal while
    relevant bindings remain makes verification unavailable rather than bypassing
    suppression. This primitive does not implement the key-retention policy.
    """

    def __init__(self, *, namespace: str, active_key: str, keys: dict[str, bytes]):
        self._namespace = _uuid(namespace)
        self._active = _name(active_key)
        if type(keys) is not dict or not 1 <= len(keys) <= 32:
            _reject()
        self._keys = {}
        for key_id, key in keys.items():
            _name(key_id)
            if type(key) is not bytes or not 32 <= len(key) <= 128:
                _reject()
            self._keys[key_id] = key
        if self._active not in self._keys:
            _reject()

    def bind(self, *, provider, audience, subject, generation) -> RestoreBinding:
        return RestoreBinding(
            1,
            self._active,
            self._digest(self._active, provider, audience, subject, generation),
        )

    def matches(self, binding, *, provider, audience, subject, generation) -> bool:
        if (
            type(binding) is not RestoreBinding
            or type(binding.version) is not int
            or binding.version != 1
            or type(binding.digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", binding.digest) is None
        ):
            _reject()
        _name(binding.key_id)
        expected = self._digest(binding.key_id, provider, audience, subject, generation)
        return hmac.compare_digest(binding.digest, expected)

    def _digest(self, key_id, provider, audience, subject, generation):
        if type(provider) is not str or provider not in {"apple", "google", "line"}:
            _reject()
        for value in (audience, subject):
            if (
                type(value) is not str
                or not 1 <= len(value) <= 255
                or any(
                    ord(character) < 32
                    or ord(character) == 127
                    or 0xD800 <= ord(character) <= 0xDFFF
                    for character in value
                )
            ):
                _reject()
        _uuid(generation)
        key = self._keys.get(key_id)
        if key is None:
            _reject()
        # A JSON array avoids delimiter ambiguity. Do not normalize subjects or
        # audiences: provider identities are exact, not names/email addresses.
        payload = json.dumps(
            [
                "ntubtob-account-erasure-restore-binding",
                1,
                self._namespace,
                key_id,
                provider,
                audience,
                subject,
                generation,
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        return hmac.new(key, payload, hashlib.sha256).hexdigest()
