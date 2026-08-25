from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.google_auth_staging_preflight import (
    ProviderApprovalError,
    _consume_cli_approval,
    _consumed_sidecar_path,
    _read_opened_json,
    canonical_approval_sha256,
    execution_binding_sha256,
    load_provider_approval,
    main,
)
from tools.mobile_staging_broker_rollout import BrokerRolloutError


PROJECT = "ntubtob-mobile-staging"
TESTER = "fictional.tester@example.invalid"
FINGERPRINT = "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD"
WEB_ALIAS = "google-auth-staging-web"
ANDROID_ALIAS = "google-auth-staging-android"
WEB_DISPLAY_NAME = "NTUBTOB Mobile Staging Web Server"
ANDROID_DISPLAY_NAME = "NTUBTOB Mobile Staging Android"
NOW = datetime(2026, 8, 26, 0, 10, tzinfo=timezone.utc)


def approval() -> dict:
    return {
        "schema_version": 2,
        "approval_id": "123e4567-e89b-42d3-a456-426614174000",
        "authority": {
            "task_id": "TASK-157",
            "decision_id": "DEC-100",
            "owner_gate_id": "TASK-157-OWNER-GATE-GOOGLE-AUTH-SEPARATION-20260826",
            "main_claim_id": "main-work-20260825",
            "main_lease_version": 17,
        },
        "owner_approved": True,
        "project": PROJECT,
        "validity": {
            "not_before": "2026-08-26T00:05:00Z",
            "expires_at": "2026-08-26T00:20:00Z",
        },
        "execution_binding": {
            "nonce": "a" * 64,
            "one_shot": True,
            "consume_via": "private-sidecar",
        },
        "consent_screen": {
            "application_name": "NTUBTOB Mobile Staging",
            "user_type": "external",
            "publishing_status": "testing",
            "scopes": ["openid", "email", "profile"],
            "tester_classification": "fictional",
            "tester_accounts": [TESTER],
        },
        "inventory": {
            "status": "complete",
            "project": PROJECT,
            "observed_at": "2026-08-26T00:00:00Z",
            "matching_client_count": 0,
            "duplicate_client_count": 0,
            "cross_project_client_count": 0,
            "matching_keys": {
                "web": {"alias": WEB_ALIAS, "display_name": WEB_DISPLAY_NAME},
                "android": {
                    "alias": ANDROID_ALIAS,
                    "display_name": ANDROID_DISPLAY_NAME,
                    "package_name": "tw.org.ntubtob.portal",
                    "sha1_fingerprint": FINGERPRINT,
                },
            },
        },
        "planned_clients": [
            {
                "client_type": "web",
                "alias": WEB_ALIAS,
                "display_name": WEB_DISPLAY_NAME,
                "action": "create",
                "owning_project": PROJECT,
                "dedicated": True,
                "javascript_origins": [],
                "redirect_uris": [],
            },
            {
                "client_type": "android",
                "alias": ANDROID_ALIAS,
                "display_name": ANDROID_DISPLAY_NAME,
                "action": "create",
                "owning_project": PROJECT,
                "dedicated": True,
                "package_name": "tw.org.ntubtob.portal",
                "sha1_fingerprint": FINGERPRINT,
            },
        ],
        "mutation_boundary": {
            "auth_platform_registration_count": 1,
            "consent_configuration_count": 1,
            "tester_add_count": 1,
            "web_client_create_count": 1,
            "android_client_create_count": 1,
            "secret_mutation_count": 0,
            "iam_mutation_count": 0,
            "public_access_mutation_count": 0,
            "billing_mutation_count": 0,
            "runtime_mutation_count": 0,
            "traffic_mutation_count": 0,
            "rollback": "retain-provider-resources-and-evidence",
        },
    }


def approval_for_now(now: datetime) -> dict:
    value = approval()
    exact_now = now.astimezone(timezone.utc).replace(microsecond=0)

    def rendered(delta: timedelta) -> str:
        return (exact_now + delta).strftime("%Y-%m-%dT%H:%M:%SZ")

    value["inventory"]["observed_at"] = rendered(timedelta(minutes=-5))
    value["validity"]["not_before"] = rendered(timedelta(minutes=-1))
    value["validity"]["expires_at"] = rendered(timedelta(minutes=10))
    return value


class GoogleAuthStagingPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "private-approval.json"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value: dict, *, indent: int | None = None) -> None:
        self.path.write_text(
            json.dumps(value, indent=indent, ensure_ascii=False), encoding="utf-8"
        )

    def load(self, **kwargs) -> dict:
        return load_provider_approval(self.path, now=NOW, **kwargs)

    def replace(self, field: str, replacement: object) -> dict:
        value = approval()
        target = value
        parts = field.split(".")
        for part in parts[:-1]:
            target = target[int(part)] if part.isdigit() else target[part]
        last = parts[-1]
        if last.isdigit():
            target[int(last)] = replacement
        else:
            target[last] = replacement
        return value

    def assert_rejected(self, field: str, replacement: object) -> None:
        self.write(self.replace(field, replacement))
        with self.assertRaises(ProviderApprovalError):
            self.load()

    def test_accepts_exact_short_lived_authority_bound_bootstrap(self):
        value = approval()
        self.write(value)
        self.assertEqual(self.load(), value)

    def test_hash_is_canonical_and_format_independent(self):
        value = approval()
        self.write(value, indent=2)
        first = canonical_approval_sha256(self.load())
        self.write(value)
        second = canonical_approval_sha256(self.load())
        expected = hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual((first, second), (expected, expected))

    def test_replay_is_rejected_by_consumed_sidecar_binding(self):
        self.write(approval())
        binding = execution_binding_sha256(self.load())
        with self.assertRaises(ProviderApprovalError):
            self.load(consumed_execution_bindings={binding})

    def test_rejects_not_before_expired_or_overlong_windows(self):
        self.write(approval())
        for now in (
            datetime(2026, 8, 26, 0, 4, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 26, 0, 20, tzinfo=timezone.utc),
        ):
            with self.subTest(now=now), self.assertRaises(ProviderApprovalError):
                load_provider_approval(self.path, now=now)
        self.write(self.replace("validity.expires_at", "2026-08-26T00:31:00Z"))
        with self.assertRaises(ProviderApprovalError):
            self.load()

    def test_rejects_non_utc_or_non_exact_timestamp(self):
        for field, replacement in (
            ("inventory.observed_at", "2026-08-26T08:00:00+08:00"),
            ("validity.not_before", "2026-08-26T00:05:00.000Z"),
            ("validity.expires_at", "not-a-time"),
        ):
            with self.subTest(field=field):
                self.assert_rejected(field, replacement)

    def test_requires_exact_authority_and_packet_identifiers(self):
        mutations = (
            ("approval_id", "not-a-uuid"),
            ("authority.task_id", "TASK-158"),
            ("authority.decision_id", "DEC-099"),
            ("authority.owner_gate_id", "another-owner-gate"),
            ("authority.main_claim_id", "another-main"),
            ("authority.main_lease_version", 16),
            ("execution_binding.nonce", "short"),
            ("execution_binding.one_shot", False),
        )
        for field, replacement in mutations:
            with self.subTest(field=field):
                self.assert_rejected(field, replacement)

    def test_rejects_repository_path(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=repository) as directory:
            path = Path(directory) / "private-approval.json"
            path.write_text(json.dumps(approval()), encoding="utf-8")
            with self.assertRaises(ProviderApprovalError):
                load_provider_approval(path, now=NOW)

    def test_rejects_hardlinked_approval(self):
        self.write(approval())
        hardlink = Path(self.temp.name) / "hardlink.json"
        try:
            os.link(self.path, hardlink)
        except OSError:
            self.skipTest("hardlink creation unavailable")
        with self.assertRaises(ProviderApprovalError):
            load_provider_approval(hardlink, now=NOW)

    def test_rejects_reparse_ancestor_through_shared_helper(self):
        self.write(approval())
        with patch(
            "tools.google_auth_staging_preflight._assert_path_chain_no_reparse",
            side_effect=BrokerRolloutError("PATH_INVALID"),
        ):
            with self.assertRaises(ProviderApprovalError):
                self.load()

    def test_rejects_opened_handle_identity_or_mtime_change(self):
        self.write(approval())
        actual = os.stat(self.path, follow_symlinks=False)
        changed = SimpleNamespace(
            st_dev=actual.st_dev,
            st_ino=actual.st_ino,
            st_size=actual.st_size,
            st_mtime_ns=actual.st_mtime_ns + 1,
        )
        with patch(
            "tools.google_auth_staging_preflight._assert_path_chain_no_reparse"
        ), patch(
            "tools.google_auth_staging_preflight.os.stat",
            side_effect=(actual, changed),
        ):
            with self.assertRaises(ProviderApprovalError):
                _read_opened_json(self.path)

    def test_cli_emits_only_classification_and_hash(self):
        self.write(approval())
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main([str(self.path)], now=NOW)
        output = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(set(output), {"classification", "approval_sha256"})
        for private_value in (TESTER, FINGERPRINT, PROJECT, "redirect_uris"):
            self.assertNotIn(private_value, stdout.getvalue())
        sidecar = json.loads(_consumed_sidecar_path(self.path).read_text("utf-8"))
        self.assertEqual(
            set(sidecar),
            {"schema_version", "binding_sha256", "approval_sha256", "consumed_at"},
        )
        rendered = json.dumps(sidecar)
        for private_value in (TESTER, FINGERPRINT, PROJECT, self.path.name):
            self.assertNotIn(private_value, rendered)

    def test_second_cli_process_is_rejected_after_first_pass(self):
        self.write(approval_for_now(datetime.now(timezone.utc)))
        repository = Path(__file__).resolve().parents[2]
        command = [
            sys.executable,
            "-m",
            "tools.google_auth_staging_preflight",
            str(self.path),
        ]
        first = subprocess.run(
            command,
            cwd=repository,
            check=False,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        second = subprocess.run(
            command,
            cwd=repository,
            check=False,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(first.returncode, 0)
        self.assertEqual(json.loads(first.stdout)["classification"], "PASS")
        self.assertEqual((second.returncode, second.stdout), (2, ""))
        self.assertEqual(second.stderr, "ERROR: PROVIDER_APPROVAL_INVALID\n")
        self.assertNotIn(str(self.path), first.stdout + first.stderr + second.stderr)

    def test_preexisting_empty_or_malformed_sidecar_blocks_pass(self):
        for content in (b"", b"not-json"):
            with self.subTest(content=content):
                directory = Path(self.temp.name) / hashlib.sha256(content).hexdigest()
                directory.mkdir()
                path = directory / "private-approval.json"
                path.write_text(json.dumps(approval()), encoding="utf-8")
                _consumed_sidecar_path(path).write_bytes(content)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = main([str(path)], now=NOW)
                self.assertEqual(result, 2)
                self.assertEqual(
                    stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n"
                )

    def test_write_failure_leaves_sidecar_and_blocks_replay(self):
        self.write(approval())
        stderr = io.StringIO()
        with patch(
            "tools.google_auth_staging_preflight._write_sidecar_bytes",
            side_effect=OSError("PRIVATE-WRITE-SENTINEL"),
        ), contextlib.redirect_stderr(stderr):
            first = main([str(self.path)], now=NOW)
        self.assertEqual(first, 2)
        self.assertTrue(_consumed_sidecar_path(self.path).exists())
        with contextlib.redirect_stderr(io.StringIO()):
            second = main([str(self.path)], now=NOW)
        self.assertEqual(second, 2)
        self.assertNotIn("PRIVATE-WRITE-SENTINEL", stderr.getvalue())

    def test_sidecar_reparse_boundary_fails_before_create(self):
        self.write(approval())
        loaded = self.load()
        with patch(
            "tools.google_auth_staging_preflight._assert_path_chain_no_reparse",
            side_effect=BrokerRolloutError("PATH_INVALID"),
        ):
            with self.assertRaises(ProviderApprovalError):
                _consume_cli_approval(self.path, loaded, NOW)
        self.assertFalse(_consumed_sidecar_path(self.path).exists())

    def test_cli_usage_error_does_not_echo_argv_or_private_path(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        sentinel = "PRIVATE-PATH-SENTINEL"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["--unexpected", sentinel], now=NOW)
        self.assertEqual((result, stdout.getvalue()), (2, ""))
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")
        self.assertNotIn(sentinel, stderr.getvalue())

    def test_cli_contract_failure_is_fixed_and_redacted(self):
        self.write(self.replace("planned_clients.1.sha1_fingerprint", "PRIVATE"))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main([str(self.path)], now=NOW)
        self.assertEqual((result, stdout.getvalue()), (2, ""))
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")

    def test_rejects_unknown_duplicate_or_production_fields(self):
        value = approval()
        value["unexpected"] = True
        self.write(value)
        with self.assertRaises(ProviderApprovalError):
            self.load()
        self.path.write_text(
            '{"schema_version":2,"schema_version":2}', encoding="utf-8"
        )
        with self.assertRaises(ProviderApprovalError):
            self.load()
        self.assert_rejected(
            "consent_screen.tester_accounts",
            ["fictional@ntubtob-schedule-405614.invalid"],
        )

    def test_rejects_target_inventory_alias_or_matching_key_drift(self):
        mutations = (
            ("project", "another-staging"),
            ("inventory.status", "unknown"),
            ("inventory.matching_client_count", 1),
            ("inventory.duplicate_client_count", 1),
            ("inventory.cross_project_client_count", 1),
            ("planned_clients.0.alias", "another-web"),
            ("planned_clients.1.display_name", "Another Android"),
            ("inventory.matching_keys.web.alias", "another-web"),
            ("inventory.matching_keys.android.sha1_fingerprint", "00:" * 19 + "00"),
        )
        for field, replacement in mutations:
            with self.subTest(field=field):
                self.assert_rejected(field, replacement)

    def test_rejects_consent_tester_and_client_drift(self):
        mutations = (
            ("consent_screen.user_type", "internal"),
            ("consent_screen.publishing_status", "production"),
            ("consent_screen.scopes", ["openid", "email", "profile", "calendar"]),
            ("consent_screen.tester_classification", "real-user"),
            ("consent_screen.tester_accounts", []),
            ("planned_clients.0.javascript_origins", ["https://example.invalid"]),
            ("planned_clients.0.redirect_uris", ["https://example.invalid"]),
            ("planned_clients.1.package_name", "org.example.other"),
            ("planned_clients.1.sha1_fingerprint", FINGERPRINT.lower()),
            ("planned_clients.1.action", "reuse"),
            ("planned_clients.1.dedicated", False),
            ("planned_clients.1.owning_project", "another-staging"),
        )
        for field, replacement in mutations:
            with self.subTest(field=field):
                self.assert_rejected(field, replacement)

    def test_requires_exactly_one_web_and_one_android_client(self):
        for clients in (
            [],
            [approval()["planned_clients"][0]],
            [approval()["planned_clients"][0]] * 2,
            approval()["planned_clients"] * 2,
        ):
            with self.subTest(client_count=len(clients)):
                value = approval()
                value["planned_clients"] = copy.deepcopy(clients)
                self.write(value)
                with self.assertRaises(ProviderApprovalError):
                    self.load()

    def test_requires_exact_action_counts_and_zero_external_mutations(self):
        fields = (
            "auth_platform_registration_count",
            "consent_configuration_count",
            "tester_add_count",
            "web_client_create_count",
            "android_client_create_count",
            "secret_mutation_count",
            "iam_mutation_count",
            "public_access_mutation_count",
            "billing_mutation_count",
            "runtime_mutation_count",
            "traffic_mutation_count",
        )
        for field in fields:
            with self.subTest(field=field):
                value = approval()
                value["mutation_boundary"][field] += 1
                self.write(value)
                with self.assertRaises(ProviderApprovalError):
                    self.load()
        self.assert_rejected("mutation_boundary.rollback", "delete-provider-resources")


if __name__ == "__main__":
    unittest.main()
