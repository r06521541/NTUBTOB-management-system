"""Fictional CLI responses through the actual baseline and IPA inspector."""

import base64
import hashlib
import io
import json
import plistlib
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tools import ios_native_signing as native
from tools.tests.test_ios_candidate_inspector import _ipa_bytes, _plist

TEAM = "FAKETEAM01"
CERT = b"fictional-certificate"
SELECTOR = hashlib.sha1(CERT).hexdigest().upper()
PASSWORD = "fictional-private-password"


def metadata():
    return {
        "IOS_TEAM_ID": TEAM,
        "IOS_VERSION": "1.2.3",
        "IOS_BUILD_NUMBER": "42",
        "IOS_API_BASE_URL": "https://mobile-api-staging-fictional-de.a.run.app",
        "IOS_LINE_CHANNEL_ID": "1234567890",
        "IOS_GOOGLE_CLIENT_ID": "fictional-ios.apps.googleusercontent.com",
        "IOS_GOOGLE_SERVER_CLIENT_ID": "fictional-web.apps.googleusercontent.com",
    }


def profile():
    return {
        "UUID": "11111111-2222-4333-8444-555555555555",
        "TeamIdentifier": [TEAM],
        "DeveloperCertificates": [CERT],
        "ExpirationDate": datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(days=30),
        "Entitlements": {
            "application-identifier": TEAM + "." + native.BUNDLE,
            "com.apple.developer.team-identifier": TEAM,
            "com.apple.developer.applesignin": ["Default"],
            "get-task-allow": False,
        },
    }


class FakeCommands:
    def __init__(self):
        self.calls = []
        self.failures = {}
        self.search = b'    "/fictional/login.keychain-db"\n'
        self.default = b'    "/fictional/login.keychain-db"\n'
        self.decoded = profile()

    def __call__(self, stage, args, cwd, timeout=60):
        self.calls.append((stage, args))
        if stage in self.failures:
            raise self.failures[stage]
        if args[1] == "default-keychain":
            return self.default
        if args[1] == "list-keychains":
            if "-s" in args:
                self.search = "".join('    "' + p + '"\n' for p in args[5:]).encode()
            return self.search
        if args[1] == "create-keychain":
            Path(args[-1]).write_bytes(b"fictional-keychain")
        if args[1] == "delete-keychain":
            Path(args[-1]).unlink()
        if args[1] == "cms":
            return plistlib.dumps(self.decoded)
        if args[1] == "find-identity":
            return f'  1) {SELECTOR} "Apple Distribution: fictional"\n'.encode()
        if "-exportArchive" in args:
            target = Path(args[args.index("-exportPath") + 1])
            target.mkdir()
            (target / "虛構.ipa").write_bytes(_ipa_bytes(info=_plist()))
        if args[0] == "/usr/bin/codesign" and "--entitlements" in args:
            return plistlib.dumps(self.decoded["Entitlements"])
        return b""


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo, self.home, self.temp_root = (
            self.base / name for name in ("repo", "home", "temp")
        )
        for path in (
            self.repo / "clients/flutter_app/ios/Flutter",
            self.home,
            self.temp_root,
        ):
            path.mkdir(parents=True)
        (self.repo / "clients/flutter_app/ios/Runner").mkdir()
        self.commands = FakeCommands()
        self.material = {
            "IOS_DISTRIBUTION_P12_BASE64": base64.b64encode(b"fictional-p12").decode(),
            "IOS_DISTRIBUTION_P12_PASSWORD": PASSWORD,
            "IOS_DISTRIBUTION_PROFILE_BASE64": base64.b64encode(
                b"fictional-profile"
            ).decode(),
        }

    def execute(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = native.Baseline(
                self.repo, self.home, self.temp_root, metadata(), self.commands
            ).run(self.material)
        self.assertNotIn(PASSWORD, output.getvalue())
        self.assertNotIn(TEAM, output.getvalue())
        return result

    def test_full_native_chain_and_real_inspector_without_upload(self):
        result = self.execute()
        self.assertEqual(result["classification"], "SIGNED_BASELINE_VERIFIED")
        self.assertTrue(result["signature_verified"])
        self.assertTrue(result["cleanup_verified"])
        self.assertFalse(result["upload_attempted"])
        self.assertFalse(result["device_verified"])
        self.assertFalse((self.temp_root / native.ROOT_NAME).exists())
        calls = self.commands.calls
        import_args = next(args for stage, args in calls if stage == "p12_import")
        self.assertIn("-T", import_args)
        self.assertIn("/usr/bin/codesign", import_args)
        self.assertNotIn("-A", import_args)
        for stage, args in calls:
            if args[1] == "cms":
                self.assertIn("-k", args)
            if stage not in {"p12_import"}:
                self.assertNotIn(PASSWORD, args)
        self.assertEqual(self.commands.search, self.commands.default)

    def test_primary_native_error_and_cleanup_error_survive_together(self):
        self.commands.failures["archive"] = native.Failure(
            "archive", "PROFILE_MISSING", 65
        )
        self.commands.failures["keychain_delete"] = native.Failure(
            "keychain_delete", "CLI_FAILED", 1
        )
        result = self.execute()
        self.assertEqual(
            result["failure"],
            {"stage": "archive", "reason": "PROFILE_MISSING", "exit_code": 65},
        )
        self.assertEqual(result["cleanup_failures"][0]["stage"], "keychain_delete")
        self.assertFalse(result["cleanup_verified"])
        self.assertEqual(result["next_action"], "READ_ONLY_REVIEW")
        self.assertNotIn("export", [stage for stage, _ in self.commands.calls])

    def test_password_rejection_does_not_archive_or_hide_stage(self):
        self.commands.failures["p12_import"] = native.Failure(
            "p12_import", "P12_IMPORT_REJECTED", 1
        )
        result = self.execute()
        self.assertEqual(result["failure"]["stage"], "p12_import")
        self.assertTrue(result["cleanup_verified"])
        self.assertFalse(result["signature_verified"])
        self.assertNotIn("archive", [stage for stage, _ in self.commands.calls])

    def test_inspection_rejects_debuggable_native_entitlements(self):
        original = self.commands.__call__

        def altered(stage, args, cwd, timeout=60):
            if args[0] == "/usr/bin/codesign" and "--entitlements" in args:
                return plistlib.dumps(
                    dict(profile()["Entitlements"], **{"get-task-allow": True})
                )
            return original(stage, args, cwd, timeout)

        with redirect_stdout(io.StringIO()):
            result = native.Baseline(
                self.repo, self.home, self.temp_root, metadata(), altered
            ).run(self.material)
        self.assertEqual(result["failure"]["stage"], "inspect")
        self.assertTrue(result["cleanup_verified"])
        self.assertFalse(result["signature_verified"])

    def test_preexisting_config_is_not_overwritten_or_deleted(self):
        path = self.repo / "clients/flutter_app/ios/Flutter/StoreReleaseConfig.xcconfig"
        path.write_text("existing-user-file", encoding="utf-8")
        result = self.execute()
        self.assertEqual(result["failure"]["reason"], "PATH_CONFLICT")
        self.assertEqual(path.read_text(), "existing-user-file")
        self.assertEqual(self.commands.calls, [])

    def test_malformed_input_identifies_field_before_keychain(self):
        self.material["IOS_DISTRIBUTION_PROFILE_BASE64"] = "not base64"
        result = self.execute()
        self.assertEqual(result["failure"]["stage"], "profile_input")
        self.assertEqual(self.commands.calls, [])

    def test_metadata_rejects_production_mixed_or_injected_values(self):
        for key, value in (
            ("IOS_API_BASE_URL", "https://production.invalid"),
            ("IOS_GOOGLE_CLIENT_ID", metadata()["IOS_GOOGLE_SERVER_CLIENT_ID"]),
            ("IOS_TEAM_ID", "TEAM\nINJECT=YES"),
            ("IOS_BUILD_NUMBER", "0"),
        ):
            with self.subTest(key=key), self.assertRaises(native.Failure):
                native.validate_metadata(dict(metadata(), **{key: value}))

    def test_sanitized_cli_reason_never_uses_arbitrary_output(self):
        for data, reason in (
            (
                b"security: MAC verification failed during PKCS12 import (wrong password?)",
                "P12_IMPORT_REJECTED",
            ),
            (b'error: No profiles for "private.app" were found', "PROFILE_MISSING"),
            (b"error: errSecInternalComponent PRIVATE", "KEYCHAIN_ACCESS_REJECTED"),
            (PASSWORD.encode(), "CLI_FAILED"),
        ):
            self.assertEqual(native.classify(data), reason)
        self.assertNotIn(
            PASSWORD, json.dumps(native.Failure("archive", "CLI_FAILED", 65).public())
        )

    def test_import_failure_still_restores_native_create_search_effect(self):
        self.commands.failures["p12_import"] = native.Failure(
            "p12_import", "P12_IMPORT_REJECTED", 1
        )
        result = self.execute()
        self.assertTrue(result["cleanup_verified"])
        self.assertIn("search_restore", [stage for stage, _ in self.commands.calls])

    def test_uncertain_child_prevents_cleanup_and_export(self):
        self.commands.failures["archive"] = native.Failure(
            "archive", "PROCESS_UNRESOLVED", stopped=False
        )
        result = self.execute()
        self.assertFalse(result["cleanup_verified"])
        self.assertTrue((self.temp_root / native.ROOT_NAME).exists())
        self.assertNotIn("keychain_delete", [stage for stage, _ in self.commands.calls])
        self.assertNotIn("export", [stage for stage, _ in self.commands.calls])

    def test_search_restore_failure_cannot_report_success(self):
        self.commands.failures["search_restore"] = native.Failure(
            "search_restore", "CLI_FAILED", 1
        )
        result = self.execute()
        self.assertEqual(result["classification"], "STOP")
        self.assertTrue(result["signature_verified"])
        self.assertFalse(result["cleanup_verified"])
        self.assertIsNone(result["failure"])

    def test_profile_team_mismatch_fails_before_project_build(self):
        self.commands.decoded["TeamIdentifier"] = ["OTHERTEAM1"]
        result = self.execute()
        self.assertEqual(result["failure"]["reason"], "TEAM_MISMATCH")
        self.assertTrue(result["cleanup_verified"])
        self.assertNotIn("archive", [stage for stage, _ in self.commands.calls])

    def test_cleanup_interruption_keeps_primary_and_final_result(self):
        self.commands.failures["archive"] = native.Failure(
            "archive", "PROFILE_MISSING", 65
        )
        self.commands.failures["search_restore"] = KeyboardInterrupt()
        result = self.execute()
        self.assertEqual(result["failure"]["reason"], "PROFILE_MISSING")
        self.assertEqual(result["cleanup_failures"][0]["reason"], "CLEANUP_INTERRUPTED")
        self.assertFalse(result["cleanup_verified"])
        self.assertNotIn("keychain_delete", [stage for stage, _ in self.commands.calls])


class CommandTests(unittest.TestCase):
    def setUp(self):
        # The production entry is Darwin-only. Simulate that process primitive
        # when exercising its fake I/O on Windows; do not weaken runtime guards.
        patch = mock.patch.object(native.signal, "SIGKILL", 9, create=True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_teardown_interruption_never_claims_group_stopped(self):
        cases = (
            ([0, 0], KeyboardInterrupt()),
            ([0, KeyboardInterrupt()], None),
            ([0, 0], [None, KeyboardInterrupt()]),
        )
        for waits, kills in cases:
            process = mock.Mock(pid=2468, returncode=0)
            process.wait.side_effect = waits
            with (
                self.subTest(case=str(waits)),
                mock.patch.object(native.subprocess, "Popen", return_value=process),
                mock.patch.object(native.os, "killpg", create=True, side_effect=kills),
                self.assertRaises(native.Failure) as raised,
            ):
                native.command("archive", [native.XCODE, "archive"], Path.cwd())
            self.assertFalse(raised.exception.stopped)
            self.assertEqual(raised.exception.reason, "PROCESS_UNRESOLVED")

    def test_context_rejects_wrong_ref_attempt_or_debug_before_command(self):
        env = {
            "GITHUB_SHA": "a" * 40,
            "INPUT_APPROVED_SHA": "a" * 40,
            "RUNNER_ENVIRONMENT": "github-hosted",
            "GITHUB_REPOSITORY": native.REPO,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF": native.REPO
            + "/.github/workflows/ios-native-signing.yml@refs/heads/main",
        }
        for key, value in (
            ("GITHUB_REF", "refs/heads/other"),
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("RUNNER_ENVIRONMENT", "self-hosted"),
            ("INPUT_APPROVED_SHA", "b" * 40),
            ("RUNNER_DEBUG", "1"),
        ):
            with (
                self.subTest(key=key),
                mock.patch.object(native.platform, "system", return_value="Darwin"),
                mock.patch.object(native, "command") as command,
                self.assertRaises(native.Failure),
            ):
                native.context(dict(env, **{key: value}))
            command.assert_not_called()

    def test_native_process_keeps_exit_reason_and_scrubs_inherited_secrets(self):
        process = mock.Mock(pid=2468, returncode=65)

        def start(args, **kwargs):
            self.assertNotIn("IOS_DISTRIBUTION_P12_PASSWORD", kwargs["env"])
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            self.assertNotIn("shell", kwargs)
            self.assertTrue(kwargs["start_new_session"])
            kwargs["stdout"].write(
                b'error: No profiles for "fictional-private-app" were found'
            )
            return process

        with (
            mock.patch.dict(
                native.os.environ,
                {
                    "IOS_DISTRIBUTION_P12_PASSWORD": PASSWORD,
                    "GITHUB_TOKEN": "fictional-token",
                },
            ),
            mock.patch.object(native.subprocess, "Popen", side_effect=start),
            mock.patch.object(
                native.os, "killpg", create=True, side_effect=ProcessLookupError
            ),
            self.assertRaises(native.Failure) as raised,
        ):
            native.command("archive", [native.XCODE, "archive"], Path.cwd())
        self.assertEqual(
            raised.exception.public(),
            {"stage": "archive", "reason": "PROFILE_MISSING", "exit_code": 65},
        )
        self.assertNotIn(PASSWORD, str(raised.exception))

    def test_timeout_reaps_group_and_reports_timeout_not_password_failure(self):
        process = mock.Mock(pid=2468, returncode=-9)
        process.wait.side_effect = [
            native.subprocess.TimeoutExpired("private-command", 1),
            0,
        ]
        with (
            mock.patch.object(native.subprocess, "Popen", return_value=process),
            mock.patch.object(
                native.os, "killpg", create=True, side_effect=ProcessLookupError
            ) as kill,
            self.assertRaises(native.Failure) as raised,
        ):
            native.command("archive", [native.XCODE, "archive"], Path.cwd(), 1)
        self.assertEqual(raised.exception.reason, "CLI_TIMEOUT")
        self.assertTrue(raised.exception.stopped)
        self.assertEqual(process.wait.call_count, 2)
        self.assertEqual(kill.call_count, 2)

    def test_workflow_custody_and_retirement_contract(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / ".github/workflows/ios-native-signing.yml").read_text(
            encoding="utf-8"
        )
        for value in (
            "github.run_attempt == 1",
            "github.sha == inputs.approved_sha",
            "environment: ios-native-signing",
            "contents: read",
            "cancel-in-progress: false",
            "persist-credentials: false",
            "cache: false",
        ):
            self.assertIn(value, text)
        for value in (
            "pull_request",
            "upload-artifact",
            "secrets.ASC",
            "secrets.APPLE",
            "--allowProvisioningUpdates",
            "$GITHUB_ENV",
            "secrets: inherit",
        ):
            self.assertNotIn(value, text)
        self.assertLess(
            text.index("-resolvePackageDependencies"), text.index("secrets.IOS_")
        )
        self.assertEqual(
            set(native.re.findall(r"secrets\.([A-Z_0-9]+)", text)),
            set(native.INPUT_NAMES),
        )
        self.assertNotIn("uses:", text[text.index("secrets.IOS_") :])
        old = (root / ".github/workflows/ios-owner-testflight.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("if: >-\n      false &&", old)


@unittest.skipUnless(
    native.platform.system() == "Darwin"
    and native.os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
    "native smoke is restricted to ephemeral GitHub macOS",
)
class NativeCLISmoke(unittest.TestCase):
    def test_native_keychain_and_bad_p12_cleanup_without_real_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            repo = base / "repo"
            (repo / "clients/flutter_app/ios/Flutter").mkdir(parents=True)
            (repo / "clients/flutter_app/ios/Runner").mkdir()
            with redirect_stdout(io.StringIO()):
                result = native.Baseline(
                    repo, Path.home().resolve(), base, metadata()
                ).run(
                    {
                        native.INPUT_NAMES[0]: base64.b64encode(
                            b"fictional invalid P12"
                        ).decode(),
                        native.INPUT_NAMES[1]: PASSWORD,
                        native.INPUT_NAMES[2]: base64.b64encode(
                            b"fictional invalid profile"
                        ).decode(),
                    }
                )
            self.assertEqual(result["failure"]["stage"], "p12_import", result)
            self.assertTrue(result["cleanup_verified"], result)
            self.assertFalse(result["signature_verified"])


if __name__ == "__main__":
    unittest.main()
