"""Signing-only GitHub macOS baseline; native tools, no transfer/upload controller.

Only the reviewed workflow may supply real inputs. Temporary files and necessary
security argv are deliberate custody exceptions (TASK-198); no raw output escapes.
This is not isolation from malicious same-user processes or reviewed build phases.
"""

import argparse
import base64
import hashlib
import json
import os
import platform
import plistlib
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from tools import ios_candidate_inspector as inspector

REPO = "r06521541/NTUBTOB-management-system"
BUNDLE = inspector.EXPECTED_BUNDLE_ID
ROOT_NAME = "ntubtob-native-signing"
DEVELOPER = "/Applications/Xcode_26.3.app/Contents/Developer"
XCODE = DEVELOPER + "/usr/bin/xcodebuild"
SECURITY = "/usr/bin/security"
PROFILE_NAME = "ntubtob-native-signing.mobileprovision"
CONFIGS = (
    "Flutter/AuthConfig.xcconfig",
    "Flutter/StoreReleaseConfig.xcconfig",
    "Runner/Runner.entitlements",
)
PROFILES = (
    "Library/MobileDevice/Provisioning Profiles",
    "Library/Developer/Xcode/UserData/Provisioning Profiles",
)
INPUT_NAMES = (
    "IOS_DISTRIBUTION_P12_BASE64",
    "IOS_DISTRIBUTION_P12_PASSWORD",
    "IOS_DISTRIBUTION_PROFILE_BASE64",
)


class Failure(Exception):
    def __init__(
        self, stage, reason, exit_code=None, *, stopped=True, provider_codes=None
    ):
        super().__init__("native signing step failed")
        self.stage, self.reason, self.exit_code, self.stopped = (
            stage,
            reason,
            exit_code,
            stopped,
        )
        self.provider_codes = provider_codes
        self.cleanup_failures = []

    def public(self):
        value = {
            "stage": self.stage,
            "reason": self.reason,
            "exit_code": self.exit_code,
        }
        if self.provider_codes is not None:
            value["provider_codes"] = self.provider_codes
        return value


def require(condition, stage, reason):
    if not condition:
        raise Failure(stage, reason)


def classify(output):
    # Return a fixed category, never the matching text or arbitrary native output.
    for marker, reason in (
        (b"MAC verification failed", "P12_IMPORT_REJECTED"),
        (b"Unknown format in import", "P12_FORMAT_REJECTED"),
        (b"No profiles for", "PROFILE_MISSING"),
        (b"requires a provisioning profile", "PROFILE_MISSING"),
        (b"No signing certificate", "SIGNING_IDENTITY_MISSING"),
        (b"errSecInternalComponent", "KEYCHAIN_ACCESS_REJECTED"),
        (b"User interaction is not allowed", "KEYCHAIN_INTERACTION_REQUIRED"),
        (b"Could not resolve package dependencies", "DEPENDENCY_RESOLUTION_FAILED"),
        (b"Command PhaseScriptExecution failed", "BUILD_PHASE_FAILED"),
    ):
        if marker in output:
            return reason
    return "CLI_FAILED"


@contextmanager
def private_output():
    """Closing the spool must not erase an already-classified native failure."""
    stream = tempfile.TemporaryFile()
    primary = None
    try:
        yield stream
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            stream.close()
        except (Exception, KeyboardInterrupt):
            error = Failure("output_cleanup", "CLOSE_FAILED")
            if isinstance(primary, Failure):
                primary.cleanup_failures.append(error.public())
            elif primary is None:
                error.cleanup_failures.append(error.public())
                raise error from None


def command(stage, args, cwd, timeout=60, *, effect=None, private_home=None):
    """No shell/argv echo. Private unlinked spool; reap group before cleanup.

    Last 1 MiB is classified; unknown/truncated failures keep stage and exit code,
    not a guessed root cause. The ephemeral VM remains the cancellation backstop.
    """
    child_env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "FLUTTER_ROOT", "PUB_CACHE", "TMPDIR")
        if key in os.environ
    }
    child_env.update(
        DEVELOPER_DIR=DEVELOPER, LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8", CI="true"
    )
    if private_home is not None:
        child_env["HOME"] = child_env["TMPDIR"] = str(private_home)
    child = None
    timed_out = False
    group_absent = False
    with private_output() as output:
        try:
            child = subprocess.Popen(
                args,
                cwd=cwd,
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                **({"umask": 0o077} if os.name == "posix" else {}),
            )
            if effect is not None:
                effect["started"] = True
                effect["process_stopped"] = False
            try:
                child.wait(timeout=timeout)
                # Record the natural exit before reaping descendants/reading or
                # closing output. Later cleanup failures cannot erase this fact.
                if effect is not None:
                    effect["observed_exit"] = child.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                # Terminate any build descendants, including after parent failure.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        os.killpg(child.pid, 0)
                    except ProcessLookupError:
                        group_absent = True
                        if effect is not None:
                            effect["process_stopped"] = True
                        break
                    if time.monotonic() >= deadline:
                        raise Failure(stage, "PROCESS_UNRESOLVED", stopped=False)
                    time.sleep(0.05)
            require(not timed_out, stage, "CLI_TIMEOUT")
            size = output.tell()
            output.seek(max(0, size - 1048576))
            data = output.read(1048576)
            if child.returncode:
                codes = None
                if stage == "altool_upload":
                    codes = sorted(
                        {
                            code.decode("ascii")
                            for code in re.findall(rb"\bITMS-[0-9]{5}\b", data)
                        }
                    )[:10]
                raise Failure(
                    stage, classify(data), child.returncode, provider_codes=codes
                )
            # Metadata commands must never parse a truncated successful response.
            if stage not in {"archive", "export"}:
                require(size <= 1048576, stage, "OUTPUT_LIMIT")
            return data
        except Failure:
            raise
        except KeyboardInterrupt:
            # Popen or teardown may have been interrupted before obtaining a
            # reliable handle/group-absence observation. Never infer zero effect.
            raise Failure(
                stage,
                "CANCELLED" if group_absent else "PROCESS_UNRESOLVED",
                stopped=group_absent,
            ) from None
        except (OSError, subprocess.SubprocessError):
            raise Failure(
                stage,
                "PROCESS_UNRESOLVED" if child else "PROCESS_START_FAILED",
                stopped=child is None,
            ) from None


def validate_metadata(env):
    patterns = {
        "IOS_TEAM_ID": r"[A-Z0-9]{10}",
        "IOS_VERSION": r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}",
        "IOS_BUILD_NUMBER": r"[1-9][0-9]{0,8}",
        "IOS_API_BASE_URL": r"https://mobile-api-staging-(?:[a-z0-9]+-[a-z]{2}\.a|[0-9]+\.asia-east1)\.run\.app",
        "IOS_LINE_CHANNEL_ID": r"[0-9]{6,20}",
        "IOS_GOOGLE_CLIENT_ID": r"[A-Za-z0-9_-]{6,200}\.apps\.googleusercontent\.com",
        "IOS_GOOGLE_SERVER_CLIENT_ID": r"[A-Za-z0-9_-]{6,200}\.apps\.googleusercontent\.com",
    }
    for key, pattern in patterns.items():
        require(
            re.fullmatch(pattern, env.get(key, "")), key.lower(), "METADATA_INVALID"
        )
    require(
        env["IOS_GOOGLE_CLIENT_ID"] != env["IOS_GOOGLE_SERVER_CLIENT_ID"],
        "google_clients",
        "CLIENTS_MUST_DIFFER",
    )
    # Naming is only a guard. Main separately verifies the exact Cloud Run URL's
    # isolated project/service ownership before approving the Environment/run.
    return {key: env[key] for key in patterns}


def context(env):
    require(
        platform.system() == "Darwin"
        and env.get("RUNNER_ENVIRONMENT") == "github-hosted",
        "context",
        "HOST_REJECTED",
    )
    sha = env.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[a-f0-9]{40}", sha), "context", "SOURCE_REJECTED")
    expected = {
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "INPUT_APPROVED_SHA": sha,
        "GITHUB_WORKFLOW_REF": REPO
        + "/.github/workflows/ios-native-signing.yml@refs/heads/main",
    }
    require(
        all(env.get(key) == value for key, value in expected.items()),
        "context",
        "WORKFLOW_REJECTED",
    )
    require(
        env.get("ACTIONS_STEP_DEBUG", "false").lower() != "true"
        and env.get("RUNNER_DEBUG") != "1",
        "context",
        "DEBUG_REJECTED",
    )
    for key in ("GITHUB_WORKSPACE", "HOME", "RUNNER_TEMP"):
        require(
            bool(env.get(key)) and Path(env[key]).is_absolute(),
            "context",
            "PATH_REJECTED",
        )
    repo, home, temp = (
        Path(env[key]).resolve(strict=True)
        for key in ("GITHUB_WORKSPACE", "HOME", "RUNNER_TEMP")
    )
    require(
        command("checkout", ["/usr/bin/git", "rev-parse", "HEAD"], repo)
        .decode()
        .strip()
        == sha,
        "checkout",
        "SOURCE_REJECTED",
    )
    command("tracked_source", ["/usr/bin/git", "diff", "--quiet"], repo)
    command("staged_source", ["/usr/bin/git", "diff", "--cached", "--quiet"], repo)
    return repo, home, temp


class Baseline:
    def __init__(self, repo, home, temp, metadata, run=command):
        self.repo, self.home, self.temp = repo, home, temp
        self.app = repo / "clients/flutter_app"
        self.ios = self.app / "ios"
        self.root = temp / ROOT_NAME
        self.flutter_output = self.app / "build/native-signing"
        self.keychain = self.root / "signing.keychain-db"
        self.metadata, self.call = validate_metadata(metadata), run
        self.owned_files = []
        self.created = self.key_attempted = self.search_attempted = False
        self.saved_search = self.saved_default = None
        self.stage = "paths"
        self.process_stopped = True

    def paths(self):
        return [self.ios / name for name in CONFIGS] + [
            self.home / name / PROFILE_NAME for name in PROFILES
        ]

    def preflight(self):
        require(
            not self.root.exists() and not self.root.is_symlink(),
            "paths",
            "PATH_CONFLICT",
        )
        require(
            not self.flutter_output.exists() and not self.flutter_output.is_symlink(),
            "paths",
            "PATH_CONFLICT",
        )
        require(not self.flutter_output.parent.is_symlink(), "paths", "PATH_REJECTED")
        for path in self.paths():
            require(
                not path.exists() and not path.is_symlink(), "paths", "PATH_CONFLICT"
            )
            for parent in path.parents:
                require(not parent.is_symlink(), "paths", "PATH_REJECTED")

    def native(self, stage, args, timeout=60, cwd=None):
        self.stage = stage
        print(json.dumps({"stage": stage, "status": "STARTED"}), flush=True)
        try:
            return self.call(
                stage, [str(value) for value in args], cwd or self.app, timeout
            )
        except Failure as error:
            self.process_stopped = self.process_stopped and error.stopped
            raise

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            self.owned_files.append(path)
            path.chmod(0o600)
            stream.write(data)

    def decode(self, value, stage):
        require(
            isinstance(value, str) and 0 < len(value) <= 48000,
            stage,
            "SECRET_MISSING_OR_OVERSIZED",
        )
        try:
            return base64.b64decode(value, validate=True)
        except ValueError:
            raise Failure(stage, "BASE64_INVALID") from None

    def sign(self, material):
        p12 = self.decode(material.get(INPUT_NAMES[0]), "p12_input")
        profile_bytes = self.decode(material.get(INPUT_NAMES[2]), "profile_input")
        password = material.get(INPUT_NAMES[1])
        require(
            isinstance(password, str)
            and 0 < len(password) <= 1024
            and "\x00" not in password,
            "password_input",
            "PASSWORD_MISSING_OR_INVALID",
        )
        self.root.mkdir(mode=0o700)
        self.created = True
        self.saved_search = self.native(
            "search_snapshot", [SECURITY, "list-keychains", "-d", "user"]
        )
        self.saved_default = self.native(
            "default_snapshot", [SECURITY, "default-keychain", "-d", "user"]
        )
        original = shlex.split(self.saved_search.decode())
        require(
            bool(original) and all(PurePosixPath(p).is_absolute() for p in original),
            "search_snapshot",
            "SEARCH_LIST_INVALID",
        )
        key_password = secrets.token_urlsafe(32)
        self.key_attempted = True
        self.native(
            "keychain_create",
            [SECURITY, "create-keychain", "-p", key_password, self.keychain],
        )
        self.native(
            "keychain_settings",
            [SECURITY, "set-keychain-settings", "-lut", "3600", self.keychain],
        )
        self.native(
            "keychain_unlock",
            [SECURITY, "unlock-keychain", "-p", key_password, self.keychain],
        )
        p12_path, profile_path = (
            self.root / "distribution.p12",
            self.root / "profile.mobileprovision",
        )
        self.write(p12_path, p12)
        self.write(profile_path, profile_bytes)
        self.native(
            "p12_import",
            [
                SECURITY,
                "import",
                p12_path,
                "-k",
                self.keychain,
                "-P",
                password,
                "-T",
                "/usr/bin/codesign",
                "-t",
                "agg",
                "-f",
                "pkcs12",
            ],
        )
        # Native partition policy permits Apple tooling, not arbitrary apps. It
        # is not an executable sandbox and does not use the insecure -A option.
        self.native(
            "key_partition",
            [
                SECURITY,
                "set-key-partition-list",
                "-S",
                "apple-tool:,apple:",
                "-s",
                "-k",
                key_password,
                self.keychain,
            ],
        )
        p12_path.unlink()
        self.owned_files.remove(p12_path)
        decoded = self.native(
            "profile_decode",
            [SECURITY, "cms", "-D", "-k", self.keychain, "-i", profile_path],
        )
        try:
            profile = plistlib.loads(decoded)
        except Exception:
            raise Failure("profile_decode", "PROFILE_PLIST_INVALID") from None
        team = self.metadata["IOS_TEAM_ID"]
        require(
            isinstance(profile, dict) and profile.get("TeamIdentifier") == [team],
            "profile_binding",
            "TEAM_MISMATCH",
        )
        uuid = profile.get("UUID", "")
        require(
            isinstance(uuid, str)
            and re.fullmatch(
                r"[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}", uuid
            ),
            "profile_binding",
            "UUID_INVALID",
        )
        self.stage = "profile_binding"
        inspector._validate_signing_contract(
            profile.get("Entitlements", {}),
            profile,
            bundle_id=BUNDLE,
            now=datetime.now(timezone.utc),
        )
        require(
            profile["Entitlements"].get("com.apple.developer.team-identifier") == team,
            "profile_binding",
            "TEAM_MISMATCH",
        )
        certificates = profile.get("DeveloperCertificates")
        require(
            isinstance(certificates, list)
            and 0 < len(certificates) <= 20
            and all(isinstance(c, bytes) and c for c in certificates),
            "profile_binding",
            "CERTIFICATE_LIST_INVALID",
        )
        identities = self.native(
            "signing_identity",
            [SECURITY, "find-identity", "-v", "-p", "codesigning", self.keychain],
        )
        available = set(re.findall(rb'\d+\) ([A-Fa-f0-9]{40}) "', identities))
        matches = {hashlib.sha1(cert).hexdigest().upper() for cert in certificates} & {
            value.decode().upper() for value in available
        }
        require(len(matches) == 1, "signing_identity", "PROFILE_IDENTITY_NOT_UNIQUE")
        selector = matches.pop()
        self.search_attempted = True
        self.native(
            "search_install",
            [SECURITY, "list-keychains", "-d", "user", "-s", self.keychain, *original],
        )
        self.expected_profile = profile
        self.configure(profile_bytes, uuid, selector)
        common = [
            XCODE,
            "-workspace",
            self.ios / "Runner.xcworkspace",
            "-scheme",
            "Runner",
            "-configuration",
            "Release",
            "-sdk",
            "iphoneos",
            "-destination",
            "generic/platform=iOS",
            "-disableAutomaticPackageResolution",
            "-onlyUsePackageVersionsFromResolvedFile",
            "-clonedSourcePackagesDirPath",
            self.temp / "ntubtob-native-packages",
            "-derivedDataPath",
            self.root / "DerivedData",
        ]
        self.native(
            "archive",
            [*common, "-archivePath", self.root / "Runner.xcarchive", "archive"],
            1800,
        )
        self.native(
            "export",
            [
                XCODE,
                "-exportArchive",
                "-archivePath",
                self.root / "Runner.xcarchive",
                "-exportPath",
                self.root / "export",
                "-exportOptionsPlist",
                self.root / "ExportOptions.plist",
            ],
            600,
        )
        candidates = list((self.root / "export").glob("*.ipa"))
        require(
            len(candidates) == 1
            and candidates[0].is_file()
            and not candidates[0].is_symlink(),
            "export",
            "IPA_NOT_UNIQUE",
        )
        return candidates[0]

    def configure(self, profile, uuid, selector):
        self.stage = "config"
        defs = {
            "APP_FLAVOR": "staging",
            "CLIENT_MODE": "real",
            "RELEASE_SCOPE": "basic",
        }
        defs.update(
            {
                key: self.metadata["IOS_" + key]
                for key in (
                    "API_BASE_URL",
                    "LINE_CHANNEL_ID",
                    "GOOGLE_CLIENT_ID",
                    "GOOGLE_SERVER_CLIENT_ID",
                )
            }
        )
        values = {
            "IOS_DISTRIBUTION_CHANNEL": "testflight",
            "IOS_EXTERNAL_SIGNING_READY": "YES",
            "CODE_SIGN_STYLE": "Manual",
            "CODE_SIGN_IDENTITY": selector,
            "CODE_SIGN_IDENTITY[sdk=iphoneos*]": selector,
            "DEVELOPMENT_TEAM": self.metadata["IOS_TEAM_ID"],
            "PROVISIONING_PROFILE_SPECIFIER": uuid,
            "CODE_SIGN_ENTITLEMENTS": "Runner/Runner.entitlements",
            "FLUTTER_BUILD_NAME": self.metadata["IOS_VERSION"],
            "FLUTTER_BUILD_NUMBER": self.metadata["IOS_BUILD_NUMBER"],
            "FLUTTER_BUILD_DIR": "build/native-signing",
            "DART_DEFINES": ",".join(
                base64.b64encode((key + "=" + value).encode()).decode()
                for key, value in sorted(defs.items())
            ),
        }
        for directory in PROFILES:
            self.write(self.home / directory / PROFILE_NAME, profile)
        self.write(
            self.ios / CONFIGS[0],
            (
                "GOOGLE_REVERSED_CLIENT_ID="
                + ".".join(defs["GOOGLE_CLIENT_ID"].split(".")[::-1])
                + "\n"
            ).encode(),
        )
        self.write(
            self.ios / CONFIGS[1],
            "".join(key + "=" + value + "\n" for key, value in values.items()).encode(),
        )
        self.write(
            self.ios / CONFIGS[2],
            plistlib.dumps({"com.apple.developer.applesignin": ["Default"]}),
        )
        self.write(
            self.root / "ExportOptions.plist",
            plistlib.dumps(
                {
                    "method": "app-store-connect",
                    "destination": "export",
                    "signingStyle": "manual",
                    "signingCertificate": selector,
                    "teamID": self.metadata["IOS_TEAM_ID"],
                    "provisioningProfiles": {BUNDLE: uuid},
                    "manageAppVersionAndBuildNumber": False,
                    "uploadSymbols": False,
                }
            ),
        )

    def inspection_command(self, args, cwd):
        args = list(args)
        stage = (
            "inspect_signature" if args[0] == "/usr/bin/codesign" else "inspect_profile"
        )
        if args[:2] == [SECURITY, "cms"]:
            args += ["-k", str(self.keychain)]
        data = self.native(stage, args, cwd=cwd)
        if args[:2] == [SECURITY, "cms"]:
            decoded = inspector._embedded_plist(data, category="provisioning profile")
            require(
                decoded.get("UUID") == self.expected_profile["UUID"]
                and decoded.get("TeamIdentifier") == [self.metadata["IOS_TEAM_ID"]]
                and decoded.get("DeveloperCertificates")
                == self.expected_profile["DeveloperCertificates"],
                "inspect_profile",
                "EXPORTED_PROFILE_MISMATCH",
            )
        return inspector.ToolResult(0, data)

    def cleanup(self):
        errors = []
        if not self.process_stopped:
            return [Failure("cleanup", "PROCESS_UNRESOLVED").public()]

        def attempt(action):
            if not self.process_stopped:
                if not any(error["reason"] == "PROCESS_UNRESOLVED" for error in errors):
                    errors.append(Failure("cleanup", "PROCESS_UNRESOLVED").public())
                return
            try:
                action()
            except Failure as error:
                errors.append(error.public())
                errors.extend(error.cleanup_failures)
            except KeyboardInterrupt:
                self.process_stopped = False
                errors.append(Failure("cleanup", "CLEANUP_INTERRUPTED").public())
            except Exception:
                errors.append(Failure("cleanup", "CLEANUP_IO_FAILED").public())

        # Native create-keychain can itself alter search order, even if the
        # subsequent P12 import is rejected. Restore after ANY creation attempt.
        if self.key_attempted:
            attempt(
                lambda: self.native(
                    "search_restore",
                    [
                        SECURITY,
                        "list-keychains",
                        "-d",
                        "user",
                        "-s",
                        *shlex.split(self.saved_search.decode()),
                    ],
                )
            )

            def verify_search():
                require(
                    shlex.split(
                        self.native(
                            "search_verify", [SECURITY, "list-keychains", "-d", "user"]
                        ).decode()
                    )
                    == shlex.split(self.saved_search.decode()),
                    "search_verify",
                    "SEARCH_LIST_CHANGED",
                )

            attempt(verify_search)
        if self.key_attempted and self.keychain.exists():
            attempt(
                lambda: self.native(
                    "keychain_delete", [SECURITY, "delete-keychain", self.keychain]
                )
            )
            attempt(
                lambda: require(
                    not self.keychain.exists(), "keychain_delete", "KEYCHAIN_REMAINS"
                )
            )
        if self.saved_default is not None:
            attempt(
                lambda: require(
                    self.native(
                        "default_verify", [SECURITY, "default-keychain", "-d", "user"]
                    ).strip()
                    == self.saved_default.strip(),
                    "default_verify",
                    "DEFAULT_KEYCHAIN_CHANGED",
                )
            )
        for path in reversed(self.owned_files):
            attempt(path.unlink)
        if self.created and not errors:
            # Exact directory created exclusively by this invocation. Never a
            # user root, old journal, or glob. rmtree does not follow symlinks.
            attempt(lambda: shutil.rmtree(self.root))
            if self.flutter_output.exists():
                attempt(lambda: shutil.rmtree(self.flutter_output))
        return errors

    def run(self, material, *, upload_binding=None):
        failure = None
        command_cleanup_errors = []
        verified = False
        retained = None
        ready = False
        try:
            self.preflight()
            artifact = self.sign(material)
            self.stage = "inspect"
            inspection = inspector.inspect_ipa(
                artifact,
                expected_version=self.metadata["IOS_VERSION"],
                expected_build=int(self.metadata["IOS_BUILD_NUMBER"]),
                previous_build=0,
                mode="artifact-only",
                runner=self.inspection_command,
            )
            verified = True
            if upload_binding is not None:
                from tools import ios_native_upload as upload

                self.stage = "retain_snapshot"
                retained = upload.snapshot(artifact, inspection)
        except Failure as error:
            failure = error.public()
            command_cleanup_errors.extend(error.cleanup_failures)
        except KeyboardInterrupt:
            failure = Failure(self.stage, "CANCELLED").public()
        except inspector.CandidateError:
            failure = Failure(
                "inspect" if self.stage.startswith("inspect") else self.stage,
                "ARTIFACT_CONTRACT_REJECTED",
            ).public()
        except Exception:
            failure = Failure(self.stage, "UNEXPECTED_LOCAL_FAILURE").public()
        finally:
            try:
                cleanup_errors = self.cleanup()
            except KeyboardInterrupt:
                cleanup_errors = [Failure("cleanup", "CLEANUP_INTERRUPTED").public()]
            except Exception:
                cleanup_errors = [Failure("cleanup", "CLEANUP_IO_FAILED").public()]
        cleanup_errors = command_cleanup_errors + cleanup_errors
        signing_clean = not cleanup_errors
        if retained is not None and failure is None and signing_clean:
            try:
                upload.publish(self.temp, retained, upload_binding)
                ready = True
            except Failure as error:
                failure = error.public()
                cleanup_errors.extend(getattr(error, "cleanup_failures", []))
            except Exception:
                failure = Failure("retain_publish", "LOCAL_IO_FAILED").public()
        retained = None
        result = {
            "classification": (
                "SIGNED_BASELINE_VERIFIED"
                if verified and failure is None and not cleanup_errors
                else "STOP"
            ),
            "failure": failure,
            "cleanup_failures": cleanup_errors,
            "signature_verified": verified,
            "cleanup_verified": not cleanup_errors,
            "upload_attempted": False,
            "device_verified": False,
            "release_authorized": False,
            "next_action": (
                "REVIEW_UPLOAD_STAGE"
                if verified and not cleanup_errors
                else "READ_ONLY_REVIEW"
            ),
        }
        if upload_binding is not None:
            result.update(
                classification="SIGNED_COPY_READY" if ready else "STOP",
                signing_cleanup_verified=signing_clean,
                candidate_retained=ready,
                # This is signing cleanup only; IPA deliberately remains.
                cleanup_verified=False,
                next_action="NATIVE_UPLOAD" if ready else "READ_ONLY_REVIEW",
            )
        print(json.dumps(result, sort_keys=True), flush=True)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("preflight", "sign", "sign-for-upload", "audit")
    )
    args = parser.parse_args(argv)
    try:
        repo, home, temp = context(os.environ)
        if args.action == "audit":
            remaining = (
                (temp / ROOT_NAME).exists()
                or (repo / "clients/flutter_app/build/native-signing").exists()
                or any(
                    (repo / "clients/flutter_app/ios" / name).exists()
                    for name in CONFIGS
                )
                or any(
                    (home / directory / PROFILE_NAME).exists() for directory in PROFILES
                )
            )
            require(not remaining, "cleanup_audit", "OWNED_PATH_REMAINS")
            print('{"stage":"cleanup_audit","classification":"ABSENT"}')
            return 0
        baseline = Baseline(repo, home, temp, os.environ)
        baseline.preflight()
        require(
            command("xcode_version", [XCODE, "-version"], repo).strip()
            == b"Xcode 26.3\nBuild version 17C529",
            "xcode_version",
            "TOOLCHAIN_DRIFT",
        )
        if args.action == "preflight":
            print(
                '{"stage":"preflight","classification":"READY","secret_input_read":false}'
            )
            return 0
        # Remove secrets from inherited process environment before any native or
        # project command. Python cannot guarantee memory zeroization.
        material = {key: os.environ.pop(key, "") for key in INPUT_NAMES}
        upload_binding = None
        if args.action == "sign-for-upload":
            from tools import ios_native_upload as upload

            require(
                os.environ.get("IOS_UPLOAD_REQUESTED") == "true",
                "context",
                "UPLOAD_NOT_SELECTED",
            )
            upload_binding = upload.binding(os.environ)
            require(
                not (temp / upload.ROOT).exists(), "retain_publish", "PATH_CONFLICT"
            )
        return (
            0
            if baseline.run(material, upload_binding=upload_binding)["classification"]
            in {"SIGNED_BASELINE_VERIFIED", "SIGNED_COPY_READY"}
            else 2
        )
    except Failure as error:
        print(
            json.dumps(
                {
                    "classification": "STOP",
                    "failure": error.public(),
                    "next_action": "READ_ONLY_REVIEW",
                    "upload_attempted": False,
                }
            )
        )
    except Exception:
        print(
            '{"classification":"STOP","failure":{"stage":"entry","reason":"UNEXPECTED_LOCAL_FAILURE"},"next_action":"READ_ONLY_REVIEW"}'
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
