from __future__ import annotations

import io
import plistlib
import stat
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tools import ios_candidate_inspector as inspector

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def _plist(**overrides: object) -> bytes:
    values: dict[str, object] = {
        "CFBundleIdentifier": inspector.EXPECTED_BUNDLE_ID,
        "CFBundleShortVersionString": "1.2.3",
        "CFBundleVersion": "42",
        "MinimumOSVersion": "15.0",
        "CFBundleExecutable": "Runner",
    }
    values.update(overrides)
    return plistlib.dumps(values)


def _ipa_bytes(
    *,
    info: bytes | None = None,
    omit: str | None = None,
    extra_entries: tuple[tuple[str, bytes], ...] = (),
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        entries = {
            "Payload/Runner.app/Info.plist": info or _plist(),
            "Payload/Runner.app/Runner": b"fictional-executable",
            "Payload/Runner.app/embedded.mobileprovision": b"fictional-profile",
            "Payload/Runner.app/_CodeSignature/CodeResources": b"fictional-signature",
        }
        for name, value in extra_entries:
            entries[name] = value
        for name, value in entries.items():
            if name == omit:
                continue
            entry = zipfile.ZipInfo(name)
            entry.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(entry, value)
    return output.getvalue()


def _entitlements(**overrides: object) -> dict[str, object]:
    team = "FICTIONALTEAM"
    values: dict[str, object] = {
        "application-identifier": f"{team}.{inspector.EXPECTED_BUNDLE_ID}",
        "com.apple.developer.team-identifier": team,
        "com.apple.developer.applesignin": ["Default"],
    }
    values.update(overrides)
    return values


def _profile(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ExpirationDate": NOW + timedelta(days=30),
        "Entitlements": dict(_entitlements(), **{"get-task-allow": False}),
    }
    values.update(overrides)
    return values


def _runner(
    *,
    signature_code: int = 0,
    entitlements: dict[str, object] | None = None,
    profile: dict[str, object] | None = None,
) -> inspector.ToolRunner:
    def run(command: list[str] | tuple[str, ...], _cwd: Path) -> inspector.ToolResult:
        if command[:2] == ["/usr/bin/codesign", "--verify"]:
            return inspector.ToolResult(signature_code)
        if command[:2] == ["/usr/bin/codesign", "--display"]:
            return inspector.ToolResult(
                0,
                stderr=b"Executable=redacted\n"
                + plistlib.dumps(entitlements or _entitlements()),
            )
        if command[:2] == ["/usr/bin/security", "cms"]:
            return inspector.ToolResult(0, stdout=plistlib.dumps(profile or _profile()))
        raise AssertionError("unexpected inspection command")

    return run


class IOSCandidateInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifact = self.root / "candidate.ipa"
        self.artifact.write_bytes(_ipa_bytes())
        self.ready_contract = self.root / "StoreReleaseContract.xcconfig"
        self.ready_contract.write_text(
            "APPLE_SIGN_IN_REPOSITORY_STATUS = ready\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inspect(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "expected_version": "1.2.3",
            "expected_build": 42,
            "previous_build": 41,
            "mode": "contract-test",
            "runner": _runner(),
            "readiness_contract": self.ready_contract,
            "now": NOW,
        }
        values.update(overrides)
        return inspector.inspect_ipa(self.artifact, **values)  # type: ignore[arg-type]

    def test_fictional_signed_candidate_is_deidentified(self) -> None:
        result = self.inspect()
        self.assertEqual(result["classification"], "CONTRACT_TEST")
        self.assertEqual(result["version"], "1.2.3")
        self.assertEqual(result["build"], 42)
        self.assertTrue(result["signature_verified"])
        self.assertFalse(result["provider_runtime_verified"])
        rendered = str(result)
        for prohibited in (
            "FICTIONALTEAM",
            inspector.EXPECTED_BUNDLE_ID,
            "embedded.mobileprovision",
            "CodeResources",
        ):
            self.assertNotIn(prohibited, rendered)

    def test_actual_candidate_is_blocked_by_committed_repository_marker(self) -> None:
        with self.assertRaisesRegex(
            inspector.CandidateError, "^repository Apple readiness is blocked$"
        ):
            inspector.inspect_ipa(
                self.artifact,
                expected_version="1.2.3",
                expected_build=42,
                previous_build=41,
                mode="testflight",
                runner=_runner(),
            )

    def test_actual_candidate_can_only_continue_with_exact_ready_marker(self) -> None:
        result = self.inspect(mode="testflight")
        self.assertEqual(result["classification"], "PASS")
        for source in (
            "APPLE_SIGN_IN_REPOSITORY_STATUS = unknown\n",
            "APPLE_SIGN_IN_REPOSITORY_STATUS = ready\n"
            "APPLE_SIGN_IN_REPOSITORY_STATUS = ready\n",
            "",
        ):
            with self.subTest(source=source):
                self.ready_contract.write_text(source, encoding="utf-8")
                with self.assertRaises(inspector.CandidateError):
                    self.inspect(mode="testflight")

    def test_metadata_and_signed_application_drift_fail_closed(self) -> None:
        cases = (
            (
                _ipa_bytes(info=_plist(CFBundleIdentifier="example.invalid")),
                "bundle identity",
            ),
            (_ipa_bytes(info=_plist(CFBundleVersion="41")), "build number"),
            (_ipa_bytes(info=_plist(MinimumOSVersion="14.9")), "minimum iOS"),
            (_ipa_bytes(omit="Payload/Runner.app/Runner"), "executable"),
            (
                _ipa_bytes(omit="Payload/Runner.app/embedded.mobileprovision"),
                "signed application data",
            ),
            (
                _ipa_bytes(omit="Payload/Runner.app/_CodeSignature/CodeResources"),
                "signed application data",
            ),
        )
        for source, reason in cases:
            with self.subTest(reason=reason):
                self.artifact.write_bytes(source)
                with self.assertRaisesRegex(inspector.CandidateError, reason):
                    self.inspect()

    def test_signature_profile_and_entitlement_drift_fail_closed(self) -> None:
        cases = (
            (_runner(signature_code=1), "signature verification"),
            (
                _runner(
                    profile=_profile(
                        Entitlements=dict(_entitlements(), **{"get-task-allow": True})
                    )
                ),
                "development provisioning profile",
            ),
            (
                _runner(profile=_profile(ProvisionedDevices=["fictional-device"])),
                "distribution-only",
            ),
            (
                _runner(profile=_profile(ExpirationDate=NOW - timedelta(seconds=1))),
                "expired",
            ),
            (
                _runner(
                    entitlements=_entitlements(**{"application-identifier": "mixed"})
                ),
                "identity categories",
            ),
            (
                _runner(
                    entitlements=_entitlements(
                        **{"com.apple.developer.applesignin": ["Default", "Extra"]}
                    )
                ),
                "application Apple entitlement",
            ),
            (
                _runner(
                    profile=_profile(
                        Entitlements=dict(
                            _entitlements(**{"com.apple.developer.applesignin": []}),
                            **{"get-task-allow": False},
                        )
                    )
                ),
                "profile Apple entitlement",
            ),
        )
        for runner, reason in cases:
            with (
                self.subTest(reason=reason),
                self.assertRaisesRegex(inspector.CandidateError, reason),
            ):
                self.inspect(runner=runner)

    def test_unsafe_duplicate_encrypted_symlink_and_multiple_apps_fail(self) -> None:
        cases: list[tuple[bytes, str]] = [
            (
                _ipa_bytes(extra_entries=(("Payload/Runner.app/../escape", b"x"),)),
                "unsafe entry path",
            ),
            (
                _ipa_bytes(extra_entries=(("Payload/Other.app/Info.plist", _plist()),)),
                "exactly one application",
            ),
        ]
        duplicate = io.BytesIO()
        with zipfile.ZipFile(duplicate, "w") as archive:
            with mock.patch("warnings.warn"):
                archive.writestr("Payload/Runner.app/Info.plist", _plist())
                archive.writestr("Payload/Runner.app/Info.plist", _plist())
        cases.append((duplicate.getvalue(), "duplicate entries"))

        symlink = io.BytesIO()
        with zipfile.ZipFile(symlink, "w") as archive:
            entry = zipfile.ZipInfo("Payload/Runner.app/link")
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, b"target")
            archive.writestr("Payload/Runner.app/Info.plist", _plist())
        cases.append((symlink.getvalue(), "non-regular entry"))

        for source, reason in cases:
            with self.subTest(reason=reason):
                self.artifact.write_bytes(source)
                with self.assertRaisesRegex(inspector.CandidateError, reason):
                    self.inspect()

    def test_archive_encryption_and_uncompressed_limit_are_rejected(self) -> None:
        encrypted = zipfile.ZipInfo("Payload/Runner.app/Info.plist")
        encrypted.flag_bits = 0x1
        with self.assertRaisesRegex(inspector.CandidateError, "encrypted entry"):
            inspector._safe_archive_entries([encrypted])

        oversized = zipfile.ZipInfo("Payload/Runner.app/Info.plist")
        oversized.file_size = inspector._MAX_UNCOMPRESSED_BYTES + 1
        with self.assertRaisesRegex(
            inspector.CandidateError, "uncompressed content exceeds"
        ):
            inspector._safe_archive_entries([oversized])

    def test_entitlement_xml_may_have_bounded_codesign_diagnostics(self) -> None:
        xml = plistlib.dumps(_entitlements(), fmt=plistlib.FMT_XML)
        parsed = inspector._embedded_plist(
            b"Executable=redacted\n" + xml + b"\nwarning=redacted\n",
            category="application entitlement",
        )
        self.assertEqual(parsed["com.apple.developer.applesignin"], ["Default"])

    def test_default_runner_is_macos_only_and_uses_bounded_fixed_process(self) -> None:
        with mock.patch.object(inspector.sys, "platform", "win32"):
            with self.assertRaisesRegex(
                inspector.CandidateError, "macOS candidate inspection tools"
            ):
                inspector._default_tool_runner(
                    ["/usr/bin/codesign", "--verify"], self.root
                )
        with mock.patch.object(inspector.sys, "platform", "darwin"):
            with self.assertRaisesRegex(inspector.CandidateError, "not approved"):
                inspector._default_tool_runner(["/tmp/unapproved"], self.root)
        completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with (
            mock.patch.object(inspector.sys, "platform", "darwin"),
            mock.patch.object(
                inspector.subprocess, "run", return_value=completed
            ) as run,
        ):
            result = inspector._default_tool_runner(
                ["/usr/bin/codesign", "--verify"], self.root
            )
        self.assertEqual(result.returncode, 0)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["timeout"], inspector._TOOL_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["stdin"], inspector.subprocess.DEVNULL)
        self.assertEqual(kwargs["env"]["PATH"], "/usr/bin:/bin")

    def test_tool_output_and_error_messages_do_not_echo_sensitive_data(self) -> None:
        secret = "SENSITIVE-TEAM-PROFILE-VALUE"

        def oversized(_command: list[str], _cwd: Path) -> inspector.ToolResult:
            return inspector.ToolResult(1, stderr=(secret.encode() * 100_000))

        with self.assertRaises(inspector.CandidateError) as captured:
            self.inspect(runner=oversized)
        self.assertNotIn(secret, str(captured.exception))
        self.assertIn("output exceeds", str(captured.exception))

    def test_non_ipa_empty_and_invalid_archive_fail_before_tools(self) -> None:
        for name, source, reason in (
            ("candidate.zip", _ipa_bytes(), "regular IPA"),
            ("candidate.ipa", b"", "empty"),
            ("candidate.ipa", b"not-an-archive", "archive is invalid"),
        ):
            with self.subTest(reason=reason):
                candidate = self.root / name
                candidate.write_bytes(source)
                with self.assertRaisesRegex(inspector.CandidateError, reason):
                    inspector.inspect_ipa(
                        candidate,
                        expected_version="1.2.3",
                        expected_build=42,
                        previous_build=41,
                        mode="contract-test",
                        runner=_runner(),
                        now=NOW,
                    )


if __name__ == "__main__":
    unittest.main()
