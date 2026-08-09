import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import launch_production_zero_admin_bootstrap as launcher


class ProductionZeroAdminLauncherTests(unittest.TestCase):
    def test_artifacts_and_exact_runtime_contract_are_locked(self):
        launcher.verify_artifacts()
        source = launcher.ARTIFACT.read_text(encoding="utf-8")
        self.assertIn('ACCOUNT = "yces3108@gmail.com"', source)
        self.assertIn('PROJECT = "ntubtob-schedule-405614"', source)
        self.assertIn('SERVICE = "web-portal"', source)
        self.assertIn('REGION = "asia-east1"', source)
        self.assertIn(
            r"C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
            source,
        )
        self.assertIn("RUNTIME_VERSION = (3, 12, 13)", source)
        self.assertIn(
            'PRIVATE_ENV_PATH = Path(r"C:\\Users\\USER\\.ntubtob-private\\backup.env")',
            source,
        )
        self.assertIn(
            'SEQUENCE = ("discovery", "preflight", "dry-run", "execute", "post-check")',
            source,
        )
        self.assertNotIn("shell=True", source)

    def test_private_env_parser_accepts_only_exact_pg_keys_without_output(self):
        fake_values = {
            "PGHOST": "fake-db.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake_database",
            "PGUSER": "fake_user",
            "PGPASSWORD": "fake_password",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.env"
            path.write_text(
                "\n".join(f"{key}={value}" for key, value in fake_values.items())
                + "\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch.object(
                launcher, "PRIVATE_ENV_PATH", path
            ), contextlib.redirect_stdout(output):
                loaded = launcher._load_private_pg_environment(path)
            self.assertEqual(loaded, fake_values)
            self.assertEqual(output.getvalue(), "")
            path.write_text(
                path.read_text(encoding="utf-8") + "EXTRA=fake\n", encoding="utf-8"
            )
            with patch.object(launcher, "PRIVATE_ENV_PATH", path), self.assertRaises(
                launcher.LauncherError
            ):
                launcher._load_private_pg_environment(path)

    def test_allowlist_uses_exact_env_metadata_and_clears_unrelated_values(self):
        response = bytearray(b"fake-response")
        error = bytearray(b"fake-error")
        metadata = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {"name": "ORDINARY", "value": "private-ordinary"},
                                    {
                                        "name": "SECRET_REF",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "key": "latest",
                                                "name": "private-secret-reference",
                                            }
                                        },
                                    },
                                    {
                                        "name": launcher.ALLOWLIST_NAME,
                                        "value": "7001,7002",
                                    },
                                ]
                            }
                        ]
                    }
                }
            }
        }
        output = io.StringIO()
        with patch.object(
            launcher, "_load_env_metadata", return_value=(response, error)
        ), patch.object(
            launcher.json, "loads", return_value=metadata
        ), contextlib.redirect_stdout(
            output
        ):
            self.assertEqual(launcher._load_allowlist(), "7001,7002")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(response, bytearray())
        self.assertEqual(error, bytearray())
        self.assertEqual(metadata, {})

    def test_metadata_rejects_ambiguity_obsolete_schema_and_secret_allowlist(self):
        plain = {"name": launcher.ALLOWLIST_NAME, "value": "7001"}

        def document(entries, *, containers=None, extra=None):
            value = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": (
                                [{"env": entries}] if containers is None else containers
                            )
                        }
                    }
                }
            }
            if extra is not None:
                value["unexpected"] = extra
            return value

        cases = (
            document([]),
            document([plain, plain.copy()]),
            document([{"name": launcher.ALLOWLIST_NAME, "value": ""}]),
            document(
                [
                    {
                        "name": launcher.ALLOWLIST_NAME,
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "latest",
                                "name": "fake-secret",
                            }
                        },
                    }
                ]
            ),
            document(
                [
                    plain,
                    {
                        "name": "OBSOLETE",
                        "valueFrom": {
                            "secretKeyRef": {
                                "secret": "fake-secret",
                                "version": "latest",
                            }
                        },
                    },
                ]
            ),
            document([plain], containers=[]),
            document([plain], containers=[{"env": [plain]}, {"env": []}]),
            document([plain], extra="unexpected"),
        )
        for metadata in cases:
            with self.subTest(metadata=metadata), self.assertRaises(
                launcher.LauncherError
            ) as caught:
                launcher._extract_plain_allowlist(metadata)
            self.assertEqual(str(caught.exception), "metadata boundary failed")
            self.assertNotIn("fake-secret", str(caught.exception))

    def test_metadata_command_is_fixed_and_captures_both_streams(self):
        completed = MagicMock(returncode=0, stdout=b"{}", stderr=b"fake-error")
        with patch.object(launcher, "subprocess") as subprocess_module:
            subprocess_module.run.return_value = completed
            response, error = launcher._load_env_metadata()
        subprocess_module.run.assert_called_once_with(
            [
                str(launcher.GCLOUD),
                "run",
                "services",
                "describe",
                launcher.SERVICE,
                "--account",
                launcher.ACCOUNT,
                "--project",
                launcher.PROJECT,
                "--region",
                launcher.REGION,
                f"--format={launcher.METADATA_FORMAT}",
            ],
            cwd=launcher.ROOT,
            check=False,
            capture_output=True,
            text=False,
            timeout=30,
        )
        self.assertEqual(response, bytearray(b"{}"))
        self.assertEqual(error, bytearray(b"fake-error"))

    def test_runtime_guards_exact_commit_account_project_python_and_dependencies(self):
        approved = "a" * 40
        commands = []

        def fake_run(command):
            commands.append(command)
            if command[1:3] == ["rev-parse", "HEAD"]:
                return approved
            if command[1:3] == ["status", "--porcelain"]:
                return ""
            if "auth" in command:
                return launcher.ACCOUNT
            return launcher.PROJECT

        with patch.object(
            launcher.Path, "cwd", return_value=launcher.ROOT
        ), patch.object(
            launcher.sys, "executable", str(launcher.RUNTIME_EXECUTABLE)
        ), patch.object(
            launcher.sys, "version_info", (3, 12, 13)
        ), patch.object(
            launcher.importlib.metadata,
            "version",
            side_effect=lambda name: launcher.REQUIRED_PACKAGES[name],
        ), patch.object(
            launcher.Path, "is_file", return_value=True
        ), patch.object(
            launcher, "_run", side_effect=fake_run
        ):
            launcher._verify_runtime({launcher.APPROVED_COMMIT_ENV: approved})
        self.assertEqual(commands[0], [launcher.GIT, "rev-parse", "HEAD"])
        self.assertEqual(commands[1], [launcher.GIT, "status", "--porcelain"])
        self.assertIn("--filter=status:ACTIVE", commands[2])
        self.assertEqual(
            commands[3],
            [str(launcher.GCLOUD), "config", "get-value", "project", "--quiet"],
        )

    def test_documented_runtime_real_subprocess_stops_before_external_access(self):
        environment = os.environ.copy()
        environment[launcher.APPROVED_COMMIT_ENV] = "0" * 40
        for key in (
            launcher.operator.DATABASE_ENV,
            launcher.operator.ALLOWLIST_ENV,
            launcher.operator.EXECUTION_ENV,
        ):
            environment.pop(key, None)
        result = subprocess.run(
            [str(launcher.RUNTIME_EXECUTABLE), str(launcher.ARTIFACT)],
            cwd=launcher.ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "TASK-086 production launcher stopped")

    def test_sequence_uses_process_only_values_and_finally_restores_environment(self):
        private = {
            "PGHOST": "fake-db.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake_database",
            "PGUSER": "fake_user",
            "PGPASSWORD": "fake_password",
        }
        observed = []
        sensitive_keys = (
            launcher.operator.DATABASE_ENV,
            launcher.operator.ALLOWLIST_ENV,
            launcher.operator.EXECUTION_ENV,
        )

        def fake_operator_run(mode):
            observed.append(
                (
                    mode,
                    os.environ.get(launcher.operator.DATABASE_ENV),
                    os.environ.get(launcher.operator.ALLOWLIST_ENV),
                    os.environ.get(launcher.operator.EXECUTION_ENV),
                )
            )

        with patch.dict(os.environ, {}, clear=False):
            for key in sensitive_keys:
                os.environ.pop(key, None)
            with patch.object(launcher, "verify_artifacts"), patch.object(
                launcher, "_verify_runtime"
            ), patch.object(
                launcher, "_load_private_pg_environment", return_value=private
            ), patch.object(
                launcher, "_load_allowlist", return_value="7001"
            ), patch.object(
                launcher.operator, "run", side_effect=fake_operator_run
            ):
                launcher.run({launcher.APPROVED_COMMIT_ENV: "a" * 40})
            self.assertEqual([row[0] for row in observed], list(launcher.SEQUENCE))
            self.assertTrue(all("fake_password" in row[1] for row in observed))
            self.assertTrue(all(row[2] == "7001" for row in observed))
            self.assertIsNone(observed[0][3])
            self.assertEqual(
                observed[3][3], launcher.operator.EXECUTION_ACKNOWLEDGEMENT
            )
            self.assertIsNone(observed[4][3])
            for key in sensitive_keys:
                self.assertIsNone(os.environ.get(key))

    def test_preexisting_sensitive_environment_fails_before_subprocess(self):
        with patch.dict(
            os.environ, {launcher.operator.ALLOWLIST_ENV: "fake-value"}, clear=False
        ), patch.object(launcher, "_run") as run_command, self.assertRaises(
            launcher.LauncherError
        ):
            launcher._require_clean_process_environment()
        run_command.assert_not_called()

    def test_failure_cleanup_and_cli_message_do_not_disclose_values(self):
        private = {
            "PGHOST": "fake-db.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake_database",
            "PGUSER": "fake_user",
            "PGPASSWORD": "fake_password",
        }
        with patch.dict(os.environ, {}, clear=False):
            for key in (
                launcher.operator.DATABASE_ENV,
                launcher.operator.ALLOWLIST_ENV,
                launcher.operator.EXECUTION_ENV,
            ):
                os.environ.pop(key, None)
            with patch.object(launcher, "verify_artifacts"), patch.object(
                launcher, "_verify_runtime"
            ), patch.object(
                launcher, "_load_private_pg_environment", return_value=private
            ), patch.object(
                launcher, "_load_allowlist", return_value="7001"
            ), patch.object(
                launcher.operator,
                "run",
                side_effect=RuntimeError("fake_password 7001"),
            ):
                with self.assertRaises(RuntimeError):
                    launcher.run({launcher.APPROVED_COMMIT_ENV: "a" * 40})
        with patch.object(
            launcher, "run", side_effect=RuntimeError("fake_password 7001")
        ), self.assertRaises(SystemExit) as caught:
            launcher.main()
        self.assertEqual(str(caught.exception), "TASK-086 production launcher stopped")
        self.assertNotIn("fake_password", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
