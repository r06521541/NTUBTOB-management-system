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
    _default_consumption_root,
    _bootstrap_consumption_root,
    _read_opened_json,
    _select_windows_logon_sid,
    _validate_windows_acl_state,
    _verify_windows_private_acl,
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


PHASE_STATES = {
    "registration": ("unconfigured", "unconfigured", 0, 0, 0),
    "web_client_create": ("registered", "exact", 0, 0, 0),
    "android_client_create": ("registered", "exact", 0, 1, 0),
    "tester_add": ("registered", "exact", 0, 1, 1),
}
PHASE_CLIENT_ACTIONS = {
    "registration": ("not-authorized", "not-authorized"),
    "web_client_create": ("create", "not-authorized"),
    "android_client_create": ("completed", "create"),
    "tester_add": ("completed", "completed"),
}
PHASE_ACTION_FIELDS = {
    "registration": (
        "auth_platform_registration_count",
        "consent_configuration_count",
    ),
    "web_client_create": ("web_client_create_count",),
    "android_client_create": ("android_client_create_count",),
    "tester_add": ("tester_add_count",),
}


def phase_approval(phase: str) -> dict:
    value = approval()
    value["schema_version"] = 3
    value["phase"] = phase
    platform, consent, tester, web, android = PHASE_STATES[phase]
    value["inventory"] = {
        "status": "complete",
        "project": PROJECT,
        "observed_at": "2026-08-26T00:00:00Z",
        "auth_platform_status": platform,
        "consent_status": consent,
        "tester_count": tester,
        "web_client_count": web,
        "android_client_count": android,
        "duplicate_client_count": 0,
        "cross_project_client_count": 0,
        "matching_keys": copy.deepcopy(approval()["inventory"]["matching_keys"]),
    }
    web_action, android_action = PHASE_CLIENT_ACTIONS[phase]
    value["planned_clients"][0]["action"] = web_action
    value["planned_clients"][1]["action"] = android_action
    for field in (
        "auth_platform_registration_count",
        "consent_configuration_count",
        "tester_add_count",
        "web_client_create_count",
        "android_client_create_count",
    ):
        value["mutation_boundary"][field] = int(field in PHASE_ACTION_FIELDS[phase])
    return value


def approval_for_now(now: datetime, value: dict | None = None) -> dict:
    value = copy.deepcopy(value or approval())
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
        self.consumption_root = Path(self.temp.name) / "consumed"
        _bootstrap_consumption_root(self.consumption_root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value: dict, *, indent: int | None = None) -> None:
        self.path.write_text(
            json.dumps(value, indent=indent, ensure_ascii=False), encoding="utf-8"
        )

    def load(self, **kwargs) -> dict:
        return load_provider_approval(self.path, now=NOW, **kwargs)

    def execute(self, path: Path | None = None, *, now: datetime = NOW) -> int:
        return main(
            [str(path or self.path)],
            now=now,
            _test_consumption_root=self.consumption_root,
        )

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

    def test_never_reads_or_accepts_baked_broker_fixture(self):
        fixture = (
            Path(__file__).resolve().parents[2]
            / "apps/mobile_staging_broker/artifacts/candidate-approval.json"
        )
        self.assertTrue(fixture.is_file())
        with patch(
            "tools.google_auth_staging_preflight._read_opened_json"
        ) as read_approval:
            with self.assertRaises(ProviderApprovalError):
                load_provider_approval(fixture, now=NOW)
        read_approval.assert_not_called()

    def test_module_entrypoint_is_canonical_and_fails_closed_without_packet(self):
        repository = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "tools.google_auth_staging_preflight"],
            cwd=repository,
            check=False,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "ERROR: PROVIDER_APPROVAL_INVALID\n")

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
        self.write(phase_approval("registration"))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = self.execute()
        output = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(set(output), {"classification", "approval_sha256"})
        for private_value in (TESTER, FINGERPRINT, PROJECT, "redirect_uris"):
            self.assertNotIn(private_value, stdout.getvalue())
        sidecar = json.loads(
            _consumed_sidecar_path(
                phase_approval("registration"), self.consumption_root
            ).read_text("utf-8")
        )
        self.assertEqual(
            set(sidecar),
            {"schema_version", "binding_sha256", "approval_sha256", "consumed_at"},
        )
        rendered = json.dumps(sidecar)
        for private_value in (TESTER, FINGERPRINT, PROJECT, self.path.name):
            self.assertNotIn(private_value, rendered)

    def test_second_cli_process_is_rejected_after_first_pass(self):
        self.write(
            approval_for_now(
                datetime.now(timezone.utc), phase_approval("web_client_create")
            )
        )
        repository = Path(__file__).resolve().parents[2]
        script = (
            "import sys; from pathlib import Path; "
            "from tools.google_auth_staging_preflight import main; "
            "raise SystemExit(main([sys.argv[1]], _test_consumption_root=Path(sys.argv[2])))"
        )
        command = [
            sys.executable,
            "-c",
            script,
            str(self.path),
            str(self.consumption_root),
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

    def test_identical_binding_copied_to_two_filenames_passes_once(self):
        value = phase_approval("android_client_create")
        first_path = Path(self.temp.name) / "first-private.json"
        second_path = Path(self.temp.name) / "second-private.json"
        rendered = json.dumps(value)
        first_path.write_text(rendered, encoding="utf-8")
        second_path.write_text(rendered, encoding="utf-8")
        outputs: list[tuple[int, str, str]] = []
        for path in (first_path, second_path):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = self.execute(path)
            outputs.append((result, stdout.getvalue(), stderr.getvalue()))
        self.assertEqual([item[0] for item in outputs], [0, 2])
        self.assertEqual(json.loads(outputs[0][1])["classification"], "PASS")
        self.assertEqual(outputs[1][1:], ("", "ERROR: PROVIDER_APPROVAL_INVALID\n"))

    def test_default_namespace_is_independent_of_checkout_path(self):
        first = _default_consumption_root()
        with patch(
            "tools.google_auth_staging_preflight.REPOSITORY_ROOT",
            Path("Z:/another-clone/renamed-checkout"),
        ):
            second = _default_consumption_root()
        self.assertEqual(first, second)
        repository = Path(__file__).resolve().parents[2]
        self.assertFalse(first == repository or first.is_relative_to(repository))

    def test_normal_cli_fails_closed_when_namespace_is_absent(self):
        self.write(phase_approval("registration"))
        absent = Path(self.temp.name) / "absent-consumption"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main([str(self.path)], now=NOW, _test_consumption_root=absent)
        self.assertEqual((result, stdout.getvalue()), (2, ""))
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")
        self.assertFalse(absent.exists())

    def test_explicit_namespace_bootstrap_is_sanitized_and_idempotent(self):
        root = Path(self.temp.name) / "explicit-bootstrap"
        outputs = []
        for _ in range(2):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(
                    ["--bootstrap-consumption-namespace"],
                    _test_consumption_root=root,
                )
            outputs.append((result, stdout.getvalue(), stderr.getvalue()))
        for result, stdout, stderr in outputs:
            self.assertEqual((result, stderr), (0, ""))
            self.assertEqual(
                json.loads(stdout),
                {
                    "classification": "PASS",
                    "operation": "CONSUMPTION_NAMESPACE_BOOTSTRAP",
                    "state": "READY",
                },
            )
            self.assertNotIn(str(root), stdout)
        _verify_windows_private_acl(root) if os.name == "nt" else None

    def test_namespace_bootstrap_rejects_approval_and_acl_drift(self):
        self.write(phase_approval("registration"))
        unused = Path(self.temp.name) / "unused-bootstrap"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(
                ["--bootstrap-consumption-namespace", str(self.path)],
                _test_consumption_root=unused,
            )
        self.assertEqual(result, 2)
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")
        self.assertFalse(unused.exists())

        drifted = Path(self.temp.name) / "drifted-bootstrap"
        drifted.mkdir()
        with contextlib.redirect_stderr(io.StringIO()):
            result = main(
                ["--bootstrap-consumption-namespace"],
                _test_consumption_root=drifted,
            )
        self.assertEqual(result, 2)
        if os.name == "nt":
            with self.assertRaises(ProviderApprovalError):
                _verify_windows_private_acl(drifted)

        drifted_parent = Path(self.temp.name) / "drifted-parent"
        drifted_parent.mkdir()
        child = drifted_parent / "must-not-be-created"
        with self.assertRaises(ProviderApprovalError):
            _bootstrap_consumption_root(child, secured_component_count=2)
        self.assertFalse(child.exists())

    def test_new_namespace_is_secured_and_existing_acl_drift_fails_closed(self):
        root = Path(self.temp.name) / "isolated-consumption"
        with patch(
            "tools.google_auth_staging_preflight._verify_private_directory_security"
        ) as verify:
            self.assertEqual(_bootstrap_consumption_root(root), root.resolve())
        verify.assert_called_with(root.resolve())

        with patch(
            "tools.google_auth_staging_preflight._verify_private_directory_security",
            side_effect=ProviderApprovalError("ACL_DRIFT_SENTINEL"),
        ):
            with self.assertRaises(ProviderApprovalError):
                _bootstrap_consumption_root(root)

    def test_windows_acl_state_is_exact_and_drift_fails_closed(self):
        exact = [
            (0, 0x03, 0x001F01FF, "user"),
            (0, 0x03, 0x001F01FF, "system"),
            (0, 0x03, 0x001F01FF, "logon"),
        ]
        _validate_windows_acl_state(
            owner_is_user=True, dacl_is_protected=True, aces=exact
        )
        drifts = (
            {"owner_is_user": False, "dacl_is_protected": True, "aces": exact},
            {"owner_is_user": True, "dacl_is_protected": False, "aces": exact},
            {
                "owner_is_user": True,
                "dacl_is_protected": True,
                "aces": exact + [(0, 0x03, 0x001F01FF, "administrators")],
            },
            {
                "owner_is_user": True,
                "dacl_is_protected": True,
                "aces": [exact[0], exact[1], (0, 0x13, 0x001F01FF, "logon")],
            },
            {
                "owner_is_user": True,
                "dacl_is_protected": True,
                "aces": [exact[0], exact[1], (0, 0x03, 0x001F01FF, "everyone")],
            },
            {
                "owner_is_user": True,
                "dacl_is_protected": True,
                "aces": [exact[0], exact[1], (0, 0x03, 0x001F01FF, "opaque")],
            },
            {
                "owner_is_user": True,
                "dacl_is_protected": True,
                "aces": [exact[0], exact[1], (0, 0x03, 0x001F01FF, "old-logon")],
            },
            {"owner_is_user": True, "dacl_is_protected": True, "aces": []},
        )
        for drift in drifts:
            with self.subTest(drift=drift):
                with self.assertRaises(ProviderApprovalError):
                    _validate_windows_acl_state(**drift)

    def test_logon_sid_selection_models_normal_and_restricted_tokens(self):
        groups = [("ordinary", 0x00000004), ("logon-current", 0xC0000004)]
        arguments = {
            "is_logon_sid": lambda sid: sid.startswith("logon-"),
            "equal_sid": lambda left, right: left == right,
        }
        self.assertEqual(
            _select_windows_logon_sid(
                groups, [], token_is_restricted=False, **arguments
            ),
            "logon-current",
        )
        self.assertEqual(
            _select_windows_logon_sid(
                groups,
                [
                    ("opaque-1", 0x00000004),
                    ("logon-current", 0xC0000004),
                    ("opaque-2", 0x00000004),
                ],
                token_is_restricted=True,
                **arguments,
            ),
            "logon-current",
        )
        invalid_restricted_groups = (
            [],
            [("opaque-1", 0x00000004), ("old-logon", 0xC0000004)],
            [("logon-current", 0xC0000014)],
            [("logon-current", 0xC0000000)],
            [("logon-current", 0xC0000004), ("logon-current", 0xC0000004)],
        )
        for restricted_groups in invalid_restricted_groups:
            with self.subTest(restricted_groups=restricted_groups):
                with self.assertRaises(ProviderApprovalError):
                    _select_windows_logon_sid(
                        groups,
                        restricted_groups,
                        token_is_restricted=True,
                        **arguments,
                    )
        for invalid_groups in (
            [("logon-current", 0xC0000014)],
            [("logon-current", 0xC0000000)],
            groups + [("logon-second", 0xC0000004)],
        ):
            with self.subTest(invalid_groups=invalid_groups):
                with self.assertRaises(ProviderApprovalError):
                    _select_windows_logon_sid(
                        invalid_groups,
                        [],
                        token_is_restricted=False,
                        **arguments,
                    )

    @unittest.skipUnless(os.name == "nt", "Windows ACL integration only")
    def test_actual_windows_namespace_acl_drift_fails_closed_and_is_restored(self):
        root = Path(self.temp.name) / "actual-windows-acl"
        secured = _bootstrap_consumption_root(root)
        _verify_windows_private_acl(secured)
        secured.rmdir()
        root.mkdir()
        try:
            with self.assertRaises(ProviderApprovalError):
                _verify_windows_private_acl(root)
        finally:
            root.rmdir()
            recreated = _bootstrap_consumption_root(root)
            _verify_windows_private_acl(recreated)

    def test_concurrent_identical_binding_two_filenames_has_exactly_one_pass(self):
        value = approval_for_now(
            datetime.now(timezone.utc), phase_approval("tester_add")
        )
        paths = [
            Path(self.temp.name) / f"concurrent-{index}.json" for index in range(2)
        ]
        rendered = json.dumps(value)
        for path in paths:
            path.write_text(rendered, encoding="utf-8")
        repository = Path(__file__).resolve().parents[2]
        script = (
            "import sys; from pathlib import Path; "
            "from tools.google_auth_staging_preflight import main; "
            "raise SystemExit(main([sys.argv[1]], _test_consumption_root=Path(sys.argv[2])))"
        )
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(path),
                    str(self.consumption_root),
                ],
                cwd=repository,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for path in paths
        ]
        results = [process.communicate(timeout=30) for process in processes]
        returncodes = [process.returncode for process in processes]
        self.assertEqual(sorted(returncodes), [0, 2])
        passed = results[returncodes.index(0)]
        failed = results[returncodes.index(2)]
        self.assertEqual(json.loads(passed[0])["classification"], "PASS")
        self.assertEqual(failed, ("", "ERROR: PROVIDER_APPROVAL_INVALID\n"))

    def test_preexisting_empty_or_malformed_sidecar_blocks_pass(self):
        for content in (b"", b"not-json"):
            with self.subTest(content=content):
                directory = Path(self.temp.name) / hashlib.sha256(content).hexdigest()
                directory.mkdir()
                consumption_root = directory / "consumed"
                path = directory / "private-approval.json"
                path.write_text(
                    json.dumps(phase_approval("android_client_create")),
                    encoding="utf-8",
                )
                _bootstrap_consumption_root(consumption_root)
                sidecar = _consumed_sidecar_path(
                    phase_approval("android_client_create"), consumption_root
                )
                sidecar.write_bytes(content)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = main(
                        [str(path)], now=NOW, _test_consumption_root=consumption_root
                    )
                self.assertEqual(result, 2)
                self.assertEqual(
                    stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n"
                )

    def test_write_failure_leaves_sidecar_and_blocks_replay(self):
        self.write(phase_approval("tester_add"))
        stderr = io.StringIO()
        with patch(
            "tools.google_auth_staging_preflight._write_sidecar_bytes",
            side_effect=OSError("PRIVATE-WRITE-SENTINEL"),
        ), contextlib.redirect_stderr(stderr):
            first = self.execute()
        self.assertEqual(first, 2)
        sidecar = _consumed_sidecar_path(
            phase_approval("tester_add"), self.consumption_root
        )
        self.assertTrue(sidecar.exists())
        with contextlib.redirect_stderr(io.StringIO()):
            second = self.execute()
        self.assertEqual(second, 2)
        self.assertNotIn("PRIVATE-WRITE-SENTINEL", stderr.getvalue())

    def test_sidecar_reparse_boundary_fails_before_create(self):
        self.write(phase_approval("web_client_create"))
        loaded = self.load()
        with patch(
            "tools.google_auth_staging_preflight._assert_path_chain_no_reparse",
            side_effect=BrokerRolloutError("PATH_INVALID"),
        ):
            with self.assertRaises(ProviderApprovalError):
                _consume_cli_approval(
                    self.path,
                    loaded,
                    NOW,
                    _test_consumption_root=self.consumption_root,
                )
        self.assertFalse(_consumed_sidecar_path(loaded, self.consumption_root).exists())

    def test_consumption_namespace_inside_repository_is_rejected(self):
        self.write(phase_approval("registration"))
        repository_namespace = Path(__file__).resolve().parents[2] / "tools"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(
                [str(self.path)],
                now=NOW,
                _test_consumption_root=repository_namespace,
            )
        self.assertEqual((result, stdout.getvalue()), (2, ""))
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")

    def test_cli_usage_error_does_not_echo_argv_or_private_path(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        sentinel = "PRIVATE-PATH-SENTINEL"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["--unexpected", sentinel], now=NOW)
        self.assertEqual((result, stdout.getvalue()), (2, ""))
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")
        self.assertNotIn(sentinel, stderr.getvalue())

    def test_cli_has_no_namespace_rekey_or_override_argument(self):
        self.write(phase_approval("registration"))
        for private_argument in ("--rekey", "--consumption-root"):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(
                private_argument=private_argument
            ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main([str(self.path), private_argument], now=NOW)
            self.assertEqual((result, stdout.getvalue()), (2, ""))
            self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")

    def test_cli_contract_failure_is_fixed_and_redacted(self):
        value = phase_approval("android_client_create")
        value["planned_clients"][1]["sha1_fingerprint"] = "PRIVATE"
        self.write(value)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.execute()
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

    def test_accepts_each_exact_progressive_phase(self):
        for phase in PHASE_STATES:
            with self.subTest(phase=phase):
                value = phase_approval(phase)
                self.write(value)
                self.assertEqual(self.load(), value)

    def test_rejects_phase_transition_precondition_drift(self):
        mutations = (
            ("registration", "inventory.auth_platform_status", "registered"),
            ("web_client_create", "inventory.tester_count", 1),
            ("web_client_create", "inventory.web_client_count", 1),
            ("android_client_create", "inventory.web_client_count", 0),
            ("android_client_create", "inventory.android_client_count", 1),
            ("tester_add", "inventory.tester_count", 1),
            ("tester_add", "inventory.android_client_count", 0),
        )
        for phase, field, replacement in mutations:
            with self.subTest(phase=phase, field=field):
                value = phase_approval(phase)
                target = value
                for part in field.split(".")[:-1]:
                    target = target[part]
                target[field.split(".")[-1]] = replacement
                self.write(value)
                with self.assertRaises(ProviderApprovalError):
                    self.load()

    def test_phase_packet_authorizes_only_current_action(self):
        for phase in PHASE_STATES:
            with self.subTest(phase=phase):
                value = phase_approval(phase)
                unexpected = next(
                    field
                    for field in (
                        "auth_platform_registration_count",
                        "consent_configuration_count",
                        "tester_add_count",
                        "web_client_create_count",
                        "android_client_create_count",
                    )
                    if field not in PHASE_ACTION_FIELDS[phase]
                )
                value["mutation_boundary"][unexpected] = 1
                self.write(value)
                with self.assertRaises(ProviderApprovalError):
                    self.load()
                value = phase_approval(phase)
                expected = next(iter(PHASE_ACTION_FIELDS[phase]))
                value["mutation_boundary"][expected] = 0
                self.write(value)
                with self.assertRaises(ProviderApprovalError):
                    self.load()

    def test_v2_remains_dry_loadable_but_cannot_be_reissued_to_cli(self):
        value = approval_for_now(NOW, approval())
        self.write(value)
        self.assertEqual(self.load(), value)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.execute()
        self.assertEqual(result, 2)
        self.assertEqual(stderr.getvalue(), "ERROR: PROVIDER_APPROVAL_INVALID\n")
        self.assertFalse(_consumed_sidecar_path(value, self.consumption_root).exists())

    def test_binding_changes_with_phase_and_observed_completed_state(self):
        web = phase_approval("web_client_create")
        android = phase_approval("android_client_create")
        changed_state = copy.deepcopy(web)
        changed_state["inventory"]["web_client_count"] = 1
        self.assertNotEqual(
            execution_binding_sha256(web), execution_binding_sha256(android)
        )
        self.assertNotEqual(
            execution_binding_sha256(web), execution_binding_sha256(changed_state)
        )

    def test_rejects_unknown_phase_and_client_action_sequence_drift(self):
        value = phase_approval("registration")
        value["phase"] = "full_bootstrap"
        self.write(value)
        with self.assertRaises(ProviderApprovalError):
            self.load()
        value = phase_approval("tester_add")
        value["planned_clients"][1]["action"] = "create"
        self.write(value)
        with self.assertRaises(ProviderApprovalError):
            self.load()


if __name__ == "__main__":
    unittest.main()
