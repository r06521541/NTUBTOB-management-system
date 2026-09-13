"""GET-only, transient confirmed-unsent proof. Never grants live authority.

The journal supplies eligibility and exclusive, identity-bound raw-byte custody.
Keep that same object/handle held through consumption and the successor append.
Remote checks are a bounded observation, not a cross-system atomic snapshot or
protection against concurrent Owner/admin remote mutations. No payloads are read.
"""

import math
import re
import threading
import time

from tools import ios_testflight_diagnostics as diagnostics
from tools import ios_testflight_dispatch as dispatch

REASONS = frozenset(
    {
        "UNSENT_JOURNAL_REJECTED",
        "UNSENT_REMOTE_REJECTED",
        "UNSENT_SOURCE_REJECTED",
        "UNSENT_PROOF_EXPIRED",
        "UNSENT_PROOF_MISMATCH",
        "UNSENT_PROOF_CONSUMED",
    }
)
_FIELDS = frozenset(
    {"sha", "nonce", "digest", "issued", "version", "build", "previous_build"}
)
_TOKEN = object()


class Rejected(Exception):
    def __init__(self, reason, failure=None):
        super().__init__(
            reason
            if type(reason) is str and reason in REASONS
            else "UNSENT_REMOTE_REJECTED"
        )
        self.failure = diagnostics.sanitize(failure)


def _sha(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise Rejected("UNSENT_SOURCE_REJECTED")


def _snapshot(journal):
    try:
        value = journal.unsent_snapshot()
        if type(value) is not dict or set(value) != _FIELDS:
            raise ValueError()
        _sha(value["sha"])
        if (
            any(
                type(value[k]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value[k])
                for k in ("nonce", "digest")
            )
            or type(value["issued"]) is not int
            or value["issued"] <= 0
            or type(value["version"]) is not str
            or not re.fullmatch(
                r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}", value["version"]
            )
            or type(value["build"]) is not int
            or type(value["previous_build"]) is not int
            or not 0 <= value["previous_build"] < value["build"] <= 2147483647
        ):
            raise ValueError()
        return dict(value)
    except (Exception, KeyboardInterrupt):
        raise Rejected("UNSENT_JOURNAL_REJECTED") from None


def _now(clock):
    try:
        value = clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError()
        return value
    except (Exception, KeyboardInterrupt):
        raise Rejected("UNSENT_PROOF_EXPIRED") from None


class Proof:
    __slots__ = (
        "_journal",
        "_sha",
        "_snapshot",
        "_started",
        "_verified",
        "_consumed",
        "_lock",
    )

    def __init__(self, token, journal, sha, snapshot, started, verified):
        if token is not _TOKEN:
            raise Rejected("UNSENT_PROOF_MISMATCH")
        self._journal, self._sha = journal, sha
        self._snapshot = dict(snapshot)
        self._started, self._verified = started, verified
        self._consumed = False
        self._lock = threading.Lock()

    def __repr__(self):
        return "<UnsentProof>"

    def consume(self, journal, sha, *, clock=time.monotonic):
        with self._lock:
            if self._consumed:
                raise Rejected("UNSENT_PROOF_CONSUMED")
            self._consumed = True
        # Mark first, including malformed arguments, stale time and read failures.
        _sha(sha)
        now = _now(clock)
        if now < self._verified or now - self._started > 60:
            raise Rejected("UNSENT_PROOF_EXPIRED")
        try:
            if (
                journal is not self._journal
                or sha != self._sha
                or journal.writable is not True
            ):
                raise Rejected("UNSENT_PROOF_MISMATCH")
            if _snapshot(journal) != self._snapshot:
                raise Rejected("UNSENT_PROOF_MISMATCH")
        except Rejected:
            raise
        except (Exception, KeyboardInterrupt):
            raise Rejected("UNSENT_PROOF_MISMATCH") from None
        after = _now(clock)
        if after < now or after - self._started > 60:
            raise Rejected("UNSENT_PROOF_EXPIRED")
        return self._snapshot["digest"]


def verify(journal, sha, *, session_factory=dispatch.Session, clock=time.monotonic):
    _sha(sha)
    started = last = _now(clock)
    initial = _snapshot(journal)

    def tick():
        nonlocal last
        now = _now(clock)
        if now < last or now - started > 60:
            raise Rejected("UNSENT_PROOF_EXPIRED")
        last = now

    try:
        probe = session_factory(b"{}", b"{}", sha=sha)
        probe.recovery_only = True  # Defense in depth: no dispatch/approve/PUT.
        tick()
        probe.policy()
        tick()
        probe.context("recovery", "run_listing")
        runs = probe.get(
            dispatch.WORKFLOW
            + "/runs?head_sha="
            + initial["sha"]
            + "&event=workflow_dispatch&per_page=100&page=1"
        )
        if (
            type(runs) is not dict
            or type(runs.get("total_count")) is not int
            or runs["total_count"] != 0
            or type(runs.get("workflow_runs")) is not list
            or runs["workflow_runs"] != []
        ):
            raise Rejected("UNSENT_REMOTE_REJECTED")
        tick()
        probe.context("dispatch_preflight", "secret_inventory")
        names = probe.listing()
        if (
            type(names) is not set
            or any(type(name) is not str for name in names)
            or set(dispatch.wire.SECRETS) & names
        ):
            raise Rejected("UNSENT_REMOTE_REJECTED")
        tick()
        for name in dispatch.wire.SECRETS:
            probe.context("dispatch_preflight", "secret_absence")
            response = probe.call("GET", dispatch.SECRET + name)
            if (
                type(response) is not tuple
                or len(response) != 2
                or type(response[0]) is not int
                or response[0] != 404
            ):
                raise Rejected("UNSENT_REMOTE_REJECTED")
            tick()
    except Rejected:
        raise
    except (Exception, KeyboardInterrupt) as error:
        detail = error.failure if isinstance(error, dispatch.Rejected) else None
        raise Rejected("UNSENT_REMOTE_REJECTED", detail) from None
    if _snapshot(journal) != initial:
        raise Rejected("UNSENT_PROOF_MISMATCH")
    tick()
    return Proof(_TOKEN, journal, sha, initial, started, last)
