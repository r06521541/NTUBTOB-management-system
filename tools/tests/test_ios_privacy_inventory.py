from __future__ import annotations

import io
import json
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools import ios_privacy_inventory as inventory

SHA = "a" * 40
PRIVATE = "PRIVATE-SENTINEL-DO-NOT-ECHO"


def manifest():
    return {
        "NSPrivacyTracking": False,
        "NSPrivacyTrackingDomains": [],
        "NSPrivacyCollectedDataTypes": [],
        "NSPrivacyAccessedAPITypes": [],
    }


def lock(version="9.0.0", identity="googlesignin-ios"):
    return {
        "version": 3,
        "pins": [
            {
                "identity": identity,
                "kind": "remoteSourceControl",
                "location": "https://" + PRIVATE + ".invalid/repo",
                "state": {"version": version, "revision": PRIVATE},
            }
        ],
    }


class PrivacyInventoryTests(unittest.TestCase):
    def setUp(self):
        # macOS's conventional /var temp alias is a symlink; use its real root.
        self.temp = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "Runner.app"
        self.app.mkdir()
        (self.app / "Runner").write_bytes(b"fictional executable")
        (self.app / "Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "tw.org.ntubtob.portal",
                    "CFBundleShortVersionString": "0.1.0",
                    "CFBundleVersion": "1",
                    "CFBundleURLTypes": [PRIVATE],
                }
            )
        )
        self.packages = [self.root / "first.resolved", self.root / "second.resolved"]

    def write_manifest(
        self, relative="PrivacyInfo.xcprivacy", value=None, binary=False
    ):
        path = self.app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            plistlib.dumps(
                manifest() if value is None else value,
                fmt=plistlib.FMT_BINARY if binary else plistlib.FMT_XML,
            )
        )
        return path

    def run_inventory(self):
        return inventory.inspect_app(
            self.app, source_commit=SHA, package_paths=self.packages
        )

    def test_xml_binary_manifest_and_both_lock_slots_are_deterministic(self):
        self.write_manifest()
        self.write_manifest(
            "Frameworks/Flutter.framework/PrivacyInfo.xcprivacy", binary=True
        )
        for path in self.packages:
            path.write_text(json.dumps(lock()), encoding="utf-8")
        result = self.run_inventory()
        self.assertEqual(result, self.run_inventory())
        self.assertTrue(result["scan_complete"])
        self.assertEqual(len(result["manifests"]), 2)
        self.assertEqual(result["root_manifest"], "present")
        self.assertEqual(result["native_dependencies"][0]["versions"], ["9.0.0"])
        self.assertEqual(result["native_dependencies"][0]["slots"], [1, 2])
        self.assertEqual(len(result["package_sources"]), 2)
        self.assertFalse(result["compliance_verified"])
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["xcode_privacy_report_verified"])
        self.assertFalse(result["upload_authorized"])
        self.assertFalse(result["release_authorized"])
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("artifact_sha256", result)

    def test_absent_false_and_empty_remain_distinct(self):
        path = self.write_manifest(value={})
        absent = self.run_inventory()["manifests"][0]["fields"]
        self.assertEqual(absent["tracking"]["state"], "absent")
        self.assertEqual(absent["accessed_apis"]["state"], "absent")
        path.write_bytes(plistlib.dumps(manifest()))
        declared = self.run_inventory()["manifests"][0]["fields"]
        self.assertEqual(declared["tracking"], {"state": "present", "value": False})
        self.assertEqual(declared["accessed_apis"]["state"], "empty")

    def test_missing_manifest_and_locks_are_findings_not_compliance_pass(self):
        result = self.run_inventory()
        self.assertTrue(result["scan_complete"])
        self.assertEqual(result["root_manifest"], "absent")
        self.assertEqual(result["classification"], "INVENTORY_COMPLETE_WITH_FINDINGS")
        self.assertEqual(result["package_sources"][0]["state"], "absent")
        self.assertEqual(result["native_dependencies"], [])

    def test_nested_shape_checks_reject_bool_as_int_and_wrong_types_without_echo(self):
        cases = [
            {"NSPrivacyTracking": 0},
            {"NSPrivacyTrackingDomains": PRIVATE},
            {"NSPrivacyCollectedDataTypes": [{}]},
            {"NSPrivacyAccessedAPITypes": [PRIVATE]},
            {
                "NSPrivacyAccessedAPITypes": [
                    {
                        "NSPrivacyAccessedAPIType": PRIVATE,
                        "NSPrivacyAccessedAPITypeReasons": [],
                    }
                ]
            },
            {
                "NSPrivacyCollectedDataTypes": [
                    {
                        "NSPrivacyCollectedDataType": PRIVATE,
                        "NSPrivacyCollectedDataTypeLinked": 1,
                        "NSPrivacyCollectedDataTypeTracking": False,
                        "NSPrivacyCollectedDataTypePurposes": [PRIVATE],
                    }
                ]
            },
        ]
        for value in cases:
            with self.subTest(value=value):
                self.write_manifest(value=value)
                result = self.run_inventory()
                self.assertTrue(result["scan_complete"])
                self.assertTrue(result["manifests"][0]["findings"])
                self.assertNotIn(PRIVATE, json.dumps(result))

    def test_tracking_domains_and_unknown_keys_are_not_echoed(self):
        value = manifest()
        value.update(NSPrivacyTracking=True, NSPrivacyTrackingDomains=[PRIVATE])
        value[PRIVATE] = PRIVATE
        self.write_manifest(value=value)
        result = self.run_inventory()
        row = result["manifests"][0]
        self.assertEqual(row["fields"]["tracking_domains"]["count"], 1)
        self.assertEqual(row["unknown_key_count"], 1)
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_malformed_and_duplicate_plist_keys_are_findings(self):
        path = self.write_manifest()
        for source in (
            PRIVATE.encode(),
            plistlib.dumps([]),
            b'<plist version="1.0"><dict><key>NSPrivacyTracking</key><true/>'
            b"<key>NSPrivacyTracking</key><false/></dict></plist>",
        ):
            path.write_bytes(source)
            result = self.run_inventory()
            self.assertTrue(result["scan_complete"])
            self.assertFalse(result["manifests"][0]["plist_decoded"])
            self.assertNotIn(PRIVATE, json.dumps(result))

    def test_bundle_and_arbitrary_asset_locations_are_not_apple_coverage_proof(self):
        self.write_manifest("GoogleSignIn_GoogleSignIn.bundle/PrivacyInfo.xcprivacy")
        self.write_manifest("assets/other/PrivacyInfo.xcprivacy")
        result = self.run_inventory()
        self.assertEqual(
            {r["location_kind"] for r in result["manifests"]}, {"bundle", "other"}
        )
        self.assertFalse(result["sdk_coverage_verified"])
        self.assertEqual(result["root_manifest"], "absent")

    def test_upstream_resource_aliases_are_exact_name_hints_only(self):
        expected = {
            "AppAuth_AppAuthCore.bundle": "app_auth",
            "GTMSessionFetcher_GTMSessionFetcherCore.bundle": "gtm_session_fetcher",
            "GoogleUtilities_GoogleUtilities-Environment.bundle": "google_utilities",
            "GoogleUtilities_GoogleUtilities-Logger.bundle": "google_utilities",
            "GoogleUtilities_GoogleUtilities-UserDefaults.bundle": "google_utilities",
            "Promises_FBLPromises.bundle": "promises",
        }
        for bundle, alias in expected.items():
            with self.subTest(bundle=bundle):
                row = inventory._manifest(
                    plistlib.dumps(manifest()),
                    Path(bundle) / "PrivacyInfo.xcprivacy",
                    1,
                )
                self.assertEqual(row["component"], alias)
                self.assertEqual(row["location_kind"], "bundle")
                self.assertFalse(row["values_validated"])
                for near_miss in (
                    PRIVATE + bundle,
                    bundle.replace(".bundle", PRIVATE + ".bundle"),
                    bundle.lower(),
                ):
                    unknown = inventory._manifest(
                        plistlib.dumps(manifest()),
                        Path(near_miss) / "PrivacyInfo.xcprivacy",
                        1,
                    )
                    self.assertEqual(unknown["component"], "unknown_component")
                    self.assertNotIn(PRIVATE, json.dumps(unknown))

    def test_google_transitive_identities_are_resolved_not_linkage(self):
        for schema in (2, 3):
            payload = {"version": schema, "pins": []}
            for identity, alias, version in (
                ("app-check", "app_check", "11.3.2"),
                ("interop-ios-for-google-sdks", "google_interop", "101.0.0"),
            ):
                payload["pins"].extend(lock(version, identity)["pins"])
                for near_miss in (
                    PRIVATE + identity,
                    identity + PRIVATE,
                    identity.upper(),
                ):
                    payload["pins"].extend(lock(version, near_miss)["pins"])
            self.packages[0].write_text(json.dumps(payload), encoding="utf-8")
            self.packages[1].write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_inventory()
            self.assertEqual(
                result["native_dependencies"],
                [
                    {
                        "component": alias,
                        "state": "resolved_version",
                        "versions": [version],
                        "slots": [1, 2],
                    }
                    for alias, version in (
                        ("app_check", "11.3.2"),
                        ("google_interop", "101.0.0"),
                    )
                ],
            )
            self.assertEqual(result["package_sources"][0]["unknown_identity_count"], 6)
            self.assertFalse(result["sdk_coverage_verified"])
            self.assertFalse(result["runtime_verified"])
            self.assertFalse(result["compliance_verified"])
            self.assertNotIn(PRIVATE, json.dumps(result))

    def test_unknown_container_is_a_finding_even_with_root_and_valid_locks(self):
        self.write_manifest()
        self.write_manifest(PRIVATE + ".bundle/PrivacyInfo.xcprivacy")
        for path in self.packages:
            path.write_text(json.dumps(lock()), encoding="utf-8")
        result = self.run_inventory()
        self.assertEqual(result["root_manifest"], "present")
        self.assertTrue(result["scan_complete"])
        self.assertEqual(result["classification"], "INVENTORY_COMPLETE_WITH_FINDINGS")
        unknown = next(
            row
            for row in result["manifests"]
            if row["component"] == "unknown_component"
        )
        self.assertIn("manifest:UNRECOGNIZED_COMPONENT", unknown["findings"])
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_generic_resource_bundle_never_inherits_line_attribution(self):
        for relative in (
            "Resource.bundle/PrivacyInfo.xcprivacy",
            "LineSDK_LineSDK.bundle/Resource.bundle/PrivacyInfo.xcprivacy",
            "Frameworks/LineSDK.framework/Resource.bundle/PrivacyInfo.xcprivacy",
        ):
            row = inventory._manifest(plistlib.dumps(manifest()), Path(relative), 1)
            self.assertEqual(row["component"], "unknown_component")
            self.assertIn("manifest:UNRECOGNIZED_COMPONENT", row["findings"])

    def test_new_identity_keeps_conflict_and_revision_only_evidence(self):
        self.packages[0].write_text(
            json.dumps(lock("11.3.1", "app-check")), encoding="utf-8"
        )
        self.packages[1].write_text(
            json.dumps(lock("11.3.2", "app-check")), encoding="utf-8"
        )
        self.assertEqual(
            self.run_inventory()["native_dependencies"][0]["state"], "conflict"
        )
        payload = lock(identity="app-check")
        payload["pins"][0]["state"] = {"revision": PRIVATE}
        self.packages[1].write_text(json.dumps(payload), encoding="utf-8")
        result = self.run_inventory()
        self.assertEqual(
            result["native_dependencies"][0]["state"], "native_version_unknown"
        )
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_lock_conflicts_unknown_versions_schemas_and_identities(self):
        self.packages[0].write_text(json.dumps(lock("9.0.0")), encoding="utf-8")
        self.packages[1].write_text(json.dumps(lock("9.1.0")), encoding="utf-8")
        result = self.run_inventory()
        self.assertEqual(result["native_dependencies"][0]["state"], "conflict")
        self.assertEqual(
            result["native_dependencies"][0]["versions"], ["9.0.0", "9.1.0"]
        )
        self.packages[1].unlink()
        for payload, expected in (
            ({"version": True, "pins": []}, "unsupported_schema"),
            ({"version": 99, "pins": []}, "unsupported_schema"),
            (lock(None), "parsed"),
            (lock(identity=PRIVATE), "parsed"),
        ):
            self.packages[0].write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_inventory()
            self.assertEqual(result["package_sources"][0]["state"], expected)
            self.assertNotIn(PRIVATE, json.dumps(result))
        result = self.run_inventory()
        self.assertEqual(result["package_sources"][0]["unknown_identity_count"], 1)

    def test_lock_duplicate_keys_and_pins_are_detected(self):
        for raw in (
            '{"version":2,"version":3,"pins":[]}',
            json.dumps({"version": 3, "pins": lock()["pins"] * 2}),
        ):
            self.packages[0].write_text(raw, encoding="utf-8")
            result = self.run_inventory()
            self.assertEqual(
                result["classification"], "INVENTORY_COMPLETE_WITH_FINDINGS"
            )
            self.assertTrue(result["package_sources"][0]["findings"])

    def test_signed_app_and_invalid_commit_stop_without_reading_manifest(self):
        (self.app / "embedded.mobileprovision").write_text(PRIVATE, encoding="utf-8")
        result = self.run_inventory()
        self.assertEqual(result["classification"], "STOP")
        self.assertEqual(result["failure"]["check"], "unsigned_application")
        self.assertEqual(result["manifests"], [])
        result = inventory.inspect_app(self.app, source_commit=PRIVATE)
        self.assertEqual(result["failure"]["check"], "source_commit")
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_limits_are_scan_failures_not_absence(self):
        self.write_manifest("nested/PrivacyInfo.xcprivacy")
        for constant, limit in (
            ("MAX_ENTRIES", 1),
            ("MAX_DEPTH", 0),
            ("MAX_METADATA_BYTES", 8),
            ("MAX_FILE_BYTES", 8),
            ("MAX_MANIFESTS", 0),
        ):
            with (
                self.subTest(constant=constant),
                mock.patch.object(inventory, constant, limit),
            ):
                result = self.run_inventory()
                self.assertEqual(result["classification"], "STOP")
                self.assertFalse(result["scan_complete"])
                self.assertIsNotNone(result["failure"])

    def test_linked_root_parent_and_leaf_are_rejected(self):
        self.write_manifest()
        link = self.root / "linked.app"
        try:
            link.symlink_to(self.app, target_is_directory=True)
        except OSError:
            self.skipTest("OS does not grant symlink creation")
        result = inventory.inspect_app(link, source_commit=SHA)
        self.assertEqual(result["classification"], "STOP")
        parent = self.root / "parent"
        parent.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(
            inventory.inspect_app(parent / "Runner.app", source_commit=SHA)[
                "classification"
            ],
            "STOP",
        )
        (self.app / "linked.xcprivacy").symlink_to(self.app / "PrivacyInfo.xcprivacy")
        self.assertEqual(self.run_inventory()["classification"], "STOP")

    def test_read_error_retains_safe_stage_and_never_echoes_exception(self):
        self.write_manifest()
        with mock.patch.object(
            inventory, "_read_metadata", side_effect=OSError(PRIVATE)
        ):
            result = self.run_inventory()
        self.assertEqual(result["classification"], "STOP")
        self.assertFalse(result["scan_complete"])
        self.assertEqual(result["failure"]["stage"], "application")
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_partial_manifest_failure_retains_evidence_and_identifies_ordinal(self):
        first = self.write_manifest("a/PrivacyInfo.xcprivacy")
        second = self.write_manifest("b/PrivacyInfo.xcprivacy")
        original_read = inventory._read_metadata

        def read(path, budget):
            if path == second:
                raise OSError(PRIVATE)
            return original_read(path, budget)

        with mock.patch.object(inventory, "_read_metadata", side_effect=read):
            result = self.run_inventory()
        self.assertEqual(result["classification"], "STOP")
        self.assertFalse(result["scan_complete"])
        self.assertEqual(len(result["manifests"]), 1)
        self.assertEqual(result["manifests"][0]["bytes"], first.stat().st_size)
        self.assertEqual(
            result["failure"],
            {"stage": "manifest", "check": "metadata_read_2", "reason": "READ_FAILED"},
        )
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_revision_or_branch_pins_do_not_become_known_versions(self):
        for schema in (2, 3):
            for state in (
                {"revision": PRIVATE},
                {"branch": PRIVATE, "revision": PRIVATE},
            ):
                payload = lock()
                payload["version"] = schema
                payload["pins"][0]["state"] = state
                self.packages[0].write_text(json.dumps(payload), encoding="utf-8")
                self.packages[1].write_text(json.dumps(lock()), encoding="utf-8")
                result = self.run_inventory()
                row = result["native_dependencies"][0]
                self.assertEqual(row["state"], "native_version_unknown")
                self.assertEqual(row["versions"], ["9.0.0"])
                self.assertEqual(row["slots"], [1, 2])
                self.assertNotIn(PRIVATE, json.dumps(result))

    def test_dotdot_and_hardlinked_metadata_are_rejected(self):
        self.write_manifest()
        result = inventory.inspect_app(
            self.root / "ignored" / ".." / "Runner.app", source_commit=SHA
        )
        self.assertEqual(result["failure"]["reason"], "PATH_TRAVERSAL_REJECTED")
        source = self.app / "Info.plist"
        try:
            os.link(source, self.root / "hardlink")
        except OSError:
            self.skipTest("OS does not grant hardlink creation")
        self.assertEqual(self.run_inventory()["failure"]["reason"], "NON_REGULAR_FILE")

    def test_changed_metadata_is_not_reported_as_scan_complete(self):
        original_stat = os.fstat

        def changed(descriptor):
            current = original_stat(descriptor)
            values = {
                name: getattr(current, name)
                for name in (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
            }
            values["st_size"] += 1
            return SimpleNamespace(**values)

        with mock.patch.object(inventory.os, "fstat", side_effect=changed):
            result = self.run_inventory()
        self.assertFalse(result["scan_complete"])
        self.assertEqual(result["failure"]["reason"], "INPUT_CHANGED")

    def test_summary_failure_is_still_stop_not_complete(self):
        # No manifests or locks: the sole digest call is the evidence summary.
        with mock.patch.object(
            inventory, "digest_bytes", side_effect=RuntimeError(PRIVATE)
        ):
            result = self.run_inventory()
        self.assertEqual(result["classification"], "STOP")
        self.assertFalse(result["scan_complete"])
        self.assertEqual(
            result["failure"],
            {
                "stage": "evidence",
                "check": "summary_digest",
                "reason": "UNEXPECTED_ERROR",
            },
        )
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_readonly_scan_and_misnamed_manifest_are_explicit(self):
        self.write_manifest("assets/NotApple.xcprivacy")
        before = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        result = self.run_inventory()
        after = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        self.assertEqual(result["root_manifest"], "absent")
        self.assertIn("filename:NOT_STANDARD_NAME", result["manifests"][0]["findings"])

    def test_nested_unknown_bundle_does_not_inherit_framework_attribution(self):
        self.write_manifest(
            "Frameworks/Flutter.framework/Other.bundle/PrivacyInfo.xcprivacy"
        )
        result = self.run_inventory()
        row = result["manifests"][0]
        self.assertEqual(row["component"], "unknown_component")
        self.assertEqual(row["location_kind"], "bundle")

    def test_cli_emits_one_json_and_no_raw_parser_input(self):
        self.write_manifest()
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            code = inventory.main(["--app", str(self.app), "--source-commit", SHA])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())["scan_complete"])
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            code = inventory.main(["--" + PRIVATE])
        self.assertEqual(code, 2)
        self.assertNotIn(PRIVATE, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["failure"]["stage"], "input")


if __name__ == "__main__":
    unittest.main()
