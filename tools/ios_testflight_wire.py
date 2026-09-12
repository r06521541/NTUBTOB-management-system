"""Finite, purpose-separated private transfer; not dispatch or release authority.

GitHub's runner service receives environment secrets at job start. Step-only
ingress is NOT end-to-end encryption, read-once custody or same-user isolation.
The controller must remove remote secrets and keep Apple Login keys outside this
transport. Signing and upload children receive only their separate stdin frame.
"""

import hashlib
import json
import re
from dataclasses import dataclass

REPO = "r06521541/NTUBTOB-management-system"
WORKFLOW = "ios-owner-testflight.yml"
ENVIRONMENT = "ios-owner-testflight"
SIGN_NAMES = tuple("IOS_TF_SIGN_" + str(i) for i in range(4))
ASC_NAME = "IOS_TF_ASC"
MANIFEST = "IOS_TF_BINDING"
SECRETS = (*SIGN_NAMES, ASC_NAME, MANIFEST)
MAX_SIGN = 131072
MAX_ASC = 8192
MAX_ENVIRONMENT = 147456
CHUNK = 32768
TTL = 7200


class Rejected(Exception):
    def __init__(self):
        super().__init__("PRIVATE_TRANSFER_REJECTED")


@dataclass(frozen=True)
class Binding:
    sha: str
    nonce: str
    run_id: str


@dataclass(frozen=True, repr=False)
class Transfer:
    signing_frame: bytes
    asc_frame: bytes
    binding: Binding


def validate_binding(binding):
    if type(binding) is not Binding or any(
        type(value) is not str or not re.fullmatch(pattern, value)
        for value, pattern in (
            (binding.sha, r"[0-9a-f]{40}"),
            (binding.nonce, r"[0-9a-f]{64}"),
            (binding.run_id, r"[1-9][0-9]{0,19}"),
        )
    ):
        raise Rejected()


def context(env):
    binding = Binding(
        env.get("INPUT_APPROVED_SHA", ""),
        env.get("INPUT_NONCE", ""),
        env.get("GITHUB_RUN_ID", ""),
    )
    validate_binding(binding)
    expected = {
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_WORKFLOW_REF": REPO
        + "/.github/workflows/"
        + WORKFLOW
        + "@refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": binding.sha,
        "RUNNER_OS": "macOS",
    }
    if any(env.get(k) != v for k, v in expected.items()):
        raise Rejected()
    return binding


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Rejected()
        value[key] = item
    return value


def _document(value, limit):
    if type(value) is not str or not 0 < len(value.encode("ascii")) <= limit:
        raise Rejected()
    document = json.loads(value, object_pairs_hook=_unique)
    if type(document) is not dict:
        raise Rejected()
    return document


def _frame(value, limit):
    if (
        type(value) is not bytes
        or not 0 < len(value) <= limit
        or any(c < 32 or c > 126 for c in value)
    ):
        raise Rejected()
    return value.decode("ascii")


def pack(signing_frame, asc_frame, binding, *, now):
    """Before dispatch/PUT; caller supplies reviewed frame schemas, not files."""
    try:
        validate_binding(binding)
        if type(now) is not int or now < 0:
            raise Rejected()
        signing = _frame(signing_frame, MAX_SIGN)
        asc = _frame(asc_frame, MAX_ASC)
        values = {
            name: json.dumps(
                {"index": index, "data": signing[index * CHUNK : (index + 1) * CHUNK]},
                separators=(",", ":"),
            )
            for index, name in enumerate(SIGN_NAMES)
        }
        values[ASC_NAME] = asc
        values[MANIFEST] = json.dumps(
            {
                "format": 1,
                "sha": binding.sha,
                "nonce": binding.nonce,
                "run_id": binding.run_id,
                "issued_at": now,
                "expires_at": now + TTL,
                "sign_sha256": hashlib.sha256(signing_frame).hexdigest(),
                "asc_sha256": hashlib.sha256(asc_frame).hexdigest(),
            },
            separators=(",", ":"),
        )
        _bounds(values)
        return values
    except Exception:
        raise Rejected() from None


def _bounds(values):
    lengths = []
    for name in SECRETS:
        raw = values[name]
        if type(raw) is not str:
            raise Rejected()
        length = len(raw.encode("ascii"))
        if not 0 < length <= 49152:
            raise Rejected()
        lengths.append(length)
    if sum(lengths) > MAX_ENVIRONMENT:
        raise Rejected()


def consume(environment, binding, *, now):
    # Remove every reserved value even when one is missing or parsing fails.
    # This does not erase an inherited process environment or its memory pages.
    unexpected = [
        n for n in environment if n.startswith("IOS_TF_") and n not in SECRETS
    ]
    values = {name: environment.pop(name, None) for name in SECRETS}
    for name in unexpected:
        environment.pop(name, None)
    try:
        if unexpected:
            raise Rejected()
        validate_binding(binding)
        _bounds(values)
        manifest = _document(values[MANIFEST], 4096)
        if (
            set(manifest)
            != {
                "format",
                "sha",
                "nonce",
                "run_id",
                "issued_at",
                "expires_at",
                "sign_sha256",
                "asc_sha256",
            }
            or type(manifest["format"]) is not int
            or manifest["format"] != 1
            or manifest["sha"] != binding.sha
            or manifest["nonce"] != binding.nonce
            or manifest["run_id"] != binding.run_id
            or type(now) is not int
            or type(manifest["issued_at"]) is not int
            or type(manifest["expires_at"]) is not int
            or manifest["issued_at"] < 0
            or manifest["expires_at"] - manifest["issued_at"] != TTL
            or not manifest["issued_at"] <= now < manifest["expires_at"]
        ):
            raise Rejected()
        chunks = []
        for index, name in enumerate(SIGN_NAMES):
            item = _document(values[name], 49152)
            if (
                set(item) != {"index", "data"}
                or type(item["index"]) is not int
                or item["index"] != index
                or type(item["data"]) is not str
                or len(item["data"]) > CHUNK
            ):
                raise Rejected()
            chunks.append(item["data"])
        sign = "".join(chunks).encode("ascii")
        asc = values[ASC_NAME].encode("ascii")
        _frame(sign, MAX_SIGN)
        _frame(asc, MAX_ASC)
        if (
            hashlib.sha256(sign).hexdigest() != manifest["sign_sha256"]
            or hashlib.sha256(asc).hexdigest() != manifest["asc_sha256"]
        ):
            raise Rejected()
        return Transfer(sign, asc, binding)
    except Exception:
        raise Rejected() from None
