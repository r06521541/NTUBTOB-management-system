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

from tools import launch_production_activate_allowlisted_admins as launcher
from tools import portal_data_production_activate_allowlisted_admins as operator


class ExactTwoActivationContractTests(unittest.TestCase):
    def test_artifacts_and_sequence_are_locked(self):
        launcher.verify_artifacts()
        self.assertEqual(launcher.SEQUENCE, ("preflight", "execute", "post-check"))
        self.assertEqual(operator.ADMIN_LOCK_KEY, 70070)
        self.assertEqual(operator._allowlist("7001,7002"), frozenset({7001, 7002}))
        for value in ("", "7001", "7001,7001", "7001,7002,7003", "7001, 0"):
            with self.subTest(value=value), self.assertRaises(
                operator.ExactTwoActivationError
            ):
                operator._allowlist(value)

    def test_operator_has_fixed_transaction_and_no_identifier_arguments(self):
        source = operator.ARTIFACT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        self.assertIn("session.execute", calls)
        self.assertIn("session.flush", calls)
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertIn("with_for_update", source)
        self.assertNotIn("argparse", source)
        self.assertNotIn("sys.argv", source)
        self.assertNotIn("IdentityLifecycleRepository", source)
        self.assertNotIn("print(person", source)
        self.assertNotIn("print(member", source)

    def test_output_schema_is_fixed_and_redacted(self):
        values = dict(
            mode="execute",
            status="applied",
            schema_ready=True,
            logging_safe=True,
            allowlisted_member_count=2,
            active_admin_count=2,
            activation_delta=2,
            audit_delta=2,
            retry_verified=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator._emit(**values)
        self.assertEqual(json.loads(output.getvalue()), values)
        with self.assertRaises(operator.ExactTwoActivationError):
            operator._emit(**values, person_id=7001)

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
                    os.environ.get(operator.DATABASE_ENV),
                    os.environ.get(operator.ALLOWLIST_ENV),
                    os.environ.get(operator.EXECUTION_ENV),
                )
            )

        keys = (operator.DATABASE_ENV, operator.ALLOWLIST_ENV, operator.EXECUTION_ENV)
        with patch.dict(os.environ, {}, clear=False):
            for key in keys:
                os.environ.pop(key, None)
            with patch.object(launcher, "verify_artifacts"), patch.object(
                launcher, "_verify_runtime"
            ), patch.object(
                launcher.boundary,
                "_load_private_pg_environment",
                return_value=private,
            ), patch.object(
                launcher.boundary, "_load_allowlist", return_value="7001,7002"
            ), patch.object(
                launcher.boundary,
                "_database_url",
                return_value="postgresql+psycopg2://fake-user:fake-password@fake.invalid/fake-db",
            ), patch.object(
                operator, "run", side_effect=fake_run
            ):
                launcher.run({})
            self.assertTrue(all(os.environ.get(key) is None for key in keys))
        self.assertEqual([row[0] for row in observed], list(launcher.SEQUENCE))
        self.assertIsNone(observed[0][3])
        self.assertEqual(observed[1][3], operator.EXECUTION_ACKNOWLEDGEMENT)
        self.assertIsNone(observed[2][3])
        self.assertEqual(private, {})

    def test_launcher_failure_is_fixed_and_real_runtime_stops_before_external_access(
        self,
    ):
        environment = os.environ.copy()
        environment[launcher.APPROVED_COMMIT_ENV] = "0" * 40
        for key in (
            operator.DATABASE_ENV,
            operator.ALLOWLIST_ENV,
            operator.EXECUTION_ENV,
        ):
            environment.pop(key, None)
        result = subprocess.run(
            [str(launcher.boundary.RUNTIME_EXECUTABLE), str(launcher.ARTIFACT)],
            cwd=launcher.ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "TASK-086 exact-two activation stopped")

    def test_metadata_failure_clears_private_values_before_operator(self):
        private = {
            "PGHOST": "fake.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake-db",
            "PGUSER": "fake-user",
            "PGPASSWORD": "fake-password",
        }
        with patch.object(launcher, "verify_artifacts"), patch.object(
            launcher, "_verify_runtime"
        ), patch.object(
            launcher.boundary,
            "_load_private_pg_environment",
            return_value=private,
        ), patch.object(
            launcher.boundary,
            "_load_allowlist",
            side_effect=RuntimeError("private-metadata"),
        ), patch.object(
            operator, "run"
        ) as operator_run, self.assertRaises(
            RuntimeError
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
            with patch.object(operator, "ARTIFACT", artifact), patch.object(
                operator, "CHECKSUM", checksum
            ), self.assertRaises(operator.ExactTwoActivationError):
                operator.verify_artifact()


if __name__ == "__main__":
    unittest.main()
