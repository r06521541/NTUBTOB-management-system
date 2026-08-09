import ast
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import launch_production_zero_admin_post_check as launcher


class ProductionZeroAdminPostCheckLauncherTests(unittest.TestCase):
    def test_source_has_one_fixed_mode_and_no_mutating_boundary(self):
        source = launcher.ARTIFACT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
        ]
        self.assertEqual(launcher.MODE, "post-check")
        self.assertEqual(len(run_calls), 1)
        self.assertEqual(ast.unparse(run_calls[0].func), "operator.run")
        self.assertEqual([ast.unparse(arg) for arg in run_calls[0].args], ["MODE"])
        self.assertNotIn("SEQUENCE", source)
        self.assertNotIn("EXECUTION_ACKNOWLEDGEMENT", source)
        self.assertNotIn("IdentityLifecycleRepository", source)
        self.assertNotIn("uuid", source)
        for forbidden in ('"discovery"', '"preflight"', '"dry-run"', '"execute"'):
            self.assertNotIn(forbidden, source)

    def test_artifacts_are_checksum_locked(self):
        launcher.verify_artifacts()
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / launcher.ARTIFACT.name
            checksum = artifact.with_suffix(".py.sha256")
            artifact.write_text("mutated\n", encoding="utf-8")
            checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
            with patch.object(launcher, "ARTIFACT", artifact), patch.object(
                launcher, "CHECKSUM", checksum
            ), self.assertRaises(launcher.RecoveryLauncherError):
                launcher.verify_artifacts()

    def test_runbook_documents_only_the_exact_recovery_command(self):
        runbook = (
            launcher.ROOT / "docs" / "operations" / "PHASE_C_ZERO_ADMIN_BOOTSTRAP.md"
        ).read_text(encoding="utf-8")
        recovery = runbook.split(
            "### Uncertain-outcome recovery: post-check only", maxsplit=1
        )[1]
        self.assertIn("tools/launch_production_zero_admin_post_check.py", recovery)
        self.assertIn("never run that\nlauncher again", recovery)
        self.assertNotIn("tools/launch_production_zero_admin_bootstrap.py", recovery)
        self.assertNotIn("--mode execute", recovery)

    def test_documented_runtime_real_subprocess_stops_before_external_access(self):
        environment = os.environ.copy()
        environment[launcher.production_launcher.APPROVED_COMMIT_ENV] = "0" * 40
        for key in (
            launcher.operator.DATABASE_ENV,
            launcher.operator.ALLOWLIST_ENV,
            launcher.operator.EXECUTION_ENV,
        ):
            environment.pop(key, None)
        result = subprocess.run(
            [
                str(launcher.production_launcher.RUNTIME_EXECUTABLE),
                str(launcher.ARTIFACT),
            ],
            cwd=launcher.ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr.strip(), "TASK-086 production post-check stopped"
        )

    def test_run_calls_only_post_check_without_execution_ack_and_cleans_up(self):
        private = {
            "PGHOST": "fake-db.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake_database",
            "PGUSER": "fake_user",
            "PGPASSWORD": "fake_password",
        }
        observed = []

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
            for key in (
                launcher.operator.DATABASE_ENV,
                launcher.operator.ALLOWLIST_ENV,
                launcher.operator.EXECUTION_ENV,
            ):
                os.environ.pop(key, None)
            with patch.object(launcher, "verify_artifacts"), patch.object(
                launcher.production_launcher, "_verify_runtime"
            ), patch.object(
                launcher.production_launcher,
                "_load_private_pg_environment",
                return_value=private,
            ), patch.object(
                launcher.production_launcher, "_load_allowlist", return_value="7001"
            ), patch.object(
                launcher.operator, "run", side_effect=fake_operator_run
            ):
                launcher.run(
                    {launcher.production_launcher.APPROVED_COMMIT_ENV: "a" * 40}
                )
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0], "post-check")
        self.assertIn("fake_password", observed[0][1])
        self.assertEqual(observed[0][2], "7001")
        self.assertIsNone(observed[0][3])
        self.assertIsNone(os.environ.get(launcher.operator.DATABASE_ENV))
        self.assertIsNone(os.environ.get(launcher.operator.ALLOWLIST_ENV))
        self.assertIsNone(os.environ.get(launcher.operator.EXECUTION_ENV))

    def test_failure_is_fixed_redacted_and_cleanup_is_unconditional(self):
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
                launcher.production_launcher, "_verify_runtime"
            ), patch.object(
                launcher.production_launcher,
                "_load_private_pg_environment",
                return_value=private,
            ), patch.object(
                launcher.production_launcher, "_load_allowlist", return_value="7001"
            ), patch.object(
                launcher.operator,
                "run",
                side_effect=RuntimeError("fake_password 7001"),
            ), self.assertRaises(
                RuntimeError
            ):
                launcher.run()
            self.assertIsNone(os.environ.get(launcher.operator.DATABASE_ENV))
            self.assertIsNone(os.environ.get(launcher.operator.ALLOWLIST_ENV))
            self.assertIsNone(os.environ.get(launcher.operator.EXECUTION_ENV))
        with patch.object(
            launcher, "run", side_effect=RuntimeError("fake_password 7001")
        ), self.assertRaises(SystemExit) as caught:
            launcher.main()
        self.assertEqual(
            str(caught.exception), "TASK-086 production post-check stopped"
        )
        self.assertNotIn("fake_password", str(caught.exception))

    def test_success_preserves_operator_fixed_redacted_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(
            launcher, "verify_artifacts"
        ), patch.object(launcher.production_launcher, "_verify_runtime"), patch.object(
            launcher.production_launcher,
            "_load_private_pg_environment",
            return_value={
                "PGHOST": "fake-db.invalid",
                "PGPORT": "5432",
                "PGDATABASE": "fake_database",
                "PGUSER": "fake_user",
                "PGPASSWORD": "fake_password",
            },
        ), patch.object(
            launcher.production_launcher, "_load_allowlist", return_value="7001"
        ), patch.object(
            launcher.operator, "run"
        ) as operator_run:
            launcher.run()
        operator_run.assert_called_once_with("post-check")
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
