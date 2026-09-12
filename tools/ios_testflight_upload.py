"""One-session Build Upload REST adapter; no CLI, distribution or authority.

Controller must prove signing cleanup, inspection, exact staging scope and exclusive
group administration before invoking. Receipts/keys/URLs are private, not logs.
No durable restart authority is supplied: uncertainty requires reconciliation.
"""

import hashlib
import http.client
import json
import os
import re
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from tools import ios_testflight_inputs as inputs

API = "https://api.appstoreconnect.apple.com"
BUNDLE = "tw.org.ntubtob.portal"
# Narrow Apple storage family approved by TASK198; actual route remains unverified.
STORAGE_HOST = re.compile(r"store-[0-9]{3}\.blobstore\.apple\.com")
MAX_BYTES = 536870912
MAX_RESPONSE = 1048576
MAX_REQUESTS = 128
CLASSIFICATIONS = frozenset(
    {
        "PREFLIGHT_PASSED",
        "PREFLIGHT_REJECTED",
        "SESSION_CONSUMED",
        "UPLOAD_COMMITTED",
        "UPLOAD_UNCERTAIN",
        "UNKNOWN_RESERVATION",
        "UPLOAD_FAILED",
        "UPLOAD_PENDING",
        "BUILD_PENDING",
        "BUILD_VALID_UNDISTRIBUTED",
        "BUILD_FAILED",
        "RECONCILIATION_UNRESOLVED",
    }
)
STORAGE_HEADERS = frozenset({"content-type", "content-md5", "x-amz-checksum-sha256"})


class Rejected(Exception):
    def __init__(self):
        super().__init__("UPLOAD_CONTRACT_REJECTED")


@dataclass(frozen=True, repr=False)
class Response:
    status: int
    body: bytes


@dataclass(repr=False)
class Receipt:
    upload_id: str | None = None
    file_id: str | None = None
    build_id: str | None = None


@dataclass(frozen=True, repr=False)
class Outcome:
    classification: str
    receipt: Receipt
    stage: str = "preflight"
    distribution_authorized: bool = field(default=False, init=False)
    release_authorized: bool = field(default=False, init=False)

    def public(self):
        return {
            "classification": (
                self.classification
                if self.classification in CLASSIFICATIONS
                else "RECONCILIATION_UNRESOLVED"
            ),
            "distribution_authorized": False,
            "release_authorized": False,
            "device_verified": False,
            "stage": (
                self.stage
                if self.stage
                in {
                    "preflight",
                    "reservation",
                    "file_reservation",
                    "storage_plan",
                    "storage",
                    "commit",
                    "reconcile",
                }
                else "reconcile"
            ),
        }


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9-]{1,128}", value):
        raise Rejected()
    return value


def parsed_url(url, *, storage=False):
    try:
        if (
            type(url) is not str
            or not 1 <= len(url) <= 8192
            or any(ord(c) < 33 or ord(c) > 126 for c in url)
            or "\\" in url
        ):
            raise ValueError()
        parts = urlsplit(url)
        allowed = (
            bool(STORAGE_HOST.fullmatch(parts.hostname or ""))
            if storage
            else parts.hostname == "api.appstoreconnect.apple.com"
        )
        if (
            parts.scheme != "https"
            or not allowed
            or parts.netloc not in {parts.hostname, (parts.hostname or "") + ":443"}
            or parts.username
            or parts.password
            or parts.fragment
            or not parts.path.startswith("/")
        ):
            raise ValueError()
        return parts
    except Exception:
        raise Rejected() from None


def transport(method, url, headers, body, timeout):
    """No redirects/proxies/debug output; API and storage authorization separated."""
    connection = None
    try:
        parts = parsed_url(url, storage=method == "PUT")
        if method == "PUT" and any(
            k.lower() in {"authorization", "cookie", "host"} for k in headers
        ):
            raise Rejected()
        connection = http.client.HTTPSConnection(parts.hostname, timeout=timeout)
        deadline = time.monotonic() + timeout

        def remaining():
            interval = deadline - time.monotonic()
            if interval <= 0:
                raise Rejected()
            if connection.sock is not None:
                connection.sock.settimeout(interval)

        # OS DNS resolver behavior remains host-controlled; all socket I/O shares
        # this per-request deadline rather than resetting a timeout per chunk.
        connection.connect()
        remaining()
        connection.putrequest(
            method,
            parts.path + ("?" + parts.query if parts.query else ""),
            skip_accept_encoding=True,
        )
        for name, value in headers.items():
            connection.putheader(name, value)
        if not any(k.lower() == "content-length" for k in headers):
            connection.putheader(
                "Content-Length", str(len(body) if type(body) is bytes else 0)
            )
        connection.endheaders()
        if body is not None:
            for chunk in (body,) if type(body) is bytes else body:
                remaining()
                connection.send(chunk)
        remaining()
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise Rejected()
        data = bytearray()
        while len(data) <= MAX_RESPONSE:
            remaining()
            chunk = response.read1(min(65536, MAX_RESPONSE + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_RESPONSE:
            raise Rejected()
        return Response(response.status, bytes(data))
    except Exception:
        raise Rejected() from None
    finally:
        if connection is not None:
            connection.close()


def document(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Rejected()
            result[key] = value
        return result

    try:
        if type(data) is not bytes or len(data) > MAX_RESPONSE:
            raise Rejected()
        value = json.loads(data, object_pairs_hook=unique)
        if type(value) is not dict or "data" not in value:
            raise Rejected()
        return value
    except Exception:
        raise Rejected() from None


def resource(value, kind, expected=None):
    if type(value) is not dict or value.get("type") != kind:
        raise Rejected()
    actual = identifier(value.get("id"))
    if expected is not None and actual != expected:
        raise Rejected()
    return value


def operations(values, size):
    """Validate entire operation set before the first storage byte is sent."""
    try:
        if type(values) is not list or not 1 <= len(values) <= 64:
            raise Rejected()
        ordered = []
        part_numbers = set()
        for value in values:
            if type(value) is not dict or set(value) - {
                "method",
                "url",
                "offset",
                "length",
                "requestHeaders",
                "expiration",
                "partNumber",
                "entityTag",
            }:
                raise Rejected()
            if value.get("method") != "PUT":
                raise Rejected()
            if "expiration" in value:
                expiration = value["expiration"]
                if type(expiration) is not str or len(expiration) > 64:
                    raise Rejected()
                expires = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
                if expires.utcoffset() is None or expires <= datetime.now(timezone.utc):
                    raise Rejected()
            if "partNumber" in value:
                number = value["partNumber"]
                if (
                    type(number) is not int
                    or not 1 <= number <= 64
                    or number in part_numbers
                ):
                    raise Rejected()
                part_numbers.add(number)
            if "entityTag" in value and (
                type(value["entityTag"]) is not str or len(value["entityTag"]) > 1024
            ):
                raise Rejected()
            parsed_url(value.get("url"), storage=True)
            offset, length = value.get("offset"), value.get("length")
            if (
                type(offset) is not int
                or type(length) is not int
                or offset < 0
                or length <= 0
                or offset + length > size
            ):
                raise Rejected()
            headers = value.get("requestHeaders")
            if type(headers) is not list or len(headers) > 16:
                raise Rejected()
            safe = {}
            for header in headers:
                if type(header) is not dict or set(header) != {"name", "value"}:
                    raise Rejected()
                name, content = header["name"], header["value"]
                if (
                    type(name) is not str
                    or name.lower() not in STORAGE_HEADERS
                    or name.lower() in safe
                    or type(content) is not str
                    or not 0 < len(content) <= 4096
                    or any(ord(c) < 32 or ord(c) > 126 for c in content)
                ):
                    raise Rejected()
                safe[name.lower()] = content
            safe["Content-Length"] = str(length)
            ordered.append((offset, length, value["url"], safe))
        ordered.sort(key=lambda v: v[0])
        end = 0
        for offset, length, _, _ in ordered:
            if offset != end:
                raise Rejected()
            end += length
        if end != size:
            raise Rejected()
        return ordered
    except Exception:
        raise Rejected() from None


class UploadSession:
    def __init__(
        self,
        asc,
        *,
        app_id,
        owner_group_id,
        owner_tester_id,
        version,
        build,
        candidate_root,
        expected_sha256,
        expected_size,
        _transport=transport,
    ):
        if (
            type(asc) is not inputs.AscMaterial
            or type(version) is not str
            or not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version)
            or type(build) is not int
            or not 1 <= build <= 2147483647
            or type(expected_sha256) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or type(expected_size) is not int
            or not 0 < expected_size <= MAX_BYTES
        ):
            raise Rejected()
        self.asc = asc
        self.app = identifier(app_id)
        self.group = identifier(owner_group_id)
        self.tester = identifier(owner_tester_id)
        self.version = version
        self.build = str(build)
        self.root = Path(candidate_root)
        self.sha = expected_sha256
        self.size = expected_size
        self.receipt = Receipt()
        self.consumed = False
        self.requests = 0
        self.deadline = time.monotonic() + 2700
        self._transport = _transport
        self.stage = "preflight"
        self._mutation_lock = threading.Lock()

    def _result(self, kind):
        return Outcome(kind, self.receipt, self.stage)

    def _request(self, method, url, headers, body):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.requests >= MAX_REQUESTS:
            raise Rejected()
        self.requests += 1
        response = self._transport(method, url, headers, body, min(30, remaining))
        if (
            type(response) is not Response
            or type(response.status) is not int
            or type(response.body) is not bytes
            or len(response.body) > MAX_RESPONSE
            or 300 <= response.status < 400
        ):
            raise Rejected()
        return response

    def _api(self, method, path, payload=None):
        if not path.startswith("/v1/") or ".." in path or "#" in path:
            raise Rejected()
        url = API + path
        parsed = parsed_url(url)
        allowed = {
            "GET": {
                "/v1/apps/" + self.app,
                "/v1/apps/" + self.app + "/betaGroups",
                "/v1/apps/" + self.app + "/buildUploads",
                "/v1/betaGroups/" + self.group + "/betaTesters",
            },
            "POST": {"/v1/buildUploads", "/v1/buildUploadFiles"},
            "PATCH": set(),
        }
        for kind, ident in (
            ("buildUploads", self.receipt.upload_id),
            ("buildUploadFiles", self.receipt.file_id),
            ("builds", self.receipt.build_id),
        ):
            if ident is not None:
                allowed["GET"].add("/v1/" + kind + "/" + identifier(ident))
        if self.receipt.upload_id is not None:
            allowed["GET"].add(
                "/v1/buildUploads/" + self.receipt.upload_id + "/buildUploadFiles"
            )
        if self.receipt.file_id is not None:
            allowed["PATCH"].add("/v1/buildUploadFiles/" + self.receipt.file_id)
        if parsed.path not in allowed.get(method, set()):
            raise Rejected()
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if (
            len(pairs) != len(dict(pairs))
            or len(pairs) > 5
            or (pairs and method != "GET")
        ):
            raise Rejected()
        for key, value in pairs:
            fixed = {
                "limit": "200",
                "filter[cfBundleShortVersionString]": self.version,
                "filter[cfBundleVersion]": self.build,
                "filter[platform]": "IOS",
            }
            if key == "include":
                if (
                    self.receipt.build_id is None
                    or parsed.path != "/v1/builds/" + self.receipt.build_id
                    or value != "app,preReleaseVersion,buildUpload"
                ):
                    raise Rejected()
            elif key == "cursor":
                if not 0 < len(value) <= 2048 or any(
                    ord(c) < 33 or ord(c) > 126 for c in value
                ):
                    raise Rejected()
            elif key not in fixed or fixed[key] != value:
                raise Rejected()
        token = inputs.asc_jwt(self.asc, now=datetime.now(timezone.utc))
        body = (
            None
            if payload is None
            else json.dumps(payload, separators=(",", ":")).encode()
        )
        if body is not None and len(body) > 65536:
            raise Rejected()
        response = self._request(
            method,
            url,
            {
                "Authorization": "Bearer " + token.value,
                "Content-Type": "application/json",
            },
            body,
        )
        if response.status != (201 if method == "POST" else 200):
            raise Rejected()
        return document(response.body)

    def _list(self, path):
        current = path + "?limit=200"
        items = []
        seen = set()
        for _ in range(10):
            if current in seen:
                raise Rejected()
            seen.add(current)
            response = self._api("GET", current)
            page = response["data"]
            if type(page) is not list or len(page) > 200:
                raise Rejected()
            items.extend(page)
            next_url = response.get("links", {}).get("next")
            if next_url is None:
                return items
            parsed = parsed_url(next_url)
            if parsed.path != path or any(
                k not in {"limit", "cursor"} for k, _ in parse_qsl(parsed.query)
            ):
                raise Rejected()
            current = parsed.path + "?" + parsed.query
        raise Rejected()

    def _preflight(self):
        app = resource(
            self._api("GET", "/v1/apps/" + self.app)["data"], "apps", self.app
        )
        if app.get("attributes", {}).get("bundleId") != BUNDLE:
            raise Rejected()
        groups = self._list("/v1/apps/" + self.app + "/betaGroups")
        found = False
        ids = set()
        for raw in groups:
            group = resource(raw, "betaGroups")
            ident = group["id"]
            if ident in ids:
                raise Rejected()
            ids.add(ident)
            attributes = group.get("attributes", {})
            if attributes.get("hasAccessToAllBuilds") is not False:
                raise Rejected()
            if ident == self.group:
                if (
                    attributes.get("isInternalGroup") is not True
                    or attributes.get("publicLinkEnabled") is not False
                ):
                    raise Rejected()
                found = True
        if not found:
            raise Rejected()
        testers = self._list("/v1/betaGroups/" + self.group + "/betaTesters")
        if len(testers) != 1:
            raise Rejected()
        resource(testers[0], "betaTesters", self.tester)

    def _matching_uploads(self):
        query = urlencode(
            {
                "filter[cfBundleShortVersionString]": self.version,
                "filter[cfBundleVersion]": self.build,
                "filter[platform]": "IOS",
                "limit": "200",
            }
        )
        result = self._api("GET", "/v1/apps/" + self.app + "/buildUploads?" + query)
        values = result["data"]
        if (
            type(values) is not list
            or len(values) > 200
            or result.get("links", {}).get("next") is not None
        ):
            raise Rejected()
        for value in values:
            self._upload_resource(value)
        return values

    def _upload_resource(self, value, expected=None):
        record = resource(value, "buildUploads", expected)
        attrs = record.get("attributes", {})
        if (
            attrs.get("cfBundleVersion") != self.build
            or attrs.get("cfBundleShortVersionString") != self.version
            or attrs.get("platform") != "IOS"
        ):
            raise Rejected()
        # Apple's BuildUpload schema has no app linkage. Explicit contradictory
        # extra linkage is rejected; _upload_membership supplies the actual proof.
        if "app" in record.get("relationships", {}):
            resource(record["relationships"]["app"].get("data"), "apps", self.app)
        return record

    def _upload_membership(self):
        matches = self._matching_uploads()
        if len(matches) != 1 or matches[0]["id"] != self.receipt.upload_id:
            raise Rejected()

    def _file_membership(self, record):
        # BuildUploadFile likewise has no parent linkage in OpenAPI4.4.1.
        if "buildUpload" in record.get("relationships", {}):
            resource(
                record["relationships"]["buildUpload"].get("data"),
                "buildUploads",
                self.receipt.upload_id,
            )
        files = self._list(
            "/v1/buildUploads/" + self.receipt.upload_id + "/buildUploadFiles"
        )
        if len(files) != 1:
            raise Rejected()
        resource(files[0], "buildUploadFiles", self.receipt.file_id)

    def _build_binding(self, response):
        built = resource(response["data"], "builds", self.receipt.build_id)
        relationships = built.get("relationships", {})
        app = resource(relationships.get("app", {}).get("data"), "apps", self.app)
        uploaded = resource(
            relationships.get("buildUpload", {}).get("data"),
            "buildUploads",
            self.receipt.upload_id,
        )
        marketing = resource(
            relationships.get("preReleaseVersion", {}).get("data"),
            "preReleaseVersions",
        )
        included = response.get("included")
        if type(included) is not list or len(included) != 3:
            raise Rejected()
        by_identity = {}
        for item in included:
            if type(item) is not dict:
                raise Rejected()
            key = (item.get("type"), identifier(item.get("id")))
            if key in by_identity:
                raise Rejected()
            by_identity[key] = item

        def exact(link):
            return by_identity[(link["type"], link["id"])]

        if exact(app).get("attributes", {}).get("bundleId") != BUNDLE:
            raise Rejected()
        self._upload_resource(exact(uploaded), self.receipt.upload_id)
        attributes = exact(marketing).get("attributes", {})
        if (
            attributes.get("version") != self.version
            or attributes.get("platform") != "IOS"
        ):
            raise Rejected()
        if "app" in exact(marketing).get("relationships", {}):
            resource(
                exact(marketing)["relationships"]["app"].get("data"), "apps", self.app
            )
        return built

    def preflight(self):
        try:
            self._preflight()
            if self._matching_uploads():
                raise Rejected()
            return self._result("PREFLIGHT_PASSED")
        except Exception:
            return self._result("PREFLIGHT_REJECTED")

    @contextmanager
    def _candidate(self):
        fd = None
        try:
            path = self.root / "candidate.ipa"
            if (
                not self.root.is_absolute()
                or ".." in path.parts
                or path.resolve(strict=True) != path
            ):
                raise Rejected()
            for parent in (path, *path.parents):
                if parent.is_symlink():
                    raise Rejected()
            root = self.root.stat()
            if root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) != 0o700:
                raise Rejected()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1
                or before.st_size != self.size
            ):
                raise Rejected()

            def stable():
                after = os.fstat(fd)
                current = path.stat(follow_symlinks=False)
                identity = lambda s: (
                    s.st_dev,
                    s.st_ino,
                    s.st_size,
                    s.st_mtime_ns,
                    s.st_uid,
                    s.st_mode,
                    s.st_nlink,
                )
                if identity(before) != identity(after) or identity(after) != identity(
                    current
                ):
                    raise Rejected()

            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(fd, min(65536, self.size + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > self.size:
                    raise Rejected()
                digest.update(chunk)
            stable()
            if digest.hexdigest() != self.sha:
                raise Rejected()
            with os.fdopen(fd, "rb", closefd=False) as stream:
                yield stream, stable
        finally:
            if fd is not None:
                os.close(fd)

    def upload_once(self):
        if not self._mutation_lock.acquire(blocking=False):
            return self._result("SESSION_CONSUMED")
        try:
            return self._upload_once()
        finally:
            self._mutation_lock.release()

    def _upload_once(self):
        if self.consumed:
            return self._result("SESSION_CONSUMED")
        self.consumed = True
        attempted = False
        try:
            self._preflight()
            if self._matching_uploads():
                raise Rejected()
            with self._candidate() as (stream, stable):
                attempted = True
                self.stage = "reservation"
                created = self._api(
                    "POST",
                    "/v1/buildUploads",
                    {
                        "data": {
                            "type": "buildUploads",
                            "attributes": {
                                "cfBundleShortVersionString": self.version,
                                "cfBundleVersion": self.build,
                                "platform": "IOS",
                            },
                            "relationships": {
                                "app": {"data": {"type": "apps", "id": self.app}}
                            },
                        }
                    },
                )
                self.receipt.upload_id = resource(created["data"], "buildUploads")["id"]
                self._upload_resource(created["data"], self.receipt.upload_id)
                self._upload_membership()
                self.stage = "file_reservation"
                file = self._api(
                    "POST",
                    "/v1/buildUploadFiles",
                    {
                        "data": {
                            "type": "buildUploadFiles",
                            "attributes": {
                                "assetType": "ASSET",
                                "fileName": "candidate.ipa",
                                "fileSize": self.size,
                                "uti": "com.apple.ipa",
                            },
                            "relationships": {
                                "buildUpload": {
                                    "data": {
                                        "type": "buildUploads",
                                        "id": self.receipt.upload_id,
                                    }
                                }
                            },
                        }
                    },
                )
                record = resource(file["data"], "buildUploadFiles")
                self.receipt.file_id = record["id"]
                attrs = record.get("attributes", {})
                if (
                    attrs.get("fileName") != "candidate.ipa"
                    or type(attrs.get("fileSize")) is not int
                    or attrs["fileSize"] != self.size
                    or attrs.get("assetType") != "ASSET"
                    or attrs.get("uti") != "com.apple.ipa"
                ):
                    raise Rejected()
                self._file_membership(record)
                self.stage = "storage_plan"
                parts = operations(attrs.get("uploadOperations"), self.size)
                self.stage = "storage"
                for offset, length, url, headers in parts:
                    stable()
                    stream.seek(offset)
                    transferred = 0

                    def chunks():
                        nonlocal transferred
                        remaining = length
                        while remaining:
                            block = stream.read(min(65536, remaining))
                            if not block:
                                raise Rejected()
                            remaining -= len(block)
                            transferred += len(block)
                            yield block

                    response = self._request("PUT", url, headers, chunks())
                    if response.status not in {200, 201, 204} or transferred != length:
                        raise Rejected()
                    stable()
                self._preflight()
                self._upload_membership()
                self._file_membership(record)
                stable()
                self.stage = "commit"
                committed = self._api(
                    "PATCH",
                    "/v1/buildUploadFiles/" + self.receipt.file_id,
                    {
                        "data": {
                            "type": "buildUploadFiles",
                            "id": self.receipt.file_id,
                            "attributes": {
                                "uploaded": True,
                                "sourceFileChecksums": {
                                    "file": {"algorithm": "SHA_256", "hash": self.sha}
                                },
                            },
                        }
                    },
                )
                resource(committed["data"], "buildUploadFiles", self.receipt.file_id)
                return self._result("UPLOAD_COMMITTED")
        except Exception:
            return self._result(
                "UPLOAD_UNCERTAIN" if attempted else "PREFLIGHT_REJECTED"
            )

    def reconcile(self):
        self.stage = "reconcile"
        try:
            if self.receipt.upload_id is None:
                if not self.consumed:
                    return self._result("UNKNOWN_RESERVATION")
                matches = self._matching_uploads()
                if len(matches) == 0:
                    return self._result("UNKNOWN_RESERVATION")
                if len(matches) != 1:
                    raise Rejected()
                self.receipt.upload_id = matches[0]["id"]
            record = self._upload_resource(
                self._api("GET", "/v1/buildUploads/" + self.receipt.upload_id)["data"],
                self.receipt.upload_id,
            )
            self._upload_membership()
            attrs = record.get("attributes", {})
            if (
                attrs.get("cfBundleVersion") != self.build
                or attrs.get("cfBundleShortVersionString") != self.version
                or attrs.get("platform") != "IOS"
            ):
                raise Rejected()
            state = attrs.get("state", {}).get("state")
            if state == "FAILED":
                return self._result("UPLOAD_FAILED")
            if state in {"AWAITING_UPLOAD", "PROCESSING"}:
                return self._result("UPLOAD_PENDING")
            if state != "COMPLETE":
                raise Rejected()
            link = record.get("relationships", {}).get("build", {}).get("data")
            if link is None:
                return self._result("BUILD_PENDING")
            self.receipt.build_id = resource(link, "builds")["id"]
            built = self._build_binding(
                self._api(
                    "GET",
                    "/v1/builds/"
                    + self.receipt.build_id
                    + "?include=app,preReleaseVersion,buildUpload",
                )
            )
            if built.get("attributes", {}).get("version") != self.build:
                raise Rejected()
            if built["attributes"].get("expired") is not False:
                raise Rejected()
            processing = built["attributes"].get("processingState")
            if processing == "VALID":
                return self._result("BUILD_VALID_UNDISTRIBUTED")
            if processing in {"FAILED", "INVALID"}:
                return self._result("BUILD_FAILED")
            if processing == "PROCESSING":
                return self._result("BUILD_PENDING")
            raise Rejected()
        except Exception:
            return self._result("RECONCILIATION_UNRESOLVED")
