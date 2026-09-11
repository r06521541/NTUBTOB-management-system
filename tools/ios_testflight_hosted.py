"""Protected hosted ingress and purpose-separated stdin workers.

Never invoke manually with real material: the reviewed local operator owns the
exact main/run/environment approval and remote secret cleanup. Ingress itself
holds both frames in memory; only child custody is separated. No secure-erasure
or protection from the runner service/same-user compromise is claimed.
"""

import base64
import json
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from tools import ios_testflight_inputs as inputs
from tools import ios_testflight_inspection as inspection
from tools import ios_testflight_runner as runner
from tools import ios_testflight_signing as signing
from tools import ios_testflight_wire as wire

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 196608
MAX_OUTPUT = 65536
STATE = "ntubtob-owner-testflight"
LIVE_CONTROLLER_READY = False


class Rejected(Exception):
    def __init__(self):
        super().__init__("HOSTED_CONTRACT_REJECTED")


class Unresolved(Exception):
    def __init__(self):
        super().__init__("HOSTED_CLEANUP_UNRESOLVED")


def document(raw, maximum=MAX_INPUT):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected()
    value = json.loads(raw, object_pairs_hook=wire._unique)
    if type(value) is not dict:
        raise Rejected()
    return value


def sign_material(raw):
    try:
        value = document(raw, wire.MAX_SIGN)
        if set(value) != {
            "p12",
            "password",
            "profile",
            "certificate",
            "team",
            "uuid",
            "version",
            "build",
            "defines",
        }:
            raise Rejected()
        material = {
            name: base64.b64decode(value[key], validate=True)
            for name, key in (
                ("p12", "p12"),
                ("profile", "profile"),
                ("certificate_der", "certificate"),
            )
        }
        material.update(
            password=value["password"].encode("utf-8"),
            team=value["team"],
            profile_uuid=value["uuid"],
            version=value["version"],
            build=value["build"],
            build_defines=value["defines"],
        )
        signing.frame(**material)  # Reuse the exact existing input contract.
        return material
    except Exception:
        raise Rejected() from None


def asc_fields(raw):
    value = document(raw, wire.MAX_ASC)
    if set(value) != {
        "pem",
        "key_id",
        "issuer_id",
        "app_id",
        "owner_group_id",
        "owner_tester_id",
        "version",
        "build",
        "previous_build",
    }:
        raise Rejected()
    for name in ("app_id", "owner_group_id", "owner_tester_id"):
        runner.upload.identifier(value[name])
    if (
        type(value["version"]) is not str
        or not re.fullmatch(
            r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}", value["version"]
        )
        or type(value["build"]) is not int
        or type(value["previous_build"]) is not int
        or not 0 <= value["previous_build"] < value["build"] <= 2147483647
    ):
        raise Rejected()
    return value


def asc_material(raw):
    try:
        value = asc_fields(raw)
        asc = inputs.load_asc_key(
            base64.b64decode(value["pem"], validate=True),
            key_id=value["key_id"],
            issuer_id=value["issuer_id"],
        )
        return asc, {
            key: value[key]
            for key in (
                "app_id",
                "owner_group_id",
                "owner_tester_id",
                "version",
                "build",
            )
        }
    except Exception:
        raise Rejected() from None


def prepared_record(prepared):
    if type(prepared) is not signing.PreparedSigning:
        raise Rejected()
    value = asdict(prepared)
    value["repo"], value["root"] = str(prepared.repo), str(prepared.root)
    value["root_identity"] = list(prepared.root_identity)
    return value


def prepared_from(value):
    try:
        if type(value) is not dict or set(value) != {
            f.name for f in fields(signing.PreparedSigning)
        }:
            raise Rejected()
        result = dict(value)
        for name in ("root", "repo"):
            if type(result[name]) is not str or not 1 <= len(result[name]) <= 4096:
                raise Rejected()
            result[name] = Path(result[name])
            if not result[name].is_absolute() or ".." in result[name].parts:
                raise Rejected()
        identity = result["root_identity"]
        if (
            type(identity) is not list
            or len(identity) != 2
            or any(type(v) is not int or v < 0 for v in identity)
        ):
            raise Rejected()
        result["root_identity"] = tuple(identity)
        for name, size in (
            ("commit", 40),
            ("helper_digest", 64),
            ("source_digest", 64),
        ):
            if type(result[name]) is not str or not re.fullmatch(
                r"[0-9a-f]{" + str(size) + "}", result[name]
            ):
                raise Rejected()
        if "dependency_digest" in result and (
            type(result["dependency_digest"]) is not str
            or not re.fullmatch(r"(?:[0-9a-f]{64})?", result["dependency_digest"])
        ):
            raise Rejected()
        return signing.PreparedSigning(**result)
    except Exception:
        raise Rejected() from None


def candidate_record(candidate):
    return {
        "prepared": prepared_record(candidate.prepared),
        "sha256": candidate.sha256,
        "size": candidate.size,
        "file_identity": list(candidate.file_identity),
        "version": candidate.version,
        "build": candidate.build,
    }


def candidate_from(value):
    if type(value) is not dict or set(value) != {
        "prepared",
        "sha256",
        "size",
        "file_identity",
        "version",
        "build",
    }:
        raise Rejected()
    if (
        type(value["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
        or type(value["size"]) is not int
        or not 0 < value["size"] <= 536870912
        or type(value["file_identity"]) is not list
        or len(value["file_identity"]) != 4
        or any(type(i) is not int or i < 0 for i in value["file_identity"])
        or type(value["version"]) is not str
        or not re.fullmatch(
            r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}", value["version"]
        )
        or type(value["build"]) is not int
        or not 1 <= value["build"] <= 2147483647
    ):
        raise Rejected()
    candidate = runner.BoundCandidate(
        prepared_from(value["prepared"]),
        value["sha256"],
        value["size"],
        tuple(value["file_identity"]),
        value["version"],
        value["build"],
    )
    runner._bound(candidate)
    return candidate


def worker(kind, payload, *, timeout):
    if (
        kind not in {"sign", "upload"}
        or type(payload) is not bytes
        or not 0 < len(payload) <= MAX_INPUT
    ):
        raise Rejected()
    child = None
    workers, output, failed = [], [], []
    try:
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tools.ios_testflight_hosted",
                "--" + kind + "-worker",
            ],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "DEVELOPER_DIR": signing.DEVELOPER},
            start_new_session=True,
            umask=0o077,
        )

        def write():
            try:
                child.stdin.write(payload)
                child.stdin.close()
            except Exception:
                failed.append(True)

        def read():
            try:
                output.append(child.stdout.read(MAX_OUTPUT + 1))
            except Exception:
                failed.append(True)

        workers = [
            threading.Thread(target=write, daemon=True),
            threading.Thread(target=read, daemon=True),
        ]
        for thread in workers:
            thread.start()
        child.wait(timeout=timeout)
        for thread in workers:
            thread.join(2)
        if (
            child.returncode
            or failed
            or any(t.is_alive() for t in workers)
            or len(output) != 1
        ):
            raise Unresolved()
        return document(output[0], MAX_OUTPUT)
    except Exception:
        raise Unresolved() from None
    finally:
        if child is not None:
            try:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)
                inspection.group_stopped(child.pid)
                for thread in workers:
                    thread.join(2)
                if any(t.is_alive() for t in workers):
                    raise Unresolved()
            except Exception:
                raise Unresolved() from None


def state_directory():
    root = Path(os.environ.get("RUNNER_TEMP", ""))
    signing._safe(root)
    if not root.is_dir():
        raise Rejected()
    return root / STATE


def write_state(directory, name, value):
    if name not in {"prepared.json", "consumed", "result.json"}:
        raise Rejected()
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
    if len(raw) > MAX_OUTPUT:
        raise Rejected()
    fd = os.open(
        directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "wb") as target:
        target.write(raw)
        target.flush()
        os.fsync(target.fileno())


def private_state(directory, name):
    """Bounded same-handle read; never reopen a private payload to parse it."""
    if name not in {"prepared.json", "consumed", "result.json"}:
        raise Rejected()
    path = directory / name
    signing._safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 0 < before.st_size <= MAX_OUTPUT
        ):
            raise Rejected()
        raw = bytearray()
        while len(raw) <= MAX_OUTPUT:
            block = os.read(fd, min(8192, MAX_OUTPUT + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        after = os.fstat(fd)
        current = path.lstat()
        identity = lambda s: (
            s.st_dev,
            s.st_ino,
            s.st_mode,
            s.st_uid,
            s.st_nlink,
            s.st_size,
            s.st_mtime_ns,
            s.st_ctime_ns,
        )
        if (
            identity(before) != identity(after)
            or identity(after) != identity(current)
            or len(raw) != before.st_size
        ):
            raise Rejected()
        return document(bytes(raw), MAX_OUTPUT), identity(current)
    finally:
        os.close(fd)


def read_prepared(binding):
    directory = state_directory()
    signing._safe(directory)
    info = directory.lstat()
    if info.st_uid != os.getuid() or signing.stat.S_IMODE(info.st_mode) != 0o700:
        raise Rejected()
    value, _ = private_state(directory, "prepared.json")
    if set(value) != {"binding", "prepared"} or value["binding"] != asdict(binding):
        raise Rejected()
    prepared = prepared_from(value["prepared"])
    if prepared.repo != ROOT or prepared.commit != binding.sha:
        raise Rejected()
    runner._root(prepared)
    return prepared


def prepare_phase():
    if any(k.startswith("IOS_TF_") for k in os.environ):
        raise Rejected()
    binding = wire.context(os.environ)
    directory = state_directory()
    directory.mkdir(mode=0o700)
    prepared = signing.prepare(ROOT, expected_commit=binding.sha)
    write_state(
        directory,
        "prepared.json",
        {"binding": asdict(binding), "prepared": prepared_record(prepared)},
    )
    return public_result("PREPARED", cleanup=False)


def sign_worker(value):
    if (
        set(value) != {"prepared", "frame", "previous_build"}
        or type(value["frame"]) is not str
    ):
        raise Rejected()
    prepared = prepared_from(value["prepared"])
    if prepared.repo != ROOT:
        raise Rejected()
    result = runner.sign_phase(
        prepared,
        sign_material(value["frame"].encode("ascii")),
        previous_build=value["previous_build"],
        now=datetime.now(timezone.utc),
    )
    if result.classification == "CANDIDATE_BOUND":
        return {
            "classification": "CANDIDATE_BOUND",
            "candidate": candidate_record(result.candidate),
        }
    if result.classification == "STOP":
        # STOP only follows a verified native/inspection child cleanup. It does
        # not itself mean the retained archive/DerivedData tree was removed.
        runner._cleanup(prepared, keep_candidate=False)
        return {"classification": "STOP", "cleanup_verified": True}
    return {"classification": "UNRESOLVED", "cleanup_verified": False}


def upload_worker(value):
    if (
        set(value) != {"candidate", "frame", "expires_at"}
        or type(value["frame"]) is not str
    ):
        raise Rejected()
    candidate = candidate_from(value["candidate"])
    try:
        if (
            type(value["expires_at"]) is not int
            or not time.time() < value["expires_at"]
        ):
            raise Rejected()
        asc, target = asc_material(value["frame"].encode("ascii"))
    except Exception:
        cleanup = runner.final_cleanup(candidate).classification == "CLEANED"
        return {"classification": "STOP", "cleanup_verified": cleanup, "receipt": {}}
    progress = runner.upload_phase(candidate, asc, **target)
    cleanup = runner.final_cleanup(candidate).classification == "CLEANED"
    if cleanup:
        for index in range(20):
            if progress.outcome.classification not in {
                "UPLOAD_COMMITTED",
                "UPLOAD_UNCERTAIN",
                "UPLOAD_PENDING",
                "BUILD_PENDING",
            }:
                break
            if index:
                if time.time() + 50 >= value["expires_at"]:
                    break
                time.sleep(50)
            progress = runner.reconcile(progress)
    return {
        "classification": progress.outcome.classification,
        "cleanup_verified": cleanup,
        "receipt": asdict(progress.session.receipt),
    }


def execute_phase():
    # Pop before validating context: even context rejection must not leave the
    # reserved values in the environment of any subsequent child.
    reserved = {
        key: os.environ.pop(key)
        for key in tuple(os.environ)
        if key.startswith("IOS_TF_")
    }
    try:
        if LIVE_CONTROLLER_READY is not True:
            raise Rejected()
        binding = wire.context(os.environ)
        # Read only after consume has validated every field below.
        manifest = reserved.get(wire.MANIFEST)
        transfer = wire.consume(reserved, binding, now=int(time.time()))
        expires_at = wire._document(manifest, 4096)["expires_at"]
        prepared = read_prepared(binding)
        material = sign_material(transfer.signing_frame)
        asc = asc_fields(transfer.asc_frame)
        if (asc["version"], asc["build"]) != (material["version"], material["build"]):
            raise Rejected()
        # The exclusive consumed journal is outside the signing output root,
        # which the signing worker reduces to candidate.ipa before ASC starts.
        write_state(state_directory(), "consumed", asdict(binding))
        print("stage=signing_started", flush=True)
        result = worker(
            "sign",
            json.dumps(
                {
                    "prepared": prepared_record(prepared),
                    "frame": transfer.signing_frame.decode("ascii"),
                    "previous_build": asc["previous_build"],
                },
                separators=(",", ":"),
            ).encode("ascii"),
            timeout=2700,
        )
        if result.get("classification") != "CANDIDATE_BOUND":
            if set(result) != {"classification", "cleanup_verified"}:
                raise Unresolved()
            outcome = public_result(
                "STOP", cleanup=result.get("cleanup_verified") is True
            )
            write_state(state_directory(), "result.json", outcome)
            return outcome
        if set(result) != {"classification", "candidate"}:
            raise Unresolved()
        candidate = candidate_from(result["candidate"])
        if prepared_record(candidate.prepared) != prepared_record(prepared) or (
            candidate.version,
            candidate.build,
        ) != (material["version"], material["build"]):
            raise Unresolved()
        print("stage=signing_and_inspection_complete", flush=True)
        result = worker(
            "upload",
            json.dumps(
                {
                    "candidate": result["candidate"],
                    "frame": transfer.asc_frame.decode("ascii"),
                    "expires_at": expires_at,
                },
                separators=(",", ":"),
            ).encode("ascii"),
            timeout=2700,
        )
        if set(result) != {"classification", "cleanup_verified", "receipt"}:
            raise Unresolved()
        # This private, ephemeral receipt is never a public CI artifact/log.
        write_state(state_directory(), "result.json", result)
        return public_result(
            result["classification"], cleanup=result["cleanup_verified"] is True
        )
    finally:
        reserved.clear()
        for name in tuple(os.environ):
            if name.startswith("IOS_TF_"):
                os.environ.pop(name, None)


def public_result(classification, *, cleanup):
    allowed = runner.upload.CLASSIFICATIONS | {
        "PREPARED",
        "STOP",
        "UNRESOLVED",
        "CLEANED",
    }
    return {
        "classification": (
            classification
            if classification in allowed
            and (cleanup is True or classification == "PREPARED")
            else "UNRESOLVED"
        ),
        "cleanup_verified": cleanup is True,
        "release_authorized": False,
        "device_verified": False,
        "owner_distribution_verified": False,
    }


def cleanup_phase():
    """Remove only verified state after known custody completion; never recover a crash."""
    binding = wire.context(os.environ)
    directory = state_directory()
    signing._safe(directory)
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise Unresolved()
    names = set(os.listdir(directory))
    if names not in ({"prepared.json"}, {"prepared.json", "consumed", "result.json"}):
        raise Unresolved()
    values = {name: private_state(directory, name)[0] for name in names}
    record = values["prepared.json"]
    if set(record) != {"binding", "prepared"} or record["binding"] != asdict(binding):
        raise Unresolved()
    prepared = prepared_from(record["prepared"])
    if prepared.repo != ROOT or prepared.commit != binding.sha:
        raise Unresolved()
    if "consumed" in names:
        if (
            values["consumed"] != asdict(binding)
            or values["result.json"].get("cleanup_verified") is not True
        ):
            raise Unresolved()
        # IPA/keychain cleanup does not acknowledge receipt custody. Until
        # durable private handoff exists, keep every known remote receipt.
        if values["result.json"].get("receipt"):
            raise Unresolved()
        # A completed worker already removed the private root; do not blindly
        # delete a remaining/replaced root after a claimed successful cleanup.
        if os.path.lexists(prepared.root):
            raise Unresolved()
    else:
        # Preparation only, with no private worker ever started.
        runner._cleanup(prepared, keep_candidate=False)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if (
            runner._identity(os.fstat(fd)) != runner._identity(info)
            or set(os.listdir(fd)) != names
        ):
            raise Unresolved()
        for name in sorted(names):
            _, checked = private_state(directory, name)
            current = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != checked[:2]:
                raise Unresolved()
            os.unlink(name, dir_fd=fd)
        if os.listdir(fd) or runner._identity(directory.lstat()) != runner._identity(
            info
        ):
            raise Unresolved()
    finally:
        os.close(fd)
    directory.rmdir()
    if os.path.lexists(directory):
        raise Unresolved()
    return public_result("CLEANED", cleanup=True)


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    private_worker = arguments in (["--sign-worker"], ["--upload-worker"])
    try:
        if platform.system() != "Darwin":
            raise Rejected()
        if private_worker:
            value = document(sys.stdin.buffer.read(MAX_INPUT + 1))
            result = (
                sign_worker(value)
                if arguments == ["--sign-worker"]
                else upload_worker(value)
            )
        elif arguments == ["--prepare"]:
            result = prepare_phase()
        elif arguments == ["--execute"]:
            result = execute_phase()
        elif arguments == ["--cleanup"]:
            result = cleanup_phase()
        else:
            raise Rejected()
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return (
            0
            if private_worker
            or result["classification"]
            in {"PREPARED", "BUILD_VALID_UNDISTRIBUTED", "CLEANED"}
            and (result["classification"] == "PREPARED" or result["cleanup_verified"])
            else 2
        )
    except BaseException:
        for name in tuple(os.environ):
            if name.startswith("IOS_TF_"):
                os.environ.pop(name, None)
        print(json.dumps(public_result("UNRESOLVED", cleanup=False)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
