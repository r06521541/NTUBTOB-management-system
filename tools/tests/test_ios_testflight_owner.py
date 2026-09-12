import json
import unittest
from dataclasses import replace
from urllib.parse import urlsplit

from tools import ios_testflight_owner as owner
from tools.tests import test_ios_testflight_recovery as recovery_fixtures


class OwnerTests(unittest.TestCase):
    def setUp(self):
        fixture = recovery_fixtures.RecoveryTests()
        fixture.setUp()
        asc, transport, _ = fixture.transport()
        _, self.recovered = owner.recovery.rediscover(
            asc,
            target=dict(app_id="123", owner_group_id="group", owner_tester_id="tester"),
            artifact=fixture.artifact,
            binding=fixture.binding,
            version="1.2.3",
            build=123,
            _transport=transport,
        )
        self.target = owner.Target("123", "group", "tester", "1.2.3", 122, 123)
        self.ready = owner.StagingReadiness(
            "ntubtob-mobile-staging", "mobile-api-staging", "a" * 40, "0012", True, True
        )
        self.calls = []
        self.assigned = False
        self.fail_post = False
        self.change = lambda path, data: None
        self.session = owner.OwnerSession(
            asc, owner_email="fictional@example.invalid", transport=self.transport
        )

    def transport(self, method, url, headers, body, timeout):
        path = urlsplit(url).path
        self.calls.append((method, path))
        self.assertLessEqual(timeout, 30)
        self.assertEqual(urlsplit(url).hostname, "api.appstoreconnect.apple.com")
        if method == "POST":
            self.assertEqual(path, "/v1/betaGroups/group/relationships/builds")
            self.assertEqual(
                json.loads(body), {"data": [{"type": "builds", "id": "built"}]}
            )
            if self.fail_post:
                raise TimeoutError("private-sentinel")
            self.assigned = True
            return owner.upload.Response(204, b"")
        if path == "/v1/apps":
            data = [
                {
                    "type": "apps",
                    "id": "123",
                    "attributes": {"bundleId": owner.upload.BUNDLE},
                }
            ]
        elif path.endswith("/betaGroups"):
            data = [
                {
                    "type": "betaGroups",
                    "id": "group",
                    "attributes": dict(
                        name=owner.GROUP,
                        isInternalGroup=True,
                        hasAccessToAllBuilds=False,
                        publicLinkEnabled=False,
                    ),
                }
            ]
        elif path.endswith("/betaTesters"):
            data = [
                {
                    "type": "betaTesters",
                    "id": "tester",
                    "attributes": {"email": "fictional@example.invalid"},
                }
            ]
        elif path.endswith("/individualTesters"):
            data = []
        elif path.endswith("/relationships/builds"):
            data = [{"type": "builds", "id": "built"}] if self.assigned else []
        elif path.endswith("/builds"):
            data = [{"type": "builds", "id": "old", "attributes": {"version": "121"}}]
        elif path.endswith("/buildUploads"):
            data = [
                {
                    "type": "buildUploads",
                    "id": "old-upload",
                    "attributes": {"cfBundleVersion": "122"},
                }
            ]
        else:
            self.fail("unexpected fixed path")
        document = {"data": data}
        self.change(path, document)
        return owner.upload.Response(200, json.dumps(document).encode())

    def assign(self, **kwargs):
        return self.session.assign(
            self.recovered,
            target=self.target,
            staging_ready=kwargs.pop("staging_ready", self.ready),
            before=kwargs.pop("before", lambda event: None),
            after=kwargs.pop("after", lambda event: None),
            **kwargs,
        )

    def test_invalid_input_before_network(self):
        with self.assertRaises(owner.Rejected):
            owner.OwnerSession(None, owner_email="private")

    def test_inventory_plans_without_mutations(self):
        self.assertEqual(self.session.inventory(version="1.2.3"), self.target)
        self.assertTrue(all(method == "GET" for method, _ in self.calls))
        self.assertNotIn("fictional", repr(self.session))
        self.assertNotIn("123", repr(self.target))

    def test_inventory_reports_fixed_http_and_transport_failures(self):
        for status, reason in (
            (401, "ASC_AUTHENTICATION_REJECTED"),
            (403, "ASC_PERMISSION_REJECTED"),
            (400, "ASC_REQUEST_REJECTED"),
            (404, "ASC_REQUEST_REJECTED"),
            (429, "ASC_SERVICE_UNAVAILABLE"),
            (503, "ASC_SERVICE_UNAVAILABLE"),
            (302, "ASC_REQUEST_REJECTED"),
        ):
            self.session.transport = lambda *args: owner.upload.Response(
                status, b"private-sentinel"
            )
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(owner.Rejected, reason),
            ):
                self.session.inventory()
            self.assertEqual(self.session.stage, "asc_apps")

        def failed(*args):
            raise TimeoutError("private-sentinel")

        self.session.transport = failed
        with self.assertRaisesRegex(owner.Rejected, "ASC_CONNECTION_FAILED"):
            self.session.inventory()
        self.assertEqual(self.session.stage, "asc_apps")

    def test_inventory_stage_distinguishes_policy_and_endpoint_without_values(self):
        for field, stage in (
            ("hasAccessToAllBuilds", "asc_group_auto_distribution"),
            ("publicLinkEnabled", "asc_group_public_link"),
        ):

            def change(path, document):
                if path.endswith("/betaGroups"):
                    document["data"][0]["attributes"].pop(field)

            self.change = change
            with self.assertRaises(owner.Rejected):
                self.session.inventory()
            self.assertEqual(self.session.stage, stage)
        self.change = lambda *args: None
        original = self.transport

        def last_request(method, url, *args):
            if urlsplit(url).path.endswith("/buildUploads"):
                return owner.upload.Response(403, b"private-sentinel")
            return original(method, url, *args)

        self.session.transport = last_request
        with self.assertRaisesRegex(owner.Rejected, "ASC_PERMISSION_REJECTED"):
            self.session.inventory()
        self.assertEqual(self.session.stage, "asc_build_uploads")
        self.assertTrue(all(method == "GET" for method, _ in self.calls))

    def test_missing_or_unsafe_scope(self):
        for field, value, reason in (
            ("name", "different", "OWNER_GROUP_REQUIRED"),
            ("publicLinkEnabled", True, "OWNER_SCOPE_REJECTED"),
            ("hasAccessToAllBuilds", True, "OWNER_SCOPE_REJECTED"),
            ("isInternalGroup", False, "OWNER_SCOPE_REJECTED"),
        ):

            def change(path, document):
                if path.endswith("/betaGroups"):
                    document["data"][0]["attributes"][field] = value

            self.change = change
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(owner.Rejected, reason),
            ):
                self.session.inventory()

    def test_empty_or_extra_tester(self):
        for count in (0, 2):

            def change(path, document):
                if path.endswith("/betaTesters"):
                    document["data"] *= count

            self.change = change
            with self.assertRaises(owner.Rejected):
                self.session.inventory()

    def test_success_durable_order_and_already_assigned_no_post(self):
        events = []

        def before(event):
            self.assertFalse(any(method == "POST" for method, _ in self.calls))
            events.append(event)

        status = self.assign(before=before, after=events.append)
        self.assertEqual(status["classification"], "OWNER_DISTRIBUTION_VERIFIED")
        self.assertFalse(status["release_authorized"])
        self.assertEqual(
            events, ["OWNER_DISTRIBUTION_ATTEMPT", "OWNER_DISTRIBUTION_CONFIRMED"]
        )
        self.assertEqual(self.assign()["classification"], "ALREADY_ASSIGNED")
        self.assertEqual(sum(method == "POST" for method, _ in self.calls), 1)

    def test_uncertain_never_reposts(self):
        self.fail_post = True
        self.assertEqual(self.assign()["classification"], "ASSIGNMENT_UNCERTAIN")
        self.fail_post = False
        self.assertEqual(self.assign()["classification"], "ASSIGNMENT_UNCERTAIN")
        self.assertEqual(sum(method == "POST" for method, _ in self.calls), 1)
        self.assigned = True
        self.assertEqual(self.assign()["classification"], "ALREADY_ASSIGNED")

    def test_journal_failure_stops_before_post(self):
        def failure(event):
            raise OSError("private-sentinel")

        self.assertEqual(
            self.assign(before=failure)["classification"], "ASSIGNMENT_UNCERTAIN"
        )
        self.assertEqual(self.assign()["classification"], "ASSIGNMENT_UNCERTAIN")
        self.assertFalse(any(method == "POST" for method, _ in self.calls))

    def test_staging_assertion_required(self):
        for delta in (
            dict(runtime_postcheck_verified=False),
            dict(apple_configuration_verified=1),
            dict(source_sha="private-sentinel"),
            dict(project="production"),
            dict(schema_revision="0009"),
        ):
            with self.subTest(delta=delta):
                status = self.assign(staging_ready=replace(self.ready, **delta))
                self.assertEqual(status["classification"], "OWNER_SCOPE_REJECTED")
                self.assertNotIn("private-sentinel", repr(status))
        self.assertEqual(self.calls, [])

    def test_fingerprint_drift_and_target_mismatch(self):
        self.recovered.sha = "b" * 64
        self.assertEqual(self.assign()["classification"], "OWNER_SCOPE_REJECTED")
        self.recovered.sha = "a" * 64
        self.target = replace(self.target, planned_build=124)
        self.assertEqual(self.assign()["classification"], "OWNER_SCOPE_REJECTED")
        self.assertEqual(self.calls, [])

    def test_direct_tester_distribution_rejected(self):
        def change(path, document):
            if path.endswith("/individualTesters"):
                document["data"] = [{"type": "betaTesters", "id": "tester"}]

        self.change = change
        self.assertEqual(self.assign()["classification"], "OWNER_SCOPE_REJECTED")
        self.assertFalse(any(method == "POST" for method, _ in self.calls))

    def test_other_group_distribution_rejected(self):
        def change(path, document):
            if path.endswith("/betaGroups"):
                document["data"].append(
                    {
                        "type": "betaGroups",
                        "id": "other",
                        "attributes": dict(
                            name="Other",
                            isInternalGroup=True,
                            hasAccessToAllBuilds=False,
                            publicLinkEnabled=False,
                        ),
                    }
                )
            if path == "/v1/betaGroups/other/relationships/builds":
                document["data"] = [{"type": "builds", "id": "built"}]

        self.change = change
        self.assertEqual(self.assign()["classification"], "OWNER_SCOPE_REJECTED")
        self.assertFalse(any(method == "POST" for method, _ in self.calls))

    def test_after_failure_and_readback_failure_uncertain(self):
        def failure(event):
            raise OSError("private-sentinel")

        self.assertEqual(
            self.assign(after=failure)["classification"], "ASSIGNMENT_UNCERTAIN"
        )
        self.assertEqual(sum(method == "POST" for method, _ in self.calls), 1)
        self.setUp()

        def change(path, document):
            if path.endswith("/relationships/builds"):
                document["data"] = []

        self.change = change
        self.assertEqual(self.assign()["classification"], "ASSIGNMENT_UNCERTAIN")
        self.assertEqual(self.assign()["classification"], "ASSIGNMENT_UNCERTAIN")
        self.assertEqual(sum(method == "POST" for method, _ in self.calls), 1)

    def test_unknown_build_version_stops_inventory(self):
        for value in (True, "1.2.3", "0", "2147483647"):

            def change(path, document):
                if path.endswith("/buildUploads"):
                    document["data"][0]["attributes"]["cfBundleVersion"] = value

            self.change = change
            with self.assertRaises(owner.Rejected):
                self.session.inventory()

    def test_pagination_origin_duplicates_budget_and_error_sanitized(self):
        for link in (
            "https://evil.invalid/v1/apps",
            owner.upload.API + "/v1/apps?limit=200&limit=200",
            owner.upload.API + "/v1/apps?limit=200",
        ):
            self.change = lambda path, document: document.update(links={"next": link})
            with self.assertRaises(owner.Rejected) as error:
                self.session.inventory()
            self.assertEqual(str(error.exception), "OWNER_SCOPE_REJECTED")
        self.session.requests = 200
        with self.assertRaises(owner.Rejected):
            self.session.inventory()


if __name__ == "__main__":
    unittest.main()
