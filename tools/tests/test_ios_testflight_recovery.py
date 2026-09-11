import json
import unittest

from tools import ios_testflight_recovery as recovery
from tools.tests import test_ios_testflight_upload as fixtures


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.binding = recovery.wire.Binding("b" * 40, "c" * 64, "123")
        self.artifact = dict(
            schema=1,
            sha=self.binding.sha,
            nonce=self.binding.nonce,
            run_id="123",
            version="1.2.3",
            build=123,
            sha256="a" * 64,
            size=4,
        )

    def transport(self, change=None):
        fixture = fixtures.UploadTests()
        base, calls = fixture.transport(existing=True)

        def request(method, url, headers, body, timeout):
            self.assertEqual(method, "GET")
            response = base(method, url, headers, body, timeout)
            data = json.loads(response.body)
            if "/buildUploadFiles?" in url:
                data["data"][0]["attributes"] = dict(
                    fileName="candidate.ipa",
                    fileSize=4,
                    assetType="ASSET",
                    uti="com.apple.ipa",
                    sourceFileChecksums={
                        "file": {"algorithm": "SHA_256", "hash": "a" * 64}
                    },
                )
            if change:
                change(url, data)
            return recovery.upload.Response(200, json.dumps(data).encode())

        return fixture.session(request).asc, request, calls

    def run_recovery(self, change=None):
        key, transport, calls = self.transport(change)
        result, session = recovery.rediscover(
            key,
            target=dict(app_id="123", owner_group_id="group", owner_tester_id="tester"),
            artifact=self.artifact,
            binding=self.binding,
            version="1.2.3",
            build=123,
            _transport=transport,
        )
        self.assertTrue(all(call[0] == "GET" for call in calls))
        with self.assertRaises(recovery.Rejected):
            session.upload_once()
        with self.assertRaises(recovery.Rejected):
            session._request(
                "PATCH", "https://api.appstoreconnect.apple.com/v1/builds/x", {}, b"{}"
            )
        return result

    def test_complete_binding_get_only_no_distribution_claim(self):
        result = self.run_recovery()
        self.assertEqual(result.classification, "BUILD_VALID_UNDISTRIBUTED")
        self.assertFalse(result.distribution_authorized)
        self.assertNotIn("reservation", repr(result))

    def test_checksum_missing_mismatch_and_ambiguous_collections_stop(self):
        for delta in (
            {"fileSize": 5},
            {"fileSize": True},
            {"fileName": "different.ipa"},
            {"sourceFileChecksums": None},
            {
                "sourceFileChecksums": {
                    "file": {"algorithm": "SHA_256", "hash": "d" * 64}
                }
            },
            {"sourceFileChecksums": {"file": {"algorithm": "MD5", "hash": "a" * 64}}},
        ):

            def change(url, data):
                if "/buildUploadFiles?" in url:
                    data["data"][0]["attributes"].update(delta)

            with self.subTest(delta=delta):
                self.assertEqual(
                    self.run_recovery(change).classification,
                    "RECONCILIATION_UNRESOLVED",
                )
        for count in (0, 2):

            def change(url, data):
                if "/apps/123/buildUploads?" in url:
                    data["data"] = data["data"] * count

            self.assertEqual(
                self.run_recovery(change).classification, "RECONCILIATION_UNRESOLVED"
            )

    def test_foreign_linkage_pagination_and_processing(self):
        for mode in ("foreign", "pagination", "pending"):

            def change(url, data):
                if mode == "pagination" and "/apps/123/buildUploads?" in url:
                    data["links"] = {
                        "next": "https://api.appstoreconnect.apple.com/v1/apps/123/buildUploads?cursor=more"
                    }
                if "/builds/built?" in url:
                    if mode == "foreign":
                        data["data"]["relationships"]["app"]["data"]["id"] = "foreign"
                    if mode == "pending":
                        data["data"]["attributes"]["processingState"] = "PROCESSING"

            self.assertEqual(
                self.run_recovery(change).classification,
                "BUILD_PENDING" if mode == "pending" else "RECONCILIATION_UNRESOLVED",
            )

    def test_fingerprint_bound_and_duplicates_missing_rejected(self):
        line = recovery.PREFIX + json.dumps(self.artifact)
        raw = ("2026-09-12T01:02:03.123Z " + line + "\n").encode()
        self.assertEqual(
            recovery.from_logs(raw, binding=self.binding, version="1.2.3", build=123),
            self.artifact,
        )
        for value in (
            b"no receipt",
            raw + raw,
            raw.replace(b'"123"', b'"124"'),
            raw.replace(b'"schema": 1', b'"schema": true'),
            raw.replace(b'"size": 4', b'"size": 4, "private-sentinel": "bad"'),
        ):
            with self.assertRaises(recovery.Rejected):
                recovery.from_logs(
                    value, binding=self.binding, version="1.2.3", build=123
                )

    def test_result_requires_exact_known_cleanup_even_when_processing_pending(self):
        from tools import ios_testflight_hosted as hosted

        values = [
            hosted.public_result("PREPARED", cleanup=False),
            hosted.public_result("UPLOAD_PENDING", cleanup=True),
            hosted.public_result("CLEANED", cleanup=True),
        ]
        raw = "\n".join(
            recovery.RESULT_PREFIX + json.dumps(item) for item in values
        ).encode()
        self.assertEqual(
            recovery.result_from_logs(raw)["classification"], "UPLOAD_PENDING"
        )
        for altered in (
            raw.replace(b'"cleanup_verified": true', b'"cleanup_verified": false'),
            raw + b"\n" + raw,
            raw.splitlines()[1],
            raw.replace(b'"release_authorized": false', b'"release_authorized": true'),
        ):
            with self.assertRaises(recovery.Rejected):
                recovery.result_from_logs(altered)


if __name__ == "__main__":
    unittest.main()
