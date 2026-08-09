import ast
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import launch_production_activate_linked_players as launcher
from tools import portal_data_production_activate_linked_players as operator


class LinkedPlayerActivationContractTests(unittest.TestCase):
    def test_artifacts_sequence_and_dynamic_cohort_are_locked(self):
        launcher.verify_artifacts()
        self.assertEqual(
            launcher.SEQUENCE, ("discovery", "preflight", "execute", "post-check")
        )
        source = operator.ARTIFACT.read_text(encoding="utf-8")
        self.assertNotIn("54", source)
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertIn("with_for_update", source)

    def test_operator_has_no_identifier_arguments_or_unrelated_repository(self):
        source = operator.ARTIFACT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        self.assertNotIn("argparse", source)
        self.assertNotIn("sys.argv", source)
        self.assertNotIn("IdentityLifecycleRepository", source)
        self.assertNotIn("print(person", source)
        self.assertNotIn("print(member", source)
        self.assertIn("session.flush", calls)

    def test_fixed_output_rejects_identifier_fields(self):
        values = dict(
            mode="discovery",
            status="ready",
            schema_ready=True,
            logging_safe=True,
            eligible_cohort_count=4,
            active_control_count=2,
            drift_count=0,
            activation_delta=0,
            audit_delta=0,
            retry_verified=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator._emit(**values)
        self.assertEqual(json.loads(output.getvalue()), values)
        with self.assertRaises(operator.LinkedPlayerActivationError):
            operator._emit(**values, member_ids=[7003])

    def test_launcher_sequence_uses_process_only_values_and_cleans_up(self):
        observed = []
        private = {
            "PGHOST": "fake.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake-db",
            "PGUSER": "fake-user",
            "PGPASSWORD": "fake-password",
        }

        def fake_run(mode):
            observed.append(
                (
                    mode,
                    os.environ.get(operator.boundary.DATABASE_ENV),
                    os.environ.get(operator.boundary.ALLOWLIST_ENV),
                    os.environ.get(operator.EXECUTION_ENV),
                )
            )

        keys = (
            operator.boundary.DATABASE_ENV,
            operator.boundary.ALLOWLIST_ENV,
            operator.EXECUTION_ENV,
        )
        with patch.dict(os.environ, {}, clear=False):
            for key in keys:
                os.environ.pop(key, None)
            with (
                patch.object(launcher, "verify_artifacts"),
                patch.object(launcher, "_verify_runtime"),
                patch.object(
                    launcher.boundary.boundary,
                    "_load_private_pg_environment",
                    return_value=private,
                ),
                patch.object(
                    launcher.boundary.boundary,
                    "_load_allowlist",
                    return_value="7001,7002",
                ),
                patch.object(
                    launcher.boundary.boundary,
                    "_database_url",
                    return_value="postgresql+psycopg2://fake-user:fake-password@fake.invalid/fake-db",
                ),
                patch.object(operator, "run", side_effect=fake_run),
            ):
                launcher.run({})
            self.assertTrue(all(os.environ.get(key) is None for key in keys))
        self.assertEqual([row[0] for row in observed], list(launcher.SEQUENCE))
        self.assertIsNone(observed[0][3])
        self.assertIsNone(observed[1][3])
        self.assertEqual(observed[2][3], operator.EXECUTION_ACKNOWLEDGEMENT)
        self.assertIsNone(observed[3][3])
        self.assertEqual(private, {})

    def test_failure_cleanup_and_real_runtime_safe_stop(self):
        environment = os.environ.copy()
        environment[launcher.APPROVED_COMMIT_ENV] = "0" * 40
        result = subprocess.run(
            [
                str(launcher.boundary.boundary.RUNTIME_EXECUTABLE),
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
            result.stderr.strip(), "TASK-087 linked-player activation stopped"
        )

    def test_metadata_failure_clears_private_values(self):
        private = {
            "PGHOST": "fake.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake-db",
            "PGUSER": "fake-user",
            "PGPASSWORD": "fake-password",
        }
        with (
            patch.object(launcher, "verify_artifacts"),
            patch.object(launcher, "_verify_runtime"),
            patch.object(
                launcher.boundary.boundary,
                "_load_private_pg_environment",
                return_value=private,
            ),
            patch.object(
                launcher.boundary.boundary,
                "_load_allowlist",
                side_effect=RuntimeError("private-metadata"),
            ),
            patch.object(operator, "run") as operator_run,
            self.assertRaises(RuntimeError),
        ):
            launcher.run({})
        self.assertEqual(private, {})
        operator_run.assert_not_called()

    def test_checksum_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / operator.ARTIFACT.name
            checksum = artifact.with_suffix(".py.sha256")
            artifact.write_text("mutated\n", encoding="utf-8")
            checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
            with (
                patch.object(operator, "ARTIFACT", artifact),
                patch.object(operator, "CHECKSUM", checksum),
                self.assertRaises(operator.LinkedPlayerActivationError),
            ):
                operator.verify_artifact()


if __name__ == "__main__":
    unittest.main()
