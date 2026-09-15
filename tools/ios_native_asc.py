"""Bounded ASC GET-only upload preflight; never assigns testers or creates builds."""

import http.client
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit

from tools.ios_native_signing import BUNDLE, Failure, require

HOST = "api.appstoreconnect.apple.com"
LIMIT = 1048576


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError()
        value[key] = item
    return value


class Reader:
    """Only GET on a fixed TLS host, no redirects/retries or response-body logs."""

    def __init__(self, material, *, connect=http.client.HTTPSConnection):
        self.material, self.connect = material, connect
        self.deadline = time.monotonic() + 180
        self.cleanup_failures = []

    def get(self, path):
        from tools.ios_testflight_inputs import asc_jwt

        require(
            path.startswith("/v1/") and len(path) <= 4096,
            "asc_get",
            "PATH_REJECTED",
        )
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "asc_get", "DEADLINE_EXCEEDED")
        connection = None
        try:
            token = asc_jwt(self.material, now=datetime.now(timezone.utc)).value
            connection = self.connect(HOST, timeout=min(30, remaining))
            connection.request(
                "GET", path, headers={"Authorization": "Bearer " + token}
            )
            response = connection.getresponse()
            require(
                response.status == 200,
                "asc_get",
                {
                    401: "HTTP_401_AUTHENTICATION",
                    403: "HTTP_403_AUTHORIZATION",
                    404: "HTTP_404_TARGET",
                    429: "HTTP_429_RATE_LIMIT",
                }.get(
                    response.status,
                    "HTTP_5XX" if response.status >= 500 else "HTTP_REJECTED",
                ),
            )
            chunks, size = [], 0
            while True:
                remaining = self.deadline - time.monotonic()
                require(remaining > 0, "asc_get", "DEADLINE_EXCEEDED")
                if connection.sock is not None:
                    connection.sock.settimeout(min(30, remaining))
                chunk = response.read1(min(65536, LIMIT + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                require(size <= LIMIT, "asc_get", "RESPONSE_LIMIT")
            raw = b"".join(chunks)
            value = json.loads(raw, object_pairs_hook=unique)
            require(type(value) is dict, "asc_get", "JSON_REJECTED")
            return value
        except Failure:
            raise
        except (ValueError, UnicodeError):
            raise Failure("asc_get", "JSON_REJECTED") from None
        except Exception:
            raise Failure("asc_get", "TRANSPORT_OR_TLS_FAILED") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    self.cleanup_failures.append(
                        Failure("asc_connection_cleanup", "CLOSE_FAILED").public()
                    )


def resources(get, path, query, resource_type):
    """Complete at most 10 pages; retain original endpoint/filter on every cursor."""
    original = {key: str(value) for key, value in query.items()}
    original["limit"] = "200"
    current = path + "?" + urlencode(original)
    pages, identifiers, output = set(), set(), []
    for _ in range(10):
        require(current not in pages, "asc_page", "CURSOR_REPEATED")
        pages.add(current)
        payload = get(current)
        require(type(payload) is dict, "asc_page", "COLLECTION_REJECTED")
        data, links = payload.get("data"), payload.get("links")
        require(
            type(data) is list and len(data) <= 200 and type(links) is dict,
            "asc_page",
            "COLLECTION_REJECTED",
        )
        for item in data:
            require(type(item) is dict, "asc_page", "RESOURCE_REJECTED")
            identity = item.get("id")
            require(
                type(identity) is str
                and re.fullmatch(r"[A-Za-z0-9-]{1,100}", identity)
                and identity not in identifiers
                and item.get("type") == resource_type
                and type(item.get("attributes")) is dict,
                "asc_page",
                "RESOURCE_REJECTED",
            )
            identifiers.add(identity)
            output.append(item)
        following = links.get("next")
        if following is None:
            return output
        require(type(following) is str, "asc_page", "CURSOR_REJECTED")
        parsed = urlsplit(following)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        values = dict(pairs)
        require(
            parsed.scheme == "https"
            and parsed.netloc == HOST
            and parsed.path == path
            and not parsed.fragment
            and len(values) == len(pairs)
            and set(values) == set(original) | {"cursor"}
            and all(values.get(key) == value for key, value in original.items())
            and 1 <= len(values.get("cursor", "")) <= 512,
            "asc_page",
            "CURSOR_REJECTED",
        )
        current = path + "?" + urlencode(values)
    raise Failure("asc_page", "PAGE_LIMIT")


def preflight(get, version, build):
    apps = resources(get, "/v1/apps", {"filter[bundleId]": BUNDLE}, "apps")
    require(
        len(apps) == 1 and apps[0]["attributes"].get("bundleId") == BUNDLE,
        "asc_app",
        "APP_BINDING_REJECTED",
    )
    app = apps[0]["id"]
    # Both collections: a prior failed/pending upload is not permission to retry.
    uploads = resources(
        get,
        f"/v1/apps/{app}/buildUploads",
        {
            "filter[cfBundleShortVersionString]": version,
            "filter[cfBundleVersion]": build,
            "filter[platform]": "IOS",
        },
        "buildUploads",
    )
    builds = resources(
        get,
        "/v1/builds",
        {
            "filter[app]": app,
            "filter[version]": build,
        },
        "builds",
    )
    # Conservatively reject ANY returned build number, even another marketing
    # version; never choose a new version to route around an uncertain upload.
    require(not uploads and not builds, "asc_build", "BUILD_ALREADY_EXISTS")
    groups = resources(get, f"/v1/apps/{app}/betaGroups", {}, "betaGroups")
    require(
        all(
            group["attributes"].get("hasAccessToAllBuilds") is False for group in groups
        ),
        "asc_distribution",
        "AUTOMATIC_ACCESS_NOT_DISABLED",
    )
    return app
