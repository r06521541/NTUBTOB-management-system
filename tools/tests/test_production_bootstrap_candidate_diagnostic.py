import ast
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import portal_data_production_bootstrap_candidate_diagnostic as diagnostic


class ProductionBootstrapCandidateDiagnosticTests(unittest.TestCase):
    def test_artifact_runtime_and_materials_are_locked(self):
        diagnostic._verify_artifacts()
        source = diagnostic.ARTIFACT.read_text(encoding="utf-8")
        self.assertIn(
            'APPROVED_COMMIT_ENV = "TASK086_CANDIDATE_DIAGNOSTIC_APPROVED_MERGED_COMMIT"',
            source,
        )
        self.assertIn('text("SET TRANSACTION READ ONLY")', source)
        self.assertIn("SET LOCAL statement_timeout", source)
        self.assertIn("SET LOCAL lock_timeout", source)
        self.assertIn("SET LOCAL idle_in_transaction_session_timeout", source)

    def test_checksum_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / diagnostic.ARTIFACT.name
            checksum = artifact.with_suffix(".py.sha256")
            artifact.write_text("mutated\n", encoding="utf-8")
            checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
            with patch.object(diagnostic, "ARTIFACT", artifact), patch.object(
                diagnostic, "CHECKSUM", checksum
            ), self.assertRaises(diagnostic.CandidateDiagnosticError):
                diagnostic._verify_artifacts()

    def test_source_is_structurally_read_only(self):
        source = diagnostic.ARTIFACT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        calls = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        self.assertNotIn("tools.launch_production_zero_admin_bootstrap", imports)
        self.assertNotIn("tools.portal_data_production_zero_admin_bootstrap", imports)
        self.assertNotIn("IdentityLifecycleRepository", source)
        self.assertNotIn("uuid", imports)
        for call in (
            "session.add",
            "session.delete",
            "session.flush",
            "session.commit",
        ):
            self.assertNotIn(call, calls)
        for forbidden in (
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "ALTER ",
            "CREATE ",
            "DROP ",
        ):
            self.assertNotIn(forbidden, source)

    def test_fixed_output_rejects_values_and_extra_fields(self):
        result = diagnostic._default_result()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            diagnostic._emit(result)
        self.assertEqual(json.loads(output.getvalue()), result)
        for field, invalid in (
            ("runtime_artifact_git", "unknown"),
            ("allowlisted_member", "2"),
            ("person_state", "disabled"),
            ("reliable_line_identity", "fake-subject"),
        ):
            changed = dict(result)
            changed[field] = invalid
            with self.subTest(field=field), self.assertRaises(
                diagnostic.CandidateDiagnosticError
            ):
                diagnostic._emit(changed)
        changed = dict(result)
        changed["extra"] = "fail"
        with self.assertRaises(diagnostic.CandidateDiagnosticError):
            diagnostic._emit(changed)

    def test_failure_cleanup_and_cli_output_are_fixed(self):
        private = {
            "PGHOST": "private-host.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "private-db",
            "PGUSER": "private-user",
            "PGPASSWORD": "private-password",
        }
        engine = MagicMock()
        with patch.object(diagnostic, "_verify_runtime_git"), patch.object(
            diagnostic.boundary,
            "_verify_gcloud_and_load_allowlist",
            return_value={7001},
        ), patch.object(
            diagnostic.boundary,
            "_load_private_pg_environment",
            return_value=private,
        ), patch.object(
            diagnostic.boundary,
            "_database_url",
            return_value="postgresql+psycopg2://private-user:private-password@private-host.invalid/private-db",
        ), patch.object(
            diagnostic, "create_engine", return_value=engine
        ), patch.object(
            diagnostic, "Session", side_effect=RuntimeError("private-password")
        ):
            result = diagnostic.classify({})
        self.assertEqual(result["connection"], "fail")
        engine.dispose.assert_called_once_with()
        self.assertEqual(private, {})
        rendered = json.dumps(result)
        for value in ("private-host", "private-user", "private-password", "7001"):
            self.assertNotIn(value, rendered)

    def test_real_runtime_safe_stop_precedes_external_access(self):
        environment = os.environ.copy()
        environment[diagnostic.APPROVED_COMMIT_ENV] = "0" * 40
        result = subprocess.run(
            [str(diagnostic.boundary.RUNTIME_EXECUTABLE), str(diagnostic.ARTIFACT)],
            cwd=diagnostic.ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), diagnostic._default_result())


if __name__ == "__main__":
    unittest.main()
