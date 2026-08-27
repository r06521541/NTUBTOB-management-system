import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from tools import launch_production_event_management_rollout as launcher
from tools import portal_data_event_management_rollout as operator


class ProductionEventManagementRolloutUnitTests(unittest.TestCase):
    def test_artifacts_are_canonical_and_locked(self):
        launcher.verify_artifacts()

    def test_operator_rejects_additional_or_divergent_repository_head(self):
        for heads in (
            [operator.TARGET_REVISION, "fake_additional_head"],
            [operator.SOURCE_REVISION],
        ):
            scripts = MagicMock()
            scripts.get_heads.return_value = heads
            with patch.object(
                operator.ScriptDirectory, "from_config", return_value=scripts
            ), self.assertRaises(operator.RolloutError):
                operator.verify_artifact()

    def test_constraint_parser_rejects_same_literals_with_extra_logic(self):
        connection = MagicMock()
        connection.execute.return_value.all.return_value = [
            (
                "c",
                True,
                "CHECK (action = ANY (ARRAY['published','invitee_included',"
                "'invitee_excluded']) OR true)",
            )
        ]
        with self.assertRaises(operator.RolloutError):
            operator._constraint_actions(connection)

    def test_private_url_requires_password_and_exact_runtime_target(self):
        target = launcher.DatabaseTarget(
            hostname="pool.fake.invalid",
            port="5432",
            database="postgres",
            username="fake-user",
        )
        url = (
            "postgresql://fake-user:fake-password@pool.fake.invalid:5432/postgres"
            "?sslmode=require"
        )
        self.assertEqual(launcher._database_target(url), target)
        launcher._require_target_match(url, target)

        for value in (
            "postgresql://fake-user@pool.fake.invalid:5432/postgres",
            "postgresql://fake-user:fake-password@other.invalid:5432/postgres"
            "?sslmode=require",
            "postgresql://fake-user:fake-password@pool.fake.invalid:5432/postgres",
            "postgresql://fake-user:fake-password@pool.fake.invalid:5432/postgres"
            "?sslmode=disable",
            "postgresql://fake-user:fake-password@pool.fake.invalid:5432/postgres"
            "?sslmode=prefer",
            "postgresql://fake-user:fake-password@pool.fake.invalid:5432/postgres"
            "?sslmode=require&sslmode=verify-full",
            "postgresql://fake-user:fake-password@pool.fake.invalid:5432/postgres"
            "?sslmode=require&application_name=fake",
        ):
            with self.subTest(value=value), self.assertRaises(launcher.LauncherError):
                launcher._require_target_match(value, target)

        for sslmode in ("require", "verify-ca", "verify-full"):
            launcher._require_target_match(
                "postgresql://fake-user:fake-password@pool.fake.invalid:5432/"
                f"postgres?sslmode={sslmode}",
                target,
            )

    def test_append_only_gate_rejects_function_and_trigger_drift(self):
        expected = (
            "O",
            27,
            0,
            "",
            None,
            0,
            None,
            None,
            False,
            False,
            "ntubtob",
            0,
            True,
            "plpgsql",
            """
            BEGIN
              RAISE EXCEPTION 'audit rows are append-only';
            END;
            """,
        )
        connection = MagicMock()
        connection.execute.return_value.all.return_value = [expected]
        operator._validate_append_only(connection)

        drift_cases = (
            expected[:10] + ("public",) + expected[11:],
            expected[:14] + ("BEGIN RETURN NEW; END;",) + expected[15:],
            expected[:1] + (25,) + expected[2:],
            expected[:1] + (26,) + expected[2:],
            expected[:3] + ("2",) + expected[4:],
            expected[:4] + ("fake-when-clause",) + expected[5:],
            expected[:5] + (1,) + expected[6:],
            expected[:6] + ("old_rows",) + expected[7:],
            expected[:7] + ("new_rows",) + expected[8:],
            expected[:8] + (True,) + expected[9:],
            expected[:9] + (True,) + expected[10:],
        )
        for drift in drift_cases:
            with self.subTest(drift=drift):
                connection.execute.return_value.all.return_value = [drift]
                with self.assertRaises(operator.RolloutError):
                    operator._validate_append_only(connection)

    def test_runtime_contract_accepts_exact_ready_service_without_disclosure(self):
        service = {
            "metadata": {
                "name": launcher.SERVICE,
                "labels": {"cloud.googleapis.com/location": launcher.REGION},
                "annotations": {"run.googleapis.com/ingress": "all"},
            },
            "spec": {"template": {"spec": {"serviceAccountName": "fake-runtime"}}},
            "status": {
                "latestReadyRevisionName": launcher.EXPECTED_READY_REVISION,
                "traffic": [
                    {"revisionName": launcher.EXPECTED_READY_REVISION, "percent": 100}
                ],
            },
        }
        revision = {
            "metadata": {"name": launcher.EXPECTED_READY_REVISION},
            "spec": {
                "serviceAccountName": "fake-runtime",
                "containers": [
                    {
                        "env": [
                            {"name": "DSN_HOSTNAME", "value": "pool.fake.invalid"},
                            {"name": "DSN_PORT", "value": "5432"},
                            {"name": "DSN_DATABASE", "value": "postgres"},
                            {"name": "DSN_UID", "value": "fake-user"},
                            *(
                                {
                                    "name": name,
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "fake-ref",
                                            "key": "1",
                                        }
                                    },
                                }
                                for name in launcher.REQUIRED_SECRET_KEYS
                            ),
                            {
                                "name": "PORTAL_DATA_PHASE_C_ENABLED",
                                "value": "true",
                            },
                            {
                                "name": "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED",
                                "value": "false",
                            },
                            {
                                "name": "WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED",
                                "value": "true",
                            },
                        ]
                    }
                ],
            },
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        policy = {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            target = launcher._validate_cloud_contract(service, revision, policy)
        self.assertEqual(target.hostname, "pool.fake.invalid")
        self.assertEqual(output.getvalue(), "")

        revision["spec"]["containers"][0]["env"].append(
            {"name": "WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID", "value": "fake"}
        )
        with self.assertRaises(launcher.LauncherError):
            launcher._validate_cloud_contract(service, revision, policy)

    def test_cloud_inventory_uses_fixed_commands_and_clears_raw_documents(self):
        documents = [
            {"status": {"latestReadyRevisionName": launcher.EXPECTED_READY_REVISION}},
            {"revision": "fake"},
            {"policy": "fake"},
        ]
        observed = []

        def fake_document(command, label):
            observed.append((command, label))
            return documents[len(observed) - 1]

        with patch.object(
            launcher, "_json_document", side_effect=fake_document
        ), patch.object(
            launcher, "_active_account_present", return_value=True
        ), patch.object(
            launcher, "_validate_cloud_contract", return_value=MagicMock()
        ):
            launcher._load_cloud_target()
        self.assertEqual(len(observed), 3)
        self.assertTrue(all("--project" in command for command, _ in observed))
        self.assertEqual(documents, [{}, {}, {}])

    def test_cloud_command_failure_does_not_disclose_captured_streams(self):
        completed = MagicMock(
            returncode=1,
            stdout=b"postgresql://fake-user:fake-password@fake.invalid/db",
            stderr=b"private-account@example.invalid",
        )
        with patch.object(
            launcher.subprocess, "run", return_value=completed
        ), self.assertRaises(launcher.LauncherError) as caught:
            launcher._json_document(["gcloud", "fake"], "Cloud Run service")
        self.assertEqual(str(caught.exception), "Cloud Run service inventory failed")
        self.assertNotIn("fake-password", str(caught.exception))
        self.assertNotIn("private-account", str(caught.exception))

    def test_execute_requires_clean_exact_merged_main(self):
        approved = "a" * 40
        observed = []

        def fake_run(command):
            observed.append(command)
            values = {
                ("status", "--porcelain"): "",
                ("branch", "--show-current"): "main",
                ("rev-parse", "HEAD"): approved,
                ("rev-parse", "origin/main"): approved,
            }
            return values[tuple(command[1:])]

        with patch.object(
            launcher.Path, "cwd", return_value=launcher.ROOT
        ), patch.object(launcher.sys, "version_info", (3, 10, 99)), patch.object(
            launcher.importlib.metadata,
            "version",
            side_effect=lambda name: launcher.REQUIRED_PACKAGES[name],
        ), patch.object(
            launcher.shutil, "which", return_value="git"
        ), patch.object(
            launcher, "_run_text", side_effect=fake_run
        ):
            launcher._verify_repository(True, approved)
        self.assertEqual(
            observed[-3:],
            [
                ["git", "branch", "--show-current"],
                ["git", "rev-parse", "HEAD"],
                ["git", "rev-parse", "origin/main"],
            ],
        )

        def wrong_branch(command):
            if command[1:] == ["status", "--porcelain"]:
                return ""
            if command[1:] == ["branch", "--show-current"]:
                return "codex/task-164-event-production-rollout"
            return approved

        with patch.object(
            launcher.Path, "cwd", return_value=launcher.ROOT
        ), patch.object(launcher.sys, "version_info", (3, 10, 99)), patch.object(
            launcher.importlib.metadata,
            "version",
            side_effect=lambda name: launcher.REQUIRED_PACKAGES[name],
        ), patch.object(
            launcher.shutil, "which", return_value="git"
        ), patch.object(
            launcher, "_run_text", side_effect=wrong_branch
        ), self.assertRaises(
            launcher.LauncherError
        ):
            launcher._verify_repository(True, approved)

    def test_dry_run_rejects_unmerged_task_branch(self):
        approved = "a" * 40

        def task_branch(command):
            values = {
                ("status", "--porcelain"): "",
                ("branch", "--show-current"): (
                    "codex/task-164-event-production-rollout"
                ),
                ("rev-parse", "HEAD"): approved,
                ("rev-parse", "origin/main"): approved,
            }
            return values[tuple(command[1:])]

        with patch.object(
            launcher.Path, "cwd", return_value=launcher.ROOT
        ), patch.object(launcher.sys, "version_info", (3, 10, 99)), patch.object(
            launcher.importlib.metadata,
            "version",
            side_effect=lambda name: launcher.REQUIRED_PACKAGES[name],
        ), patch.object(
            launcher.shutil, "which", return_value="git"
        ), patch.object(
            launcher, "_run_text", side_effect=task_branch
        ), self.assertRaises(
            launcher.LauncherError
        ):
            launcher._verify_repository(False, None)

    def test_launcher_dry_run_never_sets_execution_ack_and_clears_url(self):
        observed = []

        def fake_run(mode, database_url, acknowledgement=None):
            observed.append((mode, database_url, acknowledgement))

        with patch.object(launcher, "verify_artifacts"), patch.object(
            launcher, "_verify_repository"
        ), patch.object(
            launcher, "_load_cloud_target", return_value=MagicMock()
        ), patch.object(
            launcher, "_require_target_match"
        ), patch.object(
            launcher.getpass, "getpass", return_value="postgresql://fake"
        ), patch.object(
            operator, "run", side_effect=fake_run
        ):
            launcher.run(execute=False)
        self.assertEqual(observed, [("dry-run", "postgresql://fake", None)])

    def test_cli_failure_is_generic_and_never_discloses_private_input(self):
        with patch.object(
            launcher, "run", side_effect=RuntimeError("fake-password")
        ), self.assertRaises(SystemExit) as caught:
            launcher.main([])
        self.assertEqual(
            str(caught.exception), "TASK-164 production rollout stopped safely"
        )
        self.assertNotIn("fake-password", str(caught.exception))

    def test_operator_rejects_forward_divergent_and_unacknowledged_execution(self):
        for revision in (operator.TARGET_REVISION, "fake_divergent"):
            connection = MagicMock()
            connection.execute.return_value = MagicMock()
            with patch.object(
                operator, "_current_revision", return_value=revision
            ), self.assertRaises(operator.RolloutError):
                operator._run_locked(connection, execute=False)

        with self.assertRaises(operator.RolloutError):
            operator.run(
                "execute",
                "postgresql://fake-user:fake-password@fake.invalid/db",
                acknowledgement=None,
                engine_factory=MagicMock(),
            )

    def test_migration_source_contains_no_application_dml(self):
        source = operator.MIGRATION.read_text(encoding="utf-8").upper()
        for token in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
