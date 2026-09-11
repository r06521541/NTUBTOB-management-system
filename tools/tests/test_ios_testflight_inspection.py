import hashlib
import io
import plistlib
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from asn1crypto import cms

from tools import ios_testflight_inspection as inspection


class InspectionTests(unittest.TestCase):
    def fixture(self):
        team = "FICTTEAM01"
        entitlements = {
            "application-identifier": team + "." + inspection.signing.BUNDLE,
            "com.apple.developer.team-identifier": team,
            "get-task-allow": False,
            "com.apple.developer.applesignin": ["Default"],
        }
        profile = cms.ContentInfo(
            {
                "content_type": "signed_data",
                "content": {
                    "version": "v1",
                    "digest_algorithms": [],
                    "encap_content_info": {
                        "content_type": "data",
                        "content": plistlib.dumps(
                            {
                                "DeveloperCertificates": [b"fictional-cert"],
                                "TeamIdentifier": [team],
                                "Entitlements": entitlements,
                                "ExpirationDate": datetime(2030, 1, 1),
                            }
                        ),
                    },
                    "signer_infos": [],
                },
            }
        ).dump()
        info = {
            "CFBundleIdentifier": inspection.signing.BUNDLE,
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1",
            "MinimumOSVersion": "15.0",
            "CFBundleExecutable": "Runner",
        }
        expected = dict(
            certificate_der=b"fictional-cert",
            profile=profile,
            team=team,
            version="1.0.0",
            build=1,
            now=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        return info, entitlements, profile, expected

    def test_binding_and_independent_mismatches(self):
        info, entitlements, profile, expected = self.fixture()
        inspection.bindings(info, entitlements, profile, b"fictional-cert", **expected)
        for key, value in (
            ("team", "OTHERTEAM1"),
            ("version", "2.0.0"),
            ("build", 2),
            ("certificate_der", b"other"),
            ("profile", b"other"),
        ):
            with self.subTest(key=key), self.assertRaises(Exception):
                inspection.bindings(
                    info,
                    entitlements,
                    profile,
                    b"fictional-cert",
                    **(expected | {key: value}),
                )

    def test_container_same_return_and_rejections(self):
        _, _, profile, _ = self.fixture()
        self.assertEqual(
            inspection.plist(inspection.signing._profile_container(profile))[
                "DeveloperCertificates"
            ],
            [b"fictional-cert"],
        )
        for bad in (
            b"bad",
            profile + b"x",
            cms.ContentInfo({"content_type": "data", "content": b"nested"}).dump(),
            cms.ContentInfo(
                {
                    "content_type": "encrypted_data",
                    "content": {
                        "version": "v0",
                        "encrypted_content_info": {
                            "content_type": "data",
                            "content_encryption_algorithm": {
                                "algorithm": "aes128_cbc",
                                "parameters": b"0" * 16,
                            },
                            "encrypted_content": b"x",
                        },
                    },
                }
            ).dump(),
        ):
            with self.assertRaises(Exception):
                inspection.signing._profile_container(bad)

    def test_archive_rules(self):
        for name in ("../escape", "/absolute", "Payload/App.app/link"):
            item = zipfile.ZipInfo(name)
            if name.endswith("link"):
                item.external_attr = 0o120777 << 16
            with self.assertRaises(Exception):
                inspection.archive_rules._safe_archive_entries([item])
        item = zipfile.ZipInfo("Payload/App.app/Info.plist")
        item.flag_bits = 1
        with self.assertRaises(Exception):
            inspection.archive_rules._safe_archive_entries([item])
        with self.assertRaises(zipfile.BadZipFile):
            zipfile.ZipFile(io.BytesIO(b"bad"))

    def test_fixed_native_contract(self):
        child = mock.Mock()
        child.stdout = io.BytesIO(b"bounded")
        child.returncode = 0
        with (
            mock.patch.object(
                inspection.subprocess, "Popen", return_value=child
            ) as launch,
            mock.patch.object(
                inspection.os, "killpg", side_effect=ProcessLookupError(), create=True
            ),
            mock.patch.object(inspection.signal, "SIGKILL", 9, create=True),
        ):
            self.assertEqual(
                inspection.run(
                    ["--verify", "--deep", "--strict", "/fictional"], "/fictional"
                ),
                b"bounded",
            )
        self.assertEqual(launch.call_args.args[0][0], "/usr/bin/codesign")
        self.assertEqual(launch.call_args.kwargs["env"], {"PATH": "/usr/bin:/bin"})
        child.wait.assert_called()

    def test_output_overflow_and_reap_failure(self):
        for oversized in (False, True):
            child = mock.Mock()
            child.stdout = io.BytesIO(
                b"x" * (inspection.OUTPUT + 1) if oversized else b""
            )
            child.returncode = 0
            with (
                mock.patch.object(inspection.subprocess, "Popen", return_value=child),
                mock.patch.object(
                    inspection.os,
                    "killpg",
                    side_effect=ProcessLookupError() if oversized else OSError(),
                    create=True,
                ),
                mock.patch.object(inspection.signal, "SIGKILL", 9, create=True),
            ):
                with self.assertRaises(
                    inspection.Rejected if oversized else inspection.Unresolved
                ):
                    inspection.run(["--verify"], "/fictional")

    def test_public_failure(self):
        value = inspection.inspect(
            None,
            expected_sha256="secret",
            certificate_der=b"secret",
            profile=b"secret",
            team="secret",
            version="1.0.0",
            build=1,
            previous_build=0,
            now=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(value["classification"], "STOP")
        self.assertNotIn("secret", repr(value))
        self.assertFalse(value["upload_authorized"])

    def test_certificate_output_set_rejected_before_read(self):
        tree = object.__new__(inspection.Tree)
        directory = mock.Mock()
        for names in (
            ("codesign1",),
            ("codesign0", "unexpected"),
            tuple("codesign" + str(i) for i in range(5)),
        ):
            directory.iterdir.return_value = [Path(n) for n in names]
            with (
                mock.patch.object(inspection.os, "open") as opening,
                self.assertRaises(inspection.Rejected),
            ):
                tree.adopt_certificates(directory)
            opening.assert_not_called()

    def test_cleanup_replacement_is_not_deleted(self):
        tree = object.__new__(inspection.Tree)
        path = mock.Mock()
        path.parts = ("fictional",)
        tree.entries = {path: (1, 2, 3, 4, 5)}
        with (
            mock.patch.object(inspection.os, "unlink") as unlink,
            self.assertRaises(inspection.Unresolved),
        ):
            tree.cleanup()
        unlink.assert_not_called()

    def test_cleanup_failure_overrides_rejection(self):
        _, _, profile, expected = self.fixture()
        root = mock.MagicMock()
        metadata = root.lstat.return_value
        metadata.st_dev = 1
        metadata.st_ino = 2
        metadata.st_uid = 7
        metadata.st_mode = 0o40700
        prepared = inspection.signing.PreparedSigning(
            Path("fictional"), root, "a" * 40, "b" * 64, (1, 2), "c" * 64
        )
        tree = mock.Mock()
        tree.cleanup.side_effect = OSError("fictional-private")
        with (
            mock.patch.object(inspection.platform, "system", return_value="Darwin"),
            mock.patch.object(inspection.signing, "_safe"),
            mock.patch.object(inspection.os, "getuid", return_value=7, create=True),
            mock.patch.object(inspection, "Tree", return_value=tree),
            mock.patch.object(inspection.os, "open", side_effect=OSError()),
        ):
            result = inspection.inspect(
                prepared, expected_sha256="a" * 64, previous_build=0, **expected
            )
        self.assertEqual(result["classification"], "CLEANUP_UNRESOLVED")
        self.assertFalse(result["cleanup_verified"])
        self.assertNotIn("fictional-private", repr(result))

    def test_source_confinement_contract(self):
        source = Path(inspection.__file__).read_text()
        self.assertNotIn('"/usr/bin/security"', source)
        self.assertNotIn("extractall", source)
        self.assertIn('root / "inspection"', source)
        self.assertIn("os.O_EXCL | os.O_NOFOLLOW", source)
        self.assertIn("umask=0o077", source)
        self.assertIn('"--extract-certificates"', source)

    def test_reaped_leader_does_not_prove_group_disappearance(self):
        child = mock.Mock()
        child.stdout = io.BytesIO(b"bounded")
        child.returncode = 0
        with (
            mock.patch.object(inspection.subprocess, "Popen", return_value=child),
            mock.patch.object(inspection.os, "killpg", create=True),
            mock.patch.object(inspection.signal, "SIGKILL", 9, create=True),
            mock.patch.object(inspection, "time") as clock,
        ):
            clock.monotonic.side_effect = [0, 6]
            with self.assertRaises(inspection.Unresolved):
                inspection.run(["--verify"], "/fictional")

    def test_full_synthetic_archive_reuses_existing_validators(self):
        for scenario in (
            "success",
            "expired",
            "minimum",
            "missing_executable",
            "unsafe_executable",
            "zero_major",
            "not_monotonic",
            "devices",
            "enterprise",
            "debug_absent",
            "debug_true",
        ):
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory() as folder,
            ):
                info, entitlements, profile, expected = self.fixture()
                if scenario == "minimum":
                    info["MinimumOSVersion"] = "14.0"
                if scenario == "unsafe_executable":
                    info["CFBundleExecutable"] = "../Runner"
                if scenario == "zero_major":
                    info["CFBundleShortVersionString"] = expected["version"] = "0.1.0"
                if scenario in {"expired", "devices", "enterprise"}:
                    container = cms.ContentInfo.load(profile)
                    payload = plistlib.loads(
                        container["content"]["encap_content_info"]["content"].native
                    )
                    if scenario == "expired":
                        payload["ExpirationDate"] = datetime(2020, 1, 1)
                    elif scenario == "devices":
                        payload["ProvisionedDevices"] = ["fictional"]
                    else:
                        payload["ProvisionsAllDevices"] = True
                    container["content"]["encap_content_info"]["content"] = (
                        plistlib.dumps(payload)
                    )
                    profile = expected["profile"] = container.dump()
                if scenario == "debug_absent":
                    entitlements.pop("get-task-allow")
                elif scenario == "debug_true":
                    entitlements["get-task-allow"] = True
                root = Path(folder).resolve()
                candidate = root / "candidate.ipa"
                with zipfile.ZipFile(candidate, "w") as archive:
                    archive.writestr(
                        "Payload/Runner.app/Info.plist", plistlib.dumps(info)
                    )
                    archive.writestr(
                        "Payload/Runner.app/embedded.mobileprovision", profile
                    )
                    if scenario != "missing_executable":
                        archive.writestr(
                            "Payload/Runner.app/Runner", b"fictional executable"
                        )
                metadata = root.stat()
                prepared = inspection.signing.PreparedSigning(
                    root,
                    root,
                    "a" * 40,
                    "b" * 64,
                    (metadata.st_dev, metadata.st_ino),
                    "c" * 64,
                )
                digest = hashlib.sha256(candidate.read_bytes()).hexdigest()

                def fake_codesign(arguments, cwd):
                    self.assertTrue(str(cwd).startswith(str(root / "inspection")))
                    return (
                        plistlib.dumps(entitlements)
                        if "--entitlements" in arguments
                        else b""
                    )

                # Windows tests exercise the whole ZIP/binding path, not POSIX
                # permissions, directory-fd cleanup or real codesign behavior.
                with (
                    mock.patch.object(
                        inspection.platform, "system", return_value="Darwin"
                    ),
                    mock.patch.object(
                        inspection.os,
                        "getuid",
                        return_value=metadata.st_uid,
                        create=True,
                    ),
                    mock.patch.object(
                        inspection.os,
                        "O_NOFOLLOW",
                        getattr(inspection.os, "O_NOFOLLOW", 0),
                        create=True,
                    ),
                    mock.patch.object(
                        inspection.stat,
                        "S_IMODE",
                        side_effect=lambda m: (
                            0o700 if inspection.stat.S_ISDIR(m) else 0o600
                        ),
                    ),
                    mock.patch.object(inspection, "run", side_effect=fake_codesign),
                    mock.patch.object(
                        inspection.Tree,
                        "adopt_certificates",
                        return_value=b"fictional-cert",
                    ),
                    mock.patch.object(
                        inspection.Tree,
                        "cleanup",
                        lambda tree: shutil.rmtree(tree.root),
                    ),
                ):
                    result = inspection.inspect(
                        prepared,
                        expected_sha256=digest,
                        previous_build=1 if scenario == "not_monotonic" else 0,
                        **expected,
                    )
                self.assertEqual(
                    result["classification"],
                    (
                        "ARTIFACT_BOUND"
                        if scenario in {"success", "debug_absent"}
                        else "STOP"
                    ),
                )
                self.assertTrue(result["cleanup_verified"])
                self.assertEqual(
                    hashlib.sha256(candidate.read_bytes()).hexdigest(), digest
                )
                self.assertFalse((root / "inspection").exists())


if __name__ == "__main__":
    unittest.main()
