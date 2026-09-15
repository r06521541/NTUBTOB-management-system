"""Fictional credentials and native help; no signing or Apple request."""

import base64
import hashlib
import io
import json
import os
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
