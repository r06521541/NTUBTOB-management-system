import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from apps.mobile_staging_broker.broker import BrokerFailure
from tools.mobile_staging_broker_rollout import (APPROVAL_PATH, ARCHIVE_PATHS,
                                                 BrokerRolloutError,
                                                 _assert_path_chain_no_reparse,
                                                 _read_approval_bytes,
                                                 prepare_broker_rollout)


class MobileStagingBrokerRolloutTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for relative in ARCHIVE_PATHS:
            path = self.source / relative
            if Path(relative).suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"fixture:{relative}\n", encoding="utf-8")
            else:
                path.mkdir(parents=True, exist_ok=True)
                (path / "fixture.txt").write_text("fixture\n", encoding="utf-8")
        broker = self.source / "apps/mobile_staging_broker"
        for name in (
            "app.py",
            "artifacts.py",
            "bootstrap.py",
            "broker.py",
            "Dockerfile",
            "Dockerfile.dockerignore",
            "journal.py",
            "operator.py",
            "requirements.txt",
            "runtime.py",
        ):
            (broker / name).write_text(f"fixture:{name}\n", encoding="utf-8")
        (self.source / "migrations/versions/0006_staging_broker_operation_journal.py").write_text(
            "fixture migration\n", encoding="utf-8"
        )
        tracked_approval = self.source / APPROVAL_PATH
        tracked_approval.parent.mkdir(parents=True, exist_ok=True)
        tracked_approval.write_text("{}\n", encoding="utf-8")
        self._git("init")
        self._git("config", "user.email", "fixture@example.invalid")
        self._git("config", "user.name", "Fixture")
        self._git("add", ".")
        self._git("commit", "-m", "fixture")
        self.commit = self._git("rev-parse", "HEAD").strip()
        self.approval = self.root / "private-approval.json"
        self.sentinel = "PRIVATE_APPROVAL_SENTINEL"
        approval_text = json.dumps(self._approval_value(), indent=2).replace(
            "\n", "\r\n"
        )
        self.approval.write_bytes(approval_text.encode("utf-8"))
        self.output = self.root / "output"

    def tearDown(self):
        self.temp.cleanup()

    def _git(self, *arguments):
        completed = subprocess.run(
            ["git", "-C", str(self.source), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout

    def _approval_value(self):
        return {
            "owner_approved": True,
            "project": "ntubtob-mobile-staging",
            "region": "asia-east1",
            "service": "mobile-api-staging",
            "approved_commit": "a" * 40,
            "approval_phase": "candidate",
            "build_id": "build-task135-fixture",
            "image_uri": "asia-east1-docker.pkg.dev/ntubtob-mobile-staging/mobile-staging/mobile-api",
            "image_digest": "sha256:" + "b" * 64,
            "mode": "update",
            "candidate_revision": "mobile-api-staging-candidate1",
            "rollback_revision": "mobile-api-staging-baseline1",
            "database_identity_sha256": "5458aab22f538d601725365e26a01d6d585f0e7d07dc32451cd6309d61a40d7c",
            "production_database_identity_sha256": "f" * 64,
            "database_provider": "cloudsql",
            "database_resource_id": "projects/ntubtob-mobile-staging/instances/mobile-db",
            "database_alias": self.sentinel,
            "max_instances": 2,
            "service_account": "mobile-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com",
            "build_service_account": "mobile-build@ntubtob-mobile-staging.iam.gserviceaccount.com",
            "runtime_secret_refs": {
                "PORTAL_DATA_DATABASE_URL": "mobile-staging-database-url:7",
                "MOBILE_ACCESS_SIGNING_KEY": "mobile-staging-access-key:3",
                "MOBILE_REFRESH_REPLAY_KEY": "mobile-staging-refresh-key:5",
            },
            "mobile_api_audience": "1234567890",
        }

    def test_prepares_exact_context_and_redacted_state(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            state = prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit=self.commit,
            )
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(state["classification"], "PASS")
        self.assertEqual(state["result"], "prepared")
        self.assertNotIn(self.sentinel, json.dumps(state))
        packaged = json.loads(
            (self.output / "context" / APPROVAL_PATH).read_text(encoding="utf-8")
        )
        self.assertEqual(packaged["database_alias"], self.sentinel)
        self.assertEqual(
            (self.output / "context" / APPROVAL_PATH).read_bytes(),
            self.approval.read_bytes().replace(b"\r\n", b"\n"),
        )
        self.assertTrue((self.output / "context/apps/mobile_staging_broker/Dockerfile").is_file())
        self.assertFalse((self.output / "source.tar").exists())
        persisted = (self.output / "state.json").read_text(encoding="utf-8")
        self.assertNotIn(self.sentinel, persisted)
        self.assertNotIn("runtime_secret_refs", persisted)

    def test_repeated_packaging_has_identical_artifact_hashes(self):
        second_output = self.root / "output-two"
        first = prepare_broker_rollout(
            source=self.source,
            approval_path=self.approval,
            output=self.output,
            commit=self.commit,
        )
        second = prepare_broker_rollout(
            source=self.source,
            approval_path=self.approval,
            output=second_output,
            commit=self.commit,
        )
        for name in (
            "candidate_approval_sha256",
            "operator_artifact_sha256",
            "broker_artifact_sha256",
        ):
            self.assertEqual(first[name], second[name])

    def test_failure_after_private_copy_removes_partial_context(self):
        from tools import mobile_staging_broker_rollout as module

        with mock.patch.object(
            module,
            "artifact_hashes",
            side_effect=BrokerRolloutError("HASH_FAILED"),
        ):
            with self.assertRaisesRegex(BrokerRolloutError, "HASH_FAILED"):
                prepare_broker_rollout(
                    source=self.source,
                    approval_path=self.approval,
                    output=self.output,
                    commit=self.commit,
                )
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".output.partial-*")), [])

    def test_private_cleanup_failure_is_fixed_and_redacted(self):
        from tools import mobile_staging_broker_rollout as module

        with mock.patch.object(
            module,
            "artifact_hashes",
            side_effect=BrokerRolloutError("HASH_FAILED"),
        ), mock.patch.object(module.shutil, "rmtree", side_effect=OSError("sentinel")):
            with self.assertRaisesRegex(
                BrokerRolloutError, "PRIVATE_CLEANUP_REQUIRED"
            ):
                prepare_broker_rollout(
                    source=self.source,
                    approval_path=self.approval,
                    output=self.output,
                    commit=self.commit,
                )

    def test_rejects_dirty_and_wrong_commit_without_partial_output(self):
        (self.source / "untracked.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaisesRegex(BrokerRolloutError, "SOURCE_DIRTY"):
            prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit=self.commit,
            )
        (self.source / "untracked.txt").unlink()
        with self.assertRaisesRegex(BrokerRolloutError, "COMMIT_DRIFT"):
            prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit="c" * 40,
            )
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".output.partial-*")), [])

    def test_rejects_approval_drift_and_existing_output(self):
        value = self._approval_value()
        value["project"] = "fictional-mobile-staging"
        value["image_uri"] = "asia-east1-docker.pkg.dev/fictional-mobile-staging/mobile-staging/mobile-api"
        value["service_account"] = "mobile-runtime@fictional-mobile-staging.iam.gserviceaccount.com"
        value["build_service_account"] = "mobile-build@fictional-mobile-staging.iam.gserviceaccount.com"
        self.approval.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(BrokerRolloutError, "APPROVAL_DRIFT"):
            prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit=self.commit,
            )

    def test_rejects_independently_mismatched_database_identity(self):
        value = self._approval_value()
        value["database_identity_sha256"] = "d" * 64
        self.approval.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(BrokerRolloutError, "APPROVAL_DRIFT"):
            prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit=self.commit,
            )

    def test_original_path_chain_reparse_is_rejected(self):
        from tools import mobile_staging_broker_rollout as module

        marked = self.source.parent
        original = module._is_reparse
        with mock.patch.object(
            module,
            "_is_reparse",
            side_effect=lambda path: path == marked or original(path),
        ):
            with self.assertRaisesRegex(BrokerRolloutError, "PATH_INVALID"):
                _assert_path_chain_no_reparse(self.source)

    def test_approval_open_identity_race_is_rejected(self):
        actual = os.stat(self.approval, follow_symlinks=False)
        replaced = SimpleNamespace(
            st_dev=actual.st_dev,
            st_ino=actual.st_ino + 1,
            st_size=actual.st_size,
        )
        with mock.patch(
            "tools.mobile_staging_broker_rollout.os.stat",
            side_effect=(actual, replaced),
        ):
            with self.assertRaisesRegex(BrokerRolloutError, "APPROVAL_INVALID"):
                _read_approval_bytes(self.approval)

    def test_hardlinked_approval_is_rejected(self):
        hardlink = self.root / "approval-hardlink.json"
        try:
            os.link(self.approval, hardlink)
        except OSError:
            self.skipTest("hardlink creation unavailable")
        with self.assertRaisesRegex(BrokerRolloutError, "APPROVAL_INVALID"):
            _read_approval_bytes(self.approval)
        self.output.mkdir()
        with self.assertRaisesRegex(BrokerRolloutError, "OUTPUT_INVALID"):
            prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit=self.commit,
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_rejects_symlinked_private_approval(self):
        target = self.root / "approval-target.json"
        self.approval.replace(target)
        try:
            os.symlink(target, self.approval)
        except OSError:
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(BrokerRolloutError, "PATH_INVALID"):
            prepare_broker_rollout(
                source=self.source,
                approval_path=self.approval,
                output=self.output,
                commit=self.commit,
            )

    def test_cli_failure_is_one_bounded_json_without_private_values(self):
        from tools import mobile_staging_broker_rollout as module

        with mock.patch.object(
            module,
            "_parse_args",
            return_value=mock.Mock(
                source=self.source,
                approval=self.approval,
                output=Path("C:/forbidden") / self.sentinel,
                commit=self.commit,
            ),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = module.main()
        lines = stdout.getvalue().splitlines()
        self.assertEqual(exit_code, 2)
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["classification"], "FAILED")
        self.assertEqual(payload["details"]["reason_code"], "OUTPUT_INVALID")
        self.assertNotIn(self.sentinel, lines[0])

    def test_real_broker_failure_has_one_governed_json(self):
        from tools import mobile_staging_broker_rollout as module

        with mock.patch.object(
            module,
            "_parse_args",
            return_value=mock.Mock(
                source=module.TOOL_ROOT,
                approval=self.approval,
                output=Path("E:/codex-evidence/task-135/output"),
                commit=self.commit,
            ),
        ), mock.patch.object(
            module, "_assert_path_chain_no_reparse"
        ), mock.patch.object(
            module, "prepare_broker_rollout", side_effect=BrokerFailure("sentinel")
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = module.main()
        lines = stdout.getvalue().splitlines()
        self.assertEqual(exit_code, 2)
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["details"]["reason_code"], "HASH_INVALID")
        self.assertNotIn("sentinel", lines[0])


if __name__ == "__main__":
    unittest.main()
