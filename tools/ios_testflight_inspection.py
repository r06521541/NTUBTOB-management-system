"""Private, callable artifact binding. Not Apple trust or upload authorization.

The controller owns the prepared root and subsequent candidate lifetime. This
module removes only its exclusive inspection subtree. Same-user compromise is
not an isolation guarantee. No private inputs are passed in child environment.
"""

import hashlib
import os
import platform
import plistlib
import re
import signal
import stat
import subprocess
import threading
import time
import zipfile
from datetime import datetime

from tools import ios_candidate_inspector as archive_rules
from tools import ios_testflight_signing as signing

LIMIT = 536870912
OUTPUT = 1048576


class Rejected(Exception):
    def __init__(self):
        super().__init__("INSPECTION_REJECTED")


class Unresolved(Exception):
    pass


def group_stopped(pid):
    deadline = time.monotonic() + 5
    while True:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        except Exception:
            raise Unresolved() from None
        if time.monotonic() >= deadline:
            raise Unresolved()
        time.sleep(0.05)


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink)


def run(arguments, cwd):
    """Bounded output, no stdin, minimal environment, group kill before return."""
    child = None
    workers = []
    output = []
    errors = []
    try:
        child = subprocess.Popen(
            ["/usr/bin/codesign", *arguments],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin"},
            start_new_session=True,
            umask=0o077,
        )

        def read():
            try:
                output.append(child.stdout.read(OUTPUT + 1))
            except Exception:
                errors.append(True)

        workers = [threading.Thread(target=read, daemon=True)]
        workers[0].start()
        child.wait(timeout=30)
        workers[0].join(1)
        if (
            child.returncode
            or errors
            or workers[0].is_alive()
            or len(output) != 1
            or len(output[0]) > OUTPUT
        ):
            raise Rejected()
        return output[0]
    finally:
        if child is not None:
            try:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)
                group_stopped(child.pid)
                for worker in workers:
                    worker.join(2)
                if any(worker.is_alive() for worker in workers):
                    raise ValueError()
                child.stdout.close()
            except Exception:
                raise Unresolved() from None


def plist(data):
    if type(data) is not bytes or not 0 < len(data) <= OUTPUT:
        raise Rejected()
    value = plistlib.loads(data)
    if type(value) is not dict:
        raise Rejected()
    return value


def bindings(
    info,
    entitlements,
    embedded,
    leaf,
    *,
    certificate_der,
    profile,
    team,
    version,
    build,
    now,
):
    if embedded != profile or leaf != certificate_der:
        raise Rejected()
    decoded = plist(signing._profile_container(embedded))
    if decoded.get("DeveloperCertificates") != [certificate_der] or decoded.get(
        "TeamIdentifier"
    ) != [team]:
        raise Rejected()
    archive_rules._validate_signing_contract(
        entitlements, decoded, bundle_id=signing.BUNDLE, now=now
    )
    expected = team + "." + signing.BUNDLE
    for source in (entitlements, decoded.get("Entitlements", {})):
        if (
            type(source) is not dict
            or source.get("application-identifier") != expected
            or source.get("com.apple.developer.team-identifier") != team
            or source.get("com.apple.developer.applesignin") != ["Default"]
        ):
            raise Rejected()
    if (
        info.get("CFBundleIdentifier") != signing.BUNDLE
        or info.get("CFBundleShortVersionString") != version
        or info.get("CFBundleVersion") != str(build)
    ):
        raise Rejected()


class Tree:
    """Track every owned inode; never follow a replacement during cleanup."""

    def __init__(self, root):
        self.root = root
        self.entries = {}
        root.mkdir(mode=0o700)
        self.entries[root] = identity(root.lstat())

    def directory(self, path):
        if path in self.entries:
            return
        self.directory(path.parent)
        path.mkdir(mode=0o700)
        self.entries[path] = identity(path.lstat())

    def create(self, path, executable=False):
        self.directory(path.parent)
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o700 if executable else 0o600,
        )
        self.entries[path] = identity(os.fstat(fd))
        return os.fdopen(fd, "wb")

    def adopt_certificates(self, directory):
        choices = list(directory.iterdir())
        if not 1 <= len(choices) <= 4 or {p.name for p in choices} != {
            "codesign" + str(i) for i in range(len(choices))
        }:
            raise Rejected()
        result = []
        for path in sorted(choices):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                before = os.fstat(fd)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.getuid()
                    or before.st_nlink != 1
                    or not 0 < before.st_size <= 65536
                ):
                    raise Rejected()
                os.fchmod(fd, 0o600)
                self.entries[path] = identity(os.fstat(fd))
                data = os.read(fd, 65537)
                if (
                    identity(path.lstat()) != self.entries[path]
                    or len(data) != before.st_size
                ):
                    raise Rejected()
                from cryptography import x509
                from cryptography.hazmat.primitives.serialization import Encoding

                if (
                    x509.load_der_x509_certificate(data).public_bytes(Encoding.DER)
                    != data
                ):
                    raise Rejected()
                result.append(data)
            finally:
                os.close(fd)
        return result[0]

    def cleanup(self):
        # Unknown output is uncertainty, not permission to delete untracked files.
        for path in sorted(self.entries, key=lambda p: len(p.parts), reverse=True):
            if identity(path.lstat()) != self.entries[path]:
                raise Unresolved()
            parent = path.parent
            signing._safe(parent)
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if (
                    identity(os.stat(path.name, dir_fd=fd, follow_symlinks=False))
                    != self.entries[path]
                ):
                    raise Unresolved()
                if stat.S_ISDIR(self.entries[path][2]):
                    os.rmdir(path.name, dir_fd=fd)
                else:
                    os.unlink(path.name, dir_fd=fd)
            finally:
                os.close(fd)


def inspect(
    prepared,
    *,
    expected_sha256,
    certificate_der,
    profile,
    team,
    version,
    build,
    previous_build,
    now,
):
    """Expected material must come from approved inputs, never from this IPA."""
    tree = None
    cleanup = True
    passed = False
    try:
        if (
            platform.system() != "Darwin"
            or type(prepared) is not signing.PreparedSigning
        ):
            raise Rejected()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or not re.fullmatch(r"[A-Z0-9]{10}", team)
            or not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version)
            or type(build) is not int
            or not 1 <= build <= 2147483647
            or type(previous_build) is not int
            or previous_build < 0
            or type(now) is not datetime
            or now.utcoffset() is None
        ):
            raise Rejected()
        if type(certificate_der) is not bytes or not 0 < len(certificate_der) <= 65536:
            raise Rejected()
        signing._profile_container(profile)
        root = prepared.root
        signing._safe(root)
        metadata = root.lstat()
        if (
            (metadata.st_dev, metadata.st_ino) != prepared.root_identity
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise Rejected()
        tree = Tree(root / "inspection")
        candidate = root / "candidate.ipa"
        signing._safe(candidate)
        fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600
                or not 0 < before.st_size <= LIMIT
            ):
                raise Rejected()
            digest = hashlib.sha256()
            total = 0
            snapshot = tree.root / "snapshot.ipa"
            with tree.create(snapshot) as target:
                while block := os.read(fd, min(1048576, LIMIT + 1 - total)):
                    total += len(block)
                    if total > LIMIT:
                        raise Rejected()
                    digest.update(block)
                    target.write(block)
            if digest.hexdigest() != expected_sha256 or total != before.st_size:
                raise Rejected()
            with zipfile.ZipFile(snapshot) as archive:
                infos = archive.infolist()
                names = archive_rules._safe_archive_entries(infos)
                prefix = archive_rules._single_app_prefix(names)
                if len({n.rstrip("/").casefold() for n in names}) != len(names):
                    raise Rejected()
                for item in infos:
                    if not item.filename.startswith(prefix + "/"):
                        continue
                    parts = item.filename.split("/")
                    if (
                        any(p in {".", "..", ""} for p in parts[:-1])
                        or ":" in item.filename
                    ):
                        raise Rejected()
                    path = tree.root.joinpath(*parts)
                    if item.is_dir():
                        tree.directory(path)
                    else:
                        with (
                            archive.open(item) as source,
                            tree.create(
                                path, bool((item.external_attr >> 16) & 0o111)
                            ) as target,
                        ):
                            count = 0
                            while block := source.read(1048576):
                                count += len(block)
                                if count > item.file_size:
                                    raise Rejected()
                                target.write(block)
                            if count != item.file_size:
                                raise Rejected()
            app = tree.root / prefix
            run(["--verify", "--deep", "--strict", str(app)], tree.root)
            entitlements = plist(
                run(["--display", "--entitlements", ":-", str(app)], tree.root)
            )
            certificates = tree.root / "certificates"
            tree.directory(certificates)
            run(["--display", "--extract-certificates", str(app)], certificates)
            leaf = tree.adopt_certificates(certificates)

            def read(path, limit):
                handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    prior = os.fstat(handle)
                    if (
                        identity(prior) != tree.entries[path]
                        or not 0 < prior.st_size <= limit
                    ):
                        raise Rejected()
                    value = os.read(handle, limit + 1)
                    if (
                        len(value) != prior.st_size
                        or identity(path.lstat()) != identity(prior)
                        or os.fstat(handle).st_mtime_ns != prior.st_mtime_ns
                    ):
                        raise Rejected()
                    return value
                finally:
                    os.close(handle)

            info = plist(read(app / "Info.plist", OUTPUT))
            archive_rules._validate_application_metadata(
                info,
                app,
                expected_version=version,
                expected_build=build,
                previous_build=previous_build,
            )
            bindings(
                info,
                entitlements,
                read(app / "embedded.mobileprovision", 262144),
                leaf,
                certificate_der=certificate_der,
                profile=profile,
                team=team,
                version=version,
                build=build,
                now=now,
            )
            after = os.fstat(fd)
            if (
                identity(before) != identity(after)
                or identity(after) != identity(candidate.lstat())
                or (before.st_size, before.st_mtime_ns)
                != (after.st_size, after.st_mtime_ns)
            ):
                raise Rejected()
            passed = True
        finally:
            os.close(fd)
    except Unresolved:
        cleanup = False
    except Exception:
        pass
    finally:
        if tree is not None and cleanup:
            try:
                tree.cleanup()
            except Exception:
                cleanup = False
    return {
        "classification": (
            "CLEANUP_UNRESOLVED"
            if not cleanup
            else "ARTIFACT_BOUND" if passed else "STOP"
        ),
        "cleanup_verified": cleanup,
        "upload_authorized": False,
        "release_authorized": False,
        "apple_distribution_verified": False,
    }
