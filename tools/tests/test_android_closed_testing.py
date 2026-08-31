import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools import android_closed_testing as closed


ARTIFACT_SHA = "a" * 64
SIGNER_SHA = "b" * 64
COMMIT_SHA = "c" * 40


def evidence_fixture():
    scenarios = {
        name: {
            "result": "passed",
            "evidence_ref": f"EV-DEVICE-{name.upper().replace('_', '-')}",
        }
        for name in closed.SCENARIOS
    }
    return {
        "schema": closed.SCHEMA,
        "channel": "android-closed",
        "reviewed_commit_sha": COMMIT_SHA,
        "artifact": {
            "package_name": closed.PACKAGE_NAME,
            "version_name": "0.1.0",
            "version_code": 2,
            "previous_version_code": 1,
            "sha256": ARTIFACT_SHA,
            "strict_inspection": "passed",
        },
        "signer": {
            "expected_sha256": SIGNER_SHA,
            "observed_sha256": SIGNER_SHA,
            "comparison": "match",
            "evidence_ref": "EV-SIGNER-COMPARE",
        },
        "runtime": {
            "environment": "staging",
            "client_mode": "real",
            "data_scope": "isolated-test-data",
            "production_access": False,
            "evidence_ref": "EV-RUNTIME-SCOPE",
        },
        "scope": {
            "release_scope": "basic-only",
            "officer_admin": False,
            "push_delivery": False,
            "deep_link_delivery": False,
            "anonymous_crash_reporting": False,
        },
        "compliance": {
            "data_safety": {"status": "verified", "evidence_ref": "EV-DATA-SAFETY"},
            "privacy": {"status": "verified", "evidence_ref": "EV-PRIVACY"},
            "support": {"status": "verified", "evidence_ref": "EV-SUPPORT"},
            "deletion": {"status": "verified", "evidence_ref": "EV-DELETION"},
            "tester_notes": {
                "status": "verified",
                "evidence_ref": "EV-TESTER-NOTES",
                "declares_staging": True,
                "declares_basic_only": True,
                "declares_no_push": True,
                "declares_no_deep_link_delivery": True,
                "declares_no_crash_reporting": True,
                "unavailable_provider_scenarios": [],
            },
        },
        "device_matrix": {
            "artifact_sha256": ARTIFACT_SHA,
            "device_class": "android-phone",
            "os_major": 15,
            "device_identifier_recorded": False,
            "test_data": "fictional",
            "scenarios": scenarios,
        },
        "track": {
            "name": "closed",
            "processing_state": "available-to-closed-testers",
            "package_name": closed.PACKAGE_NAME,
            "version_name": "0.1.0",
            "version_code": 2,
            "artifact_sha256": ARTIFACT_SHA,
            "open_testing": False,
            "production_rollout": False,
            "tester_notification": "not-performed",
            "evidence_ref": "EV-TRACK-STATE",
        },
        "remaining_blockers": [],
    }


class AndroidClosedTestingEvidenceTests(unittest.TestCase):
    def test_complete_deidentified_record_is_accepted_and_summary_is_sanitized(self):
        summary = closed.validate_evidence(evidence_fixture())
        rendered = json.dumps(summary, sort_keys=True)
        self.assertEqual(summary["result"], "validated")
        self.assertEqual(summary["artifact_sha256"], ARTIFACT_SHA)
        self.assertTrue(summary["signer_match"])
        self.assertFalse(summary["external_truth_attested"])
        self.assertNotIn(SIGNER_SHA, rendered)
        self.assertNotIn("EV-", rendered)

    def test_missing_or_unknown_fields_fail_closed(self):
        for mutate in (
            lambda item: item.pop("track"),
            lambda item: item.update({"console_session": "safe-looking"}),
            lambda item: item["artifact"].update({"filename": "candidate.aab"}),
        ):
            value = evidence_fixture()
            mutate(value)
            with self.subTest(keys=set(value)), self.assertRaisesRegex(
                closed.EvidenceError, "incomplete or unsupported"
            ):
                closed.validate_evidence(value)

    def test_package_version_artifact_and_inspection_are_exact(self):
        cases = (
            ("package_name", "tw.org.example.other"),
            ("version_name", "0.0.0"),
            ("version_code", True),
            ("previous_version_code", 2),
            ("sha256", "A" * 64),
            ("strict_inspection", "unknown"),
        )
        for field, value in cases:
            record = evidence_fixture()
            record["artifact"][field] = value
            with self.subTest(field=field), self.assertRaises(closed.EvidenceError):
                closed.validate_evidence(record)

    def test_signer_mismatch_fails_without_echoing_fingerprint(self):
        record = evidence_fixture()
        observed = "d" * 64
        record["signer"]["observed_sha256"] = observed
        with self.assertRaisesRegex(closed.EvidenceError, "did not match") as raised:
            closed.validate_evidence(record)
        self.assertNotIn(observed, str(raised.exception))

    def test_runtime_must_be_real_isolated_staging_with_no_production_access(self):
        cases = (
            ("environment", "production"),
            ("client_mode", "fake"),
            ("data_scope", "shared-data"),
            ("production_access", True),
        )
        for field, value in cases:
            record = evidence_fixture()
            record["runtime"][field] = value
            with self.subTest(field=field), self.assertRaises(closed.EvidenceError):
                closed.validate_evidence(record)

    def test_basic_only_exclusions_are_mandatory(self):
        fields = (
            "officer_admin",
            "push_delivery",
            "deep_link_delivery",
            "anonymous_crash_reporting",
        )
        for field in fields:
            record = evidence_fixture()
            record["scope"][field] = True
            with self.subTest(field=field), self.assertRaises(closed.EvidenceError):
                closed.validate_evidence(record)

    def test_compliance_items_and_tester_disclosures_are_mandatory(self):
        for item in ("data_safety", "privacy", "support", "deletion"):
            record = evidence_fixture()
            record["compliance"][item]["status"] = "blocked"
            with self.subTest(item=item), self.assertRaises(closed.EvidenceError):
                closed.validate_evidence(record)
        record = evidence_fixture()
        record["compliance"]["tester_notes"]["declares_no_push"] = False
        with self.assertRaises(closed.EvidenceError):
            closed.validate_evidence(record)

    def test_compliance_evidence_references_must_be_pairwise_distinct(self):
        record = evidence_fixture()
        for name in ("data_safety", "privacy", "support", "deletion"):
            record["compliance"][name]["evidence_ref"] = "EV-SAME"
        record["compliance"]["tester_notes"]["evidence_ref"] = "EV-SAME"

        with self.assertRaisesRegex(
            closed.EvidenceError, "compliance evidence references must be distinct"
        ):
            closed.validate_evidence(record)

    def test_only_provider_login_may_be_unavailable_and_notes_must_match(self):
        record = evidence_fixture()
        record["device_matrix"]["scenarios"]["line_login"]["result"] = "unavailable"
        record["compliance"]["tester_notes"]["unavailable_provider_scenarios"] = [
            "line_login"
        ]
        closed.validate_evidence(record)

        record = evidence_fixture()
        record["device_matrix"]["scenarios"]["offline"]["result"] = "unavailable"
        with self.assertRaisesRegex(closed.EvidenceError, "no acceptable result"):
            closed.validate_evidence(record)

        record = evidence_fixture()
        record["device_matrix"]["scenarios"]["google_login"]["result"] = "unavailable"
        with self.assertRaisesRegex(closed.EvidenceError, "do not match"):
            closed.validate_evidence(record)

    def test_device_and_track_must_bind_the_exact_artifact(self):
        for container in ("device_matrix", "track"):
            record = evidence_fixture()
            record[container]["artifact_sha256"] = "d" * 64
            with self.subTest(container=container), self.assertRaises(
                closed.EvidenceError
            ):
                closed.validate_evidence(record)

    def test_track_is_closed_available_and_never_open_public_or_notified(self):
        cases = (
            ("name", "open"),
            ("processing_state", "processing"),
            ("open_testing", True),
            ("production_rollout", True),
            ("tester_notification", "performed"),
        )
        for field, value in cases:
            record = evidence_fixture()
            record["track"][field] = value
            with self.subTest(field=field), self.assertRaises(closed.EvidenceError):
                closed.validate_evidence(record)

    def test_sensitive_shaped_values_are_rejected_without_echo(self):
        for unsafe in (
            "https://staging.example.invalid",
            "owner@example.invalid",
            "provider-client-id-value",
            "secret-sentinel",
        ):
            record = evidence_fixture()
            record["runtime"]["evidence_ref"] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaises(
                closed.EvidenceError
            ) as raised:
                closed.validate_evidence(record)
            self.assertNotIn(unsafe, str(raised.exception))

    def test_blockers_or_unverified_external_state_cannot_pass(self):
        record = evidence_fixture()
        record["remaining_blockers"] = ["EV-UNKNOWN-GATE"]
        with self.assertRaisesRegex(closed.EvidenceError, "remaining blockers"):
            closed.validate_evidence(record)

    def test_loader_rejects_duplicate_keys_bom_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(closed.EvidenceError, "duplicate key"):
                closed.load_evidence(duplicate)

            bom = root / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}")
            with self.assertRaisesRegex(closed.EvidenceError, "encoding markers"):
                closed.load_evidence(bom)

            oversized = root / "oversized.json"
            oversized.write_bytes(b"x" * (closed.MAX_EVIDENCE_BYTES + 1))
            with self.assertRaisesRegex(closed.EvidenceError, "size limit"):
                closed.load_evidence(oversized)

    def test_cli_emits_only_sanitized_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(evidence_fixture()), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = closed.main([str(path)])
        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(SIGNER_SHA, stdout.getvalue())
        self.assertFalse(json.loads(stdout.getvalue())["external_truth_attested"])

    def test_tool_source_has_no_network_console_or_mutation_clients(self):
        source = Path(closed.__file__).read_text(encoding="utf-8").lower()
        for forbidden in (
            "import requests",
            "import urllib",
            "import socket",
            "import subprocess",
            "playwright",
            "selenium",
            "gcloud",
            "keytool",
            "jarsigner",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
