import copy
import unittest

from tools import ios_testflight_staging as staging


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.change = lambda command, value: None
        self.spec = {
            "serviceAccountName": "runtime@ntubtob-mobile-staging.iam.gserviceaccount.com",
            "containers": [
                {
                    "image": "asia-east1-docker.pkg.dev/ntubtob-mobile-staging/api/mobile@"
                    + staging.DIGEST,
                    "env": [
                        {
                            "name": staging.DB,
                            "valueFrom": {
                                "secretKeyRef": {"name": "fictional-db", "key": "1"}
                            },
                        },
                        {"name": "MOBILE_API_AUDIENCE", "value": "fictional"},
                    ],
                }
            ],
        }
        self.revision = {
            "metadata": {
                "name": staging.BASELINE,
                "namespace": "123",
                "generation": 1,
                "creationTimestamp": "2026-08-26T05:35:31.015912Z",
                "labels": {"serving.knative.dev/service": staging.SERVICE},
            },
            "spec": self.spec,
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "observedGeneration": 1,
                "imageDigest": staging.DIGEST,
            },
        }
        self.service = {
            "metadata": {"name": staging.SERVICE, "namespace": "123", "generation": 1},
            "spec": {"template": {"metadata": {}, "spec": copy.deepcopy(self.spec)}},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "observedGeneration": 1,
                "traffic": [{"revisionName": staging.BASELINE, "percent": 100}],
            },
        }

    def cli(self, command):
        self.calls.append(command)
        self.assertNotIn("access", command)
        self.assertIn("describe", command)
        if command[1] == "projects":
            value = dict(
                projectId=staging.PROJECT, projectNumber="123", lifecycleState="ACTIVE"
            )
        elif command[1] == "secrets":
            value = dict(
                name="projects/123/secrets/fictional-db/versions/1",
                state="ENABLED",
                createTime="2026-08-25T01:00:00Z",
            )
        elif command[2] == "services":
            value = copy.deepcopy(self.service)
        else:
            value = copy.deepcopy(self.revision)
            value["metadata"]["name"] = command[4]
        self.change(command, value)
        return value

    def verify(self):
        return staging.verify(staging.PROJECT, staging.SERVICE, cli_json=self.cli)

    def test_retained_binding_metadata_only(self):
        result = self.verify()
        self.assertTrue(result["ownership_verified"])
        self.assertFalse(result["runtime_postcheck_verified"])
        self.assertNotIn("fictional", repr(result))
        self.assertEqual(len(self.calls), 5)

    def test_new_pinned_image_not_new_ownership_authority(self):
        self.service["spec"]["template"]["spec"]["containers"][0]["image"] = self.spec[
            "containers"
        ][0]["image"].replace(staging.DIGEST, "sha256:" + "b" * 64)
        self.assertTrue(self.verify()["ownership_verified"])

    def test_qualified_digest_and_bounded_metadata(self):
        self.revision["status"]["imageDigest"] = self.spec["containers"][0]["image"]
        self.assertTrue(self.verify()["ownership_verified"])
        self.change = lambda command, document: document.update(extra="x" * 1048577)
        self.assertFalse(self.verify()["ownership_verified"])

    def test_missing_generation_and_unpinned_foreign_images(self):
        for image in (
            "asia-east1-docker.pkg.dev/production/api/app@" + staging.DIGEST,
            "asia-east1-docker.pkg.dev/ntubtob-mobile-staging/api/app:latest",
            "asia-east1-docker.pkg.dev/ntubtob-mobile-staging/../app@" + staging.DIGEST,
        ):
            self.service["spec"]["template"]["spec"]["containers"][0]["image"] = image
            self.assertFalse(self.verify()["ownership_verified"])
        self.service["spec"]["template"]["spec"] = copy.deepcopy(self.spec)
        self.service["status"]["observedGeneration"] = True
        self.assertFalse(self.verify()["ownership_verified"])

    def test_immutable_baseline_and_secret_recreation_rejected(self):
        for field, value, kind in (
            ("creationTimestamp", "2026-09-01T00:00:00Z", "revision"),
            ("createTime", "2026-08-26T06:00:00Z", "secret"),
            ("state", "DISABLED", "secret"),
            ("name", "projects/999/secrets/fictional-db/versions/1", "secret"),
        ):

            def change(command, document):
                if kind == "revision" and command[2] == "revisions":
                    document["metadata"][field] = value
                elif kind == "secret" and command[1] == "secrets":
                    document[field] = value

            self.change = change
            with self.subTest(field=field):
                self.assertFalse(self.verify()["ownership_verified"])

    def test_baseline_digest_and_account_project_rejected(self):
        self.revision["status"]["imageDigest"] = "sha256:" + "b" * 64
        self.assertFalse(self.verify()["ownership_verified"])
        self.revision["status"]["imageDigest"] = staging.DIGEST
        self.spec["serviceAccountName"] = "runtime@production.iam.gserviceaccount.com"
        self.assertFalse(self.verify()["ownership_verified"])

    def test_secret_latest_plain_missing_and_drift(self):
        env = self.service["spec"]["template"]["spec"]["containers"][0]["env"]
        original = copy.deepcopy(env[0])
        for replacement in (
            {"name": staging.DB, "value": "private-sentinel"},
            {
                "name": staging.DB,
                "valueFrom": {
                    "secretKeyRef": {"name": "fictional-db", "key": "latest"}
                },
            },
            {
                "name": staging.DB,
                "valueFrom": {"secretKeyRef": {"name": "fictional-db", "key": "2"}},
            },
        ):
            env[0] = replacement
            self.assertFalse(self.verify()["ownership_verified"])
        env[:] = [original, original]
        self.assertFalse(self.verify()["ownership_verified"])

    def test_alias_qualified_staging_only(self):
        self.service["spec"]["template"]["metadata"]["annotations"] = {
            "run.googleapis.com/secrets": "fictional-db:projects/123/secrets/fictional-db"
        }
        self.assertTrue(self.verify()["ownership_verified"])
        self.service["spec"]["template"]["metadata"]["annotations"][
            "run.googleapis.com/secrets"
        ] = "fictional-db:projects/production/secrets/fictional-db"
        self.assertFalse(self.verify()["ownership_verified"])

    def test_extra_environment_sidecar_volume(self):
        original = copy.deepcopy(self.service)
        for mode in ("env", "sidecar", "volumes"):
            self.service = copy.deepcopy(original)
            spec = self.service["spec"]["template"]["spec"]
            if mode == "env":
                spec["containers"][0]["env"].append(
                    {"name": "EXTRA", "value": "private-sentinel"}
                )
            elif mode == "sidecar":
                spec["containers"].append(copy.deepcopy(spec["containers"][0]))
            else:
                spec["volumes"] = [{"name": "private-sentinel"}]
            self.assertFalse(self.verify()["ownership_verified"])

    def test_all_positive_and_tagged_revisions_checked(self):
        other = staging.SERVICE + "-other"
        self.service["status"]["traffic"].append({"revisionName": other, "tag": "test"})
        self.assertTrue(self.verify()["ownership_verified"])

        def change(command, document):
            if command[2] == "revisions" and command[4] == other:
                document["spec"]["containers"][0]["env"][0]["valueFrom"][
                    "secretKeyRef"
                ]["key"] = "2"

        self.change = change
        self.assertFalse(self.verify()["ownership_verified"])

    def test_ambiguous_traffic_or_generation_stops(self):
        for traffic in (
            [],
            [{"revisionName": staging.BASELINE, "percent": 99}],
            [{"latestRevision": True, "percent": 100}],
            [{"revisionName": staging.BASELINE, "percent": True}],
        ):
            self.service["status"]["traffic"] = traffic
            self.assertFalse(self.verify()["ownership_verified"])

    def test_unknown_exception_or_snapshot_change_fixed_failure(self):
        def failure(command):
            raise RuntimeError("private-sentinel")

        result = staging.verify(staging.PROJECT, staging.SERVICE, cli_json=failure)
        self.assertNotIn("private-sentinel", repr(result))

        def change(command, document):
            if command[2] == "services" and len(self.calls) > 3:
                document["metadata"]["generation"] = 2

        self.change = change
        self.assertFalse(self.verify()["ownership_verified"])

    def test_wrong_target_never_calls_cli(self):
        def forbidden(command):
            self.fail("unexpected CLI")

        self.assertEqual(
            staging.verify("production", staging.SERVICE, cli_json=forbidden)[
                "classification"
            ],
            "STAGING_OWNERSHIP_UNVERIFIED",
        )


if __name__ == "__main__":
    unittest.main()
