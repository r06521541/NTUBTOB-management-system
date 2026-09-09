"""Separated code-only preparation, private verification and public cleanup phases."""

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tools import ios_profile_cms_verification as cms
from tools import ios_profile_intake as intake
from tools import ios_profile_validation

DIRECTORY = "ntubtob-profile-verification"
FILES = {"native", "receipt.json", "consumed"}
REASONS = (
    frozenset(
        {
            "PREPARED",
            "REMOVED",
            "VERIFIED_RESTRICTED",
            "FICTIONAL_RUNNER_REHEARSAL_VERIFIED",
            "CONTEXT_REJECTED",
            "ENVELOPE_REJECTED",
            "RECEIPT_REJECTED",
            "PREPARATION_REJECTED",
            "CLEANUP_REJECTED",
            "RUNNER_REJECTED",
        }
    )
    | cms.REASONS
)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def context():
    env = os.environ
    sha, nonce, run_id = (
        env.get("INPUT_APPROVED_SHA", ""),
        env.get("INPUT_NONCE", ""),
        env.get("GITHUB_RUN_ID", ""),
    )
    if (
        env.get("GITHUB_REPOSITORY") != intake.REPO
        or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or env.get("GITHUB_REF") != "refs/heads/main"
        or env.get("GITHUB_RUN_ATTEMPT") != "1"
        or env.get("GITHUB_SHA") != sha
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or not re.fullmatch(r"[0-9a-f]{64}", nonce)
        or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
    ):
        raise cms.Rejected("CONTEXT_REJECTED")
    return {"sha": sha, "nonce": nonce, "run_id": run_id}


def directory():
    root = Path(os.environ.get("RUNNER_TEMP", ""))
    if not root.is_absolute() or not root.is_dir() or root.resolve(strict=True) != root:
        raise cms.Rejected("RECEIPT_REJECTED")
    for path in (root, *root.parents):
        if path.is_symlink():
            raise cms.Rejected("RECEIPT_REJECTED")
    return root / DIRECTORY


def regular(path, maximum):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > maximum
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise cms.Rejected("RECEIPT_REJECTED")
    return info


def prepare():
    if (
        intake.SECRET in os.environ
        or platform.system() != "Darwin"
        or platform.machine() != "arm64"
    ):
        raise cms.Rejected("PREPARATION_REJECTED")
    binding = context()
    if intake.preparation.git("rev-parse", "HEAD") != binding["sha"]:
        raise cms.Rejected("CONTEXT_REJECTED")
    target = directory()
    target.mkdir(mode=0o700)  # exclusive existing-directory refusal
    with cms._compile_native() as binary:
        destination = target / "native"
        with binary.open("rb") as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output)
        destination.chmod(0o700)
    info = regular(destination, 20000000)
    receipt = {
        **binding,
        "digest": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "production": True,
    }
    with (target / "receipt.json").open("x", encoding="ascii") as output:
        output.write(json.dumps(receipt, sort_keys=True))
    (target / "receipt.json").chmod(0o600)
    return "PREPARED"


def prepared(binding):
    target = directory()
    info = target.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise cms.Rejected("RECEIPT_REJECTED")
    regular(target / "receipt.json", 4096)
    receipt = json.loads(
        (target / "receipt.json").read_bytes(), object_pairs_hook=unique
    )
    info = regular(target / "native", 20000000)
    if (
        set(receipt)
        != {"sha", "nonce", "run_id", "digest", "device", "inode", "size", "production"}
        or any(receipt[key] != value for key, value in binding.items())
        or receipt["production"] is not True
        or receipt["device"] != info.st_dev
        or receipt["inode"] != info.st_ino
        or receipt["size"] != info.st_size
        or receipt["digest"]
        != hashlib.sha256((target / "native").read_bytes()).hexdigest()
    ):
        raise cms.Rejected("RECEIPT_REJECTED")
    try:
        with (target / "consumed").open("x"):
            pass
    except OSError:
        raise cms.Rejected("RECEIPT_REJECTED") from None
    (target / "consumed").chmod(0o600)
    return target / "native"


def decode_envelope(raw, binding, now):
    try:
        if (
            type(raw) is not str
            or not 0 < len(raw.encode("ascii")) <= intake.MAX_ENVELOPE
            or type(now) is not datetime
            or now.utcoffset() is None
        ):
            raise ValueError
        value = json.loads(raw, object_pairs_hook=unique)
        if (
            type(value) is not dict
            or set(value)
            != {
                "version",
                "profile",
                "certificate",
                "team",
                "sha",
                "run_id",
                "nonce",
                "issued_at",
                "expires_at",
            }
            or type(value["version"]) is not int
            or value["version"] != 1
            or any(value[key] != expected for key, expected in binding.items())
            or type(value["issued_at"]) is not int
            or type(value["expires_at"]) is not int
            or value["expires_at"] - value["issued_at"] != 3600
            or not value["issued_at"] <= now.timestamp() < value["expires_at"]
            or type(value["team"]) is not str
            or not re.fullmatch(r"[A-Z0-9]{10}", value["team"])
        ):
            raise ValueError
        for key in ["profile", "certificate"]:
            if type(value[key]) is not str:
                raise ValueError
            value[key] = base64.b64decode(value[key], validate=True)
            if not 0 < len(value[key]) <= 65536:
                raise ValueError
        return value
    except Exception:
        raise cms.Rejected("ENVELOPE_REJECTED") from None


def verify():
    # Consume only from the step environment; never a file or CLI argument.
    raw = os.environ.pop(intake.SECRET, None)
    binding = context()
    binary = prepared(binding)
    now = datetime.now(timezone.utc)
    value = decode_envelope(raw, binding, now)
    parsed = cms.preflight(value["profile"])
    payload = cms._native_verified(parsed, now, binary)
    result = ios_profile_validation.validate_profile(
        payload,
        expected_bundle=intake.BUNDLE,
        expected_team=value["team"],
        expected_certificate_der=value["certificate"],
        now=now,
    )
    if result["classification"] != "PROFILE_CONTENT_MATCH_ONLY":
        raise cms.Rejected("PROFILE_CONTENT_REJECTED")
    return "VERIFIED_RESTRICTED"


def cleanup():
    if intake.SECRET in os.environ:
        raise cms.Rejected("CLEANUP_REJECTED")
    target = directory()
    if target.is_symlink():
        raise cms.Rejected("CLEANUP_REJECTED")
    if not target.exists():
        return "REMOVED"
    if target.is_symlink() or not target.is_dir():
        raise cms.Rejected("CLEANUP_REJECTED")
    children = list(target.iterdir())
    if any(
        child.name not in FILES or child.is_symlink() or not child.is_file()
        for child in children
    ):
        raise cms.Rejected("CLEANUP_REJECTED")
    for child in children:
        child.unlink()  # validated fixed public code/receipt only, never recursive
    target.rmdir()
    return "REMOVED"


def rehearsal():
    """Fictional end-to-end runner envelope/native/content binding, no Secret I/O."""
    from unittest.mock import patch

    from tools import ios_profile_cms_rehearsal as fixtures

    if intake.SECRET in os.environ:
        raise cms.Rejected("CONTEXT_REJECTED")

    values = fixtures.fixture()
    binding = {"sha": "a" * 40, "nonce": "b" * 64, "run_id": "123456"}
    raw = intake.envelope(
        values["cms"],
        values["der"],
        fixtures.TEAM,
        binding["sha"],
        int(binding["run_id"]),
        binding["nonce"],
        fixtures.NOW,
    ).decode("ascii")
    value = decode_envelope(raw, binding, fixtures.NOW)
    with cms._compile_native(_fictional_root=values["root"]) as binary:
        payload = cms._native_verified(
            cms.preflight(value["profile"]),
            fixtures.NOW,
            binary,
            _test_root=values["root"],
        )
        result = ios_profile_validation.validate_profile(
            payload,
            expected_bundle=fixtures.BUNDLE,
            expected_team=value["team"],
            expected_certificate_der=value["certificate"],
            now=fixtures.NOW,
        )
        if result["classification"] != "PROFILE_CONTENT_MATCH_ONLY":
            raise cms.Rejected("PROFILE_CONTENT_REJECTED")
    # Exercise the real production phase boundary too: the fictional root MUST
    # fail production verification, even though the separate test target passed.
    with tempfile.TemporaryDirectory(prefix="fictional-runner-") as temporary:
        sha = intake.preparation.git("rev-parse", "HEAD")
        env = {
            "GITHUB_REPOSITORY": intake.REPO,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": sha,
            "INPUT_APPROVED_SHA": sha,
            "INPUT_NONCE": "b" * 64,
            "GITHUB_RUN_ID": "123456",
            "RUNNER_TEMP": str(Path(temporary).resolve(strict=True)),
        }
        with patch.dict(os.environ, env):
            try:
                prepare()
                os.environ[intake.SECRET] = intake.envelope(
                    values["cms"],
                    values["der"],
                    fixtures.TEAM,
                    sha,
                    123456,
                    "b" * 64,
                    datetime.now(timezone.utc),
                ).decode("ascii")
                try:
                    verify()
                except cms.Rejected as error:
                    if error.args != ("CMS_TRUST_REJECTED",):
                        raise
                else:
                    raise cms.Rejected("RUNNER_REJECTED")
            finally:
                os.environ.pop(intake.SECRET, None)
                cleanup()
            if directory().exists():
                raise cms.Rejected("CLEANUP_REJECTED")
    return "FICTIONAL_RUNNER_REHEARSAL_VERIFIED"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    actions = {
        "--prepare": prepare,
        "--verify": verify,
        "--cleanup": cleanup,
        "--rehearsal": rehearsal,
    }
    try:
        if len(args) != 1 or args[0] not in actions:
            raise ValueError
        reason = actions[args[0]]()
    except (Exception, KeyboardInterrupt) as error:
        reason = (
            error.args[0]
            if isinstance(error, cms.Rejected)
            and error.args
            and error.args[0] in REASONS
            else "RUNNER_REJECTED"
        )
    print(
        json.dumps(
            {
                "classification": reason,
                "restricted_profile_verified": reason == "VERIFIED_RESTRICTED",
                "revocation_verified": False,
                "signing_authorized": False,
                "upload_authorized": False,
                "release_authorized": False,
            },
            sort_keys=True,
        )
    )
    return (
        0
        if reason
        in {
            "PREPARED",
            "REMOVED",
            "VERIFIED_RESTRICTED",
            "FICTIONAL_RUNNER_REHEARSAL_VERIFIED",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
