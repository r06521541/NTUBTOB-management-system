from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tools import ios_store_readiness


class IOSStoreReadinessTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ios_store_readiness.load_manifest()

    def test_repository_manifest_is_valid_and_never_release_ready(self):
        result = ios_store_readiness.validate_manifest(self.manifest)
        self.assertEqual(result["classification"], "PREPARATION_ONLY")
        self.assertEqual(result["candidate_scope"], "staging-real-basic")
        self.assertEqual(result["privacy_fact_count"], 6)
        self.assertGreater(result["blocked_gate_count"], 0)
        self.assertFalse(result["external_mutation_performed"])
        self.assertFalse(result["release_ready"])

    def test_mixed_or_expanded_candidate_scope_is_rejected(self):
        cases = {
            "app_flavor": "production",
            "client_mode": "fake",
            "release_scope": "officer",
            "minimum_ios": "14.0",
            "production_data": True,
            "push_delivery": True,
            "deep_link_delivery": True,
            "crash_upload": True,
        }
        for key, value in cases.items():
            with self.subTest(key=key):
                changed = deepcopy(self.manifest)
                changed["candidate"][key] = value
                with self.assertRaisesRegex(
                    ios_store_readiness.ReadinessError,
                    "approved TestFlight vector",
                ):
                    ios_store_readiness.validate_manifest(changed)

    def test_schema_and_candidate_values_require_exact_json_types(self):
        changed = deepcopy(self.manifest)
        changed["schema"] = True
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError, "schema is unsupported"
        ):
            ios_store_readiness.validate_manifest(changed)
        for key in (
            "production_data",
            "push_delivery",
            "deep_link_delivery",
            "crash_upload",
        ):
            with self.subTest(key=key):
                changed = deepcopy(self.manifest)
                changed["candidate"][key] = 0
                with self.assertRaisesRegex(
                    ios_store_readiness.ReadinessError,
                    "approved TestFlight vector",
                ):
                    ios_store_readiness.validate_manifest(changed)

    def test_unknown_missing_and_duplicate_fields_are_rejected(self):
        changed = deepcopy(self.manifest)
        changed["unknown"] = True
        with self.assertRaises(ios_store_readiness.ReadinessError):
            ios_store_readiness.validate_manifest(changed)
        changed = deepcopy(self.manifest)
        del changed["gates"]["feedback_contact"]
        with self.assertRaises(ios_store_readiness.ReadinessError):
            ios_store_readiness.validate_manifest(changed)
        duplicate = b'{"schema":1,"schema":1}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_bytes(duplicate)
            with self.assertRaisesRegex(
                ios_store_readiness.ReadinessError, "duplicate keys"
            ):
                ios_store_readiness.load_manifest(path)

    def test_draft_rejects_identifiers_and_apple_length_drift(self):
        for value in (
            "reply@example.test",
            "https://private.example.test",
            "ftp://private.example.test",
            "private.example.test",
            "provider=private",
            "signing: private",
            "credential=private",
            "api_key=private",
            "access_key: private",
            "authorization=Bearer-private",
            "bearer: private",
            "endpoint=private",
            "api_url=private",
            "password=value",
            "1234567890.apps.googleusercontent.com",
            "192.0.2.10",
            "[2001:db8::1]",
        ):
            with self.subTest(value=value):
                changed = deepcopy(self.manifest)
                changed["draft"]["what_to_test"] = value
                with self.assertRaisesRegex(
                    ios_store_readiness.ReadinessError,
                    "prohibited identifier category",
                ):
                    ios_store_readiness.validate_manifest(changed)
        changed = deepcopy(self.manifest)
        changed["draft"]["app_name"] = "x" * 31
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError, "app name length"
        ):
            ios_store_readiness.validate_manifest(changed)

    def test_privacy_inventory_is_exact_consistent_and_tracking_free(self):
        changed = deepcopy(self.manifest)
        changed["privacy_facts"][0]["tracking"] = True
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError, "does not permit tracking"
        ):
            ios_store_readiness.validate_manifest(changed)
        changed = deepcopy(self.manifest)
        changed["privacy_facts"][4]["linked_to_user"] = True
        with self.assertRaisesRegex(ios_store_readiness.ReadinessError, "inconsistent"):
            ios_store_readiness.validate_manifest(changed)
        changed = deepcopy(self.manifest)
        changed["privacy_facts"][1]["category"] = changed["privacy_facts"][0][
            "category"
        ]
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError, "incomplete or duplicated"
        ):
            ios_store_readiness.validate_manifest(changed)

    def test_gate_cannot_claim_release_readiness(self):
        changed = deepcopy(self.manifest)
        changed["gates"] = {key: "required" for key in changed["gates"]}
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError,
            "cannot claim release readiness",
        ):
            ios_store_readiness.validate_manifest(changed)

    def test_malformed_value_types_fail_with_readiness_error(self):
        changed = deepcopy(self.manifest)
        changed["privacy_facts"][0]["purpose"] = []
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError, "privacy fact values are invalid"
        ):
            ios_store_readiness.validate_manifest(changed)

    def test_load_is_bounded_and_rejects_non_regular_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            oversized = root / "oversized.json"
            oversized.write_bytes(b"x" * (ios_store_readiness.MAX_MANIFEST_BYTES + 1))
            with self.assertRaisesRegex(
                ios_store_readiness.ReadinessError, "encoding or size is invalid"
            ):
                ios_store_readiness.load_manifest(oversized)
            with self.assertRaisesRegex(
                ios_store_readiness.ReadinessError, "unavailable"
            ):
                ios_store_readiness.load_manifest(root)
        changed = deepcopy(self.manifest)
        changed["gates"]["feedback_contact"] = []
        with self.assertRaisesRegex(
            ios_store_readiness.ReadinessError, "gate state is invalid"
        ):
            ios_store_readiness.validate_manifest(changed)

    def test_cli_output_is_deidentified(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.ios_store_readiness"],
            cwd=ios_store_readiness.ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["classification"], "PREPARATION_ONLY")
        rendered = result.stdout.lower()
        for forbidden in (
            "beta_description",
            "what_to_test",
            "email",
            "url",
            "identifier",
            "certificate",
            "profile",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
