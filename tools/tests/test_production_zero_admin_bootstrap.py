import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import portal_data_production_zero_admin_bootstrap as operator


class ProductionZeroAdminBootstrapTests(unittest.TestCase):
    def test_artifact_is_checksummed_and_cli_has_no_sensitive_arguments(self):
        operator.verify_artifact()
        source = operator.ARTIFACT.read_text(encoding="utf-8")
        self.assertIn(
            'choices=("discovery", "preflight", "dry-run", "execute")', source
        )
        for option in (
            "--database",
            "--identity",
            "--member",
            "--request",
            "--allowlist",
        ):
            self.assertNotIn(option, source)
        self.assertNotIn("echo=True", source)
        self.assertIn('session.execute(text("SET TRANSACTION READ ONLY"))', source)

    def test_runbook_keeps_local_and_production_boundaries_separate(self):
        runbook = (
            operator.ROOT / "docs" / "operations" / "PHASE_C_ZERO_ADMIN_BOOTSTRAP.md"
        ).read_text(encoding="utf-8")
        self.assertIn("TASK-085 commands above remain local-only", runbook)
        self.assertIn("hosted PostgreSQL 15/16 CI", runbook)
        self.assertIn("exactly one eligible allowlisted Member", runbook)
        self.assertIn("Do not inspect, echo, serialize", runbook)
        self.assertIn("does not authorize deployment", runbook)

    def test_checksum_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / operator.ARTIFACT.name
            checksum = artifact.with_suffix(".py.sha256")
            artifact.write_text("mutated\n", encoding="utf-8")
            checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
            with patch.object(operator, "ARTIFACT", artifact), patch.object(
                operator, "CHECKSUM", checksum
            ), self.assertRaises(operator.ProductionBootstrapError):
                operator.verify_artifact()

    def test_private_inputs_fail_closed_without_disclosing_values(self):
        secret_url = (
            "postgresql://private-user:private-password@private-host/private-db"
        )
        secret_allowlist = "7001,7002"
        cases = (
            {},
            {operator.DATABASE_ENV: secret_url},
            {
                operator.DATABASE_ENV: secret_url,
                operator.ALLOWLIST_ENV: "7001,7001",
            },
        )
        for environment in cases:
            with self.subTest(environment=set(environment)), self.assertRaises(
                operator.ProductionBootstrapError
            ) as caught:
                operator._private_inputs(environment)
            message = str(caught.exception)
            self.assertNotIn(secret_url, message)
            self.assertNotIn(secret_allowlist, message)

    def test_cli_converts_internal_failure_to_fixed_safe_message(self):
        sensitive_failure = "private-password task086-private-request"
        with patch(
            "sys.argv", [str(operator.ARTIFACT), "--mode", "discovery"]
        ), patch.object(
            operator, "run", side_effect=RuntimeError(sensitive_failure)
        ), self.assertRaises(
            SystemExit
        ) as caught:
            operator.main()
        message = str(caught.exception)
        self.assertEqual(message, "production zero-admin bootstrap stopped")
        self.assertNotIn(sensitive_failure, message)

    def test_redacted_output_schema_rejects_extra_or_missing_fields(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator._emit(
                mode="dry-run",
                status="ready",
                schema_ready=True,
                logging_safe=True,
                active_admin_count=0,
                eligible_member_count=1,
                eligible_identity_count=1,
                audit_delta=0,
                applied=False,
                retry_verified=False,
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(tuple(payload), operator.OUTPUT_FIELDS)
        self.assertNotIn("identity", payload)
        self.assertNotIn("member", payload)
        self.assertNotIn("request", payload)
        with self.assertRaises(operator.ProductionBootstrapError):
            operator._emit(mode="dry-run", status="ready")

    def test_allowlist_requires_unique_positive_canonical_ids(self):
        self.assertEqual(operator._allowlist("7,9"), frozenset({7, 9}))
        for value in (None, "", "7,7", "7, 9", "7,,9", "-1", "+7"):
            with self.subTest(value=value), self.assertRaises(
                operator.ProductionBootstrapError
            ):
                operator._allowlist(value)


if __name__ == "__main__":
    unittest.main()
