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

from tools import portal_data_production_bootstrap_diagnostic as diagnostic


class ProductionBootstrapReadonlyDiagnosticTests(unittest.TestCase):
    def test_artifacts_and_fixed_runtime_cloud_boundaries_are_locked(self):
        diagnostic._verify_artifacts()
        source = diagnostic.ARTIFACT.read_text(encoding="utf-8")
        self.assertIn('ACCOUNT = "yces3108@gmail.com"', source)
        self.assertIn('PROJECT = "ntubtob-schedule-405614"', source)
        self.assertIn('SERVICE = "web-portal"', source)
        self.assertIn('REGION = "asia-east1"', source)
        self.assertIn("RUNTIME_VERSION = (3, 12, 13)", source)
        self.assertIn(
            r"C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
            source,
        )
        self.assertIn(
            'APPROVED_COMMIT_ENV = "TASK086_DIAGNOSTIC_APPROVED_MERGED_COMMIT"',
            source,
        )

    def test_checksum_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / diagnostic.ARTIFACT.name
            checksum = artifact.with_suffix(".py.sha256")
            artifact.write_text("mutated\n", encoding="utf-8")
            checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
            with patch.object(diagnostic, "ARTIFACT", artifact), patch.object(
                diagnostic, "CHECKSUM", checksum
            ), self.assertRaises(diagnostic.DiagnosticError):
                diagnostic._verify_artifacts()

    def test_source_has_no_mutating_or_existing_launcher_boundary(self):
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
        self.assertNotIn("tools.launch_production_zero_admin_post_check", imports)
        self.assertNotIn("IdentityLifecycleRepository", source)
        self.assertNotIn("operator.run", source)
        self.assertNotIn("uuid", imports)
        self.assertNotIn("uuid.uuid4", calls)
        self.assertNotIn("execution acknowledgement", source.lower())
        self.assertNotIn("session.commit", calls)
        self.assertNotIn("session.add", calls)
        self.assertNotIn("session.delete", calls)
        self.assertNotIn("session.flush", calls)
        self.assertIn('text("SET TRANSACTION READ ONLY")', source)
        self.assertIn("SET LOCAL statement_timeout", source)
        self.assertIn("SET LOCAL lock_timeout", source)
        self.assertIn("SET LOCAL idle_in_transaction_session_timeout", source)
        for forbidden_sql in (
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "ALTER ",
            "CREATE ",
            "DROP ",
        ):
            self.assertNotIn(forbidden_sql, source)

    def test_runbook_has_only_exact_diagnostic_command_and_fixed_schema(self):
        runbook = (
            diagnostic.ROOT / "docs" / "operations" / "PHASE_C_ZERO_ADMIN_BOOTSTRAP.md"
        ).read_text(encoding="utf-8")
        section = runbook.split(
            "### Owner-approved fixed-schema read-only diagnostic", maxsplit=1
        )[1]
        self.assertIn("tools/portal_data_production_bootstrap_diagnostic.py", section)
        self.assertIn("TASK086_DIAGNOSTIC_APPROVED_MERGED_COMMIT", section)
        self.assertIn('"active_admin":"zero|one|other"', section)
        self.assertIn('"completed_relationship":"zero|one|other"', section)
        self.assertNotIn("launch_production_zero_admin_bootstrap.py", section)
        self.assertNotIn("launch_production_zero_admin_post_check.py", section)
        self.assertNotIn("--mode", section)

    def test_gcloud_uses_exact_guards_and_env_metadata_projection(self):
        commands = []

        def fake_run(command):
            commands.append(command)
            if "auth" in command:
                return diagnostic.ACCOUNT
            return diagnostic.PROJECT

        response = bytearray(b"fake-response")
        error = bytearray(b"fake-stderr")
        metadata = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {"name": "ORDINARY", "value": "ordinary-value"},
                                    {
                                        "name": "SECRET_REF",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "secret": "fake-secret-name",
                                                "version": "latest",
                                            }
                                        },
                                    },
                                    {
                                        "name": diagnostic.ALLOWLIST_NAME,
                                        "value": "7001,7002",
                                    },
                                ]
                            }
                        ]
                    }
                }
            }
        }
        with patch.object(diagnostic.Path, "is_file", return_value=True), patch.object(
            diagnostic, "_run", side_effect=fake_run
        ), patch.object(
            diagnostic, "_load_env_metadata", return_value=(response, error)
        ), patch.object(
            diagnostic.json, "loads", return_value=metadata
        ):
            self.assertEqual(
                diagnostic._verify_gcloud_and_load_allowlist(), {7001, 7002}
            )
        self.assertEqual(len(commands), 2)
        self.assertEqual(
            commands,
            [
                [
                    str(diagnostic.GCLOUD),
                    "auth",
                    "list",
                    "--filter=status:ACTIVE",
                    "--format=value(account)",
                ],
                [str(diagnostic.GCLOUD), "config", "get-value", "project", "--quiet"],
            ],
        )
        self.assertEqual(response, bytearray())
        self.assertEqual(error, bytearray())
        self.assertEqual(metadata, {})

    def test_metadata_command_is_fixed_machine_readable_and_captures_output(self):
        completed = MagicMock(
            returncode=0,
            stdout=b'{"spec":{"template":{"spec":{"containers":[]}}}}',
            stderr=b"fake-stderr",
        )
        with patch.object(diagnostic, "subprocess") as subprocess_module:
            subprocess_module.run.return_value = completed
            response, error = diagnostic._load_env_metadata()
        subprocess_module.run.assert_called_once_with(
            [
                str(diagnostic.GCLOUD),
                "run",
                "services",
                "describe",
                diagnostic.SERVICE,
                "--account",
                diagnostic.ACCOUNT,
                "--project",
                diagnostic.PROJECT,
                "--region",
                diagnostic.REGION,
                f"--format={diagnostic.METADATA_FORMAT}",
            ],
            cwd=diagnostic.ROOT,
            check=False,
            capture_output=True,
            text=False,
            timeout=30,
        )
        self.assertIsInstance(response, bytearray)
        self.assertIsInstance(error, bytearray)

    def test_metadata_rejects_ambiguous_or_secret_backed_allowlist(self):
        plain = {"name": diagnostic.ALLOWLIST_NAME, "value": "7001"}

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
            document([{"name": diagnostic.ALLOWLIST_NAME, "value": ""}]),
            document([{"name": diagnostic.ALLOWLIST_NAME, "value": "7, 8"}]),
            document(
                [
                    {
                        "name": diagnostic.ALLOWLIST_NAME,
                        "valueFrom": {"secretKeyRef": {"secret": "fake-secret"}},
                    }
                ]
            ),
            document([plain], containers=[]),
            document([plain], containers=[{"env": [plain]}, {"env": []}]),
            document([plain], extra="unexpected"),
            {"wrong": {}},
        )
        for metadata in cases:
            with self.subTest(metadata=metadata), self.assertRaises(
                diagnostic.DiagnosticError
            ) as caught:
                diagnostic._extract_plain_allowlist(metadata)
            message = str(caught.exception)
            self.assertEqual(message, "metadata boundary failed")
            self.assertNotIn("fake-secret", message)
            self.assertNotIn("7001", message)

    def test_adversarial_metadata_never_escapes_and_is_cleared(self):
        ordinary_value = "ordinary-sensitive-metadata"
        secret_reference = "projects/fake/secrets/fake-secret"
        allowlist_value = "7001,7002"
        metadata = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {"name": "ORDINARY", "value": ordinary_value},
                                    {
                                        "name": "SECRET_REF",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "secret": secret_reference,
                                                "version": "latest",
                                            }
                                        },
                                    },
                                    {
                                        "name": diagnostic.ALLOWLIST_NAME,
                                        "value": allowlist_value,
                                    },
                                ]
                            }
                        ]
                    }
                }
            }
        }
        response = bytearray(b"adversarial-response")
        error = bytearray(b"adversarial-stderr")
        stdout = io.StringIO()
        stderr = io.StringIO()
        before_files = set(diagnostic.ROOT.rglob("*"))
        with patch.object(diagnostic.Path, "is_file", return_value=True), patch.object(
            diagnostic,
            "_run",
            side_effect=(diagnostic.ACCOUNT, diagnostic.PROJECT),
        ), patch.object(
            diagnostic, "_load_env_metadata", return_value=(response, error)
        ), patch.object(
            diagnostic.json, "loads", return_value=metadata
        ), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(
            stderr
        ):
            result = diagnostic._verify_gcloud_and_load_allowlist()
        after_files = set(diagnostic.ROOT.rglob("*"))
        self.assertEqual(result, {7001, 7002})
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(response, bytearray())
        self.assertEqual(error, bytearray())
        self.assertEqual(metadata, {})
        self.assertEqual(before_files, after_files)
        for value in (ordinary_value, secret_reference, allowlist_value):
            self.assertNotIn(value, stdout.getvalue())
            self.assertNotIn(value, stderr.getvalue())
            self.assertNotIn(value, repr(result))
            self.assertNotIn(value, repr(metadata))
            self.assertNotIn(value, repr(response))
            self.assertNotIn(value, repr(error))
            self.assertNotIn(value, repr(os.environ))

    def test_success_returns_only_fixed_classifications(self):
        private = {
            "PGHOST": "fake-db.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake_database",
            "PGUSER": "fake_user",
            "PGPASSWORD": "fake_password",
        }
        session = MagicMock()
        session.scalar.return_value = diagnostic.SCHEMA_REVISION
        session_context = MagicMock()
        session_context.__enter__.return_value = session
        transaction_context = MagicMock()
        transaction_context.__enter__.return_value = None
        session.begin.return_value = transaction_context
        engine = MagicMock()
        allowlist = {7001}
        with patch.object(diagnostic, "_verify_runtime_git"), patch.object(
            diagnostic,
            "_verify_gcloud_and_load_allowlist",
            return_value=allowlist,
        ), patch.object(
            diagnostic, "_load_private_pg_environment", return_value=private
        ), patch.object(
            diagnostic, "create_engine", return_value=engine
        ), patch.object(
            diagnostic, "Session", return_value=session_context
        ), patch.object(
            diagnostic, "_read_logging_safe", return_value=True
        ), patch.object(
            diagnostic, "_active_admin_count", return_value=1
        ), patch.object(
            diagnostic, "_completed_relationship_count", return_value=1
        ):
            result = diagnostic.classify({diagnostic.APPROVED_COMMIT_ENV: "a" * 40})
        self.assertEqual(
            result,
            {
                "runtime_artifact_git": "pass",
                "gcloud_metadata": "pass",
                "private_pg": "pass",
                "connection": "pass",
                "schema": "pass",
                "read_logging": "pass",
                "active_admin": "one",
                "completed_relationship": "one",
            },
        )
        statements = [str(call.args[0]) for call in session.execute.call_args_list]
        self.assertEqual(statements[0], "SET TRANSACTION READ ONLY")
        self.assertTrue(any("statement_timeout" in value for value in statements))
        self.assertTrue(any("lock_timeout" in value for value in statements))
        self.assertTrue(
            any("idle_in_transaction_session_timeout" in value for value in statements)
        )
        engine.dispose.assert_called_once_with()
        self.assertEqual(private, {})
        self.assertEqual(allowlist, set())

    def test_counts_are_reduced_to_zero_one_other(self):
        self.assertEqual(diagnostic._count_classification(0), "zero")
        self.assertEqual(diagnostic._count_classification(1), "one")
        for value in (2, 99, -1):
            self.assertEqual(diagnostic._count_classification(value), "other")

    def test_database_stage_exceptions_are_fixed_and_engine_is_disposed(self):
        private = {
            "PGHOST": "fake-db.invalid",
            "PGPORT": "5432",
            "PGDATABASE": "fake_database",
            "PGUSER": "fake_user",
            "PGPASSWORD": "fake_password",
        }
        cases = (
            ("schema", "fail", "scalar"),
            ("read_logging", "fail", "logging"),
            ("active_admin", "other", "admin"),
            ("completed_relationship", "other", "relationship"),
        )
        for field, expected, failing_stage in cases:
            with self.subTest(field=field):
                session = MagicMock()
                session.scalar.return_value = diagnostic.SCHEMA_REVISION
                if failing_stage == "scalar":
                    session.scalar.side_effect = RuntimeError("private-value")
                session_context = MagicMock()
                session_context.__enter__.return_value = session
                transaction_context = MagicMock()
                transaction_context.__enter__.return_value = None
                session.begin.return_value = transaction_context
                engine = MagicMock()
                logging_effect = (
                    RuntimeError("private-value")
                    if failing_stage == "logging"
                    else True
                )
                admin_effect = (
                    RuntimeError("private-value") if failing_stage == "admin" else 1
                )
                relationship_effect = (
                    RuntimeError("private-value")
                    if failing_stage == "relationship"
                    else 1
                )
                with patch.object(diagnostic, "_verify_runtime_git"), patch.object(
                    diagnostic,
                    "_verify_gcloud_and_load_allowlist",
                    return_value={7001},
                ), patch.object(
                    diagnostic,
                    "_load_private_pg_environment",
                    side_effect=lambda path: private.copy(),
                ), patch.object(
                    diagnostic, "create_engine", return_value=engine
                ), patch.object(
                    diagnostic, "Session", return_value=session_context
                ), patch.object(
                    diagnostic,
                    "_read_logging_safe",
                    side_effect=(
                        [logging_effect]
                        if isinstance(logging_effect, Exception)
                        else None
                    ),
                    return_value=(
                        logging_effect
                        if not isinstance(logging_effect, Exception)
                        else None
                    ),
                ), patch.object(
                    diagnostic,
                    "_active_admin_count",
                    side_effect=(
                        [admin_effect] if isinstance(admin_effect, Exception) else None
                    ),
                    return_value=(
                        admin_effect
                        if not isinstance(admin_effect, Exception)
                        else None
                    ),
                ), patch.object(
                    diagnostic,
                    "_completed_relationship_count",
                    side_effect=(
                        [relationship_effect]
                        if isinstance(relationship_effect, Exception)
                        else None
                    ),
                    return_value=(
                        relationship_effect
                        if not isinstance(relationship_effect, Exception)
                        else None
                    ),
                ):
                    result = diagnostic.classify()
                self.assertEqual(result[field], expected)
                self.assertNotIn("private-value", json.dumps(result))
                engine.dispose.assert_called_once_with()

        engine = MagicMock()
        session_context = MagicMock()
        session_context.__enter__.side_effect = RuntimeError("private-value")
        with patch.object(diagnostic, "_verify_runtime_git"), patch.object(
            diagnostic,
            "_verify_gcloud_and_load_allowlist",
            return_value={7001},
        ), patch.object(
            diagnostic,
            "_load_private_pg_environment",
            side_effect=lambda path: private.copy(),
        ), patch.object(
            diagnostic, "create_engine", return_value=engine
        ), patch.object(
            diagnostic, "Session", return_value=session_context
        ):
            result = diagnostic.classify()
        self.assertEqual(result["connection"], "fail")
        self.assertNotIn("private-value", json.dumps(result))
        engine.dispose.assert_called_once_with()

    def test_each_boundary_failure_returns_only_fixed_schema(self):
        cases = (
            "_verify_runtime_git",
            "_verify_gcloud_and_load_allowlist",
            "_load_private_pg_environment",
        )
        for failing_name in cases:
            with self.subTest(failing_name=failing_name), patch.object(
                diagnostic, "_verify_runtime_git"
            ), patch.object(
                diagnostic,
                "_verify_gcloud_and_load_allowlist",
                return_value={7001},
            ), patch.object(
                diagnostic,
                "_load_private_pg_environment",
                return_value={
                    "PGHOST": "fake-db.invalid",
                    "PGPORT": "5432",
                    "PGDATABASE": "fake_database",
                    "PGUSER": "fake_user",
                    "PGPASSWORD": "fake_password",
                },
            ):
                target = patch.object(
                    diagnostic, failing_name, side_effect=RuntimeError("sensitive")
                )
                with target:
                    result = diagnostic.classify()
            self.assertEqual(tuple(result), diagnostic.OUTPUT_FIELDS)
            self.assertNotIn("sensitive", json.dumps(result))
            self.assertTrue(
                all(
                    result[field] in ("pass", "fail")
                    for field in diagnostic.OUTPUT_FIELDS[:6]
                )
            )
            self.assertTrue(
                all(
                    result[field] in ("zero", "one", "other")
                    for field in diagnostic.OUTPUT_FIELDS[6:]
                )
            )

    def test_fixed_output_rejects_unknown_values_and_never_emits_exceptions(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            diagnostic._emit(diagnostic._default_result())
        payload = json.loads(output.getvalue())
        self.assertEqual(tuple(payload), diagnostic.OUTPUT_FIELDS)
        invalid = diagnostic._default_result()
        invalid["connection"] = "private-host"
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic._emit(invalid)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(
            diagnostic, "classify", side_effect=RuntimeError("private-password")
        ):
            diagnostic.main()
        self.assertEqual(json.loads(output.getvalue()), diagnostic._default_result())
        self.assertNotIn("private-password", output.getvalue())

    def test_real_runtime_safe_stop_precedes_gcloud_and_private_access(self):
        environment = os.environ.copy()
        environment[diagnostic.APPROVED_COMMIT_ENV] = "0" * 40
        result = subprocess.run(
            [str(diagnostic.RUNTIME_EXECUTABLE), str(diagnostic.ARTIFACT)],
            cwd=diagnostic.ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertEqual(payload, diagnostic._default_result())


if __name__ == "__main__":
    unittest.main()
