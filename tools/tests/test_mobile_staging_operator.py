from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from tools.mobile_staging_contract import (
    PRODUCTION_PROJECT,
    DatabaseIdentity,
    StagingContractError,
    load_approval,
    redacted_manifest,
)
from tools.mobile_staging_data import plan, recover
from tools.mobile_staging_operator import (
    OperatorError,
    build_command,
    deploy_command,
    execute,
    normalize_digest,
    validate_build_context,
    validate_candidate,
)
from tools.mobile_staging_preflight import cloud_inventory

DATABASE_URL = (
    "postgresql://fake-user:fake-password@staging-db.invalid:5432/mobile_staging"
)
PROVIDER = "cloudsql"
RESOURCE = "projects/fake-staging/instances/mobile-db"
STAGING_HASH = DatabaseIdentity.from_url(DATABASE_URL, PROVIDER, RESOURCE).fingerprint
PRODUCTION_HASH = hashlib.sha256(b"separate-production-identity").hexdigest()
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64
IMAGE = "asia-east1-docker.pkg.dev/ntubtob-mobile-staging/mobile-staging/mobile-api"


def approval(*, phase="candidate", mode="update") -> dict:
    return {
        "owner_approved": True,
        "approval_phase": phase,
        "project": "ntubtob-mobile-staging",
        "region": "asia-east1",
        "service": "mobile-api-staging",
        "approved_commit": COMMIT,
        "build_id": None if phase == "build" else "build-task112-exact",
        "image_uri": IMAGE,
        "image_digest": DIGEST if phase == "candidate" else None,
        "mode": mode,
        "candidate_revision": "mobile-api-staging-candidate1",
        "rollback_revision": (
            None if mode == "bootstrap" else "mobile-api-staging-baseline1"
        ),
        "database_identity_sha256": STAGING_HASH,
        "production_database_identity_sha256": PRODUCTION_HASH,
        "database_provider": PROVIDER,
        "database_resource_id": RESOURCE,
        "database_alias": "dedicated-mobile-staging",
        "max_instances": 2,
        "service_account": "mobile-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com",
        "build_service_account": "mobile-build@ntubtob-mobile-staging.iam.gserviceaccount.com",
        "runtime_secret_refs": {
            "PORTAL_DATA_DATABASE_URL": "mobile-staging-database-url:1",
            "MOBILE_ACCESS_SIGNING_KEY": "mobile-staging-access-key:1",
            "MOBILE_REFRESH_REPLAY_KEY": "mobile-staging-refresh-key:1",
        },
        "mobile_api_audience": "1234567890",
    }


def revision(value=DIGEST):
    environment = [
        {
            "name": name,
            "valueFrom": {
                "secretKeyRef": {
                    "name": reference.split(":")[0],
                    "key": reference.split(":")[1],
                }
            },
        }
        for name, reference in approval()["runtime_secret_refs"].items()
    ]
    environment.append({"name": "MOBILE_API_AUDIENCE", "value": "1234567890"})
    return {
        "metadata": {
            "name": "mobile-api-staging-candidate1",
            "annotations": {
                "autoscaling.knative.dev/minScale": "0",
                "autoscaling.knative.dev/maxScale": "2",
            },
        },
        "spec": {
            "serviceAccountName": approval()["service_account"],
            "containers": [{"env": environment}],
        },
        "status": {
            "imageDigest": value,
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }


def service(mode="update", candidate_percent=0):
    traffic = (
        []
        if mode == "bootstrap"
        else [{"revisionName": "mobile-api-staging-baseline1", "percent": 100}]
    )
    if candidate_percent:
        traffic = [
            {
                "revisionName": "mobile-api-staging-candidate1",
                "percent": candidate_percent,
            }
        ]
    return {
        "metadata": {"annotations": {"run.googleapis.com/ingress": "all"}},
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "autoscaling.knative.dev/minScale": "0",
                        "autoscaling.knative.dev/maxScale": "2",
                    }
                },
                "spec": {"serviceAccountName": approval()["service_account"]},
            }
        },
        "status": {"traffic": traffic},
    }


class ContractTest(unittest.TestCase):
    def test_database_identity_includes_provider_resource_and_manifest_redacts(self):
        other = DatabaseIdentity.from_url(DATABASE_URL, PROVIDER, RESOURCE + "-other")
        self.assertNotEqual(other.fingerprint, STAGING_HASH)
        manifest = redacted_manifest(
            project="ntubtob-mobile-staging",
            database_url=DATABASE_URL,
            approved_staging_hash=STAGING_HASH,
            production_hash=PRODUCTION_HASH,
            database_provider=PROVIDER,
            database_resource_id=RESOURCE,
            database_alias="dedicated-mobile-staging",
            max_instances=2,
        )
        encoded = json.dumps(manifest)
        self.assertNotIn("staging-db.invalid", encoded)
        self.assertNotIn(RESOURCE, encoded)
        self.assertEqual(manifest["database"]["provider"], PROVIDER)

    def test_approval_modes_and_project_scoped_service_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approval.json"
            for mode in ("bootstrap", "update"):
                path.write_text(json.dumps(approval(mode=mode)), encoding="utf-8")
                self.assertEqual(load_approval(path)["mode"], mode)
            bad = approval()
            bad["service_account"] = (
                "mobile-runtime@another-project.iam.gserviceaccount.com"
            )
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(StagingContractError):
                load_approval(path)
            bad = approval(mode="bootstrap")
            bad["rollback_revision"] = "mobile-api-staging-fake"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(StagingContractError):
                load_approval(path)

    def test_production_project_rejected(self):
        with self.assertRaises(StagingContractError):
            redacted_manifest(
                project=PRODUCTION_PROJECT,
                database_url=DATABASE_URL,
                approved_staging_hash=STAGING_HASH,
                production_hash=PRODUCTION_HASH,
                database_provider=PROVIDER,
                database_resource_id=RESOURCE,
                max_instances=2,
            )

    def test_flutter_command_uses_existing_config_and_origin_semantics(self):
        integration = Path("clients/flutter_app/lib/integration.dart").read_text(
            encoding="utf-8"
        )
        runbook = Path("docs/operations/mobile/MOBILE_STAGING.md").read_text(
            encoding="utf-8"
        )
        for name in ("APP_FLAVOR", "CLIENT_MODE", "API_BASE_URL", "LINE_CHANNEL_ID"):
            self.assertIn(f"String.fromEnvironment('{name}')", integration)
            self.assertIn(f"--dart-define={name}=", runbook)
        self.assertIn("baseUrl.resolve('/api/v1$path')", integration)
        self.assertNotIn("--flavor staging", runbook)
        self.assertNotIn("MOBILE_API_BASE_URL", runbook)

    def test_remote_data_plan_is_redacted_and_dry_run(self):
        value = plan(approval(), DATABASE_URL)
        encoded = json.dumps(value)
        self.assertEqual(value["mutation"], "none-dry-run")
        self.assertNotIn("fake-password", encoded)
        self.assertNotIn(
            "provider_subject",
            encoded.replace('"provider_subject": "private-input-redacted"', ""),
        )
        with patch(
            "tools.mobile_staging_data.inventory",
            return_value={
                "revision": "0005_mobile_auth_api_foundation",
                "fixture_state": "seeded",
            },
        ):
            self.assertEqual(recover(approval(), DATABASE_URL)["outcome"], "completed")

    def test_preflight_bootstrap_and_update_are_mutually_exclusive(self):
        def runner(arguments, _cwd):
            if arguments[:4] == ["gcloud", "config", "get-value", "account"]:
                return CompletedProcess(arguments, 0, "operator@example.invalid", "")
            if arguments[:4] == ["gcloud", "config", "get-value", "project"]:
                return CompletedProcess(arguments, 0, "ntubtob-mobile-staging", "")
            if arguments[1:4] == ["run", "services", "list"]:
                return CompletedProcess(arguments, 0, "[]", "")
            return CompletedProcess(arguments, 0, "[]", "")

        self.assertFalse(
            cloud_inventory(
                Path.cwd(), "ntubtob-mobile-staging", 2, runner, mode="bootstrap"
            )["service_exists"]
        )
        with self.assertRaises(StagingContractError):
            cloud_inventory(
                Path.cwd(),
                "ntubtob-mobile-staging",
                2,
                runner,
                mode="update",
                rollback_revision="mobile-api-staging-baseline1",
            )


class OperatorTest(unittest.TestCase):
    def test_build_and_candidate_are_separate_and_scoped(self):
        build = build_command(approval(phase="build"))
        deploy = deploy_command(approval())
        self.assertIn(
            "projects/ntubtob-mobile-staging/serviceAccounts/"
            + approval()["build_service_account"],
            build,
        )
        self.assertNotIn("run", build)
        self.assertNotIn("builds", deploy)
        self.assertIn("--no-traffic", deploy)
        self.assertIn("--no-allow-unauthenticated", deploy)
        self.assertIn("--ingress", deploy)

    def test_digest_normalizes_repository_and_bare_forms(self):
        self.assertEqual(normalize_digest(DIGEST), DIGEST)
        self.assertEqual(normalize_digest(IMAGE + "@" + DIGEST), DIGEST)

    def test_bootstrap_update_authoritative_traffic(self):
        validate_candidate(
            approval(mode="bootstrap"),
            revision(IMAGE + "@" + DIGEST),
            service("bootstrap"),
        )
        validate_candidate(approval(), revision(), service())
        with self.assertRaises(OperatorError):
            validate_candidate(approval(), revision(), service(candidate_percent=100))

    def test_stale_shared_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service_root = root / "apps" / "mobile_api"
            (service_root / "dist").mkdir(parents=True)
            (service_root / ".dockerignore").write_text(
                "\n".join(
                    [
                        ".env.yaml",
                        ".env",
                        ".env.*",
                        "*.json",
                        "*.pem",
                        "*.key",
                        "*approval*",
                        "*state*",
                        "__pycache__/",
                        "tests/",
                    ]
                ),
                encoding="utf-8",
            )
            (service_root / "dist" / "shared_lib-0.0.1.tar.gz").write_bytes(b"stale")
            with self.assertRaises(OperatorError):
                validate_build_context(root)

    def test_build_lost_response_recover_and_finally_cleanup(self):
        commands = []

        def runner(arguments, cwd):
            commands.append(list(arguments))
            if arguments[:3] == ["git", "status", "--porcelain"]:
                return CompletedProcess(arguments, 0, "", "")
            if arguments[:3] == ["git", "rev-parse", "HEAD"]:
                return CompletedProcess(arguments, 0, COMMIT, "")
            if "setup.py" in arguments:
                output_dir = Path(arguments[arguments.index("--dist-dir") + 1])
                output_dir.mkdir(parents=True, exist_ok=True)
                artifact = output_dir / "shared_lib-0.0.1.tar.gz"
                with tarfile.open(artifact, "w:gz") as archive:
                    info = tarfile.TarInfo(
                        "shared_lib-0.0.1/shared_module/mobile_api.py"
                    )
                    info.size = 1
                    archive.addfile(info, io.BytesIO(b"x"))
                return CompletedProcess(arguments, 0, "", "")
            result = {
                "id": "build-task112-exact",
                "results": {"images": [{"name": IMAGE, "digest": DIGEST}]},
            }
            return CompletedProcess(arguments, 0, json.dumps(result), "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mobile = root / "apps" / "mobile_api"
            mobile.mkdir(parents=True)
            (root / "shared_lib").mkdir()
            (mobile / ".dockerignore").write_text(
                "\n".join(
                    [
                        ".env.yaml",
                        ".env",
                        ".env.*",
                        "*.json",
                        "*.pem",
                        "*.key",
                        "*approval*",
                        "*state*",
                        "__pycache__/",
                        "tests/",
                    ]
                ),
                encoding="utf-8",
            )
            recovery_approval = approval(phase="build")
            recovery_approval["build_id"] = "build-task112-exact"
            state = execute(
                "recover-build",
                recovery_approval,
                DATABASE_URL,
                root / "private/state.json",
                root,
                runner,
            )
            self.assertEqual(state.phase, "built")
            self.assertFalse(
                any(
                    command[:2] == ["gcloud", "builds"] and "submit" in command
                    for command in commands
                )
            )
            self.assertFalse((mobile / "dist" / "shared_lib-0.0.1.tar.gz").exists())


if __name__ == "__main__":
    unittest.main()
