"""Fictional runner contracts only; no actual Secret, Owner files or GitHub API."""

import contextlib
import io
import json
import os
import platform
import stat
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from tools import ios_profile_cms_rehearsal as fixtures
from tools import ios_profile_intake as intake
from tools import ios_profile_verification_runner as runner

SHA = "a" * 40
BINDING = {"sha": SHA, "nonce": "b" * 64, "run_id": "42"}
ENV = {
    "GITHUB_REPOSITORY": intake.REPO,
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_SHA": SHA,
    "INPUT_APPROVED_SHA": SHA,
    "INPUT_NONCE": "b" * 64,
    "GITHUB_RUN_ID": "42",
}


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.fixture()
        cls.raw = intake.envelope(
            cls.fixture["cms"],
            cls.fixture["der"],
            fixtures.TEAM,
            SHA,
            42,
            "b" * 64,
            fixtures.NOW,
        ).decode("ascii")

    def test_envelope_exact_binding_ttl_types_and_no_duplicate(self):
        self.assertEqual(
            runner.decode_envelope(self.raw, BINDING, fixtures.NOW)["profile"],
            self.fixture["cms"],
        )
        for key, value in [
            ("version", True),
            ("run_id", "43"),
            ("sha", "c" * 40),
            ("nonce", "c" * 64),
            ("issued_at", True),
            ("team", "private-string"),
            ("profile", "!"),
            ("certificate", ""),
        ]:
            envelope = json.loads(self.raw)
            envelope[key] = value
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(runner.cms.Rejected, "ENVELOPE_REJECTED"),
            ):
                runner.decode_envelope(json.dumps(envelope), BINDING, fixtures.NOW)
        for now in [
            fixtures.NOW + timedelta(hours=1),
            fixtures.NOW - timedelta(seconds=1),
            fixtures.NOW.replace(tzinfo=None),
        ]:
            with self.assertRaisesRegex(runner.cms.Rejected, "ENVELOPE_REJECTED"):
                runner.decode_envelope(self.raw, BINDING, now)
        for raw in [
            None,
            "x" * (intake.MAX_ENVELOPE + 1),
            '{"version":1,"version":1}',
            "private-string",
        ]:
            with self.assertRaisesRegex(runner.cms.Rejected, "ENVELOPE_REJECTED"):
                runner.decode_envelope(raw, BINDING, fixtures.NOW)

    def test_run_context_rejects_rerun_fork_ref_sha_and_nonce(self):
        with patch.dict(os.environ, ENV):
            self.assertEqual(runner.context(), BINDING)
            for key, value in [
                ("GITHUB_RUN_ATTEMPT", "2"),
                ("GITHUB_REF", "refs/heads/other"),
                ("GITHUB_REPOSITORY", "other/repo"),
                ("GITHUB_EVENT_NAME", "push"),
                ("GITHUB_SHA", "c" * 40),
                ("INPUT_NONCE", "private-string"),
            ]:
                with (
                    patch.dict(os.environ, {key: value}),
                    self.assertRaisesRegex(runner.cms.Rejected, "CONTEXT_REJECTED"),
                ):
                    runner.context()

    @contextlib.contextmanager
    def prepared_fixture(self):
        with tempfile.TemporaryDirectory(
            prefix="fictional-public-runner-"
        ) as temporary:
            root = Path(temporary).resolve()
            source = root / "fixture-code"
            source.write_bytes(b"fictional-compiled-public-code")
            target = root / runner.DIRECTORY
            original_lstat = Path.lstat

            def lstat(path, *args, **kwargs):
                info = original_lstat(path, *args, **kwargs)
                if path == target:
                    items = list(info)
                    items[0] = stat.S_IFDIR | 0o700
                    items[4] = 0
                    return os.stat_result(items)
                return info

            @contextlib.contextmanager
            def compile_code():
                self.assertNotIn(intake.SECRET, os.environ)
                yield source

            with (
                patch.dict(os.environ, ENV),
                patch.object(runner, "directory", return_value=target),
                patch.object(runner.platform, "system", return_value="Darwin"),
                patch.object(runner.platform, "machine", return_value="arm64"),
                patch.object(runner.intake.preparation, "git", return_value=SHA),
                patch.object(runner.cms, "_compile_native", side_effect=compile_code),
                patch.object(
                    runner, "regular", side_effect=lambda path, maximum: path.stat()
                ),
                patch.object(Path, "lstat", lstat),
                patch.object(runner.os, "getuid", return_value=0, create=True),
            ):
                try:
                    yield target
                finally:
                    os.environ.pop(intake.SECRET, None)
                    runner.cleanup()

    def test_actual_phase_copy_receipt_consume_replay_and_cleanup(self):
        with self.prepared_fixture() as target:
            self.assertEqual(runner.prepare(), "PREPARED")
            self.assertEqual(runner.prepared(BINDING), target / "native")
            with self.assertRaisesRegex(runner.cms.Rejected, "RECEIPT_REJECTED"):
                runner.prepared(BINDING)
            self.assertEqual(runner.cleanup(), "REMOVED")
            self.assertFalse(target.exists())

    def test_receipt_changed_binary_binding_and_partial_prepare_cleanup(self):
        for kind in ["binary", "sha"]:
            with self.prepared_fixture() as target:
                runner.prepare()
                if kind == "binary":
                    (target / "native").write_bytes(b"fictional-different-code")
                else:
                    receipt = json.loads((target / "receipt.json").read_text())
                    receipt["sha"] = "c" * 40
                    (target / "receipt.json").write_text(json.dumps(receipt))
                with self.assertRaisesRegex(runner.cms.Rejected, "RECEIPT_REJECTED"):
                    runner.prepared(BINDING)
        with self.prepared_fixture() as target:
            with (
                patch.object(
                    runner.cms,
                    "_compile_native",
                    side_effect=runner.cms.Rejected("NATIVE_COMPILE_FAILED"),
                ),
                self.assertRaises(runner.cms.Rejected),
            ):
                runner.prepare()
            self.assertTrue(target.exists())
            self.assertEqual(runner.cleanup(), "REMOVED")

    def test_private_environment_never_enters_compiler_or_native_child_env(self):
        with (
            patch.dict(os.environ, {intake.SECRET: "fictional-envelope"}),
            patch.object(runner.cms, "_compile_native") as compile_code,
            self.assertRaisesRegex(runner.cms.Rejected, "PREPARATION_REJECTED"),
        ):
            runner.prepare()
        compile_code.assert_not_called()
        with (
            patch.dict(os.environ, {**ENV, intake.SECRET: self.raw}),
            patch.object(runner, "prepared", return_value=Path("fictional-code")),
            patch.object(
                runner,
                "decode_envelope",
                return_value={
                    "profile": self.fixture["cms"],
                    "certificate": self.fixture["der"],
                    "team": fixtures.TEAM,
                },
            ),
            patch.object(
                runner.cms,
                "_native_verified",
                side_effect=runner.cms.Rejected("CMS_TRUST_REJECTED"),
            ) as native,
            self.assertRaisesRegex(runner.cms.Rejected, "CMS_TRUST_REJECTED"),
        ):
            runner.verify()
        self.assertEqual(native.call_count, 1)

    def test_recomputed_digest_rejects_before_native_and_preserves_output_boundary(
        self,
    ):
        with (
            patch.dict(os.environ, {**ENV, intake.SECRET: self.raw}),
            patch.object(runner, "prepared", return_value=Path("fictional-code")),
            patch.object(
                runner,
                "decode_envelope",
                return_value={
                    "profile": fixtures.tampered(self.fixture["cms"], "content"),
                    "certificate": self.fixture["der"],
                    "team": fixtures.TEAM,
                },
            ),
            patch.object(runner.cms, "_native_verified") as native,
            self.assertRaisesRegex(runner.cms.Rejected, "CMS_STRUCTURE_REJECTED"),
        ):
            runner.verify()
        native.assert_not_called()

    def test_safe_fixed_output_no_private_cli_or_exception_echo(self):
        for args in [["private-string"], ["--verify", "private-string"]]:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(args), 1)
            self.assertNotIn("private-string", output.getvalue())
        with (
            patch.object(runner, "verify", side_effect=RuntimeError("private-string")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(runner.main(["--verify"]), 1)
        self.assertNotIn("private-string", output.getvalue())

    def test_workflow_is_manual_fixed_gate_and_private_step_only(self):
        source = (
            Path(__file__).resolve().parents[2]
            / ".github/workflows/ios-profile-verification.yml"
        ).read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("workflow_call:", source)
        self.assertIn("runs-on: macos-15", source)
        self.assertEqual(source.count("secrets.IOS_PROFILE_VERIFICATION_INPUT"), 1)
        self.assertLess(
            source.index("--prepare"),
            source.index("secrets.IOS_PROFILE_VERIFICATION_INPUT"),
        )
        self.assertIn("persist-credentials: false", source)
        self.assertIn("if: always()", source)
        for forbidden in [
            "upload-artifact",
            "actions/cache",
            "GH_TOKEN",
            "PAT",
            "write-all",
        ]:
            self.assertNotIn(forbidden, source)

    @unittest.skipUnless(
        platform.system() == "Darwin",
        "Actual production phase and fictional native rehearsal require hosted macOS",
    )
    def test_native_runner_rehearsal(self):
        self.assertEqual(runner.rehearsal(), "FICTIONAL_RUNNER_REHEARSAL_VERIFIED")


if __name__ == "__main__":
    unittest.main()
