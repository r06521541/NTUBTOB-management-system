"""No network: command-shaped GET metadata and ANSI-bearing fake logs."""

import json
import unittest

from tools import ios_native_receipt as receipt

SHA = "a" * 40


def log():
    return (
        b"\x1b[31mfictional-private-log\x1b[0m\n"
        + b"2026-09-15T01:00:00.123Z "
        + json.dumps(receipt.SUCCESS).encode()
        + b"\n"
        + json.dumps(receipt.AUDIT).encode()
    )


class ReceiptTests(unittest.TestCase):
    def test_ansi_not_rendered_only_exact_fixed_json(self):
        result = receipt.parse(log())
        self.assertEqual(result, receipt.SUCCESS)
        self.assertNotIn("private-log", json.dumps(result))
        self.assertNotIn("\x1b", json.dumps(result))

    def test_missing_duplicate_contradictory_wrong_types_and_limits(self):
        success = json.dumps(receipt.SUCCESS).encode()
        for raw in (
            b"",
            b"x" * 1048577,
            success,
            log() + b"\n" + success,
            log() + b'\n{"classification":"STOP"}',
            log().replace(b'"signature_verified": true', b'"signature_verified": 1'),
            log() + b'\n{"classification":"STOP","classification":"STOP"}',
            log() + b'\n{"stage":"cleanup_audit","classification":"PRESENT"}',
            log()
            + b'\n{"classification":"SIGNED_BASELINE_VERIFIED","cleanup_verified":false}',
            log() + b'\n{"classification":"UNKNOWN_FINAL"}',
            log() + b'\n{"classification":"STOP","padding":"' + b"x" * 4096 + b'"}',
            log() + b'\n{"\\u0063lassification":"STOP","\\u0063lassification":"STOP"}',
        ):
            with self.subTest(raw_length=len(raw)), self.assertRaises(receipt.Rejected):
                receipt.parse(raw)

    def test_api_number_bindings_are_integers_not_bool_or_float(self):
        for bad_stage in ("run_binding", "job_binding"):
            for invalid in (True, 1.0):

                def fake(stage, args, payload=None):
                    raw = self.fake(stage, args, payload)
                    if stage == bad_stage:
                        value = json.loads(raw)
                        value["run_attempt"] = invalid
                        return json.dumps(value).encode()
                    return raw

                with self.subTest(stage=bad_stage, invalid=invalid):
                    result = receipt.read(10, 20, SHA, run=fake)
                    self.assertEqual(result["classification"], "STOP")

    def fake(self, stage, args, payload=None):
        self.calls.append((stage, args))
        self.assertIsNone(payload)
        if stage == "job_log":
            self.assertIn("--allow-escape-sequences", args)
            return log()
        value = {
            "run_binding": {
                "id": 10,
                "head_sha": SHA,
                "head_branch": "main",
                "event": "workflow_dispatch",
                "run_attempt": 1,
                "path": ".github/workflows/ios-native-signing.yml",
                "status": "completed",
                "conclusion": "success",
                "repository": {"full_name": receipt.setup.REPO},
            },
            "job_binding": {
                "id": 20,
                "run_id": 10,
                "head_sha": SHA,
                "run_attempt": 1,
                "name": "native_signing",
                "status": "completed",
                "conclusion": "success",
            },
            "artifacts": {"total_count": 0, "artifacts": []},
        }[stage]
        return json.dumps(value).encode()

    def setUp(self):
        self.calls = []

    def test_bound_run_job_no_artifacts_before_log(self):
        result = receipt.read(10, 20, SHA, run=self.fake)
        self.assertEqual(result["classification"], "SIGNED_RECEIPT_VERIFIED")
        self.assertEqual(
            [c[0] for c in self.calls],
            ["run_binding", "job_binding", "artifacts", "job_log"],
        )
        self.assertEqual(result["mutation_count"], 0)

    def test_mismatched_run_job_artifacts_never_fetch_log(self):
        for bad_stage in ("run_binding", "job_binding", "artifacts"):
            self.calls = []

            def fake(stage, args, payload=None):
                raw = self.fake(stage, args, payload)
                return b"{}" if stage == bad_stage else raw

            result = receipt.read(10, 20, SHA, run=fake)
            self.assertEqual(result["classification"], "STOP")
            self.assertEqual(result["failure"]["stage"], bad_stage)
            self.assertFalse(any(c[0] == "job_log" for c in self.calls))

    def test_known_cli_guard_and_secondary_cleanup_are_preserved(self):
        def fake(stage, args, payload=None):
            if stage == "job_log":
                raise receipt.setup.Failure(
                    stage, "TERMINAL_ESCAPE_GUARD", 1, cleanup="PROCESS_UNRESOLVED"
                )
            return self.fake(stage, args, payload)

        result = receipt.read(10, 20, SHA, run=fake)
        self.assertEqual(result["failure"]["reason"], "TERMINAL_ESCAPE_GUARD")
        self.assertEqual(result["cleanup_failure"], "PROCESS_UNRESOLVED")
        self.assertNotIn("private-log", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
