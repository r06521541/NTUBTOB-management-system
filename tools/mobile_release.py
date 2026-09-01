"""Fail-closed Android App Bundle release contract inspection.

This module never builds, signs, uploads, or publishes an artifact.  It only
validates public release metadata embedded by the Android build and, when the
CLI is used, asks JDK tools to verify an already signed AAB.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping, Sequence
from urllib.parse import urlsplit
from xml.etree import ElementTree


CONTRACT_ENTRY = "base/assets/mobile-release-contract.properties"
RUNTIME_CONFIG_ENTRY = "base/assets/flutter_assets/mobile-runtime-config.json"
REQUIRED_ENTRIES = frozenset(
    {
        "BundleConfig.pb",
        "base/manifest/AndroidManifest.xml",
        "base/dex/classes.dex",
        CONTRACT_ENTRY,
        RUNTIME_CONFIG_ENTRY,
    }
)
CONTRACT_KEYS = frozenset(
    {
        "schema",
        "application_id",
        "version_code",
        "version_name",
        "compile_sdk",
        "target_sdk",
        "release_channel",
        "app_flavor",
        "client_mode",
        "release_scope",
        "contract_test",
        "api_origin_sha256",
        "provider_config_sha256",
        "previous_version_code",
    }
)
CONTRACT_TEST_VALUES = {
    "schema": "2",
    "application_id": "tw.org.ntubtob.portal.contracttest",
    "version_code": "1",
    "previous_version_code": "0",
    "version_name": "0.1.0",
    "compile_sdk": "36",
    "target_sdk": "36",
    "release_channel": "android-closed",
    "app_flavor": "staging",
    "client_mode": "real",
    "release_scope": "basic",
    "contract_test": "true",
    "api_origin_sha256": hashlib.sha256(b"https://mobile-release.invalid").hexdigest(),
    "provider_config_sha256": hashlib.sha256(
        b"12345\nandroid-contract.apps.googleusercontent.com\n"
        b"server-contract.apps.googleusercontent.com"
    ).hexdigest(),
}
_CANDIDATE_APPLICATION_ID = "tw.org.ntubtob.portal"
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]+\.[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_AAB_BYTES = 1_073_741_824
_MAX_BUNDLETOOL_OUTPUT_BYTES = 1_048_576
_BUNDLETOOL_TIMEOUT_SECONDS = 120
_ANDROID_NAMESPACE = "http://schemas.android.com/apk/res/android"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_ANDROID_ROOT = _REPOSITORY_ROOT / "clients" / "flutter_app" / "android"
_GRADLE_WRAPPER_COMPONENT_SHA256 = {
    "gradlew": "ec56c02543666d92d9ac5ae7fcc48f88ce4de0deb8b7f9b39928ca46f68c1b2b",
    "gradlew.bat": "f4f428c5626b3d90cef3bd4e7fd3ad3ea5760442db8c09d586b5bfe031dbe5e3",
    "gradle/wrapper/gradle-wrapper.jar": (
        "16caeaf66d57a0d1d2087fef6a97efa62de8da69afa5b908f40db35afc4342da"
    ),
    "gradle/wrapper/gradle-wrapper.properties": (
        "b690d26223576fe4e63889fad9a00df81945cb870b9476cc5a563152a1a88a74"
    ),
}
_GRADLE_WRAPPER_TEXT_COMPONENTS = frozenset(
    {"gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.properties"}
)


class ContractError(ValueError):
    """The release configuration or artifact is not safe to accept."""


@dataclass(frozen=True)
class BundleMetadata:
    application_id: str
    version_name: str
    version_code: int
    min_sdk: int
    target_sdk: int
    compile_sdk: int


@dataclass(frozen=True)
class ArtifactSnapshot:
    path: Path
    sha256: str
    size: int


def parse_contract(raw: bytes) -> dict[str, str]:
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("release contract encoding is invalid") from None
    if "\x00" in source or source.startswith("\ufeff"):
        raise ContractError("release contract contains forbidden encoding markers")

    values: dict[str, str] = {}
    for line in source.replace("\r\n", "\n").splitlines():
        if not line or "=" not in line:
            raise ContractError("release contract structure is invalid")
        key, value = line.split("=", 1)
        if key not in CONTRACT_KEYS:
            raise ContractError("release contract keys are invalid")
        if key in values:
            raise ContractError("release contract keys are duplicated")
        if not value or value != value.strip():
            raise ContractError("release contract values are invalid")
        values[key] = value
    if values.keys() != CONTRACT_KEYS:
        raise ContractError("release contract keys are incomplete")
    return values


def validate_runtime_config(raw: bytes, contract: Mapping[str, str]) -> None:
    if len(raw) > 8192:
        raise ContractError("runtime configuration is invalid")

    def no_duplicates(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ContractError("runtime configuration is invalid")
            result[key] = value
        return result

    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ContractError("runtime configuration is invalid") from None
    expected_keys = {
        "API_BASE_URL",
        "LINE_CHANNEL_ID",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_SERVER_CLIENT_ID",
    }
    if (
        not isinstance(decoded, dict)
        or set(decoded) != expected_keys
        or any(not isinstance(value, str) or not value for value in decoded.values())
    ):
        raise ContractError("runtime configuration is invalid")
    canonical = (
        json.dumps(decoded, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise ContractError("runtime configuration is invalid")
    try:
        origin = urlsplit(decoded["API_BASE_URL"])
        port = origin.port
    except ValueError:
        raise ContractError("runtime configuration is invalid") from None
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or port not in {None, 443}
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        raise ContractError("runtime configuration is invalid")
    line_channel_id = decoded["LINE_CHANNEL_ID"]
    google_client_id = decoded["GOOGLE_CLIENT_ID"]
    google_server_client_id = decoded["GOOGLE_SERVER_CLIENT_ID"]
    google_pattern = re.compile(
        r"^[0-9A-Za-z][0-9A-Za-z._-]{5,199}\.apps\.googleusercontent\.com$"
    )
    if (
        re.fullmatch(r"[1-9][0-9]{4,19}", line_channel_id) is None
        or google_pattern.fullmatch(google_client_id) is None
        or google_pattern.fullmatch(google_server_client_id) is None
        or google_client_id == google_server_client_id
    ):
        raise ContractError("runtime configuration is invalid")
    if contract["contract_test"] == "false":
        host = origin.hostname.lower()
        reserved_suffixes = (".localhost", ".invalid", ".test", ".example")
        reserved_examples = {"example.com", "example.net", "example.org"}
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        noncandidate = re.compile(
            r"(?:^|[-_.])(debug|dev|fake|test|contract)(?:$|[-_.])", re.IGNORECASE
        )
        if (
            host == "localhost"
            or "." not in host
            or host.endswith(reserved_suffixes)
            or host in reserved_examples
            or any(host.endswith(f".{value}") for value in reserved_examples)
            or (address is not None and not address.is_global)
            or noncandidate.search(google_client_id)
            or noncandidate.search(google_server_client_id)
        ):
            raise ContractError("runtime configuration is invalid")
    api_digest = hashlib.sha256(decoded["API_BASE_URL"].encode()).hexdigest()
    provider_digest = hashlib.sha256(
        "\n".join(
            (
                decoded["LINE_CHANNEL_ID"],
                decoded["GOOGLE_CLIENT_ID"],
                decoded["GOOGLE_SERVER_CLIENT_ID"],
            )
        ).encode()
    ).hexdigest()
    if (
        api_digest != contract["api_origin_sha256"]
        or provider_digest != contract["provider_config_sha256"]
    ):
        raise ContractError("runtime configuration does not match release contract")


def validate_contract(
    values: Mapping[str, str], *, expected_mode: str
) -> dict[str, str]:
    if expected_mode not in {"android-closed", "contract-test"}:
        raise ContractError("expected mode must be android-closed or contract-test")
    if set(values) != CONTRACT_KEYS or any(
        not isinstance(value, str) for value in values.values()
    ):
        raise ContractError("release contract keys are incomplete or unknown")

    contract_test = expected_mode == "contract-test"
    expected_package = (
        CONTRACT_TEST_VALUES["application_id"]
        if contract_test
        else _CANDIDATE_APPLICATION_ID
    )
    fixed = {
        "schema": "2",
        "application_id": expected_package,
        "compile_sdk": "36",
        "target_sdk": "36",
        "release_channel": "android-closed",
        "app_flavor": "staging",
        "client_mode": "real",
        "release_scope": "basic",
        "contract_test": str(contract_test).lower(),
    }
    for key, expected in fixed.items():
        if values[key] != expected:
            raise ContractError("release contract fixed values do not match")

    try:
        version_code = int(values["version_code"])
    except ValueError:
        raise ContractError("release contract version code is invalid") from None
    if version_code < 1 or str(version_code) != values["version_code"]:
        raise ContractError("version_code must be a canonical positive integer")
    try:
        previous_version_code = int(values["previous_version_code"])
    except ValueError:
        raise ContractError(
            "release contract previous version code is invalid"
        ) from None
    if (
        previous_version_code < 0
        or str(previous_version_code) != values["previous_version_code"]
        or version_code <= previous_version_code
    ):
        raise ContractError(
            "version_code must be greater than canonical previous_version_code"
        )
    if (
        not _SEMVER.fullmatch(values["version_name"])
        or values["version_name"] == "0.0.0"
    ):
        raise ContractError("version_name must be a non-debug semantic version")
    if not _SHA256.fullmatch(values["api_origin_sha256"]):
        raise ContractError("api_origin_sha256 must be a lowercase SHA-256 digest")
    if not _SHA256.fullmatch(values["provider_config_sha256"]):
        raise ContractError("provider_config_sha256 must be a lowercase SHA-256 digest")
    if (
        contract_test
        and values["api_origin_sha256"] != CONTRACT_TEST_VALUES["api_origin_sha256"]
    ):
        raise ContractError(
            "contract-test api_origin_sha256 must use the fixed reserved origin digest"
        )
    if (
        contract_test
        and values["provider_config_sha256"]
        != CONTRACT_TEST_VALUES["provider_config_sha256"]
    ):
        raise ContractError(
            "contract-test provider_config_sha256 must use the fixed fictional digest"
        )
    return dict(values)


@contextmanager
def snapshot_artifact(artifact: Path) -> Iterator[ArtifactSnapshot]:
    if artifact.suffix.lower() != ".aab":
        raise ContractError("artifact path is not an AAB")

    with tempfile.TemporaryDirectory(prefix="mobile-release-snapshot-") as directory:
        snapshot_path = Path(directory) / "candidate.aab"
        digest = hashlib.sha256()
        size = 0
        try:
            with artifact.open("rb") as source, snapshot_path.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > _MAX_AAB_BYTES:
                        raise ContractError("AAB exceeds the inspection limit")
                    digest.update(chunk)
                    target.write(chunk)
        except ContractError:
            raise
        except OSError:
            raise ContractError("artifact could not be snapshotted") from None
        if size < 1:
            raise ContractError("AAB is empty")
        yield ArtifactSnapshot(
            path=snapshot_path,
            sha256=digest.hexdigest(),
            size=size,
        )


def _verified_gradle_wrapper_components() -> dict[str, bytes]:
    android_root = _ANDROID_ROOT.resolve()
    verified: dict[str, bytes] = {}
    try:
        android_root.relative_to(_REPOSITORY_ROOT.resolve())
        for relative, expected_sha256 in _GRADLE_WRAPPER_COMPONENT_SHA256.items():
            component = _ANDROID_ROOT / relative
            if component.is_symlink() or not component.is_file():
                raise ContractError("bundletool runner integrity is invalid")
            resolved = component.resolve()
            resolved.relative_to(android_root)
            source = resolved.read_bytes()
            snapshot_source = source
            if relative in _GRADLE_WRAPPER_TEXT_COMPONENTS:
                source = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if hashlib.sha256(source).hexdigest() != expected_sha256:
                raise ContractError("bundletool runner integrity is invalid")
            verified[relative] = snapshot_source
    except ContractError:
        raise
    except (OSError, ValueError):
        raise ContractError("bundletool runner integrity is invalid") from None
    return verified


def _gradle_wrapper() -> Path:
    _verified_gradle_wrapper_components()
    name = "gradlew.bat" if sys.platform == "win32" else "gradlew"
    return (_ANDROID_ROOT / name).resolve()


@contextmanager
def _snapshot_gradle_wrapper() -> Iterator[Path]:
    components = _verified_gradle_wrapper_components()
    with tempfile.TemporaryDirectory(
        prefix="mobile-release-gradle-wrapper-"
    ) as directory:
        wrapper_root = Path(directory)
        for relative, source in components.items():
            target = wrapper_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source)
        wrapper = wrapper_root / (
            "gradlew.bat" if sys.platform == "win32" else "gradlew"
        )
        if sys.platform != "win32":
            wrapper.chmod(0o700)
        yield wrapper


def _bundletool_environment() -> dict[str, str]:
    java_home_source = os.environ.get("JAVA_HOME", "")
    try:
        java_home = Path(java_home_source).resolve(strict=True)
        java = java_home / "bin" / ("java.exe" if sys.platform == "win32" else "java")
        if not java.is_file():
            raise OSError
        gradle_home = (Path.home() / ".gradle").resolve()
        temporary_directory = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, ValueError):
        raise ContractError("bundletool runtime environment is unavailable") from None

    environment = {
        "GRADLE_USER_HOME": str(gradle_home),
        "JAVA_HOME": str(java_home),
        "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8",
    }
    if sys.platform == "win32":
        try:
            windows_root = Path(
                os.environ.get("SystemRoot") or os.environ.get("WINDIR") or ""
            ).resolve(strict=True)
            command_processor = windows_root / "System32" / "cmd.exe"
            if not command_processor.is_file():
                raise OSError
        except (OSError, ValueError):
            raise ContractError(
                "bundletool runtime environment is unavailable"
            ) from None
        environment.update(
            {
                "COMSPEC": str(command_processor),
                "OS": "Windows_NT",
                "PATH": os.pathsep.join(
                    (str(java_home / "bin"), str(windows_root / "System32"))
                ),
                "PATHEXT": ".COM;.EXE;.BAT;.CMD",
                "SystemRoot": str(windows_root),
                "TEMP": str(temporary_directory),
                "TMP": str(temporary_directory),
                "WINDIR": str(windows_root),
            }
        )
    else:
        environment.update(
            {
                "HOME": str(Path.home().resolve()),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": os.pathsep.join((str(java_home / "bin"), "/usr/bin", "/bin")),
                "TMPDIR": str(temporary_directory),
            }
        )
    return environment


def _run_bundletool_task(task: str, snapshot: Path) -> str:
    if task not in {"verifyCandidateBundle", "dumpCandidateManifest"}:
        raise ContractError("bundletool task is not approved")
    environment = _bundletool_environment()
    try:
        with (
            _snapshot_gradle_wrapper() as wrapper,
            tempfile.TemporaryFile() as standard_output,
            tempfile.TemporaryFile() as error_output,
        ):
            command = [
                str(wrapper),
                "--offline",
                "--no-daemon",
                "-q",
                "-Dfile.encoding=UTF-8",
                task,
                f"-PmobileReleaseBundle={snapshot}",
            ]
            completed = subprocess.run(
                command,
                cwd=_ANDROID_ROOT,
                check=False,
                stdout=standard_output,
                stderr=error_output,
                env=environment,
                timeout=_BUNDLETOOL_TIMEOUT_SECONDS,
            )
            output_size = standard_output.tell()
            error_size = error_output.tell()
            if output_size + error_size > _MAX_BUNDLETOOL_OUTPUT_BYTES:
                raise ContractError("bundletool output exceeds the inspection limit")
            standard_output.seek(0)
            output = standard_output.read()
    except (OSError, subprocess.TimeoutExpired):
        raise ContractError("bundletool invocation failed") from None
    if completed.returncode != 0:
        raise ContractError("bundletool rejected the AAB")
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("bundletool output encoding is invalid") from None


def parse_bundletool_manifest(source: str) -> BundleMetadata:
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError:
        raise ContractError("bundletool manifest output is invalid") from None
    if root.tag != "manifest":
        raise ContractError("bundletool manifest root is invalid")

    android_attribute = f"{{{_ANDROID_NAMESPACE}}}"
    uses_sdk = [child for child in root if child.tag == "uses-sdk"]
    if len(uses_sdk) != 1:
        raise ContractError("bundletool SDK metadata is incomplete")

    def required_text(element: ElementTree.Element, name: str) -> str:
        value = element.get(name)
        if value is None or not value or value != value.strip():
            raise ContractError("bundletool manifest metadata is incomplete")
        return value

    def required_integer(element: ElementTree.Element, name: str) -> int:
        value = required_text(element, name)
        try:
            parsed = int(value)
        except ValueError:
            raise ContractError("bundletool manifest integer is invalid") from None
        if parsed < 0 or str(parsed) != value:
            raise ContractError("bundletool manifest integer is invalid")
        return parsed

    return BundleMetadata(
        application_id=required_text(root, "package"),
        version_name=required_text(root, f"{android_attribute}versionName"),
        version_code=required_integer(root, f"{android_attribute}versionCode"),
        min_sdk=required_integer(uses_sdk[0], f"{android_attribute}minSdkVersion"),
        target_sdk=required_integer(
            uses_sdk[0], f"{android_attribute}targetSdkVersion"
        ),
        compile_sdk=required_integer(root, f"{android_attribute}compileSdkVersion"),
    )


def read_bundletool_metadata(snapshot: Path) -> BundleMetadata:
    _run_bundletool_task("verifyCandidateBundle", snapshot)
    manifest = _run_bundletool_task("dumpCandidateManifest", snapshot)
    return parse_bundletool_manifest(manifest)


def _safe_archive_names(infos: Sequence[zipfile.ZipInfo]) -> list[str]:
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise ContractError("AAB contains duplicate entries")
    total_size = 0
    for info in infos:
        path = PurePosixPath(info.filename)
        if (
            not info.filename
            or info.filename.startswith(("/", "\\"))
            or "\\" in info.filename
            or ".." in path.parts
        ):
            raise ContractError("AAB contains an unsafe entry path")
        if info.flag_bits & 0x1:
            raise ContractError("AAB contains an encrypted entry")
        total_size += info.file_size
        lowered = info.filename.lower()
        if (
            lowered.endswith((".jks", ".keystore"))
            or path.name.lower() == "key.properties"
        ):
            raise ContractError("AAB contains signing material")
    if total_size > _MAX_AAB_BYTES:
        raise ContractError("AAB uncompressed content exceeds the inspection limit")
    return names


def _inspect_snapshot(
    snapshot: ArtifactSnapshot,
    metadata: BundleMetadata,
    *,
    expected_mode: str,
    expected_package: str,
    expected_version_name: str,
    expected_version_code: int,
    expected_previous_version_code: int,
    expected_api_origin_sha256: str,
    expected_provider_config_sha256: str,
) -> dict[str, object]:
    try:
        with zipfile.ZipFile(snapshot.path) as archive:
            infos = archive.infolist()
            names = _safe_archive_names(infos)
            missing = sorted(REQUIRED_ENTRIES.difference(names))
            if missing:
                raise ContractError(
                    f"AAB is missing required entries: {', '.join(missing)}"
                )
            if archive.testzip() is not None:
                raise ContractError("AAB contains a corrupt entry")
            for required in REQUIRED_ENTRIES:
                if archive.getinfo(required).file_size < 1:
                    raise ContractError(f"AAB required entry is empty: {required}")

            signature_files = {
                PurePosixPath(name).suffix.upper()
                for name in names
                if PurePosixPath(name).parent == PurePosixPath("META-INF")
            }
            jar_signed = (
                ".MF" in signature_files
                and ".SF" in signature_files
                and bool(signature_files.intersection({".RSA", ".DSA", ".EC"}))
            )
            if not jar_signed:
                raise ContractError("AAB has no complete JAR signature entries")

            contract = validate_contract(
                parse_contract(archive.read(CONTRACT_ENTRY)),
                expected_mode=expected_mode,
            )
            validate_runtime_config(archive.read(RUNTIME_CONFIG_ENTRY), contract)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        raise ContractError("artifact is not a readable AAB") from None

    comparisons = {
        "application_id": expected_package,
        "version_name": expected_version_name,
        "version_code": str(expected_version_code),
        "previous_version_code": str(expected_previous_version_code),
        "api_origin_sha256": expected_api_origin_sha256,
        "provider_config_sha256": expected_provider_config_sha256,
    }
    for key, expected in comparisons.items():
        if contract[key] != expected:
            raise ContractError("AAB contract does not match expected metadata")

    if (
        metadata.application_id != expected_package
        or metadata.version_name != expected_version_name
        or metadata.version_code != expected_version_code
    ):
        raise ContractError("bundletool identity metadata does not match")
    if (
        metadata.min_sdk != 24
        or metadata.target_sdk != 36
        or metadata.compile_sdk != 36
    ):
        raise ContractError("bundletool SDK metadata does not match")

    return {
        "api_origin_sha256": contract["api_origin_sha256"],
        "application_id": metadata.application_id,
        "compile_sdk": metadata.compile_sdk,
        "contract_test": contract["contract_test"] == "true",
        "entry_count": len(names),
        "jar_signature_entries": jar_signed,
        "min_sdk": metadata.min_sdk,
        "release_channel": contract["release_channel"],
        "release_scope": contract["release_scope"],
        "sha256": snapshot.sha256,
        "size": snapshot.size,
        "target_sdk": metadata.target_sdk,
        "version_code": metadata.version_code,
        "previous_version_code": int(contract["previous_version_code"]),
        "provider_config_sha256": contract["provider_config_sha256"],
        "version_name": metadata.version_name,
    }


def parse_signer_sha256(output: str) -> str:
    match = re.search(
        r"(?im)^\s*SHA256:\s*((?:[0-9a-f]{2}:){31}[0-9a-f]{2})\s*$", output
    )
    if match is None:
        raise ContractError("keytool output has no unambiguous SHA256 fingerprint")
    return match.group(1).replace(":", "").lower()


def verify_aab_signer(
    artifact: Path,
    *,
    expected_sha256: str,
    jarsigner: str,
    keytool: str,
) -> str:
    normalized = expected_sha256.replace(":", "").lower()
    if not _SHA256.fullmatch(normalized):
        raise ContractError("expected signer SHA256 is malformed")

    certificate = subprocess.run(
        [keytool, "-printcert", "-jarfile", str(artifact)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if certificate.returncode != 0:
        raise ContractError("keytool could not read the AAB signer")
    actual = parse_signer_sha256(certificate.stdout)
    if actual != normalized:
        raise ContractError("AAB signer SHA256 does not match the approved fingerprint")

    exported = subprocess.run(
        [keytool, "-printcert", "-rfc", "-jarfile", str(artifact)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    certificate_pem = re.search(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        exported.stdout,
        flags=re.DOTALL,
    )
    if exported.returncode != 0 or certificate_pem is None:
        raise ContractError("keytool could not export the AAB signer certificate")

    with tempfile.TemporaryDirectory(prefix="mobile-release-verify-") as directory:
        verification_root = Path(directory)
        certificate_path = verification_root / "approved-signer.pem"
        trust_store = verification_root / "approved-signer.p12"
        trust_password = secrets.token_hex(24)
        certificate_path.write_text(certificate_pem.group(0) + "\n", encoding="ascii")
        imported = subprocess.run(
            [
                keytool,
                "-importcert",
                "-noprompt",
                "-alias",
                "approved-mobile-release-signer",
                "-file",
                str(certificate_path),
                "-keystore",
                str(trust_store),
                "-storetype",
                "PKCS12",
                "-storepass",
                trust_password,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if imported.returncode != 0:
            raise ContractError("keytool could not prepare strict signer verification")
        verified = subprocess.run(
            [
                jarsigner,
                "-verify",
                "-strict",
                "-certs",
                "-keystore",
                str(trust_store),
                "-storetype",
                "PKCS12",
                "-storepass",
                trust_password,
                str(artifact),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if verified.returncode != 0:
        raise ContractError("jarsigner did not strictly verify every AAB entry")
    return actual


def inspect_and_verify_aab(
    artifact: Path,
    *,
    expected_mode: str,
    expected_package: str,
    expected_version_name: str,
    expected_version_code: int,
    expected_previous_version_code: int,
    expected_api_origin_sha256: str,
    expected_provider_config_sha256: str,
    expected_signer_sha256: str,
    jarsigner: str,
    keytool: str,
) -> dict[str, object]:
    with snapshot_artifact(artifact) as snapshot:
        metadata = read_bundletool_metadata(snapshot.path)
        result = _inspect_snapshot(
            snapshot,
            metadata,
            expected_mode=expected_mode,
            expected_package=expected_package,
            expected_version_name=expected_version_name,
            expected_version_code=expected_version_code,
            expected_previous_version_code=expected_previous_version_code,
            expected_api_origin_sha256=expected_api_origin_sha256,
            expected_provider_config_sha256=expected_provider_config_sha256,
        )
        result["signer_sha256"] = verify_aab_signer(
            snapshot.path,
            expected_sha256=expected_signer_sha256,
            jarsigner=jarsigner,
            keytool=keytool,
        )
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect-aab")
    inspect.add_argument("--artifact", type=Path, required=True)
    inspect.add_argument(
        "--mode", choices=("android-closed", "contract-test"), required=True
    )
    inspect.add_argument("--expected-package", required=True)
    inspect.add_argument("--expected-version-name", required=True)
    inspect.add_argument("--expected-version-code", type=int, required=True)
    inspect.add_argument("--expected-previous-version-code", type=int, required=True)
    inspect.add_argument(
        "--expected-staging-api-origin-sha256",
        required=True,
    )
    inspect.add_argument(
        "--expected-staging-provider-config-sha256",
        required=True,
    )
    inspect.add_argument("--expected-signer-sha256", required=True)
    inspect.add_argument("--jarsigner", default="jarsigner")
    inspect.add_argument("--keytool", default="keytool")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = inspect_and_verify_aab(
            arguments.artifact,
            expected_mode=arguments.mode,
            expected_package=arguments.expected_package,
            expected_version_name=arguments.expected_version_name,
            expected_version_code=arguments.expected_version_code,
            expected_previous_version_code=arguments.expected_previous_version_code,
            expected_api_origin_sha256=arguments.expected_staging_api_origin_sha256,
            expected_provider_config_sha256=(
                arguments.expected_staging_provider_config_sha256
            ),
            expected_signer_sha256=arguments.expected_signer_sha256,
            jarsigner=arguments.jarsigner,
            keytool=arguments.keytool,
        )
    except ContractError as error:
        print(f"mobile release inspection failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
