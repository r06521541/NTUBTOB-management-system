import json
import re
import unittest
from pathlib import Path

from apps.mobile_staging_broker.artifacts import artifact_hashes, load_attested_approval
from apps.mobile_staging_broker.broker import BrokerManifest

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "apps/mobile_staging_broker"


class DeploymentContractTest(unittest.TestCase):
    def test_runtime_and_build_inputs_have_valid_first_bytes(self):
        expected = {
            "app.py": b'"',
            "Dockerfile": b"F",
            "requirements.txt": b"F",
        }
        for name, first_byte in expected.items():
            with self.subTest(name=name):
                self.assertEqual((SERVICE / name).read_bytes()[:1], first_byte)

    def test_deployment_is_private_singleton_digest_pinned_and_numeric(self):
        configuration = (SERVICE / "cloudbuild.staging.yaml").read_text(
            encoding="utf-8"
        )
        command = " ".join(configuration.replace("\\\n", " ").split())
        self.assertIn("--no-allow-unauthenticated", command)
        self.assertIn("--max-instances=1", command)
        self.assertIn("--concurrency=1", command)
        self.assertIn("--service-account=${_RUNTIME_IDENTITY}", command)
        self.assertRegex(command, r"--image=\$\{_IMAGE\}@sha256:")
        self.assertNotIn(":latest", command)
        self.assertEqual(
            len(re.findall(r"/versions/\$\{_[A-Z_]+_VERSION\}", command)), 2
        )
        self.assertNotIn("BROKER_CANDIDATE_APPROVAL=", command)

    def test_build_uses_exact_root_context_and_filtered_required_files(self):
        build = (SERVICE / "cloudbuild.build.yaml").read_text(encoding="utf-8")
        self.assertIn("--file=apps/mobile_staging_broker/Dockerfile", build)
        self.assertRegex(build, r"(?m)^\s+- \.$")
        dockerfile = (SERVICE / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY apps/mobile_staging_broker/requirements.txt", dockerfile)
        self.assertIn("COPY . /app", dockerfile)
        self.assertRegex(dockerfile, r'"--workers", "1"')
        self.assertFalse((SERVICE / ".dockerignore").exists())
        ignored = (SERVICE / "Dockerfile.dockerignore").read_text(encoding="utf-8")
        for included in (
            "!apps/mobile_staging_broker/**",
            "!migrations/versions/**",
            "!tools/mobile_staging_data.py",
            "!shared_lib/shared_module/**",
        ):
            self.assertIn(included, ignored)
        for excluded in ("**/.env", "**/*credential*", "**/*secret*"):
            self.assertIn(excluded, ignored)

    def test_baked_approval_is_nonsecret_fictional_and_in_build_context(self):
        approval_path = SERVICE / "artifacts/candidate-approval.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        encoded = json.dumps(approval, sort_keys=True)
        self.assertTrue(approval["owner_approved"])
        self.assertEqual(approval["approval_phase"], "candidate")
        self.assertIn("fictional-mobile-staging", encoded)
        self.assertNotIn("ntubtob-schedule-405614", encoded)
        self.assertNotRegex(encoded, r"postgres(?:ql)?://")
        ignored = (SERVICE / "Dockerfile.dockerignore").read_text(encoding="utf-8")
        self.assertNotIn("*approval*", ignored)

    def test_baked_approval_loads_through_attested_runtime_contract(self):
        hashes = artifact_hashes(ROOT)
        manifest = BrokerManifest.from_mapping(
            {
                **hashes,
                "project": "fictional-mobile-staging",
                "region": "asia-east1",
                "service": "mobile-staging-broker",
                "runtime_identity": (
                    "broker-runtime@fictional-mobile-staging.iam.gserviceaccount.com"
                ),
                "image_digest": "sha256:" + "d" * 64,
                "database_secret_version": (
                    "projects/fictional-mobile-staging/secrets/database-url/versions/7"
                ),
                "subject_secret_version": (
                    "projects/fictional-mobile-staging/secrets/provider-subject/versions/9"
                ),
                "database_identity_sha256": "e" * 64,
            }
        )

        approval = load_attested_approval(manifest, ROOT)

        self.assertEqual(
            approval["mobile_api_google_audiences"],
            "fictional-staging-web.apps.googleusercontent.com",
        )


if __name__ == "__main__":
    unittest.main()
