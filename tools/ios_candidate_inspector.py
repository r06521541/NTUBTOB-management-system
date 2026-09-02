"""Fail-closed, deidentified inspection for an already-signed iOS IPA.

This module never creates signing material, signs an app, archives it, uploads it,
or connects to Apple.  Actual inspection is deliberately available only on macOS
with the platform-owned ``codesign`` and ``security`` tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator, Mapping, Sequence

EXPECTED_BUNDLE_ID = "tw.org.ntubtob.portal"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_READINESS_CONTRACT = (
    _REPOSITORY_ROOT
    / "clients"
    / "flutter_app"
    / "ios"
    / "Flutter"
    / "StoreReleaseContract.xcconfig"
)
_MAX_IPA_BYTES = 1_073_741_824
_MAX_UNCOMPRESSED_BYTES = 2_147_483_648
_MAX_ARCHIVE_ENTRIES = 50_000
_MAX_PLIST_BYTES = 1_048_576
_MAX_TOOL_OUTPUT_BYTES = 1_048_576
_TOOL_TIMEOUT_SECONDS = 30
_SEMANTIC_VERSION = re.compile(r"[1-9][0-9]*\.[0-9]+\.[0-9]+")
_POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*")
_APPLE_ENTITLEMENT = "com.apple.developer.applesignin"
_APPLICATION_IDENTIFIER = "application-identifier"
_TEAM_IDENTIFIER = "com.apple.developer.team-identifier"


class CandidateError(ValueError):
    """A safe, fixed-category candidate rejection."""


@dataclass(frozen=True)
class ArtifactSnapshot:
    path: Path
    sha256: str
    size: int


@dataclass(frozen=True)
class ToolResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


ToolRunner = Callable[[Sequence[str], Path], ToolResult]


def _is_regular_non_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and not (attributes & reparse_flag)
    )


@contextmanager
def snapshot_ipa(artifact: Path) -> Iterator[ArtifactSnapshot]:
    if artifact.suffix.lower() != ".ipa" or not _is_regular_non_reparse(artifact):
        raise CandidateError("candidate artifact is not a regular IPA")
    with tempfile.TemporaryDirectory(prefix="ios-candidate-snapshot-") as directory:
        snapshot = Path(directory) / "candidate.ipa"
        digest = hashlib.sha256()
        size = 0
        try:
            with artifact.open("rb") as source, snapshot.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > _MAX_IPA_BYTES:
                        raise CandidateError(
                            "candidate IPA exceeds the inspection limit"
                        )
                    digest.update(chunk)
                    target.write(chunk)
        except CandidateError:
            raise
        except OSError:
            raise CandidateError("candidate IPA could not be snapshotted") from None
        if size == 0:
            raise CandidateError("candidate IPA is empty")
        yield ArtifactSnapshot(snapshot, digest.hexdigest(), size)


def _safe_archive_entries(infos: Sequence[zipfile.ZipInfo]) -> list[str]:
    if len(infos) > _MAX_ARCHIVE_ENTRIES:
        raise CandidateError("candidate IPA contains too many entries")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise CandidateError("candidate IPA contains duplicate entries")
    total_size = 0
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        unix_mode = info.external_attr >> 16
        file_type = stat.S_IFMT(unix_mode)
        if (
            not name
            or "\x00" in name
            or name.startswith(("/", "\\"))
            or "\\" in name
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise CandidateError("candidate IPA contains an unsafe entry path")
        if info.flag_bits & 0x1:
            raise CandidateError("candidate IPA contains an encrypted entry")
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise CandidateError("candidate IPA contains a non-regular entry")
        total_size += info.file_size
        if total_size > _MAX_UNCOMPRESSED_BYTES:
            raise CandidateError(
                "candidate IPA uncompressed content exceeds the inspection limit"
            )
    return names


def _single_app_prefix(names: Sequence[str]) -> str:
    info_suffix = "/Info.plist"
    prefixes = {
        name[: -len(info_suffix)]
        for name in names
        if name.startswith("Payload/")
        and name.endswith(".app/Info.plist")
        and len(PurePosixPath(name).parts) == 3
    }
    if len(prefixes) != 1:
        raise CandidateError("candidate IPA must contain exactly one application")
    return next(iter(prefixes))


def _extract_application(
    archive: zipfile.ZipFile,
    infos: Sequence[zipfile.ZipInfo],
    app_prefix: str,
    destination: Path,
) -> Path:
    app_root = destination / PurePosixPath(app_prefix).name
    prefix = f"{app_prefix}/"
    for info in infos:
        if not info.filename.startswith(prefix):
            continue
        relative = PurePosixPath(info.filename[len(prefix) :])
        target = app_root.joinpath(*relative.parts)
        try:
            target.resolve().relative_to(app_root.resolve())
        except ValueError:
            raise CandidateError(
                "candidate IPA contains an unsafe entry path"
            ) from None
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with archive.open(info) as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
        except (OSError, RuntimeError, zipfile.BadZipFile):
            raise CandidateError(
                "candidate IPA application could not be extracted"
            ) from None
        unix_mode = info.external_attr >> 16
        permissions = stat.S_IMODE(unix_mode)
        if permissions:
            target.chmod(permissions)
    return app_root


def _read_plist(source: bytes, *, category: str) -> Mapping[str, object]:
    if not source or len(source) > _MAX_PLIST_BYTES:
        raise CandidateError(f"{category} plist is invalid")
    try:
        value = plistlib.loads(source)
    except (plistlib.InvalidFileException, ValueError, TypeError):
        raise CandidateError(f"{category} plist is invalid") from None
    if not isinstance(value, dict):
        raise CandidateError(f"{category} plist is invalid")
    return value


def _read_file(path: Path, *, category: str) -> bytes:
    try:
        if not _is_regular_non_reparse(path) or path.stat().st_size > _MAX_PLIST_BYTES:
            raise OSError
        return path.read_bytes()
    except OSError:
        raise CandidateError(f"{category} is unavailable") from None


def _required_text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise CandidateError("candidate application metadata is invalid")
    return value


def _minimum_os_at_least_15(value: str) -> bool:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", value):
        return False
    components = tuple(int(component) for component in value.split("."))
    return components >= (15,)


def _validate_application_metadata(
    values: Mapping[str, object],
    app_root: Path,
    *,
    expected_version: str,
    expected_build: int,
    previous_build: int,
) -> tuple[str, str]:
    bundle_id = _required_text(values, "CFBundleIdentifier")
    version = _required_text(values, "CFBundleShortVersionString")
    build = _required_text(values, "CFBundleVersion")
    minimum_os = _required_text(values, "MinimumOSVersion")
    executable = _required_text(values, "CFBundleExecutable")
    if bundle_id != EXPECTED_BUNDLE_ID:
        raise CandidateError("candidate bundle identity does not match")
    if not _SEMANTIC_VERSION.fullmatch(version) or version != expected_version:
        raise CandidateError("candidate version does not match")
    if (
        not _POSITIVE_INTEGER.fullmatch(build)
        or int(build) != expected_build
        or expected_build <= previous_build
    ):
        raise CandidateError("candidate build number is not monotonic")
    if not _minimum_os_at_least_15(minimum_os):
        raise CandidateError("candidate minimum iOS version is unsupported")
    if PurePosixPath(executable).name != executable:
        raise CandidateError("candidate executable metadata is invalid")
    executable_path = app_root / executable
    if not _is_regular_non_reparse(executable_path):
        raise CandidateError("candidate executable is unavailable")
    return version, build


def repository_apple_ready(contract_path: Path = _READINESS_CONTRACT) -> bool:
    try:
        source = contract_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise CandidateError(
            "repository Apple readiness contract is unavailable"
        ) from None
    matches = re.findall(
        r"^APPLE_SIGN_IN_REPOSITORY_STATUS\s*=\s*([^\s#]+)\s*$",
        source,
        flags=re.MULTILINE,
    )
    if len(matches) != 1 or matches[0] not in {"ready", "not_implemented"}:
        raise CandidateError("repository Apple readiness contract is invalid")
    return matches[0] == "ready"


def _default_tool_runner(command: Sequence[str], cwd: Path) -> ToolResult:
    if sys.platform != "darwin":
        raise CandidateError("macOS candidate inspection tools are unavailable")
    if not command or command[0] not in {"/usr/bin/codesign", "/usr/bin/security"}:
        raise CandidateError("candidate inspection command is not approved")
    environment = {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CandidateError("candidate inspection command failed") from None
    if len(completed.stdout) + len(completed.stderr) > _MAX_TOOL_OUTPUT_BYTES:
        raise CandidateError("candidate inspection output exceeds the limit")
    return ToolResult(completed.returncode, completed.stdout, completed.stderr)


def _successful_tool_result(result: ToolResult, *, category: str) -> ToolResult:
    if len(result.stdout) + len(result.stderr) > _MAX_TOOL_OUTPUT_BYTES:
        raise CandidateError("candidate inspection output exceeds the limit")
    if result.returncode != 0:
        raise CandidateError(f"candidate {category} verification failed")
    return result


def _embedded_plist(output: bytes, *, category: str) -> Mapping[str, object]:
    binary_offset = output.find(b"bplist00")
    xml_offset = output.find(b"<?xml")
    offsets = [offset for offset in (binary_offset, xml_offset) if offset >= 0]
    if not offsets:
        raise CandidateError(f"{category} plist is invalid")
    offset = min(offsets)
    source = output[offset:]
    if offset == xml_offset:
        end = source.find(b"</plist>")
        if end < 0:
            raise CandidateError(f"{category} plist is invalid")
        source = source[: end + len(b"</plist>")]
    return _read_plist(source, category=category)


def _verify_signature_and_read_entitlements(
    app_root: Path, profile_path: Path, runner: ToolRunner
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    _successful_tool_result(
        runner(
            [
                "/usr/bin/codesign",
                "--verify",
                "--deep",
                "--strict",
                "--verbose=0",
                str(app_root),
            ],
            app_root.parent,
        ),
        category="signature",
    )
    entitlements_result = _successful_tool_result(
        runner(
            [
                "/usr/bin/codesign",
                "--display",
                "--entitlements",
                ":-",
                str(app_root),
            ],
            app_root.parent,
        ),
        category="entitlement",
    )
    entitlements = _embedded_plist(
        entitlements_result.stdout + entitlements_result.stderr,
        category="application entitlement",
    )
    profile_result = _successful_tool_result(
        runner(
            ["/usr/bin/security", "cms", "-D", "-i", str(profile_path)],
            app_root.parent,
        ),
        category="profile",
    )
    profile = _embedded_plist(
        profile_result.stdout + profile_result.stderr,
        category="provisioning profile",
    )
    return entitlements, profile


def _validate_signing_contract(
    app_entitlements: Mapping[str, object],
    profile: Mapping[str, object],
    *,
    bundle_id: str,
    now: datetime,
) -> None:
    profile_entitlements = profile.get("Entitlements")
    if not isinstance(profile_entitlements, dict):
        raise CandidateError("candidate provisioning profile is invalid")
    if profile_entitlements.get("get-task-allow") is not False:
        raise CandidateError("candidate uses a development provisioning profile")
    if profile.get("ProvisionedDevices") is not None or profile.get(
        "ProvisionsAllDevices"
    ) not in {None, False}:
        raise CandidateError("candidate provisioning profile is not distribution-only")
    expiration = profile.get("ExpirationDate")
    if not isinstance(expiration, datetime):
        raise CandidateError("candidate provisioning profile expiration is invalid")
    normalized_expiration = (
        expiration.replace(tzinfo=timezone.utc)
        if expiration.tzinfo is None
        else expiration.astimezone(timezone.utc)
    )
    if normalized_expiration <= now.astimezone(timezone.utc):
        raise CandidateError("candidate provisioning profile is expired")

    profile_application = profile_entitlements.get(_APPLICATION_IDENTIFIER)
    profile_team = profile_entitlements.get(_TEAM_IDENTIFIER)
    app_application = app_entitlements.get(_APPLICATION_IDENTIFIER)
    app_team = app_entitlements.get(_TEAM_IDENTIFIER)
    if (
        not isinstance(profile_application, str)
        or not isinstance(profile_team, str)
        or not profile_team
        or profile_application != f"{profile_team}.{bundle_id}"
        or app_application != profile_application
        or app_team != profile_team
    ):
        raise CandidateError("candidate signing identity categories do not match")
    if profile_entitlements.get(_APPLE_ENTITLEMENT) != ["Default"]:
        raise CandidateError("candidate profile Apple entitlement is invalid")
    if app_entitlements.get(_APPLE_ENTITLEMENT) != ["Default"]:
        raise CandidateError("candidate application Apple entitlement is invalid")


def inspect_ipa(
    artifact: Path,
    *,
    expected_version: str,
    expected_build: int,
    previous_build: int,
    mode: str = "testflight",
    runner: ToolRunner = _default_tool_runner,
    readiness_contract: Path = _READINESS_CONTRACT,
    now: datetime | None = None,
) -> dict[str, object]:
    if mode not in {"testflight", "contract-test"}:
        raise CandidateError("candidate inspection mode is invalid")
    if mode == "testflight" and not repository_apple_ready(readiness_contract):
        raise CandidateError("repository Apple readiness is blocked")
    if not _SEMANTIC_VERSION.fullmatch(expected_version):
        raise CandidateError("expected candidate version is invalid")
    if expected_build < 1 or previous_build < 0:
        raise CandidateError("expected candidate build is invalid")

    with snapshot_ipa(artifact) as snapshot:
        try:
            with zipfile.ZipFile(snapshot.path) as archive:
                infos = archive.infolist()
                names = _safe_archive_entries(infos)
                app_prefix = _single_app_prefix(names)
                required = {
                    f"{app_prefix}/Info.plist",
                    f"{app_prefix}/embedded.mobileprovision",
                    f"{app_prefix}/_CodeSignature/CodeResources",
                }
                if not required.issubset(names):
                    raise CandidateError(
                        "candidate IPA is missing signed application data"
                    )
                with tempfile.TemporaryDirectory(
                    prefix="ios-candidate-application-"
                ) as directory:
                    app_root = _extract_application(
                        archive, infos, app_prefix, Path(directory)
                    )
                    info = _read_plist(
                        _read_file(
                            app_root / "Info.plist", category="application metadata"
                        ),
                        category="application metadata",
                    )
                    version, build = _validate_application_metadata(
                        info,
                        app_root,
                        expected_version=expected_version,
                        expected_build=expected_build,
                        previous_build=previous_build,
                    )
                    profile_path = app_root / "embedded.mobileprovision"
                    if not _is_regular_non_reparse(
                        app_root / "_CodeSignature" / "CodeResources"
                    ) or not _is_regular_non_reparse(profile_path):
                        raise CandidateError(
                            "candidate IPA is missing signed application data"
                        )
                    app_entitlements, profile = _verify_signature_and_read_entitlements(
                        app_root, profile_path, runner
                    )
                    _validate_signing_contract(
                        app_entitlements,
                        profile,
                        bundle_id=EXPECTED_BUNDLE_ID,
                        now=now or datetime.now(timezone.utc),
                    )
        except CandidateError:
            raise
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
            raise CandidateError("candidate IPA archive is invalid") from None

    return {
        "schema": 1,
        "classification": "CONTRACT_TEST" if mode == "contract-test" else "PASS",
        "artifact_sha256": snapshot.sha256,
        "artifact_size": snapshot.size,
        "version": version,
        "build": int(build),
        "bundle_identity_match": True,
        "minimum_ios_match": True,
        "signature_verified": True,
        "distribution_profile_match": True,
        "apple_entitlement_match": True,
        "provider_runtime_verified": False,
        "testflight_upload_verified": False,
        "real_device_verified": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspect", choices=("inspect",))
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-build", required=True, type=int)
    parser.add_argument("--previous-build", required=True, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = inspect_ipa(
            arguments.artifact,
            expected_version=arguments.expected_version,
            expected_build=arguments.expected_build,
            previous_build=arguments.previous_build,
        )
    except CandidateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
