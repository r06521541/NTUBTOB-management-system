"""Callable private phase orchestration; no CLI, intake or distribution.

Caller must retain private results, prohibit concurrent root access, and never
reconstruct a consumed candidate/session to retry uncertainty. Same-user attacks
are not isolated. Final cleanup requires workers to have synchronously stopped.
"""

import os
import re
import stat
import threading
from dataclasses import dataclass, field

from tools import ios_testflight_inspection as inspection
from tools import ios_testflight_signing as signing
from tools import ios_testflight_upload as upload


class Rejected(Exception):
    def __init__(self):
        super().__init__("RUNNER_REJECTED")


@dataclass(repr=False)
class BoundCandidate:
    prepared: signing.PreparedSigning
    sha256: str
    size: int
    file_identity: tuple
    version: str
    build: int
    consumed: bool = False
    closed: bool = False
    uncertain: bool = False
    lock: object = field(default_factory=threading.Lock)


@dataclass(frozen=True, repr=False)
class PhaseResult:
    classification: str
    candidate: BoundCandidate = None

    def public(self):
        return {
            "classification": (
                self.classification
                if self.classification
                in {"CANDIDATE_BOUND", "STOP", "UNRESOLVED", "CLEANED"}
                else "UNRESOLVED"
            ),
            "upload_authorized": False,
            "release_authorized": False,
            "device_verified": False,
        }


@dataclass(repr=False)
class UploadProgress:
    candidate: BoundCandidate
    session: object
    outcome: object


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid)


def _root(prepared):
    if type(prepared) is not signing.PreparedSigning:
        raise Rejected()
    root = prepared.root
    signing._safe(root)
    if root.parent != signing.feasibility.os_temp_root() or not re.fullmatch(
        r"task-198-[A-Za-z0-9_-]+", root.name
    ):
        raise Rejected()
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or (info.st_dev, info.st_ino) != prepared.root_identity
    ):
        raise Rejected()
    return root, info


def _bound(candidate):
    root, _ = _root(candidate.prepared)
    digest, info = signing._private_digest(
        root / "candidate.ipa", 536870912, return_identity=True
    )
    if (
        digest != candidate.sha256
        or info.st_size != candidate.size
        or _identity(info) != candidate.file_identity
    ):
        raise Rejected()
    return root


def _cleanup(prepared, *, keep_candidate):
    """Bounded fd-relative deletion, no following links including DerivedData."""
    root, original = _root(prepared)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    budget = [100000]
    try:
        if _identity(os.fstat(fd)) != _identity(original):
            raise Rejected()

        def walk(parent, depth):
            if depth > 64:
                raise Rejected()
            for name in os.listdir(parent):
                budget[0] -= 1
                if budget[0] < 0 or name in {".", ".."} or "/" in name:
                    raise Rejected()
                if depth == 0 and keep_candidate and name == "candidate.ipa":
                    continue
                prior = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if prior.st_uid != os.getuid():
                    raise Rejected()
                if stat.S_ISDIR(prior.st_mode):
                    child = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=parent,
                    )
                    try:
                        if _identity(os.fstat(child)) != _identity(prior):
                            raise Rejected()
                        walk(child, depth + 1)
                    finally:
                        os.close(child)
                    if _identity(
                        os.stat(name, dir_fd=parent, follow_symlinks=False)
                    ) != _identity(prior):
                        raise Rejected()
                    os.rmdir(name, dir_fd=parent)
                elif stat.S_ISREG(prior.st_mode) or stat.S_ISLNK(prior.st_mode):
                    if _identity(
                        os.stat(name, dir_fd=parent, follow_symlinks=False)
                    ) != _identity(prior):
                        raise Rejected()
                    os.unlink(name, dir_fd=parent)
                else:
                    raise Rejected()

        walk(fd, 0)
        if set(os.listdir(fd)) != (
            {"candidate.ipa"} if keep_candidate else set()
        ) or _identity(root.lstat()) != _identity(original):
            raise Rejected()
    finally:
        os.close(fd)
    if not keep_candidate:
        parent = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if _identity(
                os.stat(root.name, dir_fd=parent, follow_symlinks=False)
            ) != _identity(original):
                raise Rejected()
            os.rmdir(root.name, dir_fd=parent)
            try:
                os.stat(root.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise Rejected()
        finally:
            os.close(parent)


def sign_phase(prepared, material, *, previous_build, now):
    try:
        _root(prepared)
        result = signing.sign(prepared, **material)
        if result.get("cleanup") != "VERIFIED":
            return PhaseResult("UNRESOLVED")
        if result.get("classification") != "EXPORTED_UNINSPECTED":
            return PhaseResult("STOP")
        if result.get("operation") != "EXPORTED" or result.get("stage") != "complete":
            return PhaseResult("UNRESOLVED")
        if result.get("artifact_relative") != "candidate.ipa":
            return PhaseResult("UNRESOLVED")
        checked = inspection.inspect(
            prepared,
            expected_sha256=result["artifact_sha256"],
            certificate_der=material["certificate_der"],
            profile=material["profile"],
            team=material["team"],
            version=material["version"],
            build=material["build"],
            previous_build=previous_build,
            now=now,
        )
        if checked.get("cleanup_verified") is not True:
            return PhaseResult("UNRESOLVED")
        if checked.get("classification") != "ARTIFACT_BOUND":
            return PhaseResult("STOP")
        digest, info = signing._private_digest(
            prepared.root / "candidate.ipa", 536870912, return_identity=True
        )
        if digest != result["artifact_sha256"]:
            raise Rejected()
        candidate = BoundCandidate(
            prepared,
            digest,
            info.st_size,
            _identity(info),
            material["version"],
            material["build"],
        )
        _cleanup(prepared, keep_candidate=True)
        _bound(candidate)
        return PhaseResult("CANDIDATE_BOUND", candidate)
    except Exception:
        return PhaseResult("UNRESOLVED")


def upload_phase(
    candidate, asc, *, app_id, owner_group_id, owner_tester_id, version, build
):
    if type(candidate) is not BoundCandidate or not candidate.lock.acquire(
        blocking=False
    ):
        raise Rejected()
    progress = None
    attempted = False
    try:
        if (
            candidate.consumed
            or candidate.closed
            or candidate.uncertain
            or (version, build) != (candidate.version, candidate.build)
        ):
            raise Rejected()
        root = _bound(candidate)
        candidate.consumed = True
        attempted = True
        session = upload.UploadSession(
            asc,
            app_id=app_id,
            owner_group_id=owner_group_id,
            owner_tester_id=owner_tester_id,
            version=version,
            build=build,
            candidate_root=root,
            expected_sha256=candidate.sha256,
            expected_size=candidate.size,
        )
        progress = UploadProgress(candidate, session, None)
        progress.outcome = session.upload_once()
        # Return the mutation outcome with its private receipt; caller can invoke
        # reconcile once per desired observation, using the same bounded session.
        return progress
    except Exception:
        if attempted:
            candidate.uncertain = True
        if progress is not None:
            progress.outcome = upload.Outcome(
                "UPLOAD_UNCERTAIN", progress.session.receipt, "reconcile"
            )
            return progress
        raise Rejected() from None
    finally:
        candidate.lock.release()


def reconcile(progress):
    if type(progress) is not UploadProgress or not progress.candidate.lock.acquire(
        blocking=False
    ):
        raise Rejected()
    try:
        if progress.candidate.uncertain:
            raise Rejected()
        progress.outcome = progress.session.reconcile()
        return progress
    except Exception:
        raise Rejected() from None
    finally:
        progress.candidate.lock.release()


def final_cleanup(candidate):
    if type(candidate) is not BoundCandidate or not candidate.lock.acquire(
        blocking=False
    ):
        return PhaseResult("UNRESOLVED")
    try:
        if candidate.closed or candidate.uncertain:
            return PhaseResult("UNRESOLVED")
        _bound(candidate)
        _cleanup(candidate.prepared, keep_candidate=False)
        candidate.closed = True
        return PhaseResult("CLEANED")
    except Exception:
        candidate.uncertain = True
        return PhaseResult("UNRESOLVED")
    finally:
        candidate.lock.release()
