from __future__ import annotations

import hashlib
import io
import secrets
import shutil
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from tools import mobile_release


ROOT = Path(__file__).resolve().parents[2]


def _contract_bytes(**overrides: str) -> bytes:
    values = {
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
        if signed:
            archive.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\n")
            archive.writestr("META-INF/RELEASE.SF", b"Signature-Version: 1.0\n")
            archive.writestr("META-INF/RELEASE.RSA", b"fictional-certificate")
    return output.getvalue()


class MobileReleaseConfigurationTests(unittest.TestCase):
    def test_candidate_configuration_is_strict_and_basic_only(self):
        values = mobile_release.validate_contract(
            {
                "schema": "1",
                "application_id": "tw.org.ntubtob.portal",
                "version_code": "42",
                "version_name": "1.2.3",
                "compile_sdk": "36",
                "target_sdk": "36",
                "app_flavor": "production",
                "client_mode": "real",
                "release_scope": "basic",
                "contract_test": "false",
                "api_origin": "https://api.unit-test-placeholder.net",
            },
            expected_mode="candidate",
        )
        self.assertEqual(values["application_id"], "tw.org.ntubtob.portal")

    def test_missing_mixed_or_debug_shaped_configuration_fails_closed(self):
        valid = dict(mobile_release.CONTRACT_TEST_VALUES)
        cases = (
            ("application_id", ""),
            ("application_id", "com.example.debug"),
            ("version_code", "0"),
            ("version_name", "0.0.0-debug"),
            ("compile_sdk", "35"),
            ("target_sdk", "35"),
            ("app_flavor", "development"),
            ("client_mode", "fake"),
            ("release_scope", "officer"),
            ("api_origin", "http://mobile-release.invalid"),
            ("api_origin", "https://127.0.0.1"),
            ("api_origin", "https://mobile-release.invalid:8443"),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                changed = dict(valid, **{key: value})
                with self.assertRaises(mobile_release.ContractError):
                    mobile_release.validate_contract(
                        changed, expected_mode="contract-test"
                    )

    def test_unknown_duplicate_and_cross_mode_values_fail_closed(self):
        with self.assertRaises(mobile_release.ContractError):
            mobile_release.parse_contract(
                _contract_bytes() + b"application_id=tw.org.ntubtob.portal\n"
            )
        with self.assertRaises(mobile_release.ContractError):
            mobile_release.parse_contract(_contract_bytes() + b"secret=value\n")
        with self.assertRaises(mobile_release.ContractError):
            mobile_release.validate_contract(
                dict(mobile_release.CONTRACT_TEST_VALUES), expected_mode="candidate"
            )

    def test_candidate_rejects_reserved_and_local_origins(self):
        valid = {
            "schema": "1",
            "application_id": "tw.org.ntubtob.portal",
            "version_code": "42",
            "version_name": "1.2.3",
            "compile_sdk": "36",
            "target_sdk": "36",
            "app_flavor": "production",
            "client_mode": "real",
            "release_scope": "basic",
            "contract_test": "false",
            "api_origin": "https://api.unit-test-placeholder.net",
        }
        for origin in (
            "https://localhost",
            "https://internal",
            "https://192.168.1.1",
            "https://mobile.example.org",
            "https://api.unit-test-placeholder.net:8443",
        ):
            with self.subTest(origin=origin), self.assertRaises(
                mobile_release.ContractError
            ):
                mobile_release.validate_contract(
                    dict(valid, api_origin=origin), expected_mode="candidate"
                )


class MobileReleaseArtifactTests(unittest.TestCase):
    def test_inspection_is_deterministic_and_reports_public_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "candidate.aab"
            artifact.write_bytes(_aab_bytes())
            first = mobile_release.inspect_aab(
                artifact,
                expected_mode="contract-test",
                expected_package="tw.org.ntubtob.portal.contracttest",
                expected_version_name="0.1.0",
                expected_version_code=1,
            )
            second = mobile_release.inspect_aab(
                artifact,
                expected_mode="contract-test",
                expected_package="tw.org.ntubtob.portal.contracttest",
                expected_version_name="0.1.0",
                expected_version_code=1,
            )
        self.assertEqual(first, second)
        self.assertEqual(first["sha256"], hashlib.sha256(_aab_bytes()).hexdigest())
        self.assertEqual(first["release_scope"], "basic")
        self.assertTrue(first["jar_signature_entries"])
        self.assertNotIn("api_origin", first)

    def test_archive_corruption_missing_signature_and_contract_drift_fail_closed(self):
        cases = (
            (b"not-a-zip", "not a readable AAB"),
            (_aab_bytes(signed=False), "JAR signature"),
            (_aab_bytes(_contract_bytes(target_sdk="35")), "target_sdk"),
        )
        for data, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                artifact = Path(directory) / "candidate.aab"
                artifact.write_bytes(data)
                with self.assertRaisesRegex(mobile_release.ContractError, message):
                    mobile_release.inspect_aab(
                        artifact,
                        expected_mode="contract-test",
                        expected_package="tw.org.ntubtob.portal.contracttest",
                        expected_version_name="0.1.0",
                        expected_version_code=1,
                    )

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
                    mobile_release.inspect_aab(
                        artifact,
                        expected_mode="contract-test",
                        expected_package="tw.org.ntubtob.portal.contracttest",
                        expected_version_name="0.1.0",
                        expected_version_code=1,
                    )

    def test_signer_verification_requires_expected_fingerprint(self):
        expected = "AB" * 32
        output = f"Certificate fingerprints:\n\t SHA256: {':'.join(expected[i:i+2] for i in range(0, 64, 2))}\n"
        self.assertEqual(
            mobile_release.parse_signer_sha256(output), expected.lower()
        )
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
            actual = mobile_release.verify_aab_signer(
                artifact,
                expected_sha256=expected,
                jarsigner=jarsigner,
                keytool=keytool,
            )
            inspected = mobile_release.inspect_aab(
                artifact,
                expected_mode="contract-test",
                expected_package="tw.org.ntubtob.portal.contracttest",
                expected_version_name="0.1.0",
                expected_version_code=1,
            )
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
    def test_android_gradle_contract_is_explicit(self):
        source = (ROOT / "clients/flutter_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "compileSdk = 36",
            "targetSdk = 36",
            "MOBILE_RELEASE_APPLICATION_ID",
            "MOBILE_RELEASE_KEYSTORE_PATH",
            "MOBILE_RELEASE_KEY_ALIAS",
            "MOBILE_RELEASE_STORE_PASSWORD",
            "MOBILE_RELEASE_KEY_PASSWORD",
            "mobile-release-contract.properties",
            'releaseScope = "basic"',
        ):
            self.assertIn(fragment, source)
        self.assertNotIn("signingConfigs.getByName(\"debug\")", source)

    def test_pubspec_has_explicit_android_version_code(self):
        source = (ROOT / "clients/flutter_app/pubspec.yaml").read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^version: [0-9]+\.[0-9]+\.[0-9]+\+[1-9][0-9]*$")

    def test_hosted_gate_builds_and_inspects_only_contract_test_aab(self):
        source = (ROOT / ".github/workflows/flutter-tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('"platforms;android-36"', source)
        self.assertIn("MOBILE_RELEASE_CONTRACT_TEST: \"true\"", source)
        self.assertIn("flutter build appbundle --release", source)
        self.assertIn("python3 -m tools.mobile_release inspect-aab", source)
        self.assertIn("tw.org.ntubtob.portal.contracttest", source)
        self.assertNotIn("play.google.com", source.lower())
        self.assertNotIn("upload-artifact", source)


if __name__ == "__main__":
    unittest.main()
