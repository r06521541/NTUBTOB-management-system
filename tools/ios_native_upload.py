"""One-shot native altool upload, after signing cleanup; no tester distribution.

CLI exit zero is an observation, not Apple processing/device evidence. All
uncertain outcomes stop without resubmission. No raw native/API output escapes.
"""

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
from pathlib import Path, PurePosixPath

from tools import ios_native_signing as signing

Failure = signing.Failure
require = signing.require
MAX_CREDENTIAL = 48000
MAX_IPA = 512 * 1024 * 1024
ROOT = "ntubtob-native-upload"
OPTIONS = {
    "upload_app": "--upload-app",
    "upload_package": "--upload-package",
    "api_key_camel": "--apiKey",
    "api_issuer_camel": "--apiIssuer",
    "api_key_kebab": "--api-key",
    "api_issuer_kebab": "--api-issuer",
    "p8_file_path": "--p8-file-path",
    "output_format": "--output-format",
    "show_progress": "--show-progress",
    "log_file": "--log-file",
    "private_key_directory_env": "API_PRIVATE_KEYS_DIR",
}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def credential(raw):
    """Validate an in-memory package using the already-reviewed key parser."""
    from tools import ios_testflight_inputs as inputs

    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CREDENTIAL:
            raise ValueError()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if type(value) is not dict or set(value) != {
            "key_id",
            "issuer_id",
            "p8_base64",
        }:
            raise ValueError()
        inputs._identifier(value["key_id"])
        inputs._issuer(value["issuer_id"])
        pem = base64.b64decode(value["p8_base64"], validate=True)
        if base64.b64encode(pem).decode("ascii") != value["p8_base64"]:
            raise ValueError()
        inputs._key(pem)
        return {key: value[key] for key in ("key_id", "issuer_id")}, pem
    except Exception:
        raise Failure("asc_input", "ASC_CREDENTIAL_REJECTED") from None


def probe(*, run=signing.command):
    """Only --version/--help, no private inputs, Apple login, or upload."""
    root = Path(__file__).resolve().parents[1]
    require(
        run("xcode_version", [signing.XCODE, "-version"], root).strip()
        == b"Xcode 26.3\nBuild version 17C529",
        "xcode_version",
        "TOOLCHAIN_DRIFT",
    )
    path = run("altool_location", ["/usr/bin/xcrun", "--find", "altool"], root).strip()
    try:
        location = PurePosixPath(path.decode("utf-8"))
        bundle = PurePosixPath(signing.DEVELOPER).parent
        under_bundle = (
            location.is_absolute()
            and ".." not in location.parts
            and bundle in location.parents
            and location.name == "altool"
            and str(location).encode("utf-8") == path
        )
    except (UnicodeError, TypeError):
        under_bundle = False
    require(
        under_bundle,
        "altool_location",
        "TOOLCHAIN_DRIFT",
    )
    raw = run("altool_help", ["/usr/bin/xcrun", "altool", "--help"], root)
    require(
        type(raw) is bytes and 1 <= len(raw) <= 1048576,
        "altool_help",
        "HELP_OUTPUT_REJECTED",
    )
    # Fixed booleans only, not raw help or an assumed Apple response schema.
    return {
        "classification": "TOOL_PROBED",
        "xcode": "26.3/17C529",
        "altool_under_pinned_xcode": True,
        "options": {
            name: bool(
                re.search(
                    rb"(?<![\w-])" + re.escape(token.encode()) + rb"(?![\w-])", raw
                )
            )
            for name, token in OPTIONS.items()
        },
        "upload_attempted": False,
        "upload_authorized": False,
        "secret_input_read": False,
    }


def binding(env):
    patterns = {
        "GITHUB_SHA": r"[a-f0-9]{40}",
        "GITHUB_RUN_ID": r"[1-9][0-9]{0,19}",
        "GITHUB_RUN_ATTEMPT": r"1",
        "IOS_VERSION": r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}",
        "IOS_BUILD_NUMBER": r"[1-9][0-9]{0,8}",
    }
    require(
        all(
            re.fullmatch(pattern, env.get(key, "")) for key, pattern in patterns.items()
        ),
        "handoff_binding",
        "RUN_BINDING_REJECTED",
    )
    return {key: env[key] for key in patterns}


def root_path(temp):
    root = temp / ROOT
    require(temp.is_absolute() and temp.is_dir(), "upload_paths", "PATH_REJECTED")
    require(
        all(not parent.is_symlink() for parent in (root, *root.parents)),
        "upload_paths",
        "PATH_REJECTED",
    )
    return root


def read_regular(path, limit):
    require(not path.is_symlink(), "handoff_read", "PATH_REJECTED")
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode)
        and before.st_nlink == 1
        and 0 < before.st_size <= limit,
        "handoff_read",
        "FILE_REJECTED",
    )
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        require(
            (before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino)
            and stat.S_ISREG(opened.st_mode)
            and opened.st_nlink == 1,
            "handoff_read",
            "FILE_CHANGED",
        )
        data = stream.read(limit + 1)
    require(
        len(data) == before.st_size and len(data) <= limit,
        "handoff_read",
        "FILE_CHANGED",
    )
    return data


def snapshot(artifact, inspection):
    data = read_regular(artifact, MAX_IPA)
    require(
        inspection.get("artifact_size") == len(data)
        and inspection.get("artifact_sha256") == hashlib.sha256(data).hexdigest(),
        "retain_snapshot",
        "INSPECTED_SNAPSHOT_CHANGED",
    )
    return data


def write_private(path, data):
    # Atomic exclusive creation with private permissions, not chmod after write.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish(temp, data, bound):
    root = root_path(temp)
    require(not root.exists(), "retain_publish", "PATH_CONFLICT")
    root.mkdir(mode=0o700)
    try:
        write_private(root / "custody.json", json.dumps(bound, sort_keys=True).encode())
        write_private(root / "candidate.ipa", data)
        digest = hashlib.sha256(data).hexdigest()
        require(
            hashlib.sha256(read_regular(root / "candidate.ipa", MAX_IPA)).hexdigest()
            == digest,
            "retain_publish",
            "COPY_CHANGED",
        )
        # Last file is the ready marker. Caller has already removed signing data.
        write_private(
            root / "ready.json",
            json.dumps(
                {
                    **bound,
                    "artifact_size": len(data),
                    "artifact_sha256": digest,
                },
                sort_keys=True,
            ).encode(),
        )
    except BaseException as primary:
        # This invocation exclusively created this exact validated directory.
        failure = (
            primary
            if isinstance(primary, Failure)
            else Failure("retain_publish", "LOCAL_IO_FAILED")
        )
        failure.cleanup_failures = []
        try:
            shutil.rmtree(root)
        except Exception:
            failure.cleanup_failures.append(
                Failure("retain_publish_cleanup", "OWNED_PATH_REMAINS").public()
            )
        raise failure from None


def custody(root, bound):
    value = json.loads(
        read_regular(root / "custody.json", 4096), object_pairs_hook=unique
    )
    require(value == bound, "handoff_binding", "RUN_BINDING_REJECTED")


def candidate(temp, bound):
    root = root_path(temp)
    custody(root, bound)
    value = json.loads(
        read_regular(root / "ready.json", 4096), object_pairs_hook=unique
    )
    require(
        type(value) is dict
        and set(value) == set(bound) | {"artifact_size", "artifact_sha256"}
        and all(value.get(key) == item for key, item in bound.items()),
        "handoff_binding",
        "RUN_BINDING_REJECTED",
    )
    raw = read_regular(root / "candidate.ipa", MAX_IPA)
    require(
        type(value["artifact_size"]) is int
        and value["artifact_size"] == len(raw)
        and value["artifact_sha256"] == hashlib.sha256(raw).hexdigest(),
        "handoff_binding",
        "CANDIDATE_CHANGED",
    )
    return root / "candidate.ipa"


def cleanup(temp, bound, *, current_process_stopped=False):
    root = root_path(temp)
    if not root.exists():
        return
    custody(root, bound)
    require(
        current_process_stopped
        or not (root / "started").exists()
        or (
            (root / "stopped").exists()
            and read_regular(root / "stopped", 16) == b"reaped"
        ),
        "upload_cleanup",
        "PROCESS_UNRESOLVED",
    )
    shutil.rmtree(root)
    require(not root.exists(), "upload_cleanup", "OWNED_PATH_REMAINS")


def native_metadata(home):
    # Metadata-only comparison of native log/cache parents outside our private
    # HOME. Detects change, not causality or whole-VM absence; never deletes them.
    result = []
    for relative in ("Library/Logs", "Library/Caches"):
        path = home / relative
        if not path.exists():
            result.append(None)
            continue
        require(
            not path.is_symlink() and path.is_dir(), "native_sidefiles", "PATH_REJECTED"
        )
        children = list(path.iterdir())
        require(len(children) <= 2000, "native_sidefiles", "METADATA_LIMIT")
        result.append(
            sorted((p.name, p.lstat().st_mtime_ns, p.lstat().st_size) for p in children)
        )
    return result


def execute(temp, home, bound, raw, *, run=signing.command, make_reader=None):
    from tools import ios_native_asc as asc
    from tools import ios_testflight_inputs as inputs

    effect = {"started": False, "observed_exit": None, "process_stopped": True}
    failure, errors, reader = None, [], None
    root, before, owned = None, None, False
    current_attempt = False
    try:
        root = root_path(temp)
        custody(root, bound)
        owned = True
        ipa = candidate(temp, bound)
        require(not (root / "started").exists(), "upload", "ALREADY_ATTEMPTED")
        ids, pem = credential(raw)
        material = inputs.load_asc_key(pem, **ids)
        reader = (make_reader or asc.Reader)(material)
        asc.preflight(reader.get, bound["IOS_VERSION"], bound["IOS_BUILD_NUMBER"])
        require(
            not reader.cleanup_failures, "asc_preflight", "CONNECTION_CLEANUP_FAILED"
        )
        ipa = candidate(temp, bound)
        # No key file or native upload before target/duplicate/auto-access checks.
        private_home = root / "home"
        private_home.mkdir(mode=0o700)
        key_path = root / "upload.p8"
        write_private(key_path, pem)
        before = native_metadata(home)
        write_private(root / "started", b"one-shot")
        current_attempt = True
        try:
            run(
                "altool_upload",
                [
                    "/usr/bin/xcrun",
                    "altool",
                    "--upload-app",
                    "-f",
                    str(ipa),
                    "-t",
                    "ios",
                    "--apiKey",
                    ids["key_id"],
                    "--apiIssuer",
                    ids["issuer_id"],
                    "--p8-file-path",
                    str(key_path),
                    "--output-format",
                    "json",
                ],
                root,
                1800,
                effect=effect,
                private_home=private_home,
            )
            # Do NOT guess a native JSON success schema. The observed exit remains
            # distinct from ASC acceptance; follow with GET/Console, never retry.
        except Failure as error:
            if not error.stopped:
                effect["process_stopped"] = False
                effect["started"] = True
            raise
        finally:
            if effect["process_stopped"]:
                try:
                    write_private(root / "stopped", b"reaped")
                except (Exception, KeyboardInterrupt):
                    errors.append(Failure("stopped_marker", "WRITE_FAILED").public())
    except Failure as error:
        failure = error.public()
        errors.extend(error.cleanup_failures)
        if not error.stopped:
            effect["process_stopped"] = False
            # Failure to obtain/reap the process handle is not proof of no upload.
            effect["started"] = True
    except KeyboardInterrupt:
        failure = Failure("native_upload", "CANCELLED").public()
    except Exception:
        failure = Failure("native_upload", "LOCAL_OR_OUTPUT_IO_FAILED").public()
    finally:
        if reader is not None:
            errors.extend(reader.cleanup_failures)
        if before is not None:
            try:
                require(
                    before == native_metadata(home),
                    "native_sidefiles",
                    "EXTERNAL_METADATA_CHANGED",
                )
            except Failure as error:
                errors.append(error.public())
            except Exception:
                errors.append(Failure("native_sidefiles", "AUDIT_FAILED").public())
        if owned:
            try:
                cleanup(
                    temp,
                    bound,
                    current_process_stopped=current_attempt
                    and effect["process_stopped"],
                )
            except Failure as error:
                errors.append(error.public())
            except Exception:
                errors.append(Failure("upload_cleanup", "CLEANUP_IO_FAILED").public())
    return {
        "classification": (
            "CLI_COMPLETED"
            if effect["observed_exit"] == 0 and failure is None and not errors
            else "STOP"
        ),
        "failure": failure,
        "cleanup_failures": errors,
        "upload_attempted": effect["started"],
        "observed_exit": effect["observed_exit"],
        "process_stopped": effect["process_stopped"],
        "owned_cleanup_verified": owned and not errors,
        "acceptance_verified": False,
        "processing_verified": False,
        "distribution_verified": False,
        "device_verified": False,
        "release_authorized": False,
        "retry_authorized": False,
        "next_action": (
            "READ_ONLY_ASC_RECONCILE" if effect["started"] else "READ_ONLY_REVIEW"
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "upload", "cleanup"))
    args = parser.parse_args(argv)
    try:
        require(platform.system() == "Darwin", "probe", "HOST_REJECTED")
        if args.action == "probe":
            result = probe()
        else:
            raw = os.environ.pop("IOS_ASC_UPLOAD_CREDENTIAL", "").encode("utf-8")
            _, home, temp = signing.context(os.environ)
            bound = binding(os.environ)
            require(
                os.environ.get("IOS_UPLOAD_REQUESTED") == "true",
                "context",
                "UPLOAD_NOT_SELECTED",
            )
            if args.action == "cleanup":
                cleanup(temp, bound)
                result = {
                    "stage": "upload_cleanup_audit",
                    "classification": "OWNED_PATHS_ABSENT",
                }
            else:
                result = execute(temp, home, bound, raw)
    except Failure as failure:
        result = {
            "classification": "STOP",
            "failure": failure.public(),
            "upload_attempted": False,
            "next_action": "READ_ONLY_REVIEW",
        }
    except Exception:
        result = {
            "classification": "STOP",
            "failure": {"stage": "probe", "reason": "UNEXPECTED_LOCAL_FAILURE"},
            "upload_attempted": False,
            "next_action": "READ_ONLY_REVIEW",
        }
    print(json.dumps(result, sort_keys=True))
    return 1 if result["classification"] == "STOP" else 0


if __name__ == "__main__":
    raise SystemExit(main())
