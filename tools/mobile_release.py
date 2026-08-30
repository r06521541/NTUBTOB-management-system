"""Fail-closed Android App Bundle release contract inspection.

This module never builds, signs, uploads, or publishes an artifact.  It only
validates public release metadata embedded by the Android build and, when the
CLI is used, asks JDK tools to verify an already signed AAB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence
from urllib.parse import urlsplit


CONTRACT_ENTRY = "base/assets/mobile-release-contract.properties"
REQUIRED_ENTRIES = frozenset(
    {
        "BundleConfig.pb",
        "base/manifest/AndroidManifest.xml",
        "base/dex/classes.dex",
        CONTRACT_ENTRY,
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
        "app_flavor",
        "client_mode",
        "release_scope",
        "contract_test",
        "api_origin",
    }
)
CONTRACT_TEST_VALUES = {
    "schema": "1",
    "application_id": "tw.org.ntubtob.portal.contracttest",
    "version_code": "1",
    "version_name": "0.1.0",
    "compile_sdk": "36",
    "target_sdk": "36",
    "app_flavor": "production",
    "client_mode": "real",
    "release_scope": "basic",
    "contract_test": "true",
    "api_origin": "https://mobile-release.invalid",
}
_CANDIDATE_APPLICATION_ID = "tw.org.ntubtob.portal"
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]+\.[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_AAB_BYTES = 1_073_741_824


class ContractError(ValueError):
    """The release configuration or artifact is not safe to accept."""


def parse_contract(raw: bytes) -> dict[str, str]:
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("release contract is not UTF-8") from error
    if "\x00" in source or source.startswith("\ufeff"):
        raise ContractError("release contract contains forbidden encoding markers")

    values: dict[str, str] = {}
    for line in source.replace("\r\n", "\n").splitlines():
        if not line or "=" not in line:
            raise ContractError("release contract contains a malformed line")
        key, value = line.split("=", 1)
        if key not in CONTRACT_KEYS:
            raise ContractError(f"release contract contains unknown key: {key}")
        if key in values:
            raise ContractError(f"release contract contains duplicate key: {key}")
        if not value or value != value.strip():
            raise ContractError(f"release contract value is empty or padded: {key}")
        values[key] = value
    if values.keys() != CONTRACT_KEYS:
        missing = sorted(CONTRACT_KEYS.difference(values))
        raise ContractError(f"release contract is missing keys: {', '.join(missing)}")
    return values


def _validate_api_origin(value: str, *, contract_test: bool) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ContractError("api_origin is malformed") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ContractError("api_origin must be an HTTPS origin without credentials or path")
    host = parsed.hostname.lower()
    if contract_test:
        if value != CONTRACT_TEST_VALUES["api_origin"]:
            raise ContractError("contract-test api_origin must use the fixed reserved origin")
        return
    if (
        host == "localhost"
        or "." not in host
        or host.endswith(".localhost")
        or host.endswith(".invalid")
        or host.endswith(".test")
        or host.endswith(".example")
        or host in {"example.com", "example.net", "example.org"}
        or host.endswith((".example.com", ".example.net", ".example.org"))
        or re.match(
            r"^(?:10|127|169\.254|192\.168|172\.(?:1[6-9]|2[0-9]|3[01]))\.",
            host,
        )
        or host in {"0.0.0.0", "::1"}
    ):
        raise ContractError("candidate api_origin is local or reserved")


def validate_contract(
    values: Mapping[str, str], *, expected_mode: str
) -> dict[str, str]:
    if expected_mode not in {"candidate", "contract-test"}:
        raise ContractError("expected mode must be candidate or contract-test")
    if set(values) != CONTRACT_KEYS or any(not isinstance(value, str) for value in values.values()):
        raise ContractError("release contract keys are incomplete or unknown")

    contract_test = expected_mode == "contract-test"
    expected_package = (
        CONTRACT_TEST_VALUES["application_id"]
        if contract_test
        else _CANDIDATE_APPLICATION_ID
    )
    fixed = {
        "schema": "1",
        "application_id": expected_package,
        "compile_sdk": "36",
        "target_sdk": "36",
        "app_flavor": "production",
        "client_mode": "real",
        "release_scope": "basic",
        "contract_test": str(contract_test).lower(),
    }
    for key, expected in fixed.items():
        if values[key] != expected:
            raise ContractError(f"release contract {key} must be {expected}")

    try:
        version_code = int(values["version_code"])
    except ValueError as error:
        raise ContractError("version_code must be a positive integer") from error
    if version_code < 1 or str(version_code) != values["version_code"]:
        raise ContractError("version_code must be a canonical positive integer")
    if (
        not _SEMVER.fullmatch(values["version_name"])
        or values["version_name"] == "0.0.0"
    ):
        raise ContractError("version_name must be a non-debug semantic version")
    _validate_api_origin(values["api_origin"], contract_test=contract_test)
    return dict(values)


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


def inspect_aab(
    artifact: Path,
    *,
    expected_mode: str,
    expected_package: str,
    expected_version_name: str,
    expected_version_code: int,
) -> dict[str, object]:
    if artifact.suffix.lower() != ".aab" or not artifact.is_file():
        raise ContractError("artifact must be an existing .aab file")
    size = artifact.stat().st_size
    if size < 1 or size > _MAX_AAB_BYTES:
        raise ContractError("AAB size is empty or exceeds the inspection limit")

    try:
        with zipfile.ZipFile(artifact) as archive:
            infos = archive.infolist()
            names = _safe_archive_names(infos)
            missing = sorted(REQUIRED_ENTRIES.difference(names))
            if missing:
                raise ContractError(f"AAB is missing required entries: {', '.join(missing)}")
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
            jar_signed = ".MF" in signature_files and ".SF" in signature_files and bool(
                signature_files.intersection({".RSA", ".DSA", ".EC"})
            )
            if not jar_signed:
                raise ContractError("AAB has no complete JAR signature entries")

            contract = validate_contract(
                parse_contract(archive.read(CONTRACT_ENTRY)),
                expected_mode=expected_mode,
            )
            manifest = archive.read("base/manifest/AndroidManifest.xml")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise ContractError("artifact is not a readable AAB") from error

    comparisons = {
        "application_id": expected_package,
        "version_name": expected_version_name,
        "version_code": str(expected_version_code),
    }
    for key, expected in comparisons.items():
        if contract[key] != expected:
            raise ContractError(f"AAB {key} does not match the expected value")
    for marker_name in ("application_id", "version_name"):
        marker = contract[marker_name].encode("utf-8")
        if marker not in manifest:
            raise ContractError(f"AAB manifest is missing the {marker_name} marker")

    return {
        "application_id": contract["application_id"],
        "compile_sdk": int(contract["compile_sdk"]),
        "contract_test": contract["contract_test"] == "true",
        "entry_count": len(names),
        "jar_signature_entries": jar_signed,
        "release_scope": contract["release_scope"],
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "size": size,
        "target_sdk": int(contract["target_sdk"]),
        "version_code": int(contract["version_code"]),
        "version_name": contract["version_name"],
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect-aab")
    inspect.add_argument("--artifact", type=Path, required=True)
    inspect.add_argument(
        "--mode", choices=("candidate", "contract-test"), required=True
    )
    inspect.add_argument("--expected-package", required=True)
    inspect.add_argument("--expected-version-name", required=True)
    inspect.add_argument("--expected-version-code", type=int, required=True)
    inspect.add_argument("--expected-signer-sha256", required=True)
    inspect.add_argument("--jarsigner", default="jarsigner")
    inspect.add_argument("--keytool", default="keytool")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = inspect_aab(
            arguments.artifact,
            expected_mode=arguments.mode,
            expected_package=arguments.expected_package,
            expected_version_name=arguments.expected_version_name,
            expected_version_code=arguments.expected_version_code,
        )
        result["signer_sha256"] = verify_aab_signer(
            arguments.artifact,
            expected_sha256=arguments.expected_signer_sha256,
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
