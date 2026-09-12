"""Owner-only inventory and one assignment; no CLI or user/group creation.

StagingReadiness is a trusted-controller assertion of actual postchecks, not
evidence generated here. Group membership has no remote CAS: exclusive Owner
administration is required. Uncertain POSTs are observed only, never repeated.
The controller's durable before callback must reject duplicate attempts across
process restarts; this session alone is not persistent replay protection.
Inventory conservatively includes every app build platform when choosing the
next integer, so it cannot undercount an IOS build. Non-integer history stops.
The identical AscMaterial object must be shared with GET-only recovery.
"""

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

from tools import ios_testflight_inputs as inputs
from tools import ios_testflight_recovery as recovery
from tools import ios_testflight_upload as upload

GROUP = "NTUBTOB Owner Internal"
REQUEST_REASONS = frozenset(
    {
        "ASC_AUTHENTICATION_REJECTED",
        "ASC_PERMISSION_REJECTED",
        "ASC_REQUEST_REJECTED",
        "ASC_SERVICE_UNAVAILABLE",
        "ASC_CONNECTION_FAILED",
    }
)
INVENTORY_STAGES = frozenset(
    {
        "asc_input",
        "asc_apps",
        "asc_groups",
        "asc_group_auto_distribution",
        "asc_group_public_link",
        "asc_owner_group",
        "asc_testers",
        "asc_builds",
        "asc_build_uploads",
        "asc_complete",
    }
)
STATES = {
    "OWNER_GROUP_REQUIRED",
    "OWNER_SCOPE_REJECTED",
    "INVENTORY_READY",
    "ASSIGNMENT_UNCERTAIN",
    "OWNER_DISTRIBUTION_VERIFIED",
    "ALREADY_ASSIGNED",
} | REQUEST_REASONS


class Rejected(Exception):
    def __init__(self, reason="OWNER_SCOPE_REJECTED"):
        super().__init__(
            reason
            if type(reason) is str and reason in STATES
            else "OWNER_SCOPE_REJECTED"
        )


@dataclass(frozen=True, repr=False)
class Target:
    app_id: str
    owner_group_id: str
    owner_tester_id: str
    version: str
    previous_build: int
    planned_build: int

    def upload_target(self):
        return {
            "app_id": self.app_id,
            "owner_group_id": self.owner_group_id,
            "owner_tester_id": self.owner_tester_id,
        }


@dataclass(frozen=True, repr=False)
class StagingReadiness:
    project: str
    service: str
    source_sha: str
    schema_revision: str
    apple_configuration_verified: bool
    runtime_postcheck_verified: bool

    def validate(self):
        if (
            self.project != "ntubtob-mobile-staging"
            or self.service != "mobile-api-staging"
            or type(self.source_sha) is not str
            or not re.fullmatch(r"[0-9a-f]{40}", self.source_sha)
            or self.schema_revision not in {"0010", "0011", "0012"}
            or self.apple_configuration_verified is not True
            or self.runtime_postcheck_verified is not True
        ):
            raise Rejected()


def result(status):
    return {
        "classification": status if status in STATES else "OWNER_SCOPE_REJECTED",
        "release_authorized": False,
        "device_verified": False,
    }


class OwnerSession:
    def __init__(self, asc, *, owner_email, transport=upload.transport):
        if (
            type(asc) is not inputs.AscMaterial
            or type(owner_email) is not str
            or not re.fullmatch(r"[^\s@]{1,64}@[^\s@]{1,189}", owner_email)
            or not owner_email.isascii()
        ):
            raise Rejected()
        self.asc = asc
        self.email = owner_email
        self.transport = transport
        self.deadline = time.monotonic() + 2700
        self.requests = 0
        self.allowed = {"/v1/apps"}
        self.attempted = False
        self.uncertain = False
        self.assigned_build = None
        self.lock = threading.Lock()
        self.stage = "asc_input"

    def __repr__(self):
        return "<OwnerAssignmentSession>"

    def _request(self, method, path, body=None):
        parsed = urlsplit(path)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or parsed.path not in self.allowed
            or method not in {"GET", "POST"}
        ):
            raise Rejected()
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if len(pairs) != len(dict(pairs)) or any(
            k not in {"limit", "cursor", "filter[bundleId]"}
            or (k == "limit" and v != "200")
            or (
                k == "filter[bundleId]"
                and (parsed.path != "/v1/apps" or v != upload.BUNDLE)
            )
            or len(v) > 2048
            or any(ord(ch) < 32 for ch in v)
            for k, v in pairs
        ):
            raise Rejected()
        if method == "POST" and (
            path != self.assignment_path
            or body != {"data": [{"type": "builds", "id": self.assigned_build}]}
        ):
            raise Rejected()
        if self.requests >= 200 or time.monotonic() >= self.deadline:
            raise Rejected()
        self.requests += 1
        token = inputs.asc_jwt(self.asc, now=datetime.now(timezone.utc))
        try:
            response = self.transport(
                method,
                upload.API + path,
                {
                    "Authorization": "Bearer " + token.value,
                    "Content-Type": "application/json",
                },
                (
                    json.dumps(body, separators=(",", ":")).encode()
                    if body is not None
                    else None
                ),
                min(30, self.deadline - time.monotonic()),
            )
        except Exception:
            raise Rejected("ASC_CONNECTION_FAILED") from None
        if (
            type(response) is not upload.Response
            or type(response.body) is not bytes
            or len(response.body) > upload.MAX_RESPONSE
        ):
            raise Rejected()
        if response.status != (204 if method == "POST" else 200):
            raise Rejected(
                "ASC_AUTHENTICATION_REJECTED"
                if response.status == 401
                else (
                    "ASC_PERMISSION_REJECTED"
                    if response.status == 403
                    else (
                        "ASC_SERVICE_UNAVAILABLE"
                        if response.status == 429
                        or (
                            type(response.status) is int
                            and 500 <= response.status <= 599
                        )
                        else "ASC_REQUEST_REJECTED"
                    )
                )
            )
        return None if method == "POST" else upload.document(response.body)

    def _list(self, path):
        original = urlsplit(path).path
        if original not in self.allowed:
            raise Rejected()
        next_path = path + ("&" if "?" in path else "?") + "limit=200"
        values, seen = [], set()
        for _ in range(10):
            if next_path in seen:
                raise Rejected()
            seen.add(next_path)
            document = self._request("GET", next_path)
            page = document.get("data")
            if type(page) is not list or len(page) > 200:
                raise Rejected()
            values.extend(page)
            next_url = document.get("links", {}).get("next")
            if next_url is None:
                ids = [item.get("id") for item in values]
                if any(type(v) is not str for v in ids) or len(ids) != len(set(ids)):
                    raise Rejected()
                return values
            parsed = upload.parsed_url(next_url)
            if parsed.path != original:
                raise Rejected()
            next_path = parsed.path + ("?" + parsed.query if parsed.query else "")
        raise Rejected()

    def _scope(self, expected=None):
        self.stage = "asc_apps"
        apps = self._list("/v1/apps?filter[bundleId]=" + upload.BUNDLE)
        if len(apps) != 1:
            raise Rejected()
        app = upload.resource(apps[0], "apps")
        if app.get("attributes", {}).get("bundleId") != upload.BUNDLE:
            raise Rejected()
        app_id = app["id"]
        path = "/v1/apps/" + app_id + "/betaGroups"
        self.allowed.add(path)
        self.stage = "asc_groups"
        groups = [upload.resource(item, "betaGroups") for item in self._list(path)]
        for group in groups:
            attrs = group.get("attributes", {})
            self.stage = "asc_group_auto_distribution"
            if attrs.get("hasAccessToAllBuilds") is not False:
                raise Rejected()
            self.stage = "asc_group_public_link"
            if not upload.group_has_no_public_link(attrs):
                raise Rejected()
        self.stage = "asc_owner_group"
        owners = [g for g in groups if g.get("attributes", {}).get("name") == GROUP]
        if not owners:
            raise Rejected("OWNER_GROUP_REQUIRED")
        if (
            len(owners) != 1
            or owners[0]["attributes"].get("isInternalGroup") is not True
        ):
            raise Rejected()
        group_id = owners[0]["id"]
        path = "/v1/betaGroups/" + group_id + "/betaTesters"
        self.allowed.add(path)
        self.stage = "asc_testers"
        testers = self._list(path)
        if not testers:
            raise Rejected("OWNER_GROUP_REQUIRED")
        if len(testers) != 1:
            raise Rejected()
        tester = upload.resource(testers[0], "betaTesters")
        if tester.get("attributes", {}).get("email") != self.email:
            raise Rejected("OWNER_GROUP_REQUIRED")
        identities = (app_id, group_id, tester["id"])
        if expected is not None and identities != (
            expected.app_id,
            expected.owner_group_id,
            expected.owner_tester_id,
        ):
            raise Rejected()
        return identities, groups

    def inventory(self, *, version="1.0.0"):
        try:
            if type(version) is not str or not re.fullmatch(
                r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}", version
            ):
                raise Rejected()
            (app, group, tester), _ = self._scope()
            previous = 0
            for kind, field in (
                ("builds", "version"),
                ("buildUploads", "cfBundleVersion"),
            ):
                path = "/v1/apps/" + app + "/" + kind
                self.allowed.add(path)
                self.stage = "asc_builds" if kind == "builds" else "asc_build_uploads"
                for item in self._list(path):
                    value = upload.resource(item, kind).get("attributes", {}).get(field)
                    if type(value) is not str or not re.fullmatch(
                        r"[1-9][0-9]{0,9}", value
                    ):
                        raise Rejected()
                    previous = max(previous, int(value))
            if previous >= 2147483647:
                raise Rejected()
            self.stage = "asc_complete"
            return Target(app, group, tester, version, previous, previous + 1)
        except Rejected:
            raise
        except Exception:
            raise Rejected() from None

    def _distribution(self, target, build_id):
        _, groups = self._scope(target)
        path = "/v1/builds/" + build_id + "/relationships/individualTesters"
        self.allowed.add(path)
        if self._list(path):
            raise Rejected()
        assigned = False
        for group in groups:
            path = "/v1/betaGroups/" + group["id"] + "/relationships/builds"
            self.allowed.add(path)
            ids = [upload.resource(v, "builds")["id"] for v in self._list(path)]
            if build_id in ids:
                if group["id"] != target.owner_group_id:
                    raise Rejected()
                assigned = True
        return assigned

    def assign(self, recovered, *, target, staging_ready, before, after):
        if not self.lock.acquire(blocking=False):
            return result("ASSIGNMENT_UNCERTAIN")
        try:
            if (
                type(recovered) is not recovery.ReadOnlyUpload
                or type(target) is not Target
                or type(staging_ready) is not StagingReadiness
            ):
                raise Rejected()
            staging_ready.validate()
            if (
                not callable(before)
                or not callable(after)
                or recovered.asc is not self.asc
            ):
                raise Rejected()
            if (
                recovered.app,
                recovered.group,
                recovered.tester,
                recovered.version,
                recovered.build,
            ) != (
                target.app_id,
                target.owner_group_id,
                target.owner_tester_id,
                target.version,
                str(target.planned_build),
            ):
                raise Rejected()
            # Re-establish the recovered fingerprint immediately before distribution.
            # ASC metadata comparison is not an independent Apple byte-hash proof.
            files = recovered._list(
                "/v1/buildUploads/"
                + upload.identifier(recovered.receipt.upload_id)
                + "/buildUploadFiles"
            )
            if len(files) != 1:
                raise Rejected()
            file = upload.resource(
                files[0], "buildUploadFiles", recovered.receipt.file_id
            )
            attrs = file.get("attributes", {})
            if (
                attrs.get("fileName") != "candidate.ipa"
                or attrs.get("assetType") != "ASSET"
                or attrs.get("uti") != "com.apple.ipa"
                or type(attrs.get("fileSize")) is not int
                or attrs["fileSize"] != recovered.size
                or attrs.get("sourceFileChecksums")
                != {"file": {"algorithm": "SHA_256", "hash": recovered.sha}}
            ):
                raise Rejected()
            recovered._file_membership(file)
            status = recovered.reconcile()
            if status.classification != "BUILD_VALID_UNDISTRIBUTED":
                raise Rejected()
            build_id = upload.identifier(recovered.receipt.build_id)
            if self.assigned_build is not None and self.assigned_build != build_id:
                raise Rejected()
            if self._distribution(target, build_id):
                return result("ALREADY_ASSIGNED")
            if self.attempted:
                return result("ASSIGNMENT_UNCERTAIN")
            self.assigned_build = build_id
            self.assignment_path = (
                "/v1/betaGroups/" + target.owner_group_id + "/relationships/builds"
            )
            self.allowed.add(self.assignment_path)
            self.attempted = True
            before("OWNER_DISTRIBUTION_ATTEMPT")
            self._request(
                "POST",
                self.assignment_path,
                {"data": [{"type": "builds", "id": build_id}]},
            )
            if not self._distribution(target, build_id):
                raise Rejected()
            after("OWNER_DISTRIBUTION_CONFIRMED")
            return result("OWNER_DISTRIBUTION_VERIFIED")
        except Exception:
            self.uncertain = self.attempted
            return result(
                "ASSIGNMENT_UNCERTAIN" if self.attempted else "OWNER_SCOPE_REJECTED"
            )
        finally:
            self.lock.release()
