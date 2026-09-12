"""Callable manual Runner signing adapter. No CLI, upload or real-ready claims.

Prepare dependencies separately before prepare(); only reviewed Xcode/Flutter
build phases run in the key window. Same-user/VM compromise and escaped process
groups are outside isolation guarantees. Python cannot guarantee zeroization.
"""

import base64
import hashlib
import json
import os
import platform
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tools import ios_xcode_feasibility as feasibility

MAX_FRAME = 524288
MAX_OUTPUT = 2048
DEVELOPER = "/Applications/Xcode_26.3.app/Contents/Developer"
BUNDLE = "tw.org.ntubtob.portal"
RESOLVED = (
    "ios/Runner.xcworkspace/xcshareddata/swiftpm/Package.resolved",
    "ios/Runner.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved",
)
MANIFEST = (
    "ios/Flutter/ephemeral/Packages/FlutterGeneratedPluginSwiftPackage/Package.swift"
)
STAGES = {
    "input",
    "paths",
    "profile",
    "snapshot",
    "create",
    "import",
    "search",
    "config",
    "archive",
    "export",
    "cleanup",
    "complete",
}
BINDING_REASONS = frozenset(
    {
        "SIGNING_DEPENDENCY_REJECTED",
        "P12_DECODE_REJECTED",
        "SIGNING_KEY_REJECTED",
        "SIGNING_CERTIFICATE_MISMATCH",
        "SIGNING_TEAM_MISMATCH",
        "SIGNING_CERTIFICATE_TIME_REJECTED",
        "SIGNING_CERTIFICATE_PURPOSE_REJECTED",
    }
)


class Rejected(Exception):
    def __init__(self, reason="INPUT_REJECTED"):
        super().__init__(
            reason
            if reason
            in BINDING_REASONS
            | {
                "INPUT_REJECTED",
                "PREPARE_REJECTED",
                "BINDING_REJECTED",
                "OUTPUT_REJECTED",
                "CLEANUP_UNRESOLVED",
            }
            else "INPUT_REJECTED"
        )


@dataclass(frozen=True, repr=False)
class PreparedSigning:
    repo: Path
    root: Path
    commit: str
    helper_digest: str
    root_identity: tuple
    source_digest: str
    dependency_digest: str = ""


def _safe(path):
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.resolve(strict=True) != path
    ):
        raise Rejected("BINDING_REJECTED")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Rejected("BINDING_REJECTED")


def _public(args, cwd, timeout=30):
    try:
        code, output = feasibility.process(args, cwd=cwd, timeout=timeout)
        if code:
            raise ValueError()
        return output
    except Exception:
        raise Rejected("PREPARE_REJECTED") from None


def _checkout(repo, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise Rejected("BINDING_REJECTED")
    if _public(
        ["/usr/bin/git", "rev-parse", "HEAD"], repo
    ).decode().strip() != commit or any(
        line not in {"?? clients/flutter_app/" + path for path in RESOLVED}
        for line in _public(
            ["/usr/bin/git", "status", "--porcelain", "--untracked-files=all"], repo
        )
        .decode()
        .splitlines()
    ):
        raise Rejected("BINDING_REJECTED")


def _dependencies_ready(app):
    _safe(app / MANIFEST)
    if any(
        (app / name).exists() or (app / name).is_symlink()
        for name in (
            "ios/Flutter/AuthConfig.xcconfig",
            "ios/Flutter/StoreReleaseConfig.xcconfig",
            "ios/Runner/Runner.entitlements",
        )
    ):
        raise Rejected("PREPARE_REJECTED")
    if (app / "ios/Podfile").exists():
        for name in ("ios/Podfile", "ios/Podfile.lock", "ios/Pods/Manifest.lock"):
            _safe(app / name)
        if (app / "ios/Podfile.lock").read_bytes() != (
            app / "ios/Pods/Manifest.lock"
        ).read_bytes():
            raise Rejected("PREPARE_REJECTED")


def _dependency_digest(app, root):
    _dependencies_ready(app)
    paths = [
        (MANIFEST, app / MANIFEST),
        ("Generated.xcconfig", app / "ios/Flutter/Generated.xcconfig"),
        ("workspace-state.json", root / "SourcePackages/workspace-state.json"),
    ]
    paths += [(name, app / name) for name in RESOLVED if (app / name).exists()]
    if (app / "ios/Podfile").exists():
        paths += [
            (name, app / name)
            for name in ("ios/Podfile", "ios/Podfile.lock", "ios/Pods/Manifest.lock")
        ]
    digest = hashlib.sha256()
    for label, path in paths:
        _safe(path)
        if not path.is_file() or not 0 < path.stat().st_size <= 1048576:
            raise Rejected("BINDING_REJECTED")
        before = path.stat()
        with path.open("rb") as source:
            data = source.read(1048577)
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise Rejected("BINDING_REJECTED")
        if len(data) > 1048576:
            raise Rejected("BINDING_REJECTED")
        if label == "workspace-state.json":
            if type(json.loads(data)) is not dict:
                raise Rejected("BINDING_REJECTED")
        if label in RESOLVED and type(json.loads(data)) is not dict:
            raise Rejected("BINDING_REJECTED")
        digest.update(label.encode() + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def _resolve(app, root):
    child = None
    successful = False
    try:
        child = subprocess.Popen(
            [
                DEVELOPER + "/usr/bin/xcodebuild",
                "-workspace",
                str(app / "ios/Runner.xcworkspace"),
                "-scheme",
                "Runner",
                "-configuration",
                "Release",
                "-sdk",
                "iphoneos",
                "-derivedDataPath",
                str(root / "DerivedData"),
                "-clonedSourcePackagesDirPath",
                str(root / "SourcePackages"),
                "-resolvePackageDependencies",
            ],
            cwd=app,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "DEVELOPER_DIR": DEVELOPER},
            start_new_session=True,
        )
        successful = child.wait(timeout=300) == 0
    finally:
        if child is not None:
            try:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        os.killpg(child.pid, 0)
                    except ProcessLookupError:
                        break
                    if time.monotonic() >= deadline:
                        raise ValueError()
                    time.sleep(0.05)
            except Exception:
                raise Rejected("CLEANUP_UNRESOLVED") from None
    if not successful:
        raise Rejected("PREPARE_REJECTED")


def prepare(repo, *, expected_commit):
    """Code-only; returns a private root retained for controller-owned cleanup."""
    root = None
    root_identity = None
    compilation_uncertain = False
    try:
        if platform.system() != "Darwin" or platform.mac_ver()[0].split(".")[0] != "15":
            raise ValueError()
        repo = Path(repo)
        _safe(repo)
        _checkout(repo, expected_commit)
        app = repo / "clients/flutter_app"
        for relative in (
            "ios/Runner.xcworkspace/contents.xcworkspacedata",
            "ios/Flutter/Generated.xcconfig",
            ".dart_tool/package_config.json",
        ):
            _safe(app / relative)
        _dependencies_ready(app)
        generated = (app / "ios/Flutter/Generated.xcconfig").read_text()
        roots = re.findall(r"^FLUTTER_ROOT=(.+)$", generated, re.MULTILINE)
        if len(roots) != 1:
            raise ValueError()
        flutter = Path(roots[0].strip())
        _safe(flutter)
        for item in (
            "bin/cache/dart-sdk/bin/dart",
            "bin/cache/artifacts/engine/ios-release/Flutter.xcframework",
        ):
            _safe(flutter / item)
        version_file = flutter / "bin/cache/flutter.version.json"
        _safe(version_file)
        if (
            version_file.stat().st_size > 65536
            or json.loads(version_file.read_bytes()).get("flutterVersion") != "3.47.0"
        ):
            raise ValueError()
        if (
            _public([DEVELOPER + "/usr/bin/xcodebuild", "-version"], repo).strip()
            != b"Xcode 26.3\nBuild version 17C529"
        ):
            raise ValueError()
        if (
            _public(
                ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-version"], repo
            ).strip()
            != b"26.2"
        ):
            raise ValueError()
        root = Path(
            tempfile.mkdtemp(prefix="task-198-", dir=feasibility.os_temp_root())
        ).resolve(strict=True)
        root.chmod(0o700)
        root_info = root.stat()
        root_identity = (root_info.st_dev, root_info.st_ino)
        _resolve(app, root)
        dependency_digest = _dependency_digest(app, root)
        _checkout(repo, expected_commit)
        source = repo / "tools/native/ios_testflight_signing.swift"
        _safe(source)
        compilation_uncertain = True
        _public(
            ["/usr/bin/xcrun", "swiftc", str(source), "-o", str(root / "native")],
            root,
            120,
        )
        compilation_uncertain = False
        (root / "native").chmod(0o700)
        info = root.stat()
        return PreparedSigning(
            repo,
            root,
            expected_commit,
            hashlib.sha256((root / "native").read_bytes()).hexdigest(),
            (info.st_dev, info.st_ino),
            hashlib.sha256(source.read_bytes()).hexdigest(),
            dependency_digest,
        )
    except Exception as error:
        # No keys yet. Delete only our exact code-only files, never a recursive tree.
        if root is not None:
            if compilation_uncertain or (
                isinstance(error, Rejected) and error.args == ("CLEANUP_UNRESOLVED",)
            ):
                raise Rejected("CLEANUP_UNRESOLVED") from None
            try:
                _safe(root)
                info = root.stat()
                if (
                    info.st_dev,
                    info.st_ino,
                ) != root_identity or root.parent != feasibility.os_temp_root():
                    raise ValueError()
                from tools import ios_testflight_runner as runner

                runner._cleanup(
                    PreparedSigning(repo, root, expected_commit, "", root_identity, ""),
                    keep_candidate=False,
                )
            except Exception:
                raise Rejected("CLEANUP_UNRESOLVED") from None
        raise Rejected("PREPARE_REJECTED") from None


def frame(
    *,
    p12,
    password,
    profile,
    certificate_der,
    team,
    profile_uuid,
    version,
    build,
    build_defines,
):
    try:
        for value, limit in (
            (p12, 65536),
            (password, 1024),
            (profile, 262144),
            (certificate_der, 65536),
        ):
            if type(value) is not bytes or not 0 < len(value) <= limit:
                raise ValueError()
        password_text = password.decode("utf-8")
        if "\x00" in password_text:
            raise ValueError()
        if (
            type(team) is not str
            or not re.fullmatch(r"[A-Z0-9]{10}", team)
            or type(profile_uuid) is not str
            or not re.fullmatch(
                r"[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}", profile_uuid
            )
        ):
            raise ValueError()
        if (
            build_defines["GOOGLE_CLIENT_ID"]
            == build_defines["GOOGLE_SERVER_CLIENT_ID"]
        ):
            raise ValueError()
        if (
            type(version) is not str
            or not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version)
            or type(build) is not int
            or not 1 <= build <= 2147483647
        ):
            raise ValueError()
        keys = {
            "API_BASE_URL",
            "LINE_CHANNEL_ID",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_SERVER_CLIENT_ID",
        }
        if (
            type(build_defines) is not dict
            or set(build_defines) != keys
            or any(
                type(v) is not str
                or not 1 <= len(v) <= 2048
                or not re.fullmatch(r"[A-Za-z0-9:/._-]+", v)
                for v in build_defines.values()
            )
        ):
            raise ValueError()
        if (
            not build_defines["API_BASE_URL"].startswith("https://")
            or not build_defines["LINE_CHANNEL_ID"].isdigit()
            or any(
                not re.fullmatch(
                    r"[A-Za-z0-9-]+\.apps\.googleusercontent\.com", build_defines[k]
                )
                for k in ("GOOGLE_CLIENT_ID", "GOOGLE_SERVER_CLIENT_ID")
            )
        ):
            raise ValueError()
        value = {
            "p12": base64.b64encode(p12).decode(),
            "password": password_text,
            "profile": base64.b64encode(profile).decode(),
            "certificate": base64.b64encode(certificate_der).decode(),
            "team": team,
            "uuid": profile_uuid,
            "version": version,
            "build": build,
            "defines": build_defines,
        }
        encoded = json.dumps(value, separators=(",", ":")).encode()
        if len(encoded) > MAX_FRAME:
            raise ValueError()
        return encoded
    except Exception:
        raise Rejected() from None


def decode_result(output):
    try:
        if type(output) is not bytes or len(output) > MAX_OUTPUT:
            raise ValueError()

        def unique(pairs):
            value = {}
            for k, v in pairs:
                if k in value:
                    raise ValueError()
                value[k] = v
            return value

        value = json.loads(output, object_pairs_hook=unique)
        if (
            set(value) != {"stage", "operation", "cleanup"}
            or value["stage"] not in STAGES
            or value["operation"] not in {"REJECTED", "EXPORTED", "TIMEOUT"}
            or value["cleanup"] not in {"VERIFIED", "UNRESOLVED", "NOT_STARTED"}
        ):
            raise ValueError()
        if value["operation"] == "EXPORTED" and value["stage"] != "complete":
            raise ValueError()
        return value | {
            "classification": (
                "CLEANUP_UNRESOLVED"
                if value["cleanup"] == "UNRESOLVED"
                else (
                    "EXPORTED_UNINSPECTED"
                    if value["operation"] == "EXPORTED"
                    and value["cleanup"] == "VERIFIED"
                    else "STOP"
                )
            ),
            "upload_authorized": False,
            "release_authorized": False,
        }
    except Exception:
        raise Rejected("OUTPUT_REJECTED") from None


def _native(prepared, payload):
    child = None
    buffers = []
    failures = []

    def write():
        try:
            child.stdin.write(payload)
            child.stdin.close()
        except Exception:
            failures.append(True)

    def read():
        try:
            buffers.append(child.stdout.read(MAX_OUTPUT + 1))
        except Exception:
            failures.append(True)

    try:
        child = subprocess.Popen(
            [str(prepared.root / "native"), str(prepared.repo)],
            cwd=prepared.root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "DEVELOPER_DIR": DEVELOPER},
            start_new_session=True,
        )
        workers = [
            threading.Thread(target=write, daemon=True),
            threading.Thread(target=read, daemon=True),
        ]
        for worker in workers:
            worker.start()
        child.wait(timeout=2400)
        for worker in workers:
            worker.join(2)
        if (
            child.returncode
            or failures
            or any(w.is_alive() for w in workers)
            or len(buffers) != 1
        ):
            raise ValueError()
        return decode_result(buffers[0])
    except Exception:
        # Killing a supervisor cannot prove restoration/deletion; never infer cleanup.
        raise Rejected("CLEANUP_UNRESOLVED") from None
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                raise Rejected("CLEANUP_UNRESOLVED") from None
            try:
                child.wait(timeout=5)
            except Exception:
                raise Rejected("CLEANUP_UNRESOLVED") from None


def _certificate_binding(material):
    # Actual CMS structural binding is performed by the system decoder in native.
    # This entry independently checks the P12/expected certificate before key IPC.
    # Fixed stage labels only. A P12 decode failure is not proof of a wrong
    # password: malformed/unsupported P12 data can produce the same failure.
    reason = "SIGNING_DEPENDENCY_REJECTED"
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs12

        from tools import ios_certificate_preparation as preparation

        _, _, serialization, rsa = preparation.dependencies()
        reason = "P12_DECODE_REJECTED"
        key, cert, _ = pkcs12.load_key_and_certificates(
            material["p12"], material["password"]
        )
        reason = "SIGNING_KEY_REJECTED"
        if (
            not isinstance(key, rsa.RSAPrivateKey)
            or key.key_size < 2048
            or cert is None
        ):
            raise ValueError()
        reason = "SIGNING_CERTIFICATE_MISMATCH"
        public = cert.public_key()
        if (
            not isinstance(public, rsa.RSAPublicKey)
            or public.public_numbers() != key.public_key().public_numbers()
            or cert.public_bytes(serialization.Encoding.DER)
            != material["certificate_der"]
        ):
            raise ValueError()
        reason = "SIGNING_TEAM_MISMATCH"
        if [
            v.value
            for v in cert.subject.get_attributes_for_oid(
                x509.NameOID.ORGANIZATIONAL_UNIT_NAME
            )
        ] != [material["team"]]:
            raise ValueError()
        reason = "SIGNING_CERTIFICATE_TIME_REJECTED"
        if (
            not cert.not_valid_before_utc
            <= datetime.now(timezone.utc)
            <= cert.not_valid_after_utc
        ):
            raise ValueError()
        reason = "SIGNING_CERTIFICATE_PURPOSE_REJECTED"
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        if (
            not bc.critical
            or bc.value.ca
            or not ku.critical
            or not ku.value.digital_signature
            or ku.value.key_cert_sign
            or ku.value.crl_sign
            or not eku.critical
            or list(eku.value) != [x509.ExtendedKeyUsageOID.CODE_SIGNING]
        ):
            raise ValueError()
        known = {bc.oid, ku.oid, eku.oid}
        for oid in ("1.2.840.113635.100.6.1.4", "1.2.840.113635.100.6.1.7"):
            marker = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(oid))
            if not marker.critical:
                raise ValueError()
            known.add(marker.oid)
        if any(ext.critical and ext.oid not in known for ext in cert.extensions):
            raise ValueError()
    except Exception:
        raise Rejected(reason) from None


def _profile_container(data):
    """Anti-decryption shape only; never signer/digest/attribute/trust policy."""
    try:
        import asn1crypto
        from asn1crypto import cms

        if (
            asn1crypto.__version__ != "1.5.1"
            or type(data) is not bytes
            or not 0 < len(data) <= 262144
        ):
            raise ValueError()
        document = cms.ContentInfo.load(data, strict=True)
        if document["content_type"].native != "signed_data":
            raise ValueError()
        signed = document["content"]
        content = signed["encap_content_info"]
        if (
            content["content_type"].native != "data"
            or content["content"].native is None
        ):
            raise ValueError()
        # Materialize fields without choosing any signing algorithms or attributes.
        signed.native
        if document.dump(force=True) != data:
            raise ValueError()
        payload = content["content"].native
        if type(payload) is not bytes or not 0 < len(payload) <= 262144:
            raise ValueError()
        return payload
    except Exception:
        raise Rejected("INPUT_REJECTED") from None


def _private_digest(path, limit, *, executable=False, return_identity=False):
    _safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or not 0 < before.st_size <= limit
            or stat.S_IMODE(before.st_mode) != (0o700 if executable else 0o600)
        ):
            raise Rejected("BINDING_REJECTED")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, min(1048576, limit + 1 - total))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise Rejected("BINDING_REJECTED")
            digest.update(block)
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
            or total != before.st_size
        ):
            raise Rejected("BINDING_REJECTED")
        return (digest.hexdigest(), before) if return_identity else digest.hexdigest()
    finally:
        os.close(fd)


def sign(prepared, **material):
    """Controller must approve exact staging target; HTTPS syntax is not approval."""
    try:
        return _sign(prepared, **material)
    except Rejected:
        raise
    except Exception:
        raise Rejected("BINDING_REJECTED") from None


def _candidate(root):
    """Copy unchanged bytes; preserve partial output for controller cleanup."""
    source_fd = target_fd = None
    try:
        exported = root / "export"
        _safe(exported)
        choices = list(exported.glob("*.ipa"))
        if len(choices) != 1:
            raise ValueError()
        source = choices[0]
        expected, validated = _private_digest(source, 536870912, return_identity=True)
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        before = os.fstat(source_fd)

        def identity(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_uid,
                info.st_mode,
                info.st_nlink,
            )

        if identity(before) != identity(validated):
            raise ValueError()
        target = root / "candidate.ipa"
        target_fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(source_fd, min(1048576, 536870913 - total))
            if not block:
                break
            total += len(block)
            if total > 536870912:
                raise ValueError()
            digest.update(block)
            offset = 0
            while offset < len(block):
                written = os.write(target_fd, block[offset:])
                if written <= 0:
                    raise ValueError()
                offset += written
        os.fsync(target_fd)
        after = os.fstat(source_fd)
        if identity(before) != identity(after) or identity(after) != identity(
            source.stat(follow_symlinks=False)
        ):
            raise ValueError()
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or total != before.st_size
            or digest.hexdigest() != expected
        ):
            raise ValueError()
        os.close(target_fd)
        target_fd = None
        if (
            _private_digest(source, 536870912) != expected
            or _private_digest(target, 536870912) != expected
        ):
            raise ValueError()
        return expected
    except Exception:
        raise Rejected("OUTPUT_REJECTED") from None
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if target_fd is not None:
            os.close(target_fd)


def _sign(prepared, **material):
    """No retry: a consumed root always stops. Result is not IPA inspection."""
    if type(prepared) is not PreparedSigning:
        raise Rejected("BINDING_REJECTED")
    _safe(prepared.root)
    _safe(prepared.repo)
    _safe(prepared.root / "native")
    source = prepared.repo / "tools/native/ios_testflight_signing.swift"
    _safe(source)
    info = prepared.root.stat()
    if (
        (info.st_dev, info.st_ino) != prepared.root_identity
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or _private_digest(prepared.root / "native", 20971520, executable=True)
        != prepared.helper_digest
        or hashlib.sha256(source.read_bytes()).hexdigest() != prepared.source_digest
    ):
        raise Rejected("BINDING_REJECTED")
    _checkout(prepared.repo, prepared.commit)
    if (
        not prepared.dependency_digest
        or _dependency_digest(prepared.repo / "clients/flutter_app", prepared.root)
        != prepared.dependency_digest
    ):
        raise Rejected("BINDING_REJECTED")
    payload = frame(**material)
    _profile_container(material["profile"])
    _certificate_binding(material)
    try:
        with (prepared.root / "consumed").open("xb"):
            pass
    except Exception:
        raise Rejected("BINDING_REJECTED") from None
    result = _native(prepared, payload)
    if result["classification"] == "EXPORTED_UNINSPECTED":
        digest = _candidate(prepared.root)
        result |= {
            "artifact_relative": "candidate.ipa",
            "artifact_sha256": digest,
        }
    return result
