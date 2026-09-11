"""Fictional transport, in-memory keys and byte streams only."""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric import ec

from tools import ios_testflight_inputs as inputs
from tools import ios_testflight_upload as upload


class UploadTests(unittest.TestCase):
    def session(self, transport):
        key = inputs.AscMaterial(
            ec.generate_private_key(ec.SECP256R1()),
            "FICTKEY001",
            "11111111-1111-4111-8111-111111111111",
        )
        return upload.UploadSession(
            key,
            app_id="123",
            owner_group_id="group",
            owner_tester_id="tester",
            version="1.2.3",
            build=123,
            candidate_root=Path("/fictional"),
            expected_sha256="a" * 64,
            expected_size=4,
            _transport=transport,
        )

    def transport(self, *, automatic=False, storage_failure=False, existing=False):
        calls = []

        def run(method, url, headers, body, timeout):
            calls.append((method, url, headers, body))
            path = url.split("apple.com", 1)[-1].split("?", 1)[0]
            reservation = {
                "type": "buildUploads",
                "id": "reservation",
                "attributes": {
                    "cfBundleShortVersionString": "1.2.3",
                    "cfBundleVersion": "123",
                    "platform": "IOS",
                    "state": {"state": "COMPLETE"},
                },
                "relationships": {"build": {"data": {"type": "builds", "id": "built"}}},
            }
            included = []
            if method == "PUT":
                self.assertNotIn("Authorization", headers)
                self.assertEqual(b"".join(body), b"fake")
                if storage_failure:
                    raise TimeoutError("private-sentinel")
                return upload.Response(200, b"")
            if path == "/v1/apps/123":
                data = {
                    "type": "apps",
                    "id": "123",
                    "attributes": {"bundleId": upload.BUNDLE},
                }
            elif path.endswith("/betaGroups"):
                data = [
                    {
                        "type": "betaGroups",
                        "id": "group",
                        "attributes": {
                            "isInternalGroup": True,
                            "hasAccessToAllBuilds": False,
                            "publicLinkEnabled": False,
                        },
                    },
                    {
                        "type": "betaGroups",
                        "id": "other",
                        "attributes": {
                            "isInternalGroup": True,
                            "hasAccessToAllBuilds": automatic,
                        },
                    },
                ]
            elif path.endswith("/betaTesters"):
                data = [{"type": "betaTesters", "id": "tester"}]
            elif method == "POST" and path == "/v1/buildUploads":
                data = reservation
            elif method == "POST" and path == "/v1/buildUploadFiles":
                data = {
                    "type": "buildUploadFiles",
                    "id": "file",
                    "attributes": {
                        "fileName": "candidate.ipa",
                        "fileSize": 4,
                        "assetType": "ASSET",
                        "uti": "com.apple.ipa",
                        "uploadOperations": [
                            {
                                "method": "PUT",
                                "url": "https://store-030.blobstore.apple.com/fictional",
                                "offset": 0,
                                "length": 4,
                                "requestHeaders": [],
                            }
                        ],
                    },
                }
            elif method == "PATCH":
                data = {"type": "buildUploadFiles", "id": "file"}
            elif path == "/v1/buildUploads/reservation":
                data = reservation
            elif path == "/v1/apps/123/buildUploads":
                data = (
                    [reservation]
                    if existing
                    or any(
                        c[0] == "POST" and c[1].endswith("/buildUploads") for c in calls
                    )
                    else []
                )
            elif path == "/v1/buildUploads/reservation/buildUploadFiles":
                data = [{"type": "buildUploadFiles", "id": "file"}]
            elif path == "/v1/builds/built":
                data = {
                    "type": "builds",
                    "id": "built",
                    "attributes": {
                        "version": "123",
                        "processingState": "VALID",
                        "expired": False,
                    },
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": "123"}},
                        "buildUpload": {
                            "data": {"type": "buildUploads", "id": "reservation"}
                        },
                        "preReleaseVersion": {
                            "data": {"type": "preReleaseVersions", "id": "marketing"}
                        },
                    },
                }
                included = [
                    {
                        "type": "apps",
                        "id": "123",
                        "attributes": {"bundleId": upload.BUNDLE},
                    },
                    {
                        "type": "preReleaseVersions",
                        "id": "marketing",
                        "attributes": {"version": "1.2.3", "platform": "IOS"},
                    },
                    reservation,
                ]
            else:
                data = []
            return upload.Response(
                201 if method == "POST" else 200,
                json.dumps({"data": data, "included": included}).encode(),
            )

        return run, calls

    @contextmanager
    def candidate(self):
        yield io.BytesIO(b"fake"), lambda: None

    def test_once_and_separate_processing(self):
        transport, calls = self.transport()
        session = self.session(transport)
        with patch.object(session, "_candidate", self.candidate):
            result = session.upload_once()
        self.assertEqual(result.classification, "UPLOAD_COMMITTED")
        self.assertFalse(result.release_authorized)
        self.assertEqual(session.upload_once().classification, "SESSION_CONSUMED")
        self.assertEqual(
            session.reconcile().classification, "BUILD_VALID_UNDISTRIBUTED"
        )
        patches = [json.loads(c[3]) for c in calls if c[0] == "PATCH"]
        self.assertEqual(
            patches[0]["data"]["attributes"]["sourceFileChecksums"],
            {"file": {"algorithm": "SHA_256", "hash": "a" * 64}},
        )
        self.assertNotIn("reservation", repr(result))

    def test_automatic_group_stops_before_mutation(self):
        transport, calls = self.transport(automatic=True)
        session = self.session(transport)
        with patch.object(session, "_candidate", self.candidate):
            result = session.upload_once()
        self.assertEqual(result.classification, "PREFLIGHT_REJECTED")
        self.assertTrue(all(c[0] == "GET" for c in calls))

    def test_put_uncertainty_not_retried(self):
        transport, calls = self.transport(storage_failure=True)
        session = self.session(transport)
        with patch.object(session, "_candidate", self.candidate):
            result = session.upload_once()
        self.assertEqual(result.classification, "UPLOAD_UNCERTAIN")
        self.assertEqual(result.receipt.upload_id, "reservation")
        self.assertNotIn("private-sentinel", repr(result))
        self.assertFalse(any(c[0] == "PATCH" for c in calls))

    def test_operation_ranges_and_urls(self):
        good = {
            "method": "PUT",
            "url": "https://store-030.blobstore.apple.com/fictional",
            "offset": 0,
            "length": 4,
            "requestHeaders": [],
        }
        with self.subTest():
            upload.operations([good], 4)
            for changes in (
                {"offset": 1},
                {"length": 3},
                {"url": "https://evil.invalid/private"},
                {"url": "https://user:pass@store-030.blobstore.apple.com/a"},
                {
                    "requestHeaders": [
                        {"name": "Authorization", "value": "private-sentinel"}
                    ]
                },
            ):
                with self.assertRaises(upload.Rejected):
                    upload.operations([good | changes], 4)
            with self.assertRaises(upload.Rejected):
                upload.operations([good, good], 4)

    def test_unknown_storage_preserves_receipt_without_put(self):
        base, calls = self.transport()

        def altered(method, url, headers, body, timeout):
            result = base(method, url, headers, body, timeout)
            if method == "POST" and url.endswith("buildUploadFiles"):
                data = json.loads(result.body)
                data["data"]["attributes"]["uploadOperations"][0][
                    "url"
                ] = "https://private-sentinel.invalid/a"
                return upload.Response(201, json.dumps(data).encode())
            return result

        session = self.session(altered)
        with patch.object(session, "_candidate", self.candidate):
            outcome = session.upload_once()
        self.assertEqual(outcome.receipt.file_id, "file")
        self.assertEqual(outcome.classification, "UPLOAD_UNCERTAIN")
        self.assertFalse(any(c[0] == "PUT" for c in calls))
        self.assertNotIn("private-sentinel", json.dumps(outcome.public()))

    def test_processing_states_not_upload_complete(self):
        for state, expected in (
            ("PROCESSING", "BUILD_PENDING"),
            ("FAILED", "BUILD_FAILED"),
            ("INVALID", "BUILD_FAILED"),
            ("unknown", "RECONCILIATION_UNRESOLVED"),
        ):
            base, calls = self.transport(existing=True)

            def altered(method, url, headers, body, timeout):
                response = base(method, url, headers, body, timeout)
                if url.split("?", 1)[0].endswith("/builds/built"):
                    data = json.loads(response.body)
                    data["data"]["attributes"]["processingState"] = state
                    return upload.Response(200, json.dumps(data).encode())
                return response

            session = self.session(altered)
            session.receipt.upload_id = "reservation"
            self.assertEqual(session.reconcile().classification, expected)
            self.assertTrue(all(c[0] == "GET" for c in calls))

    def test_redirect_overflow_and_pagination_fail_closed(self):
        for response in (
            upload.Response(302, b"private-sentinel"),
            upload.Response(200, b"x" * (upload.MAX_RESPONSE + 1)),
            upload.Response(200, b'{"data":[],"data":[]}'),
        ):
            session = self.session(lambda *args: response)
            self.assertEqual(session.preflight().classification, "PREFLIGHT_REJECTED")
        base, calls = self.transport()

        def pagination(method, url, headers, body, timeout):
            response = base(method, url, headers, body, timeout)
            if "/betaGroups" in url:
                value = json.loads(response.body)
                value["links"] = {"next": "https://evil.invalid/v1/private"}
                return upload.Response(200, json.dumps(value).encode())
            return response

        session = self.session(pagination)
        self.assertEqual(session.preflight().classification, "PREFLIGHT_REJECTED")
        self.assertTrue(all("evil.invalid" not in c[1] for c in calls))

    def test_transport_never_redirects_or_passes_bearer_to_storage(self):
        connection = Mock()
        response = Mock()
        response.status = 302
        connection.getresponse.return_value = response
        with patch.object(
            upload.http.client, "HTTPSConnection", return_value=connection
        ) as ctor:
            with self.assertRaises(upload.Rejected):
                upload.transport("GET", upload.API + "/v1/apps/123", {}, None, 30)
            self.assertEqual(ctor.call_count, 1)
            connection.close.assert_called_once()
        with (
            patch.object(upload.http.client, "HTTPSConnection") as ctor,
            self.assertRaises(upload.Rejected),
        ):
            upload.transport(
                "PUT",
                "https://store-030.blobstore.apple.com/a",
                {"Authorization": "private-sentinel"},
                b"fake",
                30,
            )
        ctor.assert_not_called()

    def test_candidate_size_and_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            path = root / "candidate.ipa"
            path.write_bytes(b"fake")
            session = self.session(lambda *args: None)
            session.root = root
            session.sha = hashlib.sha256(b"fake").hexdigest()
            mode = lambda value: 0o700 if upload.stat.S_ISDIR(value) else 0o600
            with (
                patch.object(
                    upload.os, "getuid", return_value=path.stat().st_uid, create=True
                ),
                patch.object(
                    upload.os,
                    "O_NOFOLLOW",
                    getattr(upload.os, "O_NOFOLLOW", 0),
                    create=True,
                ),
                patch.object(upload.stat, "S_IMODE", side_effect=mode),
            ):
                with session._candidate() as (_, stable):
                    stable()
                with session._candidate() as (_, stable):
                    path.write_bytes(b"changed")
                    with self.assertRaises(upload.Rejected):
                        stable()
                with self.assertRaises(upload.Rejected):
                    with session._candidate():
                        pass

    def test_request_budget_and_unknown_reservation_no_resend(self):
        base, calls = self.transport()
        session = self.session(base)
        session.requests = upload.MAX_REQUESTS
        self.assertEqual(session.preflight().classification, "PREFLIGHT_REJECTED")
        self.assertFalse(calls)
        session = self.session(base)
        session.consumed = True
        self.assertEqual(session.reconcile().classification, "UNKNOWN_RESERVATION")
        self.assertTrue(all(c[0] == "GET" for c in calls))

    def test_create_uncertainty_and_mutation_lock(self):
        base, calls = self.transport()

        def lost(method, url, headers, body, timeout):
            if method == "POST":
                calls.append((method, url, headers, body))
                raise TimeoutError("private-sentinel")
            return base(method, url, headers, body, timeout)

        session = self.session(lost)
        with patch.object(session, "_candidate", self.candidate):
            result = session.upload_once()
        self.assertEqual(result.classification, "UPLOAD_UNCERTAIN")
        self.assertEqual(result.public()["stage"], "reservation")
        self.assertIsNone(result.receipt.upload_id)
        self.assertEqual(session.upload_once().classification, "SESSION_CONSUMED")
        self.assertEqual(sum(c[0] == "POST" for c in calls), 1)
        other = self.session(base)
        other._mutation_lock.acquire()
        try:
            self.assertEqual(other.upload_once().classification, "SESSION_CONSUMED")
        finally:
            other._mutation_lock.release()

    def test_fixed_api_paths_and_port_host_boundary(self):
        session = self.session(lambda *args: self.fail("unexpected request"))
        for method, path in (
            ("DELETE", "/v1/buildUploads/x"),
            ("POST", "/v1/betaGroups"),
            ("GET", "/v1/apps/other"),
        ):
            with self.assertRaises(upload.Rejected):
                session._api(method, path)
        for url in (
            "http://store-030.blobstore.apple.com/a",
            "https://store-030.blobstore.apple.com:444/a",
            "https://store-030.blobstore.apple.com.evil.invalid/a",
            "https://store-30.blobstore.apple.com/a",
            "https://store-030.blobstore.apple.com/a#fragment",
        ):
            with self.assertRaises(upload.Rejected):
                upload.parsed_url(url, storage=True)

    def test_foreign_or_wrong_created_upload_stops_before_second_mutation(self):
        for field, value in (
            ("cfBundleShortVersionString", "9.9.9"),
            ("cfBundleVersion", "999"),
            ("platform", "MAC_OS"),
            ("app", "OTHER"),
            ("attributes", None),
            ("membership", None),
        ):
            with self.subTest(field=field):
                base, calls = self.transport()

                def altered(method, url, headers, body, timeout):
                    response = base(method, url, headers, body, timeout)
                    data = json.loads(response.body)
                    if method == "POST" and url.endswith("/buildUploads"):
                        if field == "app":
                            data["data"]["relationships"]["app"] = {
                                "data": {"type": "apps", "id": value}
                            }
                        elif field == "attributes":
                            data["data"].pop("attributes")
                        elif field != "membership":
                            data["data"]["attributes"][field] = value
                    if field == "membership" and "/apps/123/buildUploads?" in url:
                        data["data"] = []
                    return upload.Response(response.status, json.dumps(data).encode())

                session = self.session(altered)
                with patch.object(session, "_candidate", self.candidate):
                    result = session.upload_once()
                self.assertEqual(result.classification, "UPLOAD_UNCERTAIN")
                self.assertEqual(result.receipt.upload_id, "reservation")
                self.assertEqual([c[0] for c in calls if c[0] != "GET"], ["POST"])

    def test_file_parent_requires_related_collection_proof_before_bytes(self):
        for field in ("foreign", "missing", "duplicate"):
            with self.subTest(field=field):
                base, calls = self.transport()

                def altered(method, url, headers, body, timeout):
                    response = base(method, url, headers, body, timeout)
                    data = json.loads(response.body)
                    if (
                        field == "foreign"
                        and method == "POST"
                        and url.endswith("/buildUploadFiles")
                    ):
                        data["data"]["relationships"] = {
                            "buildUpload": {
                                "data": {"type": "buildUploads", "id": "OTHER"}
                            }
                        }
                    if "/reservation/buildUploadFiles?" in url:
                        data["data"] = [] if field == "missing" else data["data"] * 2
                    return upload.Response(response.status, json.dumps(data).encode())

                session = self.session(altered)
                with patch.object(session, "_candidate", self.candidate):
                    result = session.upload_once()
                self.assertEqual(result.classification, "UPLOAD_UNCERTAIN")
                self.assertEqual(result.receipt.file_id, "file")
                self.assertFalse(any(c[0] in {"PUT", "PATCH"} for c in calls))

    def test_reconcile_requires_exact_app_upload_and_marketing_version(self):
        for field in (
            "app",
            "buildUpload",
            "preReleaseVersion",
            "version",
            "platform",
            "bundle",
            "missing_included",
            "missing_membership",
            "upload_app",
        ):
            with self.subTest(field=field):
                base, calls = self.transport(existing=True)

                def altered(method, url, headers, body, timeout):
                    response = base(method, url, headers, body, timeout)
                    data = json.loads(response.body)
                    if (
                        field == "missing_membership"
                        and "/apps/123/buildUploads?" in url
                    ):
                        data["data"] = []
                    if field == "upload_app" and url.endswith(
                        "/buildUploads/reservation"
                    ):
                        data["data"]["relationships"]["app"] = {
                            "data": {"type": "apps", "id": "OTHER"}
                        }
                    if url.split("?", 1)[0].endswith("/builds/built"):
                        if field in {"app", "buildUpload", "preReleaseVersion"}:
                            data["data"]["relationships"][field]["data"]["id"] = "OTHER"
                        elif field in {"version", "platform"}:
                            data["included"][1]["attributes"][field] = "OTHER"
                        elif field == "bundle":
                            data["included"][0]["attributes"]["bundleId"] = "OTHER"
                        elif field == "missing_included":
                            data.pop("included")
                    return upload.Response(response.status, json.dumps(data).encode())

                session = self.session(altered)
                session.receipt.upload_id = "reservation"
                self.assertEqual(
                    session.reconcile().classification, "RECONCILIATION_UNRESOLVED"
                )
                self.assertTrue(all(c[0] == "GET" for c in calls))


if __name__ == "__main__":
    unittest.main()
