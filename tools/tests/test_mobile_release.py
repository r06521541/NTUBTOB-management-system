from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import shutil
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

from tools import mobile_release

ROOT = Path(__file__).resolve().parents[2]


def _contract_bytes(**overrides: str) -> bytes:
    values = {
        "schema": "2",
        "application_id": "tw.org.ntubtob.portal.contracttest",
        "version_code": "1",
        "version_name": "0.1.0",
        "compile_sdk": "36",
        "target_sdk": "36",
        "release_channel": "android-closed",
        "app_flavor": "staging",
        "client_mode": "real",
        "release_scope": "basic",
        "contract_test": "true",
        "api_origin_sha256": hashlib.sha256(
            b"https://mobile-release.invalid"
        ).hexdigest(),
        "provider_config_sha256": hashlib.sha256(
            b"12345\nandroid-contract.apps.googleusercontent.com\n"
            b"server-contract.apps.googleusercontent.com"
        ).hexdigest(),
        "previous_version_code": "0",
    }
    values.update(overrides)
    return "".join(f"{key}={values[key]}\n" for key in sorted(values)).encode()


def _aab_bytes(contract: bytes | None = None, *, signed: bool = True) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("BundleConfig.pb", b"bundle-config")
        archive.writestr(
            "base/manifest/AndroidManifest.xml",
            b"tw.org.ntubtob.portal.contracttest\x000.1.0",
        )
        archive.writestr("base/dex/classes.dex", b"dex\n")
        archive.writestr(
            "base/assets/mobile-release-contract.properties",
            contract if contract is not None else _contract_bytes(),
        )
        archive.writestr(
            "base/assets/flutter_assets/mobile-runtime-config.json",
            b'{"API_BASE_URL":"https://mobile-release.invalid",'
            b'"GOOGLE_CLIENT_ID":"android-contract.apps.googleusercontent.com",'
            b'"GOOGLE_SERVER_CLIENT_ID":"server-contract.apps.googleusercontent.com",'
            b'"LINE_CHANNEL_ID":"12345"}\n',
        )
        if signed:
            archive.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\n")
            archive.writestr("META-INF/RELEASE.SF", b"Signature-Version: 1.0\n")
            archive.writestr("META-INF/RELEASE.RSA", b"fictional-certificate")
    return output.getvalue()


def _bundle_metadata() -> mobile_release.BundleMetadata:
    return mobile_release.BundleMetadata(
        application_id="tw.org.ntubtob.portal.contracttest",
        version_name="0.1.0",
        version_code=1,
        min_sdk=24,
        target_sdk=36,
        compile_sdk=36,
    )


def _inspect_contract_test(artifact: Path) -> dict[str, object]:
    with mobile_release.snapshot_artifact(artifact) as snapshot:
        return mobile_release._inspect_snapshot(
            snapshot,
            _bundle_metadata(),
            expected_mode="contract-test",
            expected_package="tw.org.ntubtob.portal.contracttest",
            expected_version_name="0.1.0",
            expected_version_code=1,
            expected_previous_version_code=0,
            expected_api_origin_sha256=mobile_release.CONTRACT_TEST_VALUES[
                "api_origin_sha256"
            ],
            expected_provider_config_sha256=mobile_release.CONTRACT_TEST_VALUES[
                "provider_config_sha256"
            ],
        )


class MobileReleaseConfigurationTests(unittest.TestCase):
    def test_runtime_config_requires_exact_keys_and_matching_digests(self):
        contract = mobile_release.validate_contract(
            mobile_release.parse_contract(_contract_bytes()),
            expected_mode="contract-test",
        )
        valid = (
            b'{"API_BASE_URL":"https://mobile-release.invalid",'
            b'"GOOGLE_CLIENT_ID":"android-contract.apps.googleusercontent.com",'
            b'"GOOGLE_SERVER_CLIENT_ID":"server-contract.apps.googleusercontent.com",'
            b'"LINE_CHANNEL_ID":"12345"}\n'
        )
        mobile_release.validate_runtime_config(valid, contract)
        for changed in (
            valid.replace(b'"LINE_CHANNEL_ID"', b'"UNKNOWN"'),
            valid.replace(b'"12345"', b"12345"),
            valid.replace(b"12345", b"99999"),
            valid.replace(b"12345", b'12345","LINE_CHANNEL_ID":"12345'),
            valid.replace(b"https://", b"http://"),
            valid + b"x" * 8192,
            b"not-json",
        ):
            with (
                self.subTest(changed=changed),
                self.assertRaisesRegex(
                    mobile_release.ContractError,
                    "^runtime configuration (?:is invalid|does not match release contract)$",
                ),
            ):
                mobile_release.validate_runtime_config(changed, contract)

    def test_android_closed_configuration_is_staging_real_and_basic_only(self):
        values = mobile_release.validate_contract(
            {
                "schema": "2",
                "application_id": "tw.org.ntubtob.portal",
                "version_code": "42",
                "previous_version_code": "41",
                "version_name": "1.2.3",
                "compile_sdk": "36",
                "target_sdk": "36",
                "release_channel": "android-closed",
                "app_flavor": "staging",
                "client_mode": "real",
                "release_scope": "basic",
                "contract_test": "false",
                "api_origin_sha256": "ab" * 32,
                "provider_config_sha256": "cd" * 32,
            },
            expected_mode="android-closed",
        )
        self.assertEqual(values["application_id"], "tw.org.ntubtob.portal")
        self.assertEqual(values["release_channel"], "android-closed")
        self.assertEqual(values["app_flavor"], "staging")

    def test_missing_mixed_or_debug_shaped_configuration_fails_closed(self):
        valid = dict(mobile_release.CONTRACT_TEST_VALUES)
        cases = (
            ("application_id", ""),
            ("application_id", "com.example.debug"),
            ("version_code", "0"),
            ("version_name", "0.0.0-debug"),
            ("compile_sdk", "35"),
            ("target_sdk", "35"),
            ("release_channel", "production"),
            ("app_flavor", "development"),
            ("app_flavor", "production"),
            ("client_mode", "fake"),
            ("release_scope", "officer"),
            ("api_origin_sha256", "not-a-sha256"),
            ("provider_config_sha256", "not-a-sha256"),
            ("previous_version_code", "1"),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                changed = dict(valid, **{key: value})
                with self.assertRaises(mobile_release.ContractError):
                    mobile_release.validate_contract(
                        changed, expected_mode="contract-test"
                    )

    def test_unknown_duplicate_and_cross_mode_values_fail_closed(self):
        with self.assertRaisesRegex(
            mobile_release.ContractError, "release contract keys are duplicated"
        ) as duplicate:
            mobile_release.parse_contract(
                _contract_bytes() + b"application_id=tw.org.ntubtob.portal\n"
            )
        self.assertIsNone(duplicate.exception.__cause__)
        with self.assertRaisesRegex(
            mobile_release.ContractError, "release contract keys are invalid"
        ) as unknown:
            mobile_release.parse_contract(_contract_bytes() + b"secret=value\n")
        self.assertIsNone(unknown.exception.__cause__)
        self.assertNotIn("secret", str(unknown.exception))
        with self.assertRaises(mobile_release.ContractError):
            mobile_release.validate_contract(
                dict(mobile_release.CONTRACT_TEST_VALUES),
                expected_mode="android-closed",
            )

    def test_contract_parse_errors_are_fixed_categorical_messages(self):
        cases = (
            (b"\xff", "release contract encoding is invalid"),
            (b"malformed\n", "release contract structure is invalid"),
            (b"secret=value\n", "release contract keys are invalid"),
            (b"schema=\n", "release contract values are invalid"),
            (b"schema=2\n", "release contract keys are incomplete"),
        )
        for raw, message in cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(
                    mobile_release.ContractError, f"^{message}$"
                ) as raised,
            ):
                mobile_release.parse_contract(raw)
            self.assertIsNone(raised.exception.__cause__)

    def test_android_closed_requires_monotonic_version_and_origin_digest(self):
        valid = {
            "schema": "2",
            "application_id": "tw.org.ntubtob.portal",
            "version_code": "42",
            "previous_version_code": "41",
            "version_name": "1.2.3",
            "compile_sdk": "36",
            "target_sdk": "36",
            "release_channel": "android-closed",
            "app_flavor": "staging",
            "client_mode": "real",
            "release_scope": "basic",
            "contract_test": "false",
            "api_origin_sha256": "ab" * 32,
            "provider_config_sha256": "cd" * 32,
        }
        for overrides in (
            {"previous_version_code": "42"},
            {"previous_version_code": "43"},
            {"previous_version_code": "-1"},
            {"previous_version_code": "01"},
            {"api_origin_sha256": "AB" * 32},
            {"provider_config_sha256": "CD" * 32},
        ):
            with (
                self.subTest(overrides=overrides),
                self.assertRaises(mobile_release.ContractError),
            ):
                mobile_release.validate_contract(
                    dict(valid, **overrides), expected_mode="android-closed"
                )


class MobileReleaseArtifactTests(unittest.TestCase):
    def test_tampered_gradle_wrapper_component_fails_closed(self):
        source_root = ROOT / "clients/flutter_app/android"
        components = (
            "gradlew",
            "gradlew.bat",
            "gradle/wrapper/gradle-wrapper.jar",
            "gradle/wrapper/gradle-wrapper.properties",
        )
        for tampered in components:
            with (
                self.subTest(tampered=tampered),
                tempfile.TemporaryDirectory() as directory,
            ):
                repository_root = Path(directory)
                android_root = repository_root / "clients/flutter_app/android"
                for relative in components:
                    target = android_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_root / relative, target)
                target = android_root / tampered
                target.write_bytes(target.read_bytes() + b"\nSECRET-SENTINEL\n")

                with (
                    mock.patch.object(
                        mobile_release, "_REPOSITORY_ROOT", repository_root
                    ),
                    mock.patch.object(mobile_release, "_ANDROID_ROOT", android_root),
                ):
                    with self.assertRaisesRegex(
                        mobile_release.ContractError,
                        "^bundletool runner integrity is invalid$",
                    ):
                        mobile_release._gradle_wrapper()

    def test_bundletool_child_does_not_inherit_secret_or_option_environment(self):
        captured: dict[str, str] = {}
        captured_command: list[str] = []

        def completed_run(
            *args: object, **kwargs: object
        ) -> subprocess.CompletedProcess:
            captured_command.extend(args[0])  # type: ignore[arg-type]
            captured.update(kwargs["env"])  # type: ignore[arg-type]
            return subprocess.CompletedProcess(args[0], 0)  # type: ignore[index]

        inherited = {
            "CONTRACT_PASSWORD": "SECRET-SENTINEL",
            "GOOGLE_APPLICATION_CREDENTIALS": "SECRET-SENTINEL",
            "JAVA_TOOL_OPTIONS": "-javaagent:SECRET-SENTINEL",
            "GRADLE_OPTS": "-Dprovider=SECRET-SENTINEL",
            "MOBILE_RELEASE_STORE_PASSWORD": "SECRET-SENTINEL",
        }
        with (
            mock.patch.dict(os.environ, inherited),
            mock.patch(
                "tools.mobile_release.subprocess.run", side_effect=completed_run
            ),
        ):
            mobile_release._run_bundletool_task(
                "verifyCandidateBundle", Path("fictional-snapshot.aab")
            )

        for name in inherited.keys() - {"JAVA_TOOL_OPTIONS"}:
            self.assertNotIn(name, captured)
        self.assertEqual(captured["JAVA_TOOL_OPTIONS"], "-Dfile.encoding=UTF-8")
        self.assertNotIn("SECRET-SENTINEL", repr(captured))
        self.assertFalse(Path(captured_command[0]).exists())
        self.assertNotEqual(
            Path(captured_command[0]).parent,
            ROOT / "clients/flutter_app/android",
        )

    def test_unusable_runtime_environment_is_rejected_without_echo(self):
        with (
            mock.patch.dict(os.environ, {"JAVA_HOME": "SECRET-SENTINEL"}),
            self.assertRaisesRegex(
                mobile_release.ContractError,
                "^bundletool runtime environment is unavailable$",
            ) as raised,
        ):
            mobile_release._bundletool_environment()
        self.assertNotIn("SECRET-SENTINEL", str(raised.exception))

    def test_bundletool_manifest_parser_requires_exact_identity_and_sdk_metadata(self):
        manifest = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="tw.org.ntubtob.portal.contracttest"
    android:versionCode="1"
    android:versionName="0.1.0"
    android:compileSdkVersion="36">
  <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36" />
</manifest>
"""
        self.assertEqual(
            mobile_release.parse_bundletool_manifest(manifest),
            _bundle_metadata(),
        )
        for changed in (
            manifest.replace(' android:compileSdkVersion="36"', ""),
            manifest.replace(' android:targetSdkVersion="36"', ""),
            manifest.replace(' android:versionCode="1"', ' android:versionCode="01"'),
            "not XML",
        ):
            with (
                self.subTest(changed=changed),
                self.assertRaises(mobile_release.ContractError),
            ):
                mobile_release.parse_bundletool_manifest(changed)

    def test_inspection_is_deterministic_and_reports_public_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "candidate.aab"
            artifact.write_bytes(_aab_bytes())
            first = _inspect_contract_test(artifact)
            second = _inspect_contract_test(artifact)
        self.assertEqual(first, second)
        self.assertEqual(first["sha256"], hashlib.sha256(_aab_bytes()).hexdigest())
        self.assertEqual(first["release_scope"], "basic")
        self.assertEqual(first["release_channel"], "android-closed")
        self.assertEqual(first["previous_version_code"], 0)
        self.assertTrue(first["jar_signature_entries"])
        self.assertNotIn("api_origin", first)
        self.assertNotIn("provider_ids", first)

    def test_metadata_hash_and_signer_use_one_stable_snapshot(self):
        original = _aab_bytes()
        replacement = _aab_bytes(_contract_bytes(version_name="9.9.9"))
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "candidate.aab"
            artifact.write_bytes(original)
            observed_paths: list[Path] = []

            def metadata_reader(snapshot: Path) -> mobile_release.BundleMetadata:
                observed_paths.append(snapshot)
                artifact.write_bytes(replacement)
                self.assertEqual(snapshot.read_bytes(), original)
                return _bundle_metadata()

            def signer_reader(snapshot: Path, **_: object) -> str:
                observed_paths.append(snapshot)
                self.assertEqual(snapshot.read_bytes(), original)
                return "ef" * 32

            with (
                mock.patch.object(
                    mobile_release,
                    "read_bundletool_metadata",
                    side_effect=metadata_reader,
                ),
                mock.patch.object(
                    mobile_release,
                    "verify_aab_signer",
                    side_effect=signer_reader,
                ),
            ):
                result = mobile_release.inspect_and_verify_aab(
                    artifact,
                    expected_mode="contract-test",
                    expected_package="tw.org.ntubtob.portal.contracttest",
                    expected_version_name="0.1.0",
                    expected_version_code=1,
                    expected_previous_version_code=0,
                    expected_api_origin_sha256=(
                        mobile_release.CONTRACT_TEST_VALUES["api_origin_sha256"]
                    ),
                    expected_provider_config_sha256=(
                        mobile_release.CONTRACT_TEST_VALUES["provider_config_sha256"]
                    ),
                    expected_signer_sha256="ef" * 32,
                    jarsigner="unused",
                    keytool="unused",
                )
        self.assertEqual(observed_paths[0], observed_paths[1])
        self.assertNotEqual(observed_paths[0], artifact)
        self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(result["signer_sha256"], "ef" * 32)

    def test_archive_corruption_missing_signature_and_contract_drift_fail_closed(self):
        cases = (
            (b"not-a-zip", "not a readable AAB"),
            (_aab_bytes(signed=False), "JAR signature"),
            (
                _aab_bytes(_contract_bytes(target_sdk="35")),
                "fixed values do not match",
            ),
        )
        for data, message in cases:
            with (
                self.subTest(message=message),
                tempfile.TemporaryDirectory() as directory,
            ):
                artifact = Path(directory) / "candidate.aab"
                artifact.write_bytes(data)
                with self.assertRaisesRegex(mobile_release.ContractError, message):
                    _inspect_contract_test(artifact)

    def test_duplicate_traversal_sensitive_and_unexpected_files_fail_closed(self):
        cases: list[tuple[str, bytes]] = []
        for name in (
            "../escaped",
            "base/assets/release.jks",
            "base/assets/key.properties",
        ):
            stream = io.BytesIO(_aab_bytes())
            with zipfile.ZipFile(stream, "a") as archive:
                archive.writestr(name, b"forbidden")
            cases.append((name, stream.getvalue()))
        duplicate = io.BytesIO(_aab_bytes())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "a") as archive:
                archive.writestr("BundleConfig.pb", b"duplicate")
        cases.append(("duplicate", duplicate.getvalue()))

        for name, data in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                artifact = Path(directory) / "candidate.aab"
                artifact.write_bytes(data)
                with self.assertRaises(mobile_release.ContractError):
                    _inspect_contract_test(artifact)

    def test_signer_verification_requires_expected_fingerprint(self):
        expected = "AB" * 32
        output = f"Certificate fingerprints:\n\t SHA256: {':'.join(expected[i:i+2] for i in range(0, 64, 2))}\n"
        self.assertEqual(mobile_release.parse_signer_sha256(output), expected.lower())
        with self.assertRaises(mobile_release.ContractError):
            mobile_release.parse_signer_sha256("Owner: fictional")

    def test_fictional_external_signer_is_verified_end_to_end(self):
        keytool = shutil.which("keytool")
        jarsigner = shutil.which("jarsigner")
        if keytool is None or jarsigner is None:
            self.skipTest("JDK signing tools are unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "candidate.aab"
            key_store = root / "contract.jks"
            password = secrets.token_hex(16)
            artifact.write_bytes(_aab_bytes(signed=False))
            subprocess.run(
                [
                    keytool,
                    "-genkeypair",
                    "-noprompt",
                    "-keystore",
                    str(key_store),
                    "-storepass",
                    password,
                    "-keypass",
                    password,
                    "-alias",
                    "mobile-release-contract",
                    "-keyalg",
                    "RSA",
                    "-keysize",
                    "2048",
                    "-validity",
                    "2",
                    "-dname",
                    "CN=Fictional Contract Test,OU=CI Only,O=Invalid,C=ZZ",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            subprocess.run(
                [
                    jarsigner,
                    "-keystore",
                    str(key_store),
                    "-storepass",
                    password,
                    "-keypass",
                    password,
                    str(artifact),
                    "mobile-release-contract",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            certificate = subprocess.run(
                [keytool, "-printcert", "-jarfile", str(artifact)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            expected = mobile_release.parse_signer_sha256(certificate.stdout)
            with self.assertRaisesRegex(
                mobile_release.ContractError,
                "bundletool rejected the AAB",
            ):
                mobile_release.read_bundletool_metadata(artifact)
            actual = mobile_release.verify_aab_signer(
                artifact,
                expected_sha256=expected,
                jarsigner=jarsigner,
                keytool=keytool,
            )
            inspected = _inspect_contract_test(artifact)
            with zipfile.ZipFile(artifact, "a") as archive:
                archive.writestr("base/dex/classes2.dex", b"unsigned-extra-dex\n")
            with self.assertRaisesRegex(
                mobile_release.ContractError,
                "strictly verify",
            ):
                mobile_release.verify_aab_signer(
                    artifact,
                    expected_sha256=expected,
                    jarsigner=jarsigner,
                    keytool=keytool,
                )
        self.assertEqual(actual, expected)
        self.assertTrue(inspected["jar_signature_entries"])


class MobileReleaseRepositoryContractTests(unittest.TestCase):
    def test_android_bundletool_runner_is_pinned_and_bounded(self):
        source = (ROOT / "clients/flutter_app/android/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        for fragment in (
            '"com.android.tools.build:bundletool:1.18.3"',
            'mainClass.set("com.android.tools.build.bundletool.BundleToolMain")',
            'tasks.register<JavaExec>("verifyCandidateBundle")',
            'configureMobileReleaseBundletool("validate")',
            'tasks.register<JavaExec>("dumpCandidateManifest")',
            'configureMobileReleaseBundletool("dump", "manifest")',
        ):
            self.assertIn(fragment, source)
        tool = (ROOT / "tools/mobile_release.py").read_text(encoding="utf-8")
        self.assertIn('"--offline"', tool)
        self.assertIn('"-Dfile.encoding=UTF-8"', tool)
        self.assertIn('"JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8"', tool)
        self.assertNotIn("os.environ.copy()", tool)
        self.assertNotIn('os.environ.get("JAVA_TOOL_OPTIONS"', tool)
        for (
            relative,
            expected,
        ) in mobile_release._GRADLE_WRAPPER_COMPONENT_SHA256.items():
            self.assertTrue((ROOT / "clients/flutter_app/android" / relative).is_file())
            self.assertIn(expected, tool)
        android_ignore = (ROOT / "clients/flutter_app/android/.gitignore").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("gradle-wrapper.jar", android_ignore)
        self.assertNotIn("/gradlew", android_ignore)
        self.assertIn("_BUNDLETOOL_TIMEOUT_SECONDS", tool)
        self.assertNotIn("apkanalyzer", tool.lower())

    def test_duplicate_dart_define_error_does_not_echo_decoded_key(self):
        encoded = ",".join(
            base64.b64encode(value).decode("ascii")
            for value in (b"SECRET-SENTINEL=one", b"SECRET-SENTINEL=two")
        )
        environment = mobile_release._bundletool_environment()
        environment.update(
            {
                "MOBILE_RELEASE_CONTRACT_TEST": "true",
                "MOBILE_RELEASE_CHANNEL": "android-closed",
                "MOBILE_RELEASE_APPLICATION_ID": ("tw.org.ntubtob.portal.contracttest"),
                "MOBILE_RELEASE_VERSION_NAME": "0.1.0",
                "MOBILE_RELEASE_VERSION_CODE": "1",
                "MOBILE_RELEASE_PREVIOUS_VERSION_CODE": "0",
            }
        )
        with mobile_release._snapshot_gradle_wrapper() as wrapper:
            completed = subprocess.run(
                [
                    str(wrapper),
                    "--offline",
                    "--no-daemon",
                    "-q",
                    "helpRelease",
                    "-Pmobile-release-private-mode=contract-test",
                    f"-Pdart-defines={encoded}",
                ],
                cwd=mobile_release._ANDROID_ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=120,
                input=(
                    "https://mobile-release.invalid\n12345\n"
                    "android-contract.apps.googleusercontent.com\n"
                    "server-contract.apps.googleusercontent.com\n"
                    f"{Path(tempfile.gettempdir()) / 'mobile-release-contract.jks'}\n"
                    "mobile-release-contract\nfictional-password\n"
                    "fictional-password\n"
                ),
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("dart-defines contain duplicate entries", completed.stdout)
        self.assertNotIn("SECRET-SENTINEL", completed.stdout)

    def test_android_gradle_contract_is_explicit(self):
        source = (ROOT / "clients/flutter_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "compileSdk = 36",
            "targetSdk = 36",
            "MOBILE_RELEASE_CHANNEL",
            "MOBILE_RELEASE_APPLICATION_ID",
            "MOBILE_RELEASE_PREVIOUS_VERSION_CODE",
            "MOBILE_RELEASE_STAGING_API_ORIGIN_SHA256",
            "MOBILE_RELEASE_STAGING_PROVIDER_CONFIG_SHA256",
            "mobile-release-private-mode",
            "private release input contract is invalid",
            "mobile-release-contract.properties",
            "mobile-runtime-config.json",
            'releaseScope = "basic"',
            'requiredDefine("APP_FLAVOR") != "staging"',
            'requiredDefine("RELEASE_CHANNEL") != releaseChannel',
        ):
            self.assertIn(fragment, source)
        self.assertNotIn('signingConfigs.getByName("debug")', source)
        for forbidden in (
            "MOBILE_RELEASE_KEYSTORE_PATH",
            "MOBILE_RELEASE_KEY_ALIAS",
            "MOBILE_RELEASE_STORE_PASSWORD",
            "MOBILE_RELEASE_KEY_PASSWORD",
            'requiredDefine("API_BASE_URL")',
            'requiredDefine("LINE_CHANNEL_ID")',
            'requiredDefine("GOOGLE_CLIENT_ID")',
            'requiredDefine("GOOGLE_SERVER_CLIENT_ID")',
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("APP_FLAVOR must be production", source)
        self.assertIn('throw GradleException("API_BASE_URL is malformed")', source)
        self.assertNotIn('GradleException("API_BASE_URL is malformed",', source)
        self.assertNotIn(
            'GradleException("dart-defines contain malformed base64",', source
        )
        self.assertIn(
            'GradleException("dart-defines contain duplicate entries")', source
        )
        self.assertNotIn("dart-defines contain duplicate $key", source)

    def test_android_generated_contract_uses_variant_sources_api(self):
        source = (ROOT / "clients/flutter_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "abstract class GenerateMobileReleaseContract : DefaultTask()",
            "@get:OutputDirectory",
            "androidComponents",
            'selector().withBuildType("release")',
            "variant.sources.assets",
            "addGeneratedSourceDirectory(",
            "GenerateMobileReleaseContract::outputDirectory",
            "GenerateMobileRuntimeConfig::outputDirectory",
            "outputs.upToDateWhen { false }",
            "outputs.cacheIf { false }",
        ):
            self.assertIn(fragment, source)
        self.assertNotIn('sourceSets.getByName("release").assets.srcDir', source)
        self.assertNotIn('it.name == "mergeReleaseAssets"', source)
        self.assertNotIn("android.sourceset.disallowProvider", source)

    def test_android_release_accepts_only_pinned_flutter_metadata_defines(self):
        source = (ROOT / "clients/flutter_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        for key in (
            "FLUTTER_BUILD_NAME",
            "FLUTTER_BUILD_NUMBER",
            "FLUTTER_VERSION",
            "FLUTTER_CHANNEL",
            "FLUTTER_GIT_URL",
            "FLUTTER_FRAMEWORK_REVISION",
            "FLUTTER_ENGINE_REVISION",
            "FLUTTER_DART_VERSION",
        ):
            self.assertIn(f'"{key}"', source)
        self.assertIn(
            "defines.keys != requiredReleaseDefines + flutterBuildDefines + flutterMetadataDefines",
            source,
        )
        self.assertIn(
            'requiredDefine("FLUTTER_BUILD_NAME") != expectedVersionName', source
        )
        self.assertIn(
            'requiredDefine("FLUTTER_BUILD_NUMBER") != expectedVersionCode', source
        )
        self.assertIn('defines["FLUTTER_VERSION"] != "3.47.0"', source)
        self.assertIn('defines["FLUTTER_CHANNEL"] != "stable"', source)
        self.assertIn(
            'defines["FLUTTER_GIT_URL"] != "https://github.com/flutter/flutter.git"',
            source,
        )
        self.assertIn('Regex("^[0-9a-f]{10}$")', source)
        self.assertIn('requiredDefine("FLUTTER_DART_VERSION")', source)
        self.assertNotIn('"FLUTTER_APP_FLAVOR"', source)
        self.assertNotIn('"FLUTTER_ENABLED_FEATURE_FLAGS"', source)

    def test_pubspec_has_explicit_android_version_code(self):
        source = (ROOT / "clients/flutter_app/pubspec.yaml").read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^version: [0-9]+\.[0-9]+\.[0-9]+\+[1-9][0-9]*$")

    def test_line_sdk_uses_immutable_official_ios_15_release(self):
        expected_revision = "c48b87b430f2d0c7b50926d04cc4de8050ad413a"
        pubspec = (ROOT / "clients/flutter_app/pubspec.yaml").read_text(
            encoding="utf-8"
        )
        lock = (ROOT / "clients/flutter_app/pubspec.lock").read_text(encoding="utf-8")
        self.assertIn("url: https://github.com/line/flutter_line_sdk.git", pubspec)
        self.assertIn(f"ref: {expected_revision}", pubspec)
        self.assertIn(f"resolved-ref: {expected_revision}", lock)
        self.assertIn('version: "3.0.0"', lock)

    def test_hosted_gate_builds_and_inspects_only_contract_test_aab(self):
        source = (ROOT / ".github/workflows/flutter-tests.yml").read_text(
            encoding="utf-8"
        )
        android_source = source.partition("\n  ios_compile_contract:\n")[0]
        for fragment in (
            '"${ANDROID_SDK_ROOT:-}"',
            '"${ANDROID_HOME:-}"',
            '"/usr/local/lib/android/sdk"',
            'realpath -e "$candidate"',
            '"$sdkmanager_path" --sdk_root="$sdk_root" "platforms;android-36"',
            "Android sdkmanager was not found in approved SDK roots",
            "Android API 36 installation was not materialized",
        ):
            self.assertIn(fragment, source)
        self.assertNotIn('run: sdkmanager "platforms;android-36"', source)
        self.assertNotIn("curl ", source)
        self.assertNotIn("wget ", source)
        self.assertNotIn("flutter create", source)
        self.assertNotIn("gradle wrapper", source)
        self.assertIn('MOBILE_RELEASE_CONTRACT_TEST: "true"', source)
        self.assertIn("MOBILE_RELEASE_CHANNEL: android-closed", source)
        self.assertIn('MOBILE_RELEASE_PREVIOUS_VERSION_CODE: "0"', source)
        self.assertEqual(
            source.count("--dart-define=RELEASE_CHANNEL=android-closed"), 1
        )
        self.assertEqual(android_source.count("--dart-define=APP_FLAVOR=staging"), 1)
        self.assertNotIn("--dart-define=APP_FLAVOR=production", source)
        self.assertIn("tools.tests.test_android_closed_testing", source)
        self.assertIn("tools.tests.test_android_candidate_operator", source)
        self.assertIn(
            "python3 -m tools.android_candidate_operator contract-test-build", source
        )
        self.assertIn("flutter build appbundle --release", source)
        self.assertIn("python3 -m tools.mobile_release inspect-aab", source)
        self.assertIn("bundletool", source.lower())
        self.assertLess(
            source.index("Build signed contract-test Android App Bundle"),
            source.index("Run mobile release tooling tests"),
        )
        self.assertIn("--expected-previous-version-code 0", source)
        self.assertIn("--expected-staging-api-origin-sha256", source)
        self.assertIn("--expected-staging-provider-config-sha256", source)
        self.assertIn("tw.org.ntubtob.portal.contracttest", source)
        self.assertNotIn("play.google.com", source.lower())
        self.assertNotIn("upload-artifact", source)


if __name__ == "__main__":
    unittest.main()
