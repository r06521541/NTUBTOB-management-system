"""Fictional credentials and native help; no signing or Apple request."""

import base64
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tools import ios_native_upload as upload
from tools.tests.test_ios_native_asc import ready_get


def fixture():
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return {
        "key_id": "FAKEKEY001",
        "issuer_id": "11111111-2222-4333-8444-555555555555",
        "p8_base64": base64.b64encode(pem).decode("ascii"),
    }


def binding():
    return {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "IOS_VERSION": "1.2.3",
        "IOS_BUILD_NUMBER": "42",
    }


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name).resolve()
        self.home = self.temp / "fictional-home"
        self.home.mkdir()
        self.bound = binding()
        self.root = self.temp / upload.ROOT
        self.raw = json.dumps(fixture()).encode()
        upload.publish(self.temp, b"fictional-inspected-ipa", self.bound)
        self.reader = mock.Mock(cleanup_failures=[])
        self.reader.get.side_effect = ready_get

    def native(self, stage, args, cwd, timeout, *, effect, private_home):
        self.assertEqual(stage, "altool_upload")
        self.assertEqual(args[:3], ["/usr/bin/xcrun", "altool", "--upload-app"])
        self.assertEqual(Path(args[args.index("-f") + 1]), self.root / "candidate.ipa")
        self.assertEqual(
            Path(args[args.index("--p8-file-path") + 1]), self.root / "upload.p8"
        )
        self.assertEqual(private_home, self.root / "home")
        self.assertNotIn("PRIVATE KEY", str(args))
        effect.update(started=True, observed_exit=0, process_stopped=True)
        return b"native schema is deliberately not guessed"

    def execute(self, run=None):
        output = io.StringIO()
        with redirect_stdout(output):
            result = upload.execute(
                self.temp,
                self.home,
                self.bound,
                self.raw,
                run=run or self.native,
                make_reader=lambda _: self.reader,
            )
        self.assertNotIn("PRIVATE KEY", output.getvalue())
        return result

    def test_native_zero_means_cli_only_and_cleans_owned_paths(self):
        result = self.execute()
        self.assertEqual(result["classification"], "CLI_COMPLETED")
        self.assertTrue(result["upload_attempted"])
        self.assertEqual(result["observed_exit"], 0)
        self.assertFalse(result["acceptance_verified"])
        self.assertFalse(result["distribution_verified"])
        self.assertTrue(result["owned_cleanup_verified"])
        self.assertFalse(self.root.exists())

    def test_changed_candidate_wrong_run_duplicate_ready_do_not_read_key_or_upload(
        self,
    ):
        (self.root / "candidate.ipa").write_bytes(b"changed")
        with mock.patch.object(upload, "credential") as credential:
            result = self.execute(mock.Mock())
        credential.assert_not_called()
        self.assertFalse(result["upload_attempted"])
        self.assertEqual(result["failure"]["reason"], "CANDIDATE_CHANGED")

    def test_api_rejection_never_writes_key_or_calls_altool(self):
        self.reader.get.side_effect = upload.Failure(
            "asc_get", "HTTP_403_AUTHORIZATION"
        )
        run = mock.Mock()
        result = self.execute(run)
        run.assert_not_called()
        self.assertFalse(self.root.exists())
        self.assertEqual(result["failure"]["reason"], "HTTP_403_AUTHORIZATION")

    def test_observed_exit_survives_output_or_reap_failure(self):
        for stopped in (True, False):
            if not self.root.exists():
                upload.publish(self.temp, b"fictional-inspected-ipa", self.bound)

            def run(*args, effect, **kwargs):
                effect.update(started=True, observed_exit=0, process_stopped=stopped)
                raise upload.Failure(
                    "altool_upload",
                    "PROCESS_UNRESOLVED" if not stopped else "OUTPUT_LIMIT",
                    stopped=stopped,
                )

            result = self.execute(run)
            self.assertEqual(result["observed_exit"], 0)
            self.assertTrue(result["upload_attempted"])
            self.assertEqual(result["classification"], "STOP")
            self.assertEqual(self.root.exists(), not stopped)
            if not stopped:
                self.assertEqual(
                    result["cleanup_failures"][0]["reason"], "PROCESS_UNRESOLVED"
                )

    def test_nonzero_timeout_and_launch_failure_never_authorize_retry(self):
        for started, code, reason in (
            (False, None, "PROCESS_START_FAILED"),
            (True, None, "CLI_TIMEOUT"),
            (True, 1, "CLI_FAILED"),
        ):
            if not self.root.exists():
                upload.publish(self.temp, b"fictional-inspected-ipa", self.bound)

            def run(*args, effect, **kwargs):
                effect.update(started=started, observed_exit=code, process_stopped=True)
                raise upload.Failure("altool_upload", reason, code)

            result = self.execute(run)
            self.assertEqual(result["upload_attempted"], started)
            self.assertFalse(result["retry_authorized"])
            self.assertEqual(result["failure"]["reason"], reason)

    def test_primary_and_cleanup_failure_are_both_visible(self):
        def run(*args, effect, **kwargs):
            effect.update(started=True, observed_exit=1, process_stopped=True)
            raise upload.Failure("altool_upload", "CLI_FAILED", 1)

        with mock.patch.object(
            upload.shutil, "rmtree", side_effect=OSError("fictional-private")
        ):
            result = self.execute(run)
        self.assertEqual(result["failure"]["reason"], "CLI_FAILED")
        self.assertEqual(result["cleanup_failures"][0]["reason"], "CLEANUP_IO_FAILED")

    def test_primary_native_failure_survives_stopped_marker_io(self):
        original = upload.write_private

        def write(path, data):
            if path.name == "stopped":
                raise OSError("fictional-private")
            original(path, data)

        def run(*args, effect, **kwargs):
            effect.update(started=True, observed_exit=1, process_stopped=True)
            raise upload.Failure(
                "altool_upload", "CLI_FAILED", 1, provider_codes=["ITMS-90000"]
            )

        with mock.patch.object(upload, "write_private", side_effect=write):
            result = self.execute(run)
        self.assertEqual(result["failure"]["stage"], "altool_upload")
        self.assertEqual(result["failure"]["provider_codes"], ["ITMS-90000"])
        self.assertEqual(result["cleanup_failures"][0]["stage"], "stopped_marker")
        self.assertEqual(result["observed_exit"], 1)
        self.assertFalse(result["owned_cleanup_verified"])

    def test_zero_exit_with_stopped_marker_failure_is_not_success(self):
        original = upload.write_private

        def write(path, data):
            if path.name == "stopped":
                raise OSError("fictional-private")
            original(path, data)

        with mock.patch.object(upload, "write_private", side_effect=write):
            result = self.execute()
        self.assertEqual(result["classification"], "STOP")
        self.assertEqual(result["observed_exit"], 0)
        self.assertEqual(result["cleanup_failures"][0]["stage"], "stopped_marker")
        self.assertFalse(self.root.exists())

    def test_native_failure_and_zero_exit_survive_output_spool_close(self):
        from tools import ios_native_signing as native

        for code in (1, 0):
            if not self.root.exists():
                upload.publish(self.temp, b"fictional-inspected-ipa", self.bound)
            spool = mock.MagicMock(wraps=io.BytesIO())
            spool.__enter__.return_value = spool
            spool.__exit__.side_effect = OSError("fictional-private")
            spool.close.side_effect = OSError("fictional-private")
            child = mock.Mock(pid=2468, returncode=code)

            def launch(*args, **kwargs):
                kwargs["stdout"].write(b"ITMS-90000 fictional-private")
                return child

            with (
                mock.patch.object(native.tempfile, "TemporaryFile", return_value=spool),
                mock.patch.object(native.subprocess, "Popen", side_effect=launch),
                mock.patch.object(
                    native.os, "killpg", create=True, side_effect=ProcessLookupError
                ),
                mock.patch.object(native.signal, "SIGKILL", 9, create=True),
            ):
                result = self.execute(native.command)
            self.assertEqual(result["observed_exit"], code)
            self.assertEqual(result["classification"], "STOP")
            if code:
                self.assertEqual(result["failure"]["provider_codes"], ["ITMS-90000"])
            self.assertTrue(
                any(
                    error["stage"] == "output_cleanup"
                    for error in result["cleanup_failures"]
                )
            )
            self.assertFalse(result["owned_cleanup_verified"])

    def test_candidate_changed_during_asc_preflight_blocks_native(self):
        def get(path):
            result = ready_get(path)
            if "betaGroups" in path:
                (self.root / "candidate.ipa").write_bytes(b"changed-during-get")
            return result

        self.reader.get.side_effect = get
        run = mock.Mock()
        result = self.execute(run)
        run.assert_not_called()
        self.assertEqual(result["failure"]["reason"], "CANDIDATE_CHANGED")

    def test_sidefile_change_is_not_silently_called_clean_or_deleted(self):
        def run(*args, **kwargs):
            result = self.native(*args, **kwargs)
            (self.home / "Library/Logs").mkdir(parents=True)
            (self.home / "Library/Logs/fictional-native-log").write_bytes(b"private")
            return result

        result = self.execute(run)
        self.assertEqual(result["observed_exit"], 0)
        self.assertEqual(
            result["cleanup_failures"][0]["reason"], "EXTERNAL_METADATA_CHANGED"
        )
        self.assertTrue((self.home / "Library/Logs/fictional-native-log").exists())
        self.assertFalse(self.root.exists())
        audit = result["sidefile_audit"]
        self.assertEqual(audit["status"], "CHANGED")
        self.assertEqual(audit["roots"]["logs"]["added"], 1)
        self.assertEqual(audit["roots"]["caches"]["status"], "UNCHANGED")
        self.assertFalse(audit["cause_verified"])
        self.assertNotIn("fictional-native-log", json.dumps(result))

    def test_failed_before_capture_blocks_native_with_unknown_not_zero(self):
        (self.home / "Library/Logs").mkdir(parents=True)
        run = mock.Mock()
        with mock.patch.object(
            upload.os, "scandir", side_effect=PermissionError("fictional-private")
        ):
            result = self.execute(run)
        run.assert_not_called()
        self.assertEqual(result["classification"], "STOP")
        self.assertEqual(result["failure"]["stage"], "native_sidefiles")
        logs = result["sidefile_audit"]["roots"]["logs"]
        self.assertEqual(logs["before"], "UNAVAILABLE")
        self.assertEqual(logs["after"], "NOT_OBSERVED")
        self.assertIsNone(logs["added"])
        self.assertNotIn("fictional-private", json.dumps(result))

    def test_primary_exit_and_partial_root_delta_survive_after_capture_failure(self):
        logs = self.home / "Library/Logs"
        caches = self.home / "Library/Caches"
        logs.mkdir(parents=True)
        caches.mkdir()
        original = upload.os.scandir
        attempted = False

        def scan(path):
            if attempted and path == logs:
                raise PermissionError("fictional-private")
            return original(path)

        def run(*args, effect, **kwargs):
            nonlocal attempted
            attempted = True
            (caches / "fictional-private").write_bytes(b"x")
            effect.update(started=True, observed_exit=1, process_stopped=True)
            raise upload.Failure("altool_upload", "CLI_FAILED", 1)

        with mock.patch.object(upload.os, "scandir", side_effect=scan):
            result = self.execute(run)
        self.assertEqual(result["failure"]["reason"], "CLI_FAILED")
        self.assertEqual(result["observed_exit"], 1)
        self.assertTrue(result["process_stopped"])
        audit = result["sidefile_audit"]
        self.assertEqual(audit["status"], "INCOMPLETE")
        self.assertIsNone(audit["roots"]["logs"]["added"])
        self.assertEqual(audit["roots"]["caches"]["added"], 1)
        self.assertEqual(result["cleanup_failures"][0]["reason"], "AUDIT_FAILED")
        self.assertNotIn("fictional-private", json.dumps(result))
        self.assertFalse(self.root.exists())

    def test_cli_zero_with_failed_after_capture_still_stops(self):
        def run(*args, **kwargs):
            result = self.native(*args, **kwargs)
            (self.home / "Library").write_bytes(b"not-a-directory")
            return result

        result = self.execute(run)
        self.assertEqual(result["observed_exit"], 0)
        self.assertEqual(result["classification"], "STOP")
        self.assertFalse(result["owned_cleanup_verified"])
        self.assertEqual(result["sidefile_audit"]["status"], "INCOMPLETE")

    def test_skip_cleanup_needs_no_credential_and_unresolved_process_is_not_deleted(
        self,
    ):
        upload.cleanup(self.temp, self.bound)
        self.assertFalse(self.root.exists())
        upload.publish(self.temp, b"fixture", self.bound)
        upload.write_private(self.root / "started", b"started")
        with self.assertRaises(upload.Failure):
            upload.cleanup(self.temp, self.bound)
        self.assertTrue(self.root.exists())

    def test_snapshot_and_ready_publication_fail_closed(self):
        source = self.temp / "source.ipa"
        source.write_bytes(b"before")
        evidence = {
            "artifact_size": 6,
            "artifact_sha256": hashlib.sha256(b"before").hexdigest(),
        }
        self.assertEqual(upload.snapshot(source, evidence), b"before")
        source.write_bytes(b"after!")
        with self.assertRaises(upload.Failure):
            upload.snapshot(source, evidence)
        upload.cleanup(self.temp, self.bound)
        original = upload.write_private

        def fail_ready(path, data):
            if path.name == "ready.json":
                raise OSError("fictional-private")
            original(path, data)

        with mock.patch.object(upload, "write_private", side_effect=fail_ready):
            with self.assertRaises(upload.Failure):
                upload.publish(self.temp, b"fixture", self.bound)
        self.assertFalse(self.root.exists())


class SidefileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name).resolve()
        self.logs = self.home / "Library/Logs"

    def capture(self):
        return upload.native_metadata(self.home)

    def delta(self, before):
        result = upload.sidefile_delta(before, self.capture())
        self.assertNotIn("fictional-private", json.dumps(result))
        return result["roots"]["logs"]

    def test_empty_root_presence_is_change_not_zero_count_success(self):
        before = self.capture()
        self.logs.mkdir(parents=True)
        delta = self.delta(before)
        self.assertEqual(delta["status"], "CHANGED")
        self.assertEqual(
            (delta["added"], delta["removed"], delta["modified"]), (0, 0, 0)
        )
        before = self.capture()
        self.logs.rmdir()
        self.assertEqual(self.delta(before)["status"], "CHANGED")

    def test_equal_total_rename_and_independent_mtime_size_changes(self):
        self.logs.mkdir(parents=True)
        path = self.logs / "fictional-private-before"
        path.write_bytes(b"x")
        before = self.capture()
        renamed = path.with_name("fictional-private-after")
        path.rename(renamed)
        delta = self.delta(before)
        self.assertEqual(
            (delta["added"], delta["removed"], delta["modified"]), (1, 1, 0)
        )
        before = self.capture()
        info = renamed.stat()
        os.utime(renamed, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
        self.assertEqual(self.delta(before)["modified"], 1)
        before = self.capture()
        info = renamed.stat()
        renamed.write_bytes(b"different-size")
        os.utime(renamed, ns=(info.st_atime_ns, info.st_mtime_ns))
        self.assertEqual(self.delta(before)["modified"], 1)

    def test_no_file_content_is_opened_and_nested_scope_is_not_claimed(self):
        self.logs.mkdir(parents=True)
        (self.logs / "fictional-private").write_bytes(b"fictional-private-content")
        with mock.patch.object(Path, "open", side_effect=AssertionError("no content")):
            before = self.capture()
            audit = upload.sidefile_delta(before, self.capture())
        self.assertEqual(audit["status"], "UNCHANGED")
        self.assertFalse(audit["content_inspected"])
        self.assertFalse(audit["whole_vm_absence_verified"])
        self.assertNotIn("fictional-private", json.dumps(audit))

    def test_enumeration_is_bounded_and_one_no_follow_stat_per_entry(self):
        self.logs.mkdir(parents=True)
        for count in (2000, 2001, 10000):
            seen, children = [], []

            def entries():
                for number in range(count):
                    seen.append(number)
                    child = mock.Mock(name="entry")
                    child.name = str(number)
                    child.stat.return_value = mock.Mock(st_mtime_ns=1, st_size=2)
                    children.append(child)
                    yield child

            context = mock.MagicMock()
            context.__enter__.return_value = entries()
            with mock.patch.object(upload.os, "scandir", return_value=context):
                result = self.capture()["logs"]
            self.assertEqual(len(seen), min(count, 2001))
            self.assertEqual(
                result["failure"], None if count == 2000 else "METADATA_LIMIT"
            )
            for child in children[:2000]:
                child.stat.assert_called_once_with(follow_symlinks=False)
            if count > 2000:
                children[-1].stat.assert_not_called()

    def test_entry_disappearance_iteration_and_close_errors_are_unknown(self):
        self.logs.mkdir(parents=True)
        for failure_at in ("entry", "iteration", "close"):
            context = mock.MagicMock()
            child = mock.Mock()
            child.name = "fictional-private"
            child.stat.side_effect = FileNotFoundError("fictional-private")

            def entries():
                if failure_at == "iteration":
                    raise OSError("fictional-private")
                if failure_at == "entry":
                    yield child

            context.__enter__.return_value = entries()
            if failure_at == "close":
                context.__exit__.side_effect = OSError("fictional-private")
            with mock.patch.object(upload.os, "scandir", return_value=context):
                captured = self.capture()
            delta = upload.sidefile_delta(captured, captured)["roots"]["logs"]
            self.assertEqual(delta["status"], "INCOMPLETE")
            self.assertIsNone(delta["added"])
            self.assertNotIn("fictional-private", json.dumps(delta))

    def test_ancestor_and_root_symlink_metadata_is_rejected_not_absent(self):
        self.logs.mkdir(parents=True)
        original = Path.lstat
        for target in (self.home, self.logs.parent, self.logs):

            def lstat(path):
                return (
                    mock.Mock(st_mode=stat.S_IFLNK)
                    if path == target
                    else original(path)
                )

            with mock.patch.object(Path, "lstat", lstat):
                result = self.capture()
            self.assertEqual(result["logs"]["failure"], "PATH_REJECTED")
            self.assertEqual(result["logs"]["state"], "UNAVAILABLE")

    def test_directory_replacement_or_change_during_enumeration_is_unknown(self):
        self.logs.mkdir(parents=True)
        original = upload.os.scandir

        def scan(path):
            (self.logs / "fictional-private").write_bytes(b"x")
            info = self.logs.stat()
            os.utime(self.logs, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
            return original(path)

        with mock.patch.object(upload.os, "scandir", side_effect=scan):
            result = self.capture()
        self.assertEqual(result["logs"]["failure"], "CAPTURE_CHANGED")

    @unittest.skipIf(os.name == "nt", "native symlink creation needs Windows privilege")
    def test_real_dangling_root_and_child_symlinks_are_not_followed(self):
        self.logs.parent.mkdir()
        self.logs.symlink_to(self.home / "missing", target_is_directory=True)
        self.assertEqual(self.capture()["logs"]["failure"], "PATH_REJECTED")
        self.logs.unlink()
        self.logs.mkdir()
        target = self.home / "fictional-private-target"
        target.write_bytes(b"x")
        (self.logs / "fictional-private-link").symlink_to(target)
        (self.logs / "fictional-private-dangling").symlink_to(self.home / "missing")
        before = self.capture()
        self.assertEqual(before["logs"]["state"], "PRESENT")
        target.write_bytes(b"different content outside audited roots")
        self.assertEqual(self.delta(before)["status"], "UNCHANGED")


class DiagnosticTests(unittest.TestCase):
    setUp = SidefileTests.setUp

    @staticmethod
    def native(stage, args, cwd, *, effect):
        effect.update(started=True, observed_exit=0, process_stopped=True)
        if stage == "xcode_version":
            return b"Xcode 26.3\nBuild version 17C529"
        if stage == "altool_location":
            return upload.signing.DEVELOPER.encode() + b"/usr/bin/altool"
        return b"--upload-app fictional-private-help"

    def test_changed_help_observation_completes_but_runtime_verdict_stops(self):
        calls = []

        def run(stage, args, cwd, **kwargs):
            calls.append(args)
            if stage == "altool_help":
                self.logs.mkdir(parents=True)
                (self.logs / "fictional-private-name").write_bytes(b"content")
            return self.native(stage, args, cwd, **kwargs)

        with mock.patch.object(upload, "credential", side_effect=AssertionError):
            result = upload.diagnose_sidefiles(self.home, run=run)
        self.assertEqual(result["classification"], "DIAGNOSTIC_COMPLETED")
        audit = result["observations"][-1]["audit"]
        self.assertEqual(audit["status"], "CHANGED")
        self.assertEqual(audit["runtime_audit_verdict"], "STOP")
        self.assertEqual(audit["roots"]["logs"]["added"], 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1], ["/usr/bin/xcrun", "altool", "--help"])
        self.assertNotIn("fictional-private", json.dumps(result))
        self.assertLess(len(json.dumps(result)), 8192)
        for field in (
            "upload_attempted",
            "upload_authorized",
            "release_authorized",
            "secret_input_read",
            "historical_cause_verified",
        ):
            self.assertFalse(result[field])

    def test_before_failure_never_calls_native(self):
        (self.home / "Library").write_bytes(b"not-a-directory")
        run = mock.Mock()
        result = upload.diagnose_sidefiles(self.home, run=run)
        run.assert_not_called()
        self.assertEqual(result["classification"], "STOP")
        self.assertEqual(result["observations"][0]["audit"]["status"], "INCOMPLETE")

    def test_failed_native_and_after_audit_preserve_previous_observations(self):
        calls = []

        def run(stage, args, cwd, *, effect):
            calls.append(stage)
            if stage == "altool_location":
                (self.home / "Library").write_bytes(b"not-a-directory")
                effect.update(started=True, observed_exit=1, process_stopped=True)
                error = upload.Failure(stage, "CLI_FAILED", 1)
                error.cleanup_failures = [
                    upload.Failure("output_cleanup", "CLOSE_FAILED").public()
                ]
                raise error
            return self.native(stage, args, cwd, effect=effect)

        result = upload.diagnose_sidefiles(self.home, run=run)
        self.assertEqual(calls, ["xcode_version", "altool_location"])
        self.assertEqual(result["failure"]["reason"], "CLI_FAILED")
        self.assertEqual(result["observations"][-1]["observed_exit"], 1)
        self.assertEqual(result["observations"][1]["audit"]["status"], "UNCHANGED")
        self.assertEqual(len(result["secondary_failures"]), 2)

    def test_unreaped_native_prevents_next_command(self):
        run = mock.Mock(
            side_effect=upload.Failure(
                "xcode_version", "PROCESS_UNRESOLVED", stopped=False
            )
        )
        result = upload.diagnose_sidefiles(self.home, run=run)
        self.assertEqual(run.call_count, 1)
        self.assertFalse(result["observations"][-1]["process_stopped"])
        self.assertEqual(result["classification"], "STOP")

    def test_cli_guards_before_home_private_input_or_native_access(self):
        good = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_OS": "macOS",
        }
        cases = [
            {},
            {**good, "RUNNER_ENVIRONMENT": "self-hosted"},
            {**good, "RUNNER_OS": "Windows"},
        ]
        cases += [
            {**good, key: "fictional-private"}
            for key in (*upload.signing.INPUT_NAMES, "IOS_ASC_UPLOAD_CREDENTIAL")
        ]
        for env in cases:
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch.object(upload.platform, "system", return_value="Darwin"),
                mock.patch.object(Path, "home") as home,
                mock.patch.object(upload, "diagnose_sidefiles") as diagnostic,
                mock.patch.object(upload.signing, "context") as signing_context,
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(upload.main(["diagnose-sidefiles"]), 1)
            home.assert_not_called()
            diagnostic.assert_not_called()
            signing_context.assert_not_called()
            self.assertNotIn("fictional-private", output.getvalue())

    def test_presence_guard_does_not_retrieve_private_values(self):
        class Environment(dict):
            def get(self, name, default=None):
                if name.startswith("IOS_"):
                    raise AssertionError("private value read")
                return super().get(name, default)

        env = Environment(
            GITHUB_ACTIONS="true",
            RUNNER_ENVIRONMENT="github-hosted",
            RUNNER_OS="macOS",
            IOS_ASC_UPLOAD_CREDENTIAL="fictional-private",
        )
        with mock.patch.object(upload.platform, "system", return_value="Darwin"):
            with self.assertRaises(upload.Failure) as caught:
                upload.diagnostic_context(env)
        self.assertEqual(caught.exception.reason, "PRIVATE_INPUT_PRESENT")

    def test_cli_rejects_arbitrary_arguments_without_echo(self):
        with (
            mock.patch.object(upload, "diagnose_sidefiles") as diagnostic,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(
                upload.main(["diagnose-sidefiles", "--home=fictional-private"]), 1
            )
        diagnostic.assert_not_called()
        self.assertNotIn("fictional-private", output.getvalue())
        self.assertEqual(
            json.loads(output.getvalue())["failure"]["reason"], "ARGUMENTS_REJECTED"
        )

    def test_guarded_cli_returns_completed_observation_without_entering_upload(self):
        env = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_OS": "macOS",
        }
        original = upload.diagnose_sidefiles
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(upload.platform, "system", return_value="Darwin"),
            mock.patch.object(Path, "home", return_value=self.home),
            mock.patch.object(
                upload,
                "diagnose_sidefiles",
                side_effect=lambda home: original(home, run=self.native),
            ),
            mock.patch.object(upload.signing, "context") as context,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(upload.main(["diagnose-sidefiles"]), 0)
        context.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["classification"], "DIAGNOSTIC_COMPLETED")
        self.assertEqual(len(result["observations"]), 4)


class CredentialTests(unittest.TestCase):
    def test_existing_validated_key_roundtrip(self):
        value = fixture()
        metadata, pem = upload.credential(json.dumps(value).encode())
        self.assertEqual(set(metadata), {"key_id", "issuer_id"})
        self.assertEqual(pem, base64.b64decode(value["p8_base64"]))

    def test_no_private_value_in_errors(self):
        for field in ("key_id", "issuer_id", "p8_base64"):
            value = fixture()
            value[field] = "fictional-sensitive-DO-NOT-ECHO"
            with self.assertRaises(upload.Failure) as caught:
                upload.credential(json.dumps(value).encode())
            self.assertNotIn("sensitive", str(caught.exception.public()))
            self.assertEqual(caught.exception.stage, "asc_input")

    def test_duplicate_extra_fields_bad_key_and_size_rejected(self):
        good = json.dumps(fixture()).encode()
        for raw in (
            b"{}",
            b"x" * 48001,
            good[:-1] + b',"key_id":"FAKEKEY001"}',
            good[:-1] + b',"extra":"x"}',
        ):
            with self.assertRaises(upload.Failure):
                upload.credential(raw)


class ProbeTests(unittest.TestCase):
    def test_fixed_xcode_contents_not_assumed_developer_subtree(self):
        prefix = "/Applications/Xcode_26.3.app/Contents/"
        for path, accepted in (
            (prefix + "SharedFrameworks/Fixture.framework/Support/altool", True),
            (prefix + "Developer/usr/bin/altool", True),
            (prefix + "../elsewhere/altool", False),
            (prefix + "../Contents/Developer/usr/bin/altool", False),
            (prefix.replace("26.3", "26.4") + "Developer/usr/bin/altool", False),
            (prefix.rstrip("/") + "-other/altool", False),
        ):

            def run(stage, *args, **kwargs):
                if stage == "xcode_version":
                    return b"Xcode 26.3\nBuild version 17C529"
                if stage == "altool_location":
                    return path.encode()
                return b"--help"

            with self.subTest(path=path):
                if accepted:
                    self.assertTrue(upload.probe(run=run)["altool_under_pinned_xcode"])
                else:
                    with self.assertRaises(upload.Failure):
                        upload.probe(run=run)

    def test_help_probe_no_key_file_or_upload(self):
        calls = []

        def run(stage, args, cwd, timeout=60):
            calls.append((stage, args))
            if stage == "xcode_version":
                return b"Xcode 26.3\nBuild version 17C529\n"
            if stage == "altool_location":
                return upload.signing.DEVELOPER.encode() + b"/usr/bin/altool"
            return b"--upload-app --upload-package --apiKey --apiIssuer --output-format --help"

        result = upload.probe(run=run)
        self.assertEqual(result["classification"], "TOOL_PROBED")
        self.assertEqual(result["options"]["upload_app"], True)
        self.assertFalse(result["upload_attempted"])
        self.assertEqual(calls[-1][1], ["/usr/bin/xcrun", "altool", "--help"])

    def test_toolchain_drift_precedes_altool(self):
        with self.assertRaises(upload.Failure) as caught:
            upload.probe(run=lambda *a, **k: b"Xcode unexpected")
        self.assertEqual(caught.exception.reason, "TOOLCHAIN_DRIFT")

    def test_unknown_help_is_observation_not_upload_readiness(self):
        def run(stage, *args, **kwargs):
            if stage == "altool_location":
                return upload.signing.DEVELOPER.encode() + b"/usr/bin/altool"
            return (
                b"Xcode 26.3\nBuild version 17C529"
                if stage == "xcode_version"
                else b"new interface"
            )

        result = upload.probe(run=run)
        self.assertFalse(any(result["options"].values()))
        self.assertFalse(result["upload_authorized"])


if __name__ == "__main__":
    unittest.main()
