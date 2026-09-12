"""Fictional host/controller boundaries; never launches a signing worker."""

import base64
import io
import json
import os
import re
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

from tools import ios_testflight_hosted as hosted
from tools import ios_testflight_signing as signing
from tools import ios_testflight_wire as wire


class HostedTests(unittest.TestCase):
    def test_fingerprint_precedes_upload_and_private_ids_not_persisted(self):
        binding = wire.Binding("a" * 40, "b" * 64, "123")
        prepared = signing.PreparedSigning(
            hosted.ROOT, hosted.ROOT / "fictional", "a" * 40, "c" * 64, (1, 2), "d" * 64
        )
        candidate = Mock(
            prepared=prepared, version="1.0.0", build=1, sha256="e" * 64, size=4
        )
        calls = []
        output = io.StringIO()

        def worker(kind, payload, **kwargs):
            calls.append(kind)
            if kind == "sign":
                return {"classification": "CANDIDATE_BOUND", "candidate": {}}
            self.assertIn(hosted.recovery.PREFIX, output.getvalue())
            return {
                "classification": "UPLOAD_PENDING",
                "cleanup_verified": True,
                "receipt": {"upload_id": "private-sentinel"},
            }

        with (
            patch.object(hosted, "LIVE_CONTROLLER_READY", True),
            patch.object(hosted.wire, "context", return_value=binding),
            patch.object(
                hosted.wire,
                "consume",
                return_value=Mock(signing_frame=b"{}", asc_frame=b"{}"),
            ),
            patch.object(
                hosted.wire, "_document", return_value={"expires_at": 9999999999}
            ),
            patch.object(hosted, "read_prepared", return_value=prepared),
            patch.object(
                hosted, "sign_material", return_value={"version": "1.0.0", "build": 1}
            ),
            patch.object(
                hosted,
                "asc_fields",
                return_value={"version": "1.0.0", "build": 1, "previous_build": 0},
            ),
            patch.object(hosted, "candidate_from", return_value=candidate),
            patch.object(hosted, "state_directory", return_value=hosted.ROOT),
            patch.object(hosted, "write_state") as save,
            patch.object(hosted, "worker", side_effect=worker),
            patch("sys.stdout", output),
        ):
            result = hosted.execute_phase()
        self.assertEqual(calls, ["sign", "upload"])
        self.assertEqual(result["classification"], "UPLOAD_PENDING")
        self.assertNotIn(
            "private-sentinel", repr(save.call_args_list) + output.getvalue()
        )
        self.assertEqual(
            save.call_args.args[2]["recovery_mode"], "READ_ONLY_REDISCOVERY"
        )

    @unittest.skipUnless(os.name == "posix", "POSIX private-file custody")
    def test_sanitized_receipt_can_cleanup_without_claiming_local_ack(self):
        binding = wire.Binding("a" * 40, "b" * 64, "123")
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            directory.chmod(0o700)
            prepared = signing.PreparedSigning(
                hosted.ROOT,
                directory / "already-removed",
                "a" * 40,
                "c" * 64,
                (1, 2),
                "d" * 64,
            )
            hosted.write_state(
                directory,
                "prepared.json",
                {
                    "binding": asdict(binding),
                    "prepared": hosted.prepared_record(prepared),
                },
            )
            hosted.write_state(directory, "consumed", asdict(binding))
            hosted.write_state(
                directory,
                "result.json",
                {
                    **hosted.public_result("UPLOAD_PENDING", cleanup=True),
                    "recovery_mode": "READ_ONLY_REDISCOVERY",
                    "fingerprint": {
                        "schema": 1,
                        **asdict(binding),
                        "version": "1.0.0",
                        "build": 1,
                        "sha256": "e" * 64,
                        "size": 4,
                    },
                },
            )
            with (
                patch.object(hosted.wire, "context", return_value=binding),
                patch.object(hosted, "state_directory", return_value=directory),
            ):
                result = hosted.cleanup_phase()
            self.assertEqual(result["classification"], "CLEANED")
            self.assertFalse(directory.exists())

    def material(self):
        return dict(
            p12=b"fictional",
            password=b"fictional",
            profile=b"fictional",
            certificate_der=b"fictional",
            team="FICTTEAM01",
            profile_uuid="11111111-1111-4111-8111-111111111111",
            version="1.0.0",
            build=1,
            build_defines={
                "API_BASE_URL": "https://fictional-staging.run.app",
                "LINE_CHANNEL_ID": "123",
                "GOOGLE_CLIENT_ID": "123-ios.apps.googleusercontent.com",
                "GOOGLE_SERVER_CLIENT_ID": "456-web.apps.googleusercontent.com",
            },
        )

    def test_sign_frame_uses_exact_existing_schema(self):
        original = signing.frame(**self.material())
        decoded = hosted.sign_material(original)
        self.assertEqual(decoded, self.material())
        for field, value in (
            ("unexpected", "private-sentinel"),
            ("profile", "not-base64"),
            ("build", True),
        ):
            raw = json.loads(original)
            raw[field] = value
            with self.assertRaises(hosted.Rejected):
                hosted.sign_material(json.dumps(raw).encode())

    def test_upload_frame_has_no_signing_or_apple_login_fields(self):
        raw = {
            "pem": base64.b64encode(b"fictional").decode(),
            "key_id": "FICTKEY001",
            "issuer_id": "11111111-1111-4111-8111-111111111111",
            "app_id": "123",
            "owner_group_id": "group",
            "owner_tester_id": "tester",
            "version": "1.0.0",
            "build": 1,
            "previous_build": 0,
        }
        with patch.object(hosted.inputs, "load_asc_key", return_value=Mock()) as load:
            result = hosted.asc_material(json.dumps(raw).encode())
            self.assertEqual(result[1]["version"], "1.0.0")
            load.assert_called_once()
            for field in ("p12", "profile", "password", "apple_login"):
                with self.assertRaises(hosted.Rejected):
                    hosted.asc_material(
                        json.dumps(raw | {field: "private-sentinel"}).encode()
                    )

    def test_prepared_roundtrip_and_unknown_keys_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            prepared = signing.PreparedSigning(
                root, root, "a" * 40, "b" * 64, (1, 2), "c" * 64
            )
            record = hosted.prepared_record(prepared)
            self.assertEqual(hosted.prepared_from(record), prepared)
            with self.assertRaises(hosted.Rejected):
                hosted.prepared_from(record | {"private-sentinel": "bad"})

    def test_child_environment_is_minimal_and_output_bounded(self):
        child = Mock()
        child.stdin = io.BytesIO()
        child.stdout = io.BytesIO(b'{"classification":"STOP"}')
        child.returncode = 0
        with (
            patch.object(hosted.subprocess, "Popen", return_value=child) as launch,
            patch.object(
                hosted.os, "killpg", side_effect=ProcessLookupError(), create=True
            ),
            patch.object(hosted.signal, "SIGKILL", 9, create=True),
        ):
            result = hosted.worker("sign", b"fictional-signing-only", timeout=5)
        self.assertEqual(result, {"classification": "STOP"})
        env = launch.call_args.kwargs["env"]
        self.assertEqual(set(env), {"PATH", "DEVELOPER_DIR"})
        self.assertNotIn("fictional-signing-only", repr(launch.call_args.args))
        self.assertEqual(launch.call_args.kwargs["stderr"], hosted.subprocess.DEVNULL)

    def test_worker_timeout_never_claims_cleanup(self):
        child = Mock()
        child.stdin = io.BytesIO()
        child.stdout = io.BytesIO(b"")
        child.wait.side_effect = TimeoutError("private-sentinel")
        with (
            patch.object(hosted.subprocess, "Popen", return_value=child),
            patch.object(hosted.os, "killpg", create=True),
            patch.object(hosted.signal, "SIGKILL", 9, create=True),
        ):
            with self.assertRaises(hosted.Unresolved):
                hosted.worker("sign", b"fictional", timeout=1)

    def test_public_projection_cannot_emit_receipt_or_claim_release(self):
        result = hosted.public_result("BUILD_VALID_UNDISTRIBUTED", cleanup=True)
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["device_verified"])
        self.assertEqual(
            hosted.public_result("private-sentinel", cleanup=False)["classification"],
            "UNRESOLVED",
        )
        self.assertNotIn(
            "private-sentinel",
            json.dumps(hosted.public_result("private-sentinel", cleanup=True)),
        )

    def test_cleanup_failure_cannot_report_success_classification(self):
        self.assertEqual(
            hosted.public_result("BUILD_VALID_UNDISTRIBUTED", cleanup=False)[
                "classification"
            ],
            "UNRESOLVED",
        )
        self.assertEqual(
            hosted.public_result("STOP", cleanup=False)["classification"], "UNRESOLVED"
        )
        self.assertEqual(
            hosted.public_result("CLEANED", cleanup=True)["classification"], "CLEANED"
        )

    def test_invalid_context_removes_all_private_environment_fields(self):
        with patch.dict(
            os.environ,
            {"IOS_TF_ASC": "private-sentinel", "IOS_TF_UNEXPECTED": "private-sentinel"},
            clear=True,
        ):
            with self.assertRaises(wire.Rejected):
                hosted.execute_phase()
            self.assertFalse(any(key.startswith("IOS_TF_") for key in os.environ))

    def test_controller_requires_valid_run_context_before_private_workers(self):
        self.assertIs(hosted.LIVE_CONTROLLER_READY, True)
        with patch.object(
            hosted.wire, "context", side_effect=hosted.Rejected()
        ) as context:
            with self.assertRaises(hosted.Rejected):
                hosted.execute_phase()
            context.assert_called_once()

    def test_known_remote_receipt_cannot_be_deleted_before_handoff(self):
        binding = wire.Binding("a" * 40, "b" * 64, "123")
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            prepared = signing.PreparedSigning(
                hosted.ROOT, directory, "a" * 40, "b" * 64, (1, 2), "c" * 64
            )
            records = {
                "prepared.json": {
                    "binding": asdict(binding),
                    "prepared": hosted.prepared_record(prepared),
                },
                "consumed": asdict(binding),
                "result.json": {
                    "classification": "UPLOAD_PENDING",
                    "cleanup_verified": True,
                    "receipt": {"upload_id": "private-sentinel"},
                },
            }
            for classification in (
                "UPLOAD_PENDING",
                "UPLOAD_UNCERTAIN",
                "BUILD_PENDING",
                "BUILD_VALID_UNDISTRIBUTED",
            ):
                records["result.json"]["classification"] = classification
                with (
                    patch.object(hosted.wire, "context", return_value=binding),
                    patch.object(hosted, "state_directory", return_value=directory),
                    patch.object(hosted.signing, "_safe"),
                    patch.object(
                        Path, "lstat", return_value=Mock(st_mode=0o40700, st_uid=1)
                    ),
                    patch.object(hosted.os, "getuid", return_value=1, create=True),
                    patch.object(hosted.os, "listdir", return_value=list(records)),
                    patch.object(
                        hosted,
                        "private_state",
                        side_effect=lambda d, n: (records[n], None),
                    ),
                    patch.object(hosted.os, "unlink") as unlink,
                    patch.object(hosted.runner, "_cleanup") as cleanup,
                ):
                    with self.assertRaises(hosted.Unresolved):
                        hosted.cleanup_phase()
                    unlink.assert_not_called()
                    cleanup.assert_not_called()

    def test_expired_upload_never_loads_key_or_calls_remote(self):
        with (
            patch.object(hosted, "candidate_from", return_value=Mock()),
            patch.object(hosted, "asc_material") as key,
            patch.object(hosted.runner, "upload_phase") as upload,
            patch.object(
                hosted.runner,
                "final_cleanup",
                return_value=Mock(classification="CLEANED"),
            ),
        ):
            result = hosted.upload_worker(
                {"candidate": {}, "frame": "fictional", "expires_at": 0}
            )
        self.assertEqual(
            result, {"classification": "STOP", "cleanup_verified": True, "receipt": {}}
        )
        key.assert_not_called()
        upload.assert_not_called()

    def test_expired_or_malformed_upload_still_reports_cleanup_uncertainty(self):
        with (
            patch.object(hosted, "candidate_from", return_value=Mock()),
            patch.object(
                hosted.runner,
                "final_cleanup",
                return_value=Mock(classification="UNRESOLVED"),
            ),
        ):
            result = hosted.upload_worker(
                {"candidate": {}, "frame": "fictional", "expires_at": 0}
            )
        self.assertFalse(result["cleanup_verified"])
        self.assertEqual(
            hosted.public_result(result["classification"], cleanup=False)[
                "classification"
            ],
            "UNRESOLVED",
        )

    @unittest.skipUnless(os.name == "posix", "POSIX private-file custody")
    def test_private_state_same_handle_rejects_symlink_and_wrong_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            hosted.write_state(directory, "result.json", {"classification": "STOP"})
            self.assertEqual(
                hosted.private_state(directory, "result.json")[0],
                {"classification": "STOP"},
            )
            (directory / "result.json").chmod(0o644)
            with self.assertRaises(hosted.Rejected):
                hosted.private_state(directory, "result.json")
            (directory / "consumed").symlink_to(directory / "result.json")
            with self.assertRaises(Exception):
                hosted.private_state(directory, "consumed")

    def test_workflow_private_ingress_and_existing_ci_scope(self):
        source = (hosted.ROOT / ".github/workflows/ios-owner-testflight.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("pull_request", source)
        self.assertIn("environment: ios-owner-testflight", source)
        self.assertIn("name: owner_testflight", source)
        self.assertIn("github.run_attempt == 1", source)
        self.assertNotIn("false &&", source)
        self.assertIn("run-name: ios-tf-${{ inputs.nonce }}", source)
        self.assertIn("github.sha == inputs.approved_sha", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("cache: false", source)
        self.assertIn("pub-cache: false", source)
        self.assertNotIn("upload-artifact", source)
        self.assertNotIn("$GITHUB_ENV", source)
        self.assertEqual(
            re.findall(r"secrets\.([A-Z_0-9]+)", source), list(wire.SECRETS)
        )
        self.assertLess(source.index("--config-only"), source.index("--prepare"))
        self.assertLess(source.index("--prepare"), source.index("secrets.IOS_TF"))
        self.assertLess(source.index("--execute"), source.index("--cleanup"))
        self.assertNotIn("uses:", source[source.index("secrets.IOS_TF") :])
        ci = (hosted.ROOT / ".github/workflows/python-tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('discover -s tools/tests -p "test_ios_testflight_*.py"', ci)


if __name__ == "__main__":
    unittest.main()
