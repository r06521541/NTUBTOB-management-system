"""Exact-run public fingerprint and GET-only ASC rediscovery.

No private receipt export or upload retry. A missing log/fingerprint is a hard
availability limit, never evidence of zero mutation. ASC checksum metadata match
does not claim independent byte hashing by Apple.
"""

import json
import re

from tools import ios_testflight_upload as upload
from tools import ios_testflight_wire as wire

PREFIX = "IOS_TF_FINGERPRINT "
RESULT_PREFIX = "IOS_TF_RESULT "


class Rejected(Exception):
    def __init__(self):
        super().__init__("RECOVERY_UNRESOLVED")


def fingerprint(value, *, binding, version, build):
    if (
        type(binding) is not wire.Binding
        or type(version) is not str
        or not re.fullmatch(r"[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}", version)
        or type(build) is not int
        or not 1 <= build <= 2147483647
        or type(value) is not dict
        or set(value)
        != {"schema", "sha", "nonce", "run_id", "version", "build", "sha256", "size"}
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or value["sha"] != binding.sha
        or value["nonce"] != binding.nonce
        or value["run_id"] != binding.run_id
        or value["version"] != version
        or type(value["build"]) is not int
        or value["build"] != build
        or type(value["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
        or type(value["size"]) is not int
        or not 0 < value["size"] <= upload.MAX_BYTES
    ):
        raise Rejected()
    return dict(value)


def from_logs(raw, *, binding, version, build):
    if type(raw) is not bytes or not 0 < len(raw) <= upload.MAX_RESPONSE:
        raise Rejected()
    found = []
    for line in raw.decode("utf-8", errors="strict").splitlines():
        # Exact job log timestamps are transport, never a caller-selected prefix.
        line = re.sub(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ", "", line)
        if line.startswith(PREFIX):
            if len(line) > 2048:
                raise Rejected()
            try:
                found.append(
                    fingerprint(
                        json.loads(line[len(PREFIX) :], object_pairs_hook=wire._unique),
                        binding=binding,
                        version=version,
                        build=build,
                    )
                )
            except Exception:
                raise Rejected() from None
    if len(found) != 1:
        raise Rejected()
    return found[0]


def result_from_logs(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= upload.MAX_RESPONSE:
        raise Rejected()
    records = []
    keys = {
        "classification",
        "cleanup_verified",
        "release_authorized",
        "device_verified",
        "owner_distribution_verified",
    }
    for line in raw.decode("utf-8", errors="strict").splitlines():
        line = re.sub(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ", "", line)
        if line.startswith(RESULT_PREFIX):
            if len(line) > 2048:
                raise Rejected()
            value = json.loads(
                line[len(RESULT_PREFIX) :], object_pairs_hook=wire._unique
            )
            if (
                type(value) is not dict
                or set(value) != keys
                or type(value["cleanup_verified"]) is not bool
                or any(
                    value[k] is not False
                    for k in keys - {"classification", "cleanup_verified"}
                )
            ):
                raise Rejected()
            records.append(value)
    if (
        len(records) != 3
        or records[0]["classification"] != "PREPARED"
        or records[1]["classification"] not in upload.CLASSIFICATIONS
        or records[1]["cleanup_verified"] is not True
        or records[2]["classification"] != "CLEANED"
        or records[2]["cleanup_verified"] is not True
    ):
        raise Rejected()
    return records[1]


class ReadOnlyUpload(upload.UploadSession):
    """Transport-enforced GET only, including inherited methods."""

    def _request(self, method, url, headers, body):
        if method != "GET" or body is not None:
            raise Rejected()
        return super()._request(method, url, headers, body)

    def upload_once(self):
        raise Rejected()


def rediscover(
    asc, *, target, artifact, binding, version, build, _transport=upload.transport
):
    verified = fingerprint(artifact, binding=binding, version=version, build=build)
    if set(target) != {"app_id", "owner_group_id", "owner_tester_id"}:
        raise Rejected()
    session = ReadOnlyUpload(
        asc,
        **target,
        version=version,
        build=build,
        candidate_root=".",
        expected_sha256=verified["sha256"],
        expected_size=verified["size"],
        _transport=_transport,
    )
    try:
        session._preflight()
        matches = session._matching_uploads()
        if len(matches) != 1:
            raise Rejected()
        session.receipt.upload_id = matches[0]["id"]
        files = session._list(
            "/v1/buildUploads/" + session.receipt.upload_id + "/buildUploadFiles"
        )
        if len(files) != 1:
            raise Rejected()
        file = upload.resource(files[0], "buildUploadFiles")
        session.receipt.file_id = file["id"]
        attrs = file.get("attributes", {})
        if (
            attrs.get("fileName") != "candidate.ipa"
            or attrs.get("assetType") != "ASSET"
            or attrs.get("uti") != "com.apple.ipa"
            or type(attrs.get("fileSize")) is not int
            or attrs["fileSize"] != verified["size"]
            or attrs.get("sourceFileChecksums")
            != {"file": {"algorithm": "SHA_256", "hash": verified["sha256"]}}
        ):
            raise Rejected()
        session._file_membership(file)
        session.consumed = True  # No mutation method can be reached.
        result = session.reconcile()
        return result, session
    except Exception:
        return session._result("RECONCILIATION_UNRESOLVED"), session
