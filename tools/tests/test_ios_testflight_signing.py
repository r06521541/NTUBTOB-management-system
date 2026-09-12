"""Offline seams only; no signing material or native invocation."""

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import ios_testflight_signing as signing


class SigningTests(unittest.TestCase):
    def test_spm_receipt_and_conditional_pods(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder).resolve() / "app"
            root = Path(folder).resolve() / "root"
            for path, data in (
                (app / signing.MANIFEST, b"// fictional Package"),
                (app / "ios/Flutter/Generated.xcconfig", b"fictional"),
                (root / "SourcePackages/workspace-state.json", b"{}"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            original = signing._dependency_digest(app, root)
            self.assertEqual(len(original), 64)
            resolved = app / signing.RESOLVED[0]
            resolved.parent.mkdir(parents=True)
            resolved.write_bytes(b'{"pins":[]}')
            self.assertNotEqual(original, signing._dependency_digest(app, root))
            (app / "ios/Podfile").write_bytes(b"fictional")
            with self.assertRaises(Exception):
                signing._dependencies_ready(app)
            (app / "ios/Pods").mkdir()
            (app / "ios/Podfile.lock").write_bytes(b"one")
            (app / "ios/Pods/Manifest.lock").write_bytes(b"two")
            with self.assertRaises(Exception):
                signing._dependencies_ready(app)
            (app / "ios/Pods/Manifest.lock").write_bytes(b"one")
            signing._dependencies_ready(app)

    def test_resolver_fixed_paths_and_stop_proof(self):
        child = Mock()
        child.wait.return_value = 0
        root = Path("fictional/root")
        with (
            patch.object(signing.subprocess, "Popen", return_value=child) as launch,
            patch.object(
                signing.os,
                "killpg",
                side_effect=[None, ProcessLookupError()],
                create=True,
            ),
            patch.object(signing.signal, "SIGKILL", 9, create=True),
        ):
            signing._resolve(Path("fictional/app"), root)
        args = launch.call_args.args[0]
        self.assertEqual(
            args[args.index("-clonedSourcePackagesDirPath") + 1],
            str(root / "SourcePackages"),
        )
        self.assertEqual(
            args[args.index("-derivedDataPath") + 1], str(root / "DerivedData")
        )
        self.assertNotIn("-skipPackageSignatureValidation", args)
        self.assertEqual(launch.call_args.kwargs["stdin"], signing.subprocess.DEVNULL)
        with (
            patch.object(signing.subprocess, "Popen", return_value=child),
            patch.object(
                signing.os, "killpg", side_effect=PermissionError(), create=True
            ),
            patch.object(signing.signal, "SIGKILL", 9, create=True),
        ):
            with self.assertRaisesRegex(signing.Rejected, "CLEANUP_UNRESOLVED"):
                signing._resolve(Path("fictional/app"), root)

    def test_native_uses_same_cache_and_requires_receipt(self):
        source = (
            Path(__file__).parents[1] / "native/ios_testflight_signing.swift"
        ).read_text()
        self.assertIn(
            '"-clonedSourcePackagesDirPath",root.appendingPathComponent("SourcePackages").path',
            source,
        )
        self.assertIn('"-onlyUsePackageVersionsFromResolvedFile"', source)
        python = Path(signing.__file__).read_text()
        self.assertIn("not prepared.dependency_digest", python)

    def test_checkout_only_exact_untracked_resolved(self):
        for line, allowed in (
            (
                "?? clients/flutter_app/ios/Runner.xcworkspace/xcshareddata/swiftpm/Package.resolved",
                True,
            ),
            (
                " M clients/flutter_app/ios/Runner.xcworkspace/xcshareddata/swiftpm/Package.resolved",
                False,
            ),
            ("?? unrelated", False),
        ):
            with patch.object(
                signing, "_public", side_effect=[b"a" * 40, line.encode()]
            ):
                if allowed:
                    signing._checkout(Path("fictional"), "a" * 40)
                else:
                    with self.assertRaises(signing.Rejected):
                        signing._checkout(Path("fictional"), "a" * 40)

    def test_export_copy_exact_single_and_no_overwrite(self):
        import hashlib

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "export").mkdir()
            with self.assertRaises(signing.Rejected):
                signing._candidate(root)
            original = root / "export/NTUBTOB.ipa"
            original.write_bytes(b"fictional-ipa-bytes")

            def digest(path, *args, **kwargs):
                value = hashlib.sha256(path.read_bytes()).hexdigest()
                return (value, path.stat()) if kwargs.get("return_identity") else value

            with (
                patch.object(signing, "_private_digest", side_effect=digest),
                patch.object(
                    signing.os,
                    "O_NOFOLLOW",
                    getattr(signing.os, "O_NOFOLLOW", 0),
                    create=True,
                ),
            ):
                self.assertEqual(signing._candidate(root), digest(original))
                self.assertEqual(
                    (root / "candidate.ipa").read_bytes(), original.read_bytes()
                )
                with self.assertRaises(signing.Rejected):
                    signing._candidate(root)
            (root / "export/other.ipa").write_bytes(b"fictional-second")
            with self.assertRaises(signing.Rejected):
                signing._candidate(root)

    def test_export_copy_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "export").mkdir()
            (root / "export/App.ipa").write_bytes(b"fictional")
            with (
                patch.object(
                    signing,
                    "_private_digest",
                    return_value=("a" * 64, (root / "export/App.ipa").stat()),
                ),
                patch.object(
                    signing.os,
                    "O_NOFOLLOW",
                    getattr(signing.os, "O_NOFOLLOW", 0),
                    create=True,
                ),
                self.assertRaises(signing.Rejected),
            ):
                signing._candidate(root)
            self.assertTrue((root / "candidate.ipa").exists())

    def test_keychain_settings_before_import(self):
        source = (
            Path(__file__).parents[1] / "native/ios_testflight_signing.swift"
        ).read_text()
        self.assertIn("SecKeychainSetSettings(target, &settings)", source)
        self.assertIn("SecKeychainCopySettings(target, &observedSettings)", source)
        self.assertIn("observedSettings.lockInterval == 2400", source)
        self.assertLess(
            source.index("SecKeychainSetSettings(target"),
            source.index("SecPKCS12Import(p12"),
        )
        self.assertNotIn('appendingPathComponent("Runner.ipa")', source)

    def test_fixed_frame_and_private_representation(self):
        value = signing.frame(
            p12=b"fictional-p12",
            password=b"fictional-password",
            profile=b"fictional-profile",
            certificate_der=b"fictional-cert",
            team="FICTTEAM01",
            profile_uuid="00000000-0000-4000-8000-000000000001",
            version="1.2.3",
            build=123,
            build_defines={
                "API_BASE_URL": "https://fictional.invalid",
                "LINE_CHANNEL_ID": "123",
                "GOOGLE_CLIENT_ID": "123-fictional.apps.googleusercontent.com",
                "GOOGLE_SERVER_CLIENT_ID": "456-fictional.apps.googleusercontent.com",
            },
        )
        obj = json.loads(value)
        self.assertEqual(obj["build"], 123)
        self.assertNotIn("command", obj)
        self.assertLess(len(value), signing.MAX_FRAME)

    def test_reject_unknown_or_injected_inputs(self):
        base = dict(
            p12=b"x",
            password=b"x",
            profile=b"x",
            certificate_der=b"x",
            team="FICTTEAM01",
            profile_uuid="00000000-0000-4000-8000-000000000001",
            version="1.2.3",
            build=1,
            build_defines={
                "API_BASE_URL": "https://fictional.invalid",
                "LINE_CHANNEL_ID": "123",
                "GOOGLE_CLIENT_ID": "123-fictional.apps.googleusercontent.com",
                "GOOGLE_SERVER_CLIENT_ID": "456-fictional.apps.googleusercontent.com",
            },
        )
        for key, value in (
            ("team", "$(private)"),
            ("password", b"\xff"),
            ("p12", b"x" * 65537),
            ("build", True),
            ("version", "1\nBAD=YES"),
            ("build_defines", {"OTHER": "x"}),
        ):
            with self.subTest(key=key), self.assertRaises(signing.Rejected):
                signing.frame(**(base | {key: value}))

    def test_cleanup_dominates_and_schema(self):
        good = {"stage": "complete", "operation": "EXPORTED", "cleanup": "VERIFIED"}
        self.assertEqual(
            signing.decode_result(json.dumps(good).encode())["classification"],
            "EXPORTED_UNINSPECTED",
        )
        bad = good | {"cleanup": "UNRESOLVED"}
        self.assertEqual(
            signing.decode_result(json.dumps(bad).encode())["classification"],
            "CLEANUP_UNRESOLVED",
        )
        for obj in (
            good | {"private": "sentinel"},
            good | {"stage": "private-sentinel"},
            good | {"cleanup": True},
        ):
            with self.assertRaises(signing.Rejected):
                signing.decode_result(json.dumps(obj).encode())

    def test_source_contracts_no_automatic_or_unrestricted_access(self):
        source = (
            Path(__file__).parents[1] / "native" / "ios_testflight_signing.swift"
        ).read_text()
        for value in (
            "SecKeychainCopySearchList",
            "SecKeychainSetSearchList",
            "SecKeychainCopyDefault",
            "SecKeychainDelete",
            "SecPKCS12Import",
            "SecTrustedApplicationCreateFromPath",
            "POSIX_SPAWN_SETPGROUP",
            "O_EXCL",
            "UserData/Provisioning Profiles",
            "StoreReleaseConfig.xcconfig",
            "Runner.entitlements",
        ):
            self.assertIn(value, source)
        for value in (
            "-allowProvisioning",
            "SecKeychainSetDefault",
            "set-key-partition-list",
            "SecTrustSetAnchor",
            "security import",
            "-A",
        ):
            self.assertNotIn(value, source)

    def test_native_failure_timeout_and_bounded_output(self):
        prepared = signing.PreparedSigning(
            Path("/public/repo"),
            Path("/public/temp"),
            "a" * 40,
            "b" * 64,
            (1, 2),
            "c" * 64,
        )
        for status, output, timeout in (
            (1, b"", False),
            (0, b"x" * (signing.MAX_OUTPUT + 1), False),
            (0, b"", True),
        ):
            child = Mock()
            child.pid = 123
            child.stdin = io.BytesIO()
            child.stdout = io.BytesIO(output)
            child.returncode = status
            child.wait.side_effect = (
                [subprocess.TimeoutExpired("fixed", 1), 0] if timeout else [0, 0]
            )
            with (
                patch.object(signing.subprocess, "Popen", return_value=child) as launch,
                patch.object(signing.os, "killpg", create=True) as kill,
                patch.object(signing.signal, "SIGKILL", 9, create=True),
                self.assertRaises(signing.Rejected) as caught,
            ):
                signing._native(prepared, b"fictional-private-frame")
            self.assertEqual(str(caught.exception), "CLEANUP_UNRESOLVED")
            self.assertEqual(
                launch.call_args.kwargs["env"],
                {"PATH": "/usr/bin:/bin", "DEVELOPER_DIR": signing.DEVELOPER},
            )
            self.assertNotIn("fictional-private-frame", repr(launch.call_args))
            kill.assert_called_once()

    def test_schema_rejects_duplicate_and_inconsistent_success(self):
        for value in (
            b'{"stage":"complete","stage":"input","operation":"EXPORTED","cleanup":"VERIFIED"}',
            json.dumps(
                {"stage": "input", "operation": "EXPORTED", "cleanup": "VERIFIED"}
            ).encode(),
        ):
            with self.assertRaises(signing.Rejected):
                signing.decode_result(value)

    def test_prepared_and_platform_rejections_are_sanitized(self):
        with self.assertRaises(signing.Rejected):
            signing.sign("private-sentinel")
        with (
            patch.object(signing.platform, "system", return_value="Windows"),
            self.assertRaises(signing.Rejected) as caught,
        ):
            signing.prepare("private-sentinel", expected_commit="a" * 40)
        self.assertEqual(str(caught.exception), "PREPARE_REJECTED")

    def test_container_filter_is_not_a_signature_gate(self):
        from asn1crypto import cms

        # No signer or algorithm evidence: only a safe plaintext container shape.
        document = cms.ContentInfo(
            {
                "content_type": "signed_data",
                "content": {
                    "version": "v1",
                    "digest_algorithms": [],
                    "encap_content_info": {
                        "content_type": "data",
                        "content": b"fictional-not-yet-a-profile",
                    },
                    "signer_infos": [],
                },
            }
        )
        signing._profile_container(document.dump())
        for value in (
            document.dump() + b"tail",
            b"private-sentinel",
            cms.ContentInfo({"content_type": "data", "content": b"fictional"}).dump(),
        ):
            with self.assertRaises(signing.Rejected):
                signing._profile_container(value)

    def test_encrypted_and_nested_container_rejected(self):
        from asn1crypto import cms

        for kind in ("encrypted_data", "signed_data"):
            document = cms.ContentInfo(
                {
                    "content_type": "signed_data",
                    "content": {
                        "version": "v3",
                        "digest_algorithms": [],
                        "encap_content_info": {
                            "content_type": kind,
                        },
                        "signer_infos": [],
                    },
                }
            )
            with self.assertRaises(signing.Rejected):
                signing._profile_container(document.dump())

    def test_cleanup_source_contract_covers_partial_import(self):
        source = (
            Path(__file__).parents[1] / "native/ios_testflight_signing.swift"
        ).read_text()
        for marker in (
            "keyAttempted=true",
            "if keyAttempted && SecKeychainSetSearchList(savedList)",
            "CFEqual(intended,installed)",
            "rmdir(path.path)",
            "childUnresolved",
            "CMSDecoderCopyContent",
            'plist["UUID"] as? String == uuid',
        ):
            self.assertIn(marker, source)
        self.assertNotIn("CMSDecoderCopySignerStatus", source)
        self.assertLess(
            source.index("if childUnresolved { return false }"),
            source.index("SecKeychainDelete(target)"),
        )


if __name__ == "__main__":
    unittest.main()
