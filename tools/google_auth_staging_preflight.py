"""Offline verifier for a private Google Auth staging bootstrap approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Collection
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence
from uuid import UUID

from tools.mobile_staging_broker_rollout import (
    BrokerRolloutError,
    _assert_path_chain_no_reparse,
    _same_file_identity,
)


STAGING_PROJECT = "ntubtob-mobile-staging"
PRODUCTION_PROJECT = "ntubtob-schedule-405614"
ANDROID_PACKAGE = "tw.org.ntubtob.portal"
APPLICATION_NAME = "NTUBTOB Mobile Staging"
WEB_ALIAS = "google-auth-staging-web"
ANDROID_ALIAS = "google-auth-staging-android"
WEB_DISPLAY_NAME = "NTUBTOB Mobile Staging Web Server"
ANDROID_DISPLAY_NAME = "NTUBTOB Mobile Staging Android"
BASIC_SCOPES = ["openid", "email", "profile"]
TASK_ID = "TASK-157"
DECISION_ID = "DEC-100"
OWNER_GATE_ID = "TASK-157-OWNER-GATE-GOOGLE-AUTH-SEPARATION-20260826"
MAIN_CLAIM_ID = "main-work-20260825"
MAIN_LEASE_VERSION = 17
PHASE_STATES = {
    "registration": ("unconfigured", "unconfigured", 0, 0, 0),
    "web_client_create": ("registered", "exact", 0, 0, 0),
    "android_client_create": ("registered", "exact", 0, 1, 0),
    "tester_add": ("registered", "exact", 0, 1, 1),
}
PHASE_CLIENT_ACTIONS = {
    "registration": {"web": "not-authorized", "android": "not-authorized"},
    "web_client_create": {"web": "create", "android": "not-authorized"},
    "android_client_create": {"web": "completed", "android": "create"},
    "tester_add": {"web": "completed", "android": "completed"},
}
PHASE_ACTION_FIELDS = {
    "registration": {
        "auth_platform_registration_count",
        "consent_configuration_count",
    },
    "web_client_create": {"web_client_create_count"},
    "android_client_create": {"android_client_create_count"},
    "tester_add": {"tester_add_count"},
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONSUMPTION_ROOT = (
    REPOSITORY_ROOT.parent
    / ".ntubtob-private"
    / REPOSITORY_ROOT.name
    / "task-157"
    / "google-auth-consumed"
)
MAX_APPROVAL_BYTES = 64 * 1024
MAX_VALIDITY = timedelta(minutes=30)
UTC_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
SHA1_FINGERPRINT = re.compile(r"^(?:[0-9A-F]{2}:){19}[0-9A-F]{2}$")
EXECUTION_NONCE = re.compile(r"^[0-9a-f]{64}$")
ACCOUNT = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9]"
    r"(?:[A-Za-z0-9.-]{0,187}[A-Za-z0-9])?$"
)


class ProviderApprovalError(RuntimeError):
    """A safe failure that never includes private approval values."""


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ProviderApprovalError("CLI arguments are invalid")


def _fail(reason: str) -> None:
    raise ProviderApprovalError(reason)


def _exact_object(value: object, fields: set[str], reason: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(reason)
    return value


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            _fail("Approval JSON contains duplicate fields")
        value[key] = item
    return value


def _contains_production_project(value: object) -> bool:
    if isinstance(value, str):
        return PRODUCTION_PROJECT in value
    if isinstance(value, list):
        return any(_contains_production_project(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_production_project(item) for item in value.values())
    return False


def _same_opened_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_file_identity(left, right) and left.st_mtime_ns == right.st_mtime_ns


def _require_private_path(path: Path) -> Path:
    try:
        absolute = path.absolute()
        _assert_path_chain_no_reparse(absolute)
        resolved = absolute.resolve(strict=True)
        if resolved == REPOSITORY_ROOT or resolved.is_relative_to(REPOSITORY_ROOT):
            _fail("Approval artifact must remain outside the repository")
        _assert_path_chain_no_reparse(resolved)
        return resolved
    except ProviderApprovalError:
        raise
    except (BrokerRolloutError, OSError, RuntimeError):
        _fail("Approval path is invalid")


def _read_opened_json(path: Path) -> dict:
    try:
        _assert_path_chain_no_reparse(path)
        with path.open("rb") as handle:
            opened_before = os.fstat(handle.fileno())
            named_before = os.stat(path, follow_symlinks=False)
            if (
                opened_before.st_nlink != 1
                or not stat.S_ISREG(opened_before.st_mode)
                or getattr(opened_before, "st_file_attributes", 0) & 0x400
                or not _same_opened_identity(opened_before, named_before)
            ):
                _fail("Approval artifact identity is invalid")
            raw = handle.read(MAX_APPROVAL_BYTES + 1)
            opened_after = os.fstat(handle.fileno())
            named_after = os.stat(path, follow_symlinks=False)
            _assert_path_chain_no_reparse(path)
            if not _same_opened_identity(
                opened_before, opened_after
            ) or not _same_opened_identity(opened_before, named_after):
                _fail("Approval artifact changed while reading")
    except ProviderApprovalError:
        raise
    except (BrokerRolloutError, OSError):
        _fail("Approval artifact is unavailable")
    if not raw or len(raw) > MAX_APPROVAL_BYTES or b"\x00" in raw:
        _fail("Approval artifact size or encoding is invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object)
    except ProviderApprovalError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("Approval artifact is malformed")
    if not isinstance(value, dict):
        _fail("Approval root must be an object")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not UTC_TIMESTAMP.fullmatch(value):
        _fail("Approval timestamp is not exact UTC")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail("Approval timestamp is invalid")


def _validate_authority(value: object, approval_id: object) -> None:
    authority = _exact_object(
        value,
        {
            "task_id",
            "decision_id",
            "owner_gate_id",
            "main_claim_id",
            "main_lease_version",
        },
        "Authority binding fields are not exact",
    )
    if authority != {
        "task_id": TASK_ID,
        "decision_id": DECISION_ID,
        "owner_gate_id": OWNER_GATE_ID,
        "main_claim_id": MAIN_CLAIM_ID,
        "main_lease_version": MAIN_LEASE_VERSION,
    }:
        _fail("Authority binding is not exact")
    try:
        parsed = UUID(approval_id) if isinstance(approval_id, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.version != 4 or str(parsed) != approval_id:
        _fail("Approval ID must be a canonical UUIDv4")


def _validate_validity(value: object, observed_at: datetime, now: datetime) -> None:
    validity = _exact_object(
        value,
        {"not_before", "expires_at"},
        "Approval validity fields are not exact",
    )
    not_before = _parse_utc(validity["not_before"])
    expires_at = _parse_utc(validity["expires_at"])
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        _fail("Verifier time must be UTC")
    if not (
        observed_at <= not_before <= now < expires_at
        and expires_at - observed_at <= MAX_VALIDITY
    ):
        _fail("Approval is not active and fresh")


def _validate_execution_binding(value: object) -> None:
    binding = _exact_object(
        value,
        {"nonce", "one_shot", "consume_via"},
        "Execution binding fields are not exact",
    )
    if (
        not isinstance(binding["nonce"], str)
        or not EXECUTION_NONCE.fullmatch(binding["nonce"])
        or binding["one_shot"] is not True
        or binding["consume_via"] != "private-sidecar"
    ):
        _fail("Execution binding is invalid")


def _validate_consent_screen(value: object) -> None:
    screen = _exact_object(
        value,
        {
            "application_name",
            "user_type",
            "publishing_status",
            "scopes",
            "tester_classification",
            "tester_accounts",
        },
        "Consent-screen approval fields are not exact",
    )
    if (
        screen["application_name"] != APPLICATION_NAME
        or screen["user_type"] != "external"
        or screen["publishing_status"] != "testing"
        or screen["scopes"] != BASIC_SCOPES
        or screen["tester_classification"] != "fictional"
    ):
        _fail("Consent-screen boundary is not exact")
    testers = screen["tester_accounts"]
    if (
        not isinstance(testers, list)
        or len(testers) != 1
        or not isinstance(testers[0], str)
        or len(testers[0]) > 254
        or not ACCOUNT.fullmatch(testers[0])
        or "." not in testers[0].rsplit("@", 1)[1]
    ):
        _fail("Exactly one valid fictional tester account is required")


def _validate_matching_keys(value: object) -> str:
    keys = _exact_object(
        value, {"web", "android"}, "Inventory matching keys are not exact"
    )
    web = _exact_object(
        keys["web"], {"alias", "display_name"}, "Web matching keys are not exact"
    )
    android = _exact_object(
        keys["android"],
        {"alias", "display_name", "package_name", "sha1_fingerprint"},
        "Android matching keys are not exact",
    )
    if web != {"alias": WEB_ALIAS, "display_name": WEB_DISPLAY_NAME}:
        _fail("Web matching keys drifted")
    if (
        android.get("alias") != ANDROID_ALIAS
        or android.get("display_name") != ANDROID_DISPLAY_NAME
        or android.get("package_name") != ANDROID_PACKAGE
        or not isinstance(android.get("sha1_fingerprint"), str)
        or not SHA1_FINGERPRINT.fullmatch(android["sha1_fingerprint"])
    ):
        _fail("Android matching keys drifted")
    return android["sha1_fingerprint"]


def _validate_inventory(value: object) -> tuple[datetime, str]:
    inventory = _exact_object(
        value,
        {
            "status",
            "project",
            "observed_at",
            "matching_client_count",
            "duplicate_client_count",
            "cross_project_client_count",
            "matching_keys",
        },
        "Provider inventory fields are not exact",
    )
    if inventory["status"] != "complete" or inventory["project"] != STAGING_PROJECT:
        _fail("Provider inventory target is not exact")
    for field in (
        "matching_client_count",
        "duplicate_client_count",
        "cross_project_client_count",
    ):
        if type(inventory[field]) is not int or inventory[field] != 0:
            _fail("Provider inventory is not a create-only empty baseline")
    fingerprint = _validate_matching_keys(inventory["matching_keys"])
    return _parse_utc(inventory["observed_at"]), fingerprint


def _validate_phase_inventory(value: object, phase: str) -> tuple[datetime, str]:
    inventory = _exact_object(
        value,
        {
            "status",
            "project",
            "observed_at",
            "auth_platform_status",
            "consent_status",
            "tester_count",
            "web_client_count",
            "android_client_count",
            "duplicate_client_count",
            "cross_project_client_count",
            "matching_keys",
        },
        "Phase inventory fields are not exact",
    )
    if inventory["status"] != "complete" or inventory["project"] != STAGING_PROJECT:
        _fail("Phase inventory target is not exact")
    expected = PHASE_STATES.get(phase)
    actual = (
        inventory["auth_platform_status"],
        inventory["consent_status"],
        inventory["tester_count"],
        inventory["web_client_count"],
        inventory["android_client_count"],
    )
    if expected is None or actual != expected:
        _fail("Phase inventory precondition is not exact")
    for field in (
        "tester_count",
        "web_client_count",
        "android_client_count",
        "duplicate_client_count",
        "cross_project_client_count",
    ):
        if type(inventory[field]) is not int:
            _fail("Phase inventory counts are invalid")
    if (
        inventory["duplicate_client_count"] != 0
        or inventory["cross_project_client_count"] != 0
    ):
        _fail("Phase inventory contains duplicate or cross-project clients")
    fingerprint = _validate_matching_keys(inventory["matching_keys"])
    return _parse_utc(inventory["observed_at"]), fingerprint


def _validate_clients(
    value: object,
    fingerprint: str,
    expected_actions: dict[str, str] | None = None,
) -> None:
    if not isinstance(value, list) or len(value) != 2:
        _fail("Exactly two planned clients are required")
    by_type: dict[str, dict] = {}
    for item in value:
        if not isinstance(item, dict):
            _fail("Planned client entry is malformed")
        client_type = item.get("client_type")
        if client_type in by_type or client_type not in {"web", "android"}:
            _fail("Planned client types are not exact")
        by_type[client_type] = item

    common = {
        "client_type",
        "alias",
        "display_name",
        "action",
        "owning_project",
        "dedicated",
    }
    web = _exact_object(
        by_type["web"],
        common | {"javascript_origins", "redirect_uris"},
        "Web client approval fields are not exact",
    )
    android = _exact_object(
        by_type["android"],
        common | {"package_name", "sha1_fingerprint"},
        "Android client approval fields are not exact",
    )
    for client in (web, android):
        if (
            client["owning_project"] != STAGING_PROJECT
            or client["dedicated"] is not True
        ):
            _fail("Planned clients are not new, dedicated staging resources")
    actions = expected_actions or {"web": "create", "android": "create"}
    if web["action"] != actions["web"] or android["action"] != actions["android"]:
        _fail("Client action sequence is not exact")
    if (
        web["alias"] != WEB_ALIAS
        or web["display_name"] != WEB_DISPLAY_NAME
        or web["javascript_origins"] != []
        or web["redirect_uris"] != []
    ):
        _fail("Native Web client boundary is not exact")
    if (
        android["alias"] != ANDROID_ALIAS
        or android["display_name"] != ANDROID_DISPLAY_NAME
        or android["package_name"] != ANDROID_PACKAGE
        or android["sha1_fingerprint"] != fingerprint
    ):
        _fail("Android client boundary is not exact")


def _validate_mutation_boundary(
    value: object, expected_one_fields: set[str] | None = None
) -> None:
    one_fields = {
        "auth_platform_registration_count",
        "consent_configuration_count",
        "tester_add_count",
        "web_client_create_count",
        "android_client_create_count",
    }
    zero_fields = {
        "secret_mutation_count",
        "iam_mutation_count",
        "public_access_mutation_count",
        "billing_mutation_count",
        "runtime_mutation_count",
        "traffic_mutation_count",
    }
    boundary = _exact_object(
        value,
        one_fields | zero_fields | {"rollback"},
        "Mutation boundary fields are not exact",
    )
    expected = one_fields if expected_one_fields is None else expected_one_fields
    if any(
        type(boundary[field]) is not int or boundary[field] != int(field in expected)
        for field in one_fields
    ):
        _fail("Provider bootstrap action counts are not exact")
    if any(
        type(boundary[field]) is not int or boundary[field] != 0
        for field in zero_fields
    ):
        _fail("Non-provider mutation is forbidden")
    if boundary["rollback"] != "retain-provider-resources-and-evidence":
        _fail("Rollback must retain provider resources and evidence")


def execution_binding_sha256(approval: dict) -> str:
    approval_id = approval["approval_id"]
    nonce = approval["execution_binding"]["nonce"]
    if approval.get("schema_version") == 3:
        payload = json.dumps(
            {
                "approval_id": approval_id,
                "nonce": nonce,
                "phase": approval.get("phase"),
                "inventory": approval.get("inventory"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        payload = f"{approval_id}:{nonce}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_provider_approval(
    path: Path,
    *,
    now: datetime | None = None,
    consumed_execution_bindings: Collection[str] = (),
) -> dict:
    """Load and validate one exact private provider-bootstrap approval."""

    raw = _read_opened_json(_require_private_path(path))
    common_fields = {
        "schema_version",
        "approval_id",
        "authority",
        "owner_approved",
        "project",
        "validity",
        "execution_binding",
        "consent_screen",
        "inventory",
        "planned_clients",
        "mutation_boundary",
    }
    schema_version = raw.get("schema_version")
    if type(schema_version) is not int or schema_version not in {2, 3}:
        _fail("Provider approval schema is not supported")
    approval = _exact_object(
        raw,
        common_fields | ({"phase"} if schema_version == 3 else set()),
        "Provider approval fields are not exact",
    )
    if _contains_production_project(approval):
        _fail("Production project reference is forbidden")
    if approval["owner_approved"] is not True or approval["project"] != STAGING_PROJECT:
        _fail("Provider approval target is not exact")
    _validate_authority(approval["authority"], approval["approval_id"])
    _validate_execution_binding(approval["execution_binding"])
    if schema_version == 2:
        observed_at, fingerprint = _validate_inventory(approval["inventory"])
    else:
        phase = approval["phase"]
        if phase not in PHASE_STATES:
            _fail("Provider approval phase is invalid")
        observed_at, fingerprint = _validate_phase_inventory(
            approval["inventory"], phase
        )
    _validate_validity(
        approval["validity"], observed_at, now or datetime.now(timezone.utc)
    )
    _validate_consent_screen(approval["consent_screen"])
    if schema_version == 2:
        _validate_clients(approval["planned_clients"], fingerprint)
        _validate_mutation_boundary(approval["mutation_boundary"])
    else:
        _validate_clients(
            approval["planned_clients"], fingerprint, PHASE_CLIENT_ACTIONS[phase]
        )
        _validate_mutation_boundary(
            approval["mutation_boundary"], PHASE_ACTION_FIELDS[phase]
        )
    if execution_binding_sha256(approval) in consumed_execution_bindings:
        _fail("Execution binding was already consumed")
    return approval


def canonical_approval_sha256(approval: dict) -> str:
    rendered = json.dumps(
        approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _consumed_sidecar_path(
    approval: dict, consumption_root: Path = DEFAULT_CONSUMPTION_ROOT
) -> Path:
    return consumption_root / (
        execution_binding_sha256(approval) + ".google-auth.consumed.json"
    )


def _prepare_consumption_root(consumption_root: Path) -> Path:
    try:
        absolute = consumption_root.absolute()
        if absolute == REPOSITORY_ROOT or absolute.is_relative_to(REPOSITORY_ROOT):
            _fail("Consumption namespace must remain outside the repository")

        missing: list[Path] = []
        existing = absolute
        while not existing.exists() and not existing.is_symlink():
            missing.append(existing)
            parent = existing.parent
            if parent == existing:
                _fail("Consumption namespace has no private ancestor")
            existing = parent

        current = _require_private_path(existing)
        if not current.is_dir():
            _fail("Consumption namespace ancestor is invalid")
        for path in reversed(missing):
            if path.parent.resolve(strict=True) != current:
                _fail("Consumption namespace path drifted")
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
            current = _require_private_path(path)
            if not current.is_dir():
                _fail("Consumption namespace is invalid")
        resolved = _require_private_path(absolute)
        if not resolved.is_dir():
            _fail("Consumption namespace is invalid")
        return resolved
    except ProviderApprovalError:
        raise
    except (BrokerRolloutError, OSError, RuntimeError):
        _fail("Consumption namespace is invalid")


def _write_sidecar_bytes(handle, payload: bytes) -> None:
    handle.write(payload)


def _consume_cli_approval(
    approval_path: Path,
    approval: dict,
    consumed_at: datetime,
    *,
    consumption_root: Path = DEFAULT_CONSUMPTION_ROOT,
) -> Path:
    if approval.get("schema_version") != 3 or approval.get("phase") not in PHASE_STATES:
        _fail("Only progressive phase approvals may be consumed")
    resolved_approval = _require_private_path(approval_path)
    resolved_parent = _require_private_path(resolved_approval.parent)
    if not resolved_parent.is_dir() or resolved_approval.parent != resolved_parent:
        _fail("Consumed sidecar parent is invalid")
    _assert_path_chain_no_reparse(resolved_approval)
    current = _read_opened_json(resolved_approval)
    approval_sha256 = canonical_approval_sha256(approval)
    if canonical_approval_sha256(current) != approval_sha256:
        _fail("Approval artifact changed before consumption")
    if consumed_at.tzinfo is None or consumed_at.utcoffset() != timedelta(0):
        _fail("Consumption time must be UTC")

    resolved_consumption_root = _prepare_consumption_root(consumption_root)
    sidecar = _consumed_sidecar_path(approval, resolved_consumption_root)
    _assert_path_chain_no_reparse(sidecar)
    value = {
        "schema_version": 1,
        "binding_sha256": execution_binding_sha256(approval),
        "approval_sha256": approval_sha256,
        "consumed_at": consumed_at.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for optional_flag in ("O_BINARY", "O_NOINHERIT", "O_NOFOLLOW"):
        flags |= getattr(os, optional_flag, 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(sidecar, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            opened = os.fstat(handle.fileno())
            if (
                opened.st_nlink != 1
                or opened.st_size != 0
                or not stat.S_ISREG(opened.st_mode)
                or getattr(opened, "st_file_attributes", 0) & 0x400
            ):
                _fail("Consumed sidecar identity is invalid")
            _write_sidecar_bytes(handle, payload)
            handle.flush()
            os.fsync(handle.fileno())
            written = os.fstat(handle.fileno())
            named = os.stat(sidecar, follow_symlinks=False)
            _assert_path_chain_no_reparse(sidecar)
            if (
                written.st_nlink != 1
                or written.st_size != len(payload)
                or not stat.S_ISREG(written.st_mode)
                or getattr(written, "st_file_attributes", 0) & 0x400
                or not _same_opened_identity(written, named)
            ):
                _fail("Consumed sidecar postcheck failed")
        if _require_private_path(sidecar) != sidecar:
            _fail("Consumed sidecar path drifted")
    except ProviderApprovalError:
        raise
    except (BrokerRolloutError, OSError):
        _fail("Approval packet could not be consumed")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return sidecar


def main(
    argv: Sequence[str] | None = None,
    *,
    now: datetime | None = None,
    consumed_execution_bindings: Collection[str] = (),
    consumption_root: Path = DEFAULT_CONSUMPTION_ROOT,
) -> int:
    parser = _PrivateArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("approval", type=Path)
    try:
        args = parser.parse_args(argv)
        effective_now = now or datetime.now(timezone.utc)
        approval = load_provider_approval(
            args.approval,
            now=effective_now,
            consumed_execution_bindings=consumed_execution_bindings,
        )
        if approval["schema_version"] != 3:
            _fail("Legacy full bootstrap approval is dry-validation only")
        _consume_cli_approval(
            args.approval,
            approval,
            effective_now,
            consumption_root=consumption_root,
        )
        print(
            json.dumps(
                {
                    "approval_sha256": canonical_approval_sha256(approval),
                    "classification": "PASS",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except ProviderApprovalError:
        print("ERROR: PROVIDER_APPROVAL_INVALID", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
