import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import portal_data_zero_admin_bootstrap as operator


class ZeroAdminBootstrapOperatorTests(unittest.TestCase):
    def test_artifact_is_checksummed_and_cli_has_no_sensitive_arguments(self):
        operator.verify_artifact()
        source = operator.ARTIFACT.read_text(encoding="utf-8")
        self.assertIn('choices=("preflight", "dry-run", "execute")', source)
        for option in (
            "--identity",
            "--member",
            "--reason",
            "--request",
            "--allowlist",
        ):
            self.assertNotIn(option, source)
        self.assertGreaterEqual(source.count("getpass.getpass("), 6)

    def test_checksum_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / operator.ARTIFACT.name
            checksum = artifact.with_suffix(".py.sha256")
            artifact.write_text("mutated\n", encoding="utf-8")
            checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
            with patch.object(operator, "ARTIFACT", artifact), patch.object(
                operator, "CHECKSUM", checksum
            ), self.assertRaises(operator.BootstrapOperatorError):
                operator.verify_artifact()

    def test_redacted_output_schema_rejects_extra_fields(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator._emit(
                mode="dry-run",
                status="ready",
                target_ready=True,
                active_admin_count_before=0,
                active_admin_count_after=0,
                audit_delta=0,
                applied=False,
            )
        self.assertEqual(tuple(json.loads(output.getvalue())), operator.OUTPUT_FIELDS)
        with self.assertRaises(operator.BootstrapOperatorError):
            operator._emit(mode="dry-run", status="ready")

    def test_allowlist_rejects_duplicate_or_ambiguous_values(self):
        self.assertEqual(operator._allowlist("7,9"), frozenset({7, 9}))
        for value in ("", "7,7", "7, 9", "7,,9", "-1"):
            with self.subTest(value=value), self.assertRaises(
                operator.BootstrapOperatorError
            ):
                operator._allowlist(value)


if __name__ == "__main__":
    unittest.main()
