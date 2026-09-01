"""Fail-closed local operator for an Android Closed Testing candidate.

Private runtime and signing values are accepted only from an interactive hidden
prompt and forwarded to Gradle over a nonce-authenticated, one-use loopback
memory channel.  This module never uploads, opens
Play Console, deploys a runtime, or creates/rotates signing material.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import stat
import struct
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from tools import mobile_release

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "clients" / "flutter_app"
PUBSPEC = CLIENT / "pubspec.yaml"
FLUTTER_WRAPPER = ROOT / "tools" / "Invoke-FlutterToolchain.ps1"
FLUTTER_ROOT = Path(r"E:\codex-toolchains\task-113\flutter-clean")
PINNED_DART = FLUTTER_ROOT / "bin" / "cache" / "dart-sdk" / "bin" / "dart.exe"
FLUTTER_SNAPSHOT = FLUTTER_ROOT / "bin" / "cache" / "flutter_tools.snapshot"
BUNDLED_JAVA_HOME = Path(
    r"C:\Users\USER\.codex\toolchains\task-107\jdk-17\jdk-17.0.20+8"
)
BUNDLED_ANDROID_HOME = Path(r"C:\Users\USER\.codex\toolchains\task-107\android-sdk")
PACKAGE_NAME = "tw.org.ntubtob.portal"
APP_NAME = "NTUBTOB"
PRIVATE_LABELS = (
    "staging API origin",
    "staging LINE channel ID",
    "Android Google client ID",
    "Web server Google client ID",
    "external upload-keystore path",
    "upload-key alias",
    "upload-keystore password",
    "upload-key password",
)
APPROVAL = "BUILD EXACT ANDROID CLOSED CANDIDATE"
_MAX_PRIVATE_LENGTH = 2048
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]+\.[0-9]+$")


class OperatorError(RuntimeError):
    """A fixed, safe-to-report operator failure."""


@dataclass(frozen=True)
class Version:
    name: str
    code: int


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if completed.returncode != 0:
        raise OperatorError("repository state is unavailable")
    return completed.stdout.strip()


def _assert_reviewed_main(expected_commit: str | None = None) -> str:
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    origin_main = _git("rev-parse", "refs/remotes/origin/main")
    if (
        branch != "main"
        or head != origin_main
        or (expected_commit is not None and head != expected_commit)
        or _git("status", "--porcelain")
    ):
        raise OperatorError("repository is not the clean reviewed main commit")
    return head


def parse_version(source: str) -> Version:
    line = next(
        (line for line in source.splitlines() if line.startswith("version:")), ""
    )
    value = line.partition(":")[2].strip()
    name, separator, code_source = value.partition("+")
    try:
        code = int(code_source)
    except ValueError:
        raise OperatorError("pubspec release version is invalid") from None
    if (
        separator != "+"
        or code < 1
        or str(code) != code_source
        or _SEMVER.fullmatch(name) is None
        or name == "0.0.0"
    ):
        raise OperatorError("pubspec release version is invalid")
    return Version(name=name, code=code)


def preflight(*, previous_version_code: int) -> dict[str, object]:
    if previous_version_code < 0:
        raise OperatorError("previous version code is invalid")
    head = _assert_reviewed_main()
    version = parse_version(PUBSPEC.read_text(encoding="utf-8"))
    if version.code <= previous_version_code:
        raise OperatorError("candidate version is not monotonic")
    if (
        not FLUTTER_WRAPPER.is_file()
        or not PINNED_DART.is_file()
        or not FLUTTER_SNAPSHOT.is_file()
        or not (BUNDLED_JAVA_HOME / "bin" / "keytool.exe").is_file()
        or not (BUNDLED_JAVA_HOME / "bin" / "jarsigner.exe").is_file()
        or not (BUNDLED_ANDROID_HOME / "platforms" / "android-36").is_dir()
    ):
        raise OperatorError("pinned Android release toolchain is unavailable")
    return {
        "classification": "READY_FOR_PRIVATE_INPUT",
        "app_name": APP_NAME,
        "package_name": PACKAGE_NAME,
        "release_channel": "android-closed",
        "release_scope": "basic",
        "runtime": "staging-real",
        "commit": head,
        "version_name": version.name,
        "version_code": version.code,
        "previous_version_code": previous_version_code,
        "external_mutation_count": 0,
    }


def validate_private_lines(
    lines: Sequence[str], *, contract_test: bool
) -> tuple[str, ...]:
    if len(lines) != len(PRIVATE_LABELS) or any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_PRIVATE_LENGTH
        or "\n" in value
        or "\r" in value
        for value in lines
    ):
        raise OperatorError("private input contract is invalid")
    key_path = Path(lines[4])
    try:
        resolved_key = key_path.resolve(strict=True)
        resolved_key.relative_to(ROOT.resolve())
    except ValueError:
        pass
    except OSError:
        raise OperatorError("external signing material is unavailable") from None
    else:
        raise OperatorError("signing material must remain outside the repository")
    if not resolved_key.is_file() or resolved_key.suffix.lower() not in {
        ".jks",
        ".keystore",
    }:
        raise OperatorError("external signing material is unavailable")
    if contract_test is not ("contract" in lines[5].lower()):
        raise OperatorError("signing identity does not match operator mode")
    return tuple(lines)


def _minimal_environment(extra: Mapping[str, str]) -> dict[str, str]:
    allowed = (
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "JAVA_HOME",
        "ANDROID_HOME",
        "ANDROID_SDK_ROOT",
        "PUB_CACHE",
    )
    environment = {name: os.environ[name] for name in allowed if os.environ.get(name)}
    if sys.platform == "win32":
        environment.setdefault("JAVA_HOME", str(BUNDLED_JAVA_HOME))
        environment.setdefault("ANDROID_HOME", str(BUNDLED_ANDROID_HOME))
        environment.setdefault("ANDROID_SDK_ROOT", str(BUNDLED_ANDROID_HOME))
    environment.update(extra)
    return environment


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        raise OperatorError("external candidate directory is unavailable") from None
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _assert_no_reparse_chain(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if current.exists() and _is_reparse_point(current):
            raise OperatorError("candidate directory must not use a reparse point")


def _candidate_output_directory(local_app_data: str) -> Path:
    local_root = Path(local_app_data)
    if not local_root.is_absolute():
        raise OperatorError("external candidate directory is unavailable")
    try:
        resolved_root = local_root.resolve(strict=True)
    except OSError:
        raise OperatorError("external candidate directory is unavailable") from None
    repository_root = ROOT.resolve()
    try:
        resolved_root.relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise OperatorError("candidate directory must remain outside the repository")
    _assert_no_reparse_chain(local_root)
    current = local_root
    for component in ("NTUBTOB", "android-closed-candidate"):
        current = current / component
        try:
            current.mkdir(exist_ok=True)
            resolved = current.resolve(strict=True)
        except OSError:
            raise OperatorError("external candidate directory is unavailable") from None
        _assert_no_reparse_chain(current)
        try:
            resolved.relative_to(repository_root)
        except ValueError:
            pass
        else:
            raise OperatorError(
                "candidate directory must remain outside the repository"
            )
        current = resolved
    return current


def _copy_verified_exclusive(source: Path, output: Path, expected_sha256: str) -> None:
    created = False
    digest = hashlib.sha256()
    try:
        _assert_no_reparse_chain(output.parent)
        with source.open("rb") as source_file, output.open("xb") as output_file:
            created = True
            while chunk := source_file.read(1024 * 1024):
                output_file.write(chunk)
                digest.update(chunk)
            output_file.flush()
            os.fsync(output_file.fileno())
        if digest.hexdigest() != expected_sha256:
            raise OperatorError("retained candidate does not match inspected snapshot")
    except FileExistsError:
        raise OperatorError(
            "candidate output already exists; reconcile before retry"
        ) from None
    except OSError:
        if created:
            _remove_candidate_output(output)
        raise OperatorError("candidate output could not be retained") from None
    except BaseException:
        if created:
            _remove_candidate_output(output)
        raise


def _remove_candidate_output(output: Path) -> None:
    try:
        output.unlink(missing_ok=True)
    except OSError:
        raise OperatorError("candidate output could not be removed") from None


def build_command(
    version: Version,
    *,
    private_port: int,
    private_nonce: str,
    contract_test: bool = False,
) -> list[str]:
    flutter_command = (
        [str(PINNED_DART), str(FLUTTER_SNAPSHOT)]
        if sys.platform == "win32"
        else ["flutter"]
    )
    return [
        *flutter_command,
        "build",
        "appbundle",
        "--release",
        "--no-pub",
        "--no-android-gradle-daemon",
        "--android-project-arg=mobile-release-private-mode="
        + ("contract-test" if contract_test else "candidate"),
        f"--android-project-arg=mobile-release-private-port={private_port}",
        f"--android-project-arg=mobile-release-private-nonce={private_nonce}",
        "--dart-define=RELEASE_CHANNEL=android-closed",
        "--dart-define=APP_FLAVOR=staging",
        "--dart-define=CLIENT_MODE=real",
        "--dart-define=RELEASE_SCOPE=basic",
        f"--build-name={version.name}",
        f"--build-number={version.code}",
    ]


def build_contract_test() -> dict[str, object]:
    key_source = os.environ.get("CONTRACT_KEYSTORE", "")
    password = os.environ.get("CONTRACT_PASSWORD", "")
    private_lines = validate_private_lines(
        (
            "https://mobile-release.invalid",
            "12345",
            "android-contract.apps.googleusercontent.com",
            "server-contract.apps.googleusercontent.com",
            key_source,
            "mobile-release-contract",
            password,
            password,
        ),
        contract_test=True,
    )
    version = Version("0.1.0", 1)
    environment = _minimal_environment(
        {
            "MOBILE_RELEASE_CONTRACT_TEST": "true",
            "MOBILE_RELEASE_CHANNEL": "android-closed",
            "MOBILE_RELEASE_APPLICATION_ID": "tw.org.ntubtob.portal.contracttest",
            "MOBILE_RELEASE_VERSION_NAME": version.name,
            "MOBILE_RELEASE_VERSION_CODE": str(version.code),
            "MOBILE_RELEASE_PREVIOUS_VERSION_CODE": "0",
            "MOBILE_RELEASE_STAGING_API_ORIGIN_SHA256": mobile_release.CONTRACT_TEST_VALUES[
                "api_origin_sha256"
            ],
            "MOBILE_RELEASE_STAGING_PROVIDER_CONFIG_SHA256": mobile_release.CONTRACT_TEST_VALUES[
                "provider_config_sha256"
            ],
        }
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        private_port = int(reservation.getsockname()[1])
    if (
        _run_private_build(
            build_command(
                version,
                private_port=private_port,
                private_nonce=secrets.token_hex(16),
                contract_test=True,
            ),
            private_lines=private_lines,
            environment=environment,
            suppress_output=False,
        )
        != 0
    ):
        raise OperatorError("contract-test build failed safely")
    return {
        "classification": "CONTRACT_TEST_BUILD_PASS",
        "external_mutation_count": 0,
    }


def _run_private_build(
    command: Sequence[str],
    *,
    private_lines: Sequence[str],
    environment: Mapping[str, str],
    suppress_output: bool = True,
) -> int:
    nonce = next(
        value.rpartition("=")[2]
        for value in command
        if value.startswith("--android-project-arg=mobile-release-private-nonce=")
    )
    port = int(
        next(
            value.rpartition("=")[2]
            for value in command
            if value.startswith("--android-project-arg=mobile-release-private-port=")
        )
    )
    error: list[BaseException] = []

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", port))
        server.listen(1)
        server.settimeout(120)
    except OSError:
        server.close()
        raise OperatorError("private release input channel failed safely") from None

    def deliver_once() -> None:
        try:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(30)
                reader = connection.makefile("r", encoding="ascii", newline="\n")
                received_nonce = reader.readline(65)
                if received_nonce != f"{nonce}\n":
                    reader.close()
                    raise OperatorError(
                        "private release input channel authentication failed"
                    )
                payload = bytearray()
                for value in private_lines:
                    encoded = value.encode("utf-8")
                    payload.extend(struct.pack(">I", len(encoded)))
                    payload.extend(encoded)
                connection.sendall(payload)
                connection.shutdown(socket.SHUT_WR)
        except BaseException as exception:
            error.append(exception)

    thread = threading.Thread(target=deliver_once, daemon=True)
    thread.start()
    try:
        completed = subprocess.run(
            list(command),
            cwd=CLIENT,
            check=False,
            stdout=subprocess.DEVNULL if suppress_output else None,
            stderr=subprocess.DEVNULL if suppress_output else None,
            env=dict(environment),
            timeout=1800,
        )
    finally:
        server.close()
        thread.join(timeout=5)
    if thread.is_alive() or error:
        raise OperatorError("private release input channel failed safely")
    return completed.returncode


def _hidden_input(label: str) -> str:
    prompt = f"Private input - {label} (hidden): "
    if sys.platform != "win32" or not sys.stdin.isatty():
        return getpass.getpass(prompt)
    import msvcrt

    print(prompt, end="", flush=True)
    characters: list[str] = []
    while True:
        character = msvcrt.getwch()
        if character in {"\r", "\n"}:
            print()
            return "".join(characters)
        if character == "\003":
            raise KeyboardInterrupt
        if character == "\b":
            if characters:
                characters.pop()
                print("\b \b", end="", flush=True)
            continue
        if character in {"\x00", "\xe0"}:
            msvcrt.getwch()
            continue
        characters.append(character)
        print("*", end="", flush=True)


def build_candidate(
    *,
    previous_version_code: int,
    prompt: Callable[[str], str] = input,
    hidden_prompt: Callable[[str], str] = _hidden_input,
) -> dict[str, object]:
    ready = preflight(previous_version_code=previous_version_code)
    print(json.dumps(ready, sort_keys=True))
    if prompt(f'Type "{APPROVAL}" to continue: ') != APPROVAL:
        raise OperatorError("one-shot approval was not granted")
    private_lines = validate_private_lines(
        tuple(hidden_prompt(label) for label in PRIVATE_LABELS), contract_test=False
    )
    expected_signer = hidden_prompt("expected upload-certificate SHA-256")
    if mobile_release._SHA256.fullmatch(expected_signer) is None:
        raise OperatorError("expected signer fingerprint is invalid")
    version = Version(str(ready["version_name"]), int(ready["version_code"]))
    reviewed_commit = str(ready["commit"])
    api_digest = hashlib.sha256(private_lines[0].encode()).hexdigest()
    provider_digest = hashlib.sha256("\n".join(private_lines[1:4]).encode()).hexdigest()
    environment = _minimal_environment(
        {
            "MOBILE_RELEASE_CONTRACT_TEST": "false",
            "MOBILE_RELEASE_CHANNEL": "android-closed",
            "MOBILE_RELEASE_APPLICATION_ID": PACKAGE_NAME,
            "MOBILE_RELEASE_VERSION_NAME": version.name,
            "MOBILE_RELEASE_VERSION_CODE": str(version.code),
            "MOBILE_RELEASE_PREVIOUS_VERSION_CODE": str(previous_version_code),
            "MOBILE_RELEASE_STAGING_API_ORIGIN_SHA256": api_digest,
            "MOBILE_RELEASE_STAGING_PROVIDER_CONFIG_SHA256": provider_digest,
        }
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        private_port = int(reservation.getsockname()[1])
    private_nonce = secrets.token_hex(16)
    build_root = CLIENT / "build"
    copied_output: Path | None = None
    completed_successfully = False
    try:
        _assert_reviewed_main(reviewed_commit)
        if (
            _run_private_build(
                build_command(
                    version, private_port=private_port, private_nonce=private_nonce
                ),
                private_lines=private_lines,
                environment=environment,
            )
            != 0
        ):
            raise OperatorError("candidate build failed safely; reconcile before retry")
        _assert_reviewed_main(reviewed_commit)
        artifact = (
            build_root / "app" / "outputs" / "bundle" / "release" / "app-release.aab"
        )
        java_home = Path(environment.get("JAVA_HOME", ""))
        executable_suffix = ".exe" if sys.platform == "win32" else ""
        jarsigner = java_home / "bin" / f"jarsigner{executable_suffix}"
        keytool = java_home / "bin" / f"keytool{executable_suffix}"
        if not jarsigner.is_file() or not keytool.is_file():
            raise OperatorError("JDK signing tools are unavailable")
        with mobile_release.snapshot_artifact(artifact) as stable:
            result = mobile_release.inspect_and_verify_aab(
                stable.path,
                expected_mode="android-closed",
                expected_package=PACKAGE_NAME,
                expected_version_name=version.name,
                expected_version_code=version.code,
                expected_previous_version_code=previous_version_code,
                expected_api_origin_sha256=api_digest,
                expected_provider_config_sha256=provider_digest,
                expected_signer_sha256=expected_signer,
                jarsigner=str(jarsigner),
                keytool=str(keytool),
            )
            if result["sha256"] != stable.sha256:
                raise OperatorError("candidate snapshot evidence is inconsistent")
            output_directory = _candidate_output_directory(
                os.environ.get("LOCALAPPDATA", "")
            )
            output = output_directory / f"ntubtob-{version.name}-{version.code}.aab"
            _copy_verified_exclusive(stable.path, output, stable.sha256)
            copied_output = output
        _assert_reviewed_main(reviewed_commit)
        completed_successfully = True
    finally:
        if not completed_successfully and copied_output is not None:
            _remove_candidate_output(copied_output)
        shutil.rmtree(build_root, ignore_errors=True)
        if build_root.exists():
            raise OperatorError("private build outputs could not be removed")
    return {
        "classification": "CANDIDATE_READY_FOR_OWNER_GATES",
        "package_name": result["application_id"],
        "version_name": result["version_name"],
        "version_code": result["version_code"],
        "previous_version_code": result["previous_version_code"],
        "artifact_sha256": result["sha256"],
        "release_scope": result["release_scope"],
        "release_channel": result["release_channel"],
        "signer_match": True,
        "play_upload_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "build", "contract-test-build"))
    parser.add_argument("--previous-version-code", type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == "contract-test-build":
            result = build_contract_test()
        elif args.previous_version_code is None:
            raise OperatorError("previous version code is required")
        elif args.action == "preflight":
            result = preflight(previous_version_code=args.previous_version_code)
        else:
            result = build_candidate(previous_version_code=args.previous_version_code)
    except (OperatorError, mobile_release.ContractError, subprocess.TimeoutExpired):
        print("STOP: Android candidate operator failed safely", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
