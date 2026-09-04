"""Validate the repository-only iOS TestFlight preparation manifest.

This module does not access App Store Connect, Apple accounts, signing material,
or an application artifact.  Its output is deliberately deidentified and can
only classify the current document as preparation, never as release approval.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

MAX_MANIFEST_BYTES = 65_536
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "releases" / "ios-testflight-preparation.json"

TOP_LEVEL_KEYS = {
    "schema",
    "channel",
    "locale",
    "candidate",
    "draft",
    "privacy_facts",
    "gates",
}
CANDIDATE_KEYS = {
    "app_flavor",
    "client_mode",
    "release_scope",
    "minimum_ios",
    "production_data",
    "push_delivery",
    "deep_link_delivery",
    "crash_upload",
}
DRAFT_KEYS = {"app_name", "subtitle", "beta_description", "what_to_test"}
PRIVACY_KEYS = {
    "category",
    "collected",
    "linked_to_user",
    "tracking",
    "purpose",
}
REQUIRED_PRIVACY_CATEGORIES = {
    "provider_account_identifier",
    "person_display_name",
    "attendance_and_team_activity",
    "installation_identifier",
    "crash_diagnostics",
    "notification_device_token",
}
REQUIRED_GATES = {
    "owner_branding_confirmation",
    "feedback_contact",
    "public_support_url",
    "public_privacy_policy_url",
    "in_app_account_deletion",
    "apple_app_id",
    "sign_in_with_apple_capability",
    "apple_provider_runtime",
    "distribution_certificate",
    "distribution_profile",
    "app_store_connect_record",
    "macos_xcode_builder",
    "beta_review_contact_and_access",
    "store_screenshot_set",
    "content_rights_confirmation",
    "distribution_regions_and_dsa",
    "age_rating_console_answers",
    "export_compliance_determination",
    "third_party_sdk_privacy_review",
    "privacy_manifest_archive_inspection",
    "signed_ipa",
    "real_device_testflight",
}
GATE_STATES = {"required", "blocked"}
PURPOSES = {"app_functionality", "authentication_and_security", "not_applicable"}
SENSITIVE_TEXT = re.compile(
    r"(?:https?://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\.apps\.googleusercontent\.com|"
    r"(?:team[_ -]?id|client[_ -]?id|secret|token|password|private[_ -]?key)\s*[:=])",
    re.IGNORECASE,
)


class ReadinessError(ValueError):
    """The preparation manifest is incomplete, unsafe, or internally mixed."""


def _unique_object(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReadinessError("preparation manifest contains duplicate keys")
        result[key] = value
    return result


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ReadinessError("preparation manifest is unavailable")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_MANIFEST_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise ReadinessError("preparation manifest encoding or size is invalid")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReadinessError("preparation manifest is not valid UTF-8 JSON") from None
    if not isinstance(manifest, dict):
        raise ReadinessError("preparation manifest root is invalid")
    return manifest


def _exact_mapping(value: object, keys: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReadinessError(f"{label} fields are incomplete or unknown")
    return value


def validate_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    _exact_mapping(manifest, TOP_LEVEL_KEYS, "top-level")
    if manifest["schema"] != 1:
        raise ReadinessError("preparation manifest schema is unsupported")
    if manifest["channel"] != "ios-testflight" or manifest["locale"] != "zh-Hant":
        raise ReadinessError("preparation manifest channel or locale is invalid")

    candidate = _exact_mapping(manifest["candidate"], CANDIDATE_KEYS, "candidate")
    expected_candidate = {
        "app_flavor": "staging",
        "client_mode": "real",
        "release_scope": "basic",
        "minimum_ios": "15.0",
        "production_data": False,
        "push_delivery": False,
        "deep_link_delivery": False,
        "crash_upload": False,
    }
    if candidate != expected_candidate:
        raise ReadinessError("candidate scope is not the approved TestFlight vector")

    draft = _exact_mapping(manifest["draft"], DRAFT_KEYS, "draft")
    for key, value in draft.items():
        if not isinstance(value, str) or not value or value != value.strip():
            raise ReadinessError("draft text is incomplete")
        if SENSITIVE_TEXT.search(value):
            raise ReadinessError("draft text contains a prohibited identifier category")
    if not 2 <= len(draft["app_name"]) <= 30:
        raise ReadinessError("draft app name length is invalid")
    if len(draft["subtitle"]) > 30:
        raise ReadinessError("draft subtitle length is invalid")
    if len(draft["beta_description"]) > 4000 or len(draft["what_to_test"]) > 4000:
        raise ReadinessError("draft TestFlight text length is invalid")

    privacy = manifest["privacy_facts"]
    if not isinstance(privacy, list) or len(privacy) != len(
        REQUIRED_PRIVACY_CATEGORIES
    ):
        raise ReadinessError("privacy fact inventory is incomplete")
    categories: list[str] = []
    for item in privacy:
        fact = _exact_mapping(item, PRIVACY_KEYS, "privacy fact")
        category = fact["category"]
        if not isinstance(category, str):
            raise ReadinessError("privacy fact category is invalid")
        categories.append(category)
        if (
            type(fact["collected"]) is not bool
            or type(fact["linked_to_user"]) is not bool
            or type(fact["tracking"]) is not bool
            or not isinstance(fact["purpose"], str)
            or fact["purpose"] not in PURPOSES
        ):
            raise ReadinessError("privacy fact values are invalid")
        if fact["tracking"] is not False:
            raise ReadinessError("the approved candidate does not permit tracking")
        if not fact["collected"] and (
            fact["linked_to_user"] or fact["purpose"] != "not_applicable"
        ):
            raise ReadinessError("non-collected privacy facts are inconsistent")
        if fact["collected"] and fact["purpose"] == "not_applicable":
            raise ReadinessError("collected privacy facts require a purpose")
    if set(categories) != REQUIRED_PRIVACY_CATEGORIES or len(set(categories)) != len(
        categories
    ):
        raise ReadinessError("privacy fact categories are incomplete or duplicated")

    gates = _exact_mapping(manifest["gates"], REQUIRED_GATES, "gate")
    if any(
        not isinstance(state, str) or state not in GATE_STATES
        for state in gates.values()
    ):
        raise ReadinessError("gate state is invalid")
    if not any(state == "blocked" for state in gates.values()):
        raise ReadinessError("preparation manifest cannot claim release readiness")
    counts = Counter(gates.values())
    return {
        "schema": 1,
        "classification": "PREPARATION_ONLY",
        "channel": "ios-testflight",
        "candidate_scope": "staging-real-basic",
        "privacy_fact_count": len(privacy),
        "required_gate_count": counts["required"],
        "blocked_gate_count": counts["blocked"],
        "external_mutation_performed": False,
        "release_ready": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the repository-only iOS TestFlight preparation manifest."
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST, help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    try:
        result = validate_manifest(load_manifest(args.manifest))
    except (OSError, ReadinessError):
        print("ERROR: iOS store preparation manifest is invalid")
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
