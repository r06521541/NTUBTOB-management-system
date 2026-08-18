from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

from tools.mobile_staging_contract import (PRODUCTION_PROJECT,
                                           DatabaseIdentity,
                                           StagingContractError, load_approval,
                                           redacted_manifest,
                                           validate_database_identity)
from tools.mobile_staging_operator import (OperatorError, OperatorState,
                                           candidate_commands, execute,
                                           load_state, save_state,
                                           traffic_command,
                                           validate_shared_artifact)
from tools.mobile_staging_preflight import cloud_inventory

DATABASE_URL = "postgresql://fake-user:fake-password@staging-db.invalid:5432/mobile_staging"
STAGING_HASH = DatabaseIdentity.from_url(DATABASE_URL).fingerprint
PRODUCTION_HASH = hashlib.sha256(
    b"postgresql://production-db.invalid:5432/postgres"
).hexdigest()
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64


def approval() -> dict:
    return {
        "owner_approved": True,
        "project": "ntubtob-mobile-staging",
        "region": "asia-east1",
        "service": "mobile-api-staging",
        "approved_commit": COMMIT,
        "image_digest": DIGEST,
        "candidate_revision": "mobile-api-staging-candidate1",
        "rollback_revision": "mobile-api-staging-baseline1",
        "database_identity_sha256": STAGING_HASH,
        "production_database_identity_sha256": PRODUCTION_HASH,
        "max_instances": 2,
        "service_account": "mobile-staging@ntubtob-mobile-staging.iam.gserviceaccount.com",
        "runtime_secret_refs": {
            "PORTAL_DATA_DATABASE_URL": "mobile-staging-database-url:1",
            "MOBILE_ACCESS_SIGNING_KEY": "mobile-staging-access-key:1",
            "MOBILE_REFRESH_REPLAY_KEY": "mobile-staging-refresh-key:1",
        },
        "mobile_api_audience": "1234567890",
    }


class ContractTest(unittest.TestCase):
    def test_production_project_and_database_are_rejected(self):
        with self.assertRaises(StagingContractError):
            redacted_manifest(
                project=PRODUCTION_PROJECT,
                database_url=DATABASE_URL,
                approved_staging_hash=STAGING_HASH,
                production_hash=PRODUCTION_HASH,
                max_instances=2,
            )
        with self.assertRaises(StagingContractError):
            validate_database_identity(
                DATABASE_URL, PRODUCTION_HASH, PRODUCTION_HASH
            )
        with self.assertRaises(StagingContractError):
            validate_database_identity(
                DATABASE_URL, "c" * 64, STAGING_HASH
            )

    def test_manifest_redacts_dsn_and_has_exact_runtime_names(self):
        manifest = redacted_manifest(
            project="ntubtob-mobile-staging",
            database_url=DATABASE_URL,
            approved_staging_hash=STAGING_HASH,
            production_hash=PRODUCTION_HASH,
            max_instances=2,
            secret_refs=approval()["runtime_secret_refs"],
            commit=COMMIT,
            digest=DIGEST,
        )
        encoded = json.dumps(manifest, sort_keys=True)
        self.assertNotIn("fake-password", encoded)
        self.assertNotIn("staging-db.invalid", encoded)
        self.assertEqual(manifest["tester_count"], 1)
        self.assertEqual(manifest["runtime_plain_names"], ["MOBILE_API_AUDIENCE"])
        self.assertEqual(
            set(manifest["runtime_secret_refs"]),
            {
                "PORTAL_DATA_DATABASE_URL",
                "MOBILE_ACCESS_SIGNING_KEY",
                "MOBILE_REFRESH_REPLAY_KEY",
            },
        )

    def test_approval_requires_exact_fields_and_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approval.json"
            path.write_text(json.dumps(approval()), encoding="utf-8")
            self.assertEqual(load_approval(path)["approved_commit"], COMMIT)
            bad = approval()
            bad["unexpected"] = True
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(StagingContractError):
                load_approval(path)

    def test_shared_artifact_rejects_private_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared_lib-0.0.1.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                for name in (
                    "shared_lib-0.0.1/shared_module/mobile_api.py",
                    "shared_lib-0.0.1/credential.json",
                ):
                    info = tarfile.TarInfo(name)
                    info.size = 1
                    archive.addfile(info, io.BytesIO(b"x"))
            with self.assertRaises(OperatorError):
                validate_shared_artifact(Path(directory), path)

    def test_cloud_inventory_is_read_only_and_returns_names_only(self):
        commands = []

        def runner(arguments, _cwd):
            commands.append(arguments)
            if arguments[:4] == ["gcloud", "config", "get-value", "account"]:
                return CompletedProcess(arguments, 0, "operator@example.invalid", "")
            if arguments[:4] == ["gcloud", "config", "get-value", "project"]:
                return CompletedProcess(arguments, 0, "ntubtob-mobile-staging", "")
            if arguments[1:4] == ["run", "services", "list"]:
                return CompletedProcess(arguments, 0, "[]", "")
            return CompletedProcess(
                arguments,
                0,
                json.dumps([{"name": "projects/x/secrets/mobile-staging-key"}]),
                "",
            )

        result = cloud_inventory(
            Path.cwd(), "ntubtob-mobile-staging", 2, runner
        )
        self.assertFalse(result["service_exists"])
        self.assertEqual(result["secret_metadata_names"], ["mobile-staging-key"])
        joined = " ".join(" ".join(command) for command in commands)
        for forbidden in ("deploy", "create", "add-iam-policy-binding"):
            self.assertNotIn(forbidden, joined)


class OperatorTest(unittest.TestCase):
    def test_commands_are_no_traffic_bounded_and_never_create_resources(self):
        build, deploy = candidate_commands(approval())
        joined = " ".join(build + deploy)
        self.assertIn("--no-traffic", deploy)
        self.assertIn("--min 0 --max 2", joined)
        self.assertIn(COMMIT, joined)
        self.assertIn(DIGEST, joined)
        for forbidden in (
            "projects create",
            "add-iam-policy-binding",
            "service-accounts create",
            "secrets create",
            "billing",
        ):
            self.assertNotIn(forbidden, joined)
        self.assertEqual(
            traffic_command(approval(), approval()["rollback_revision"])[-2],
            "mobile-api-staging-baseline1=100",
        )

    def test_candidate_promotion_rollback_and_interrupted_recovery(self):
        commands = []

        def runner(arguments, _cwd):
            commands.append(list(arguments))
            if arguments[:3] == ["git", "status", "--porcelain"]:
                return CompletedProcess(arguments, 0, "", "")
            if arguments[:3] == ["git", "rev-parse", "HEAD"]:
                return CompletedProcess(arguments, 0, COMMIT, "")
            if arguments[:4] == ["gcloud", "run", "revisions", "describe"]:
                environment = [
                    {
                        "name": name,
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": reference.split(":", 1)[0],
                                "key": reference.split(":", 1)[1],
                            }
                        },
                    }
                    for name, reference in approval()["runtime_secret_refs"].items()
                ]
                environment.append(
                    {
                        "name": "MOBILE_API_AUDIENCE",
                        "value": approval()["mobile_api_audience"],
                    }
                )
                revision = {
                    "metadata": {
                        "name": approval()["candidate_revision"],
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
                        "imageDigest": DIGEST,
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "traffic": 0,
                    },
                }
                return CompletedProcess(arguments, 0, json.dumps(revision), "")
            if arguments[:4] == ["gcloud", "run", "services", "describe"]:
                target = (
                    approval()["candidate_revision"]
                    if any(
                        approval()["candidate_revision"] in part
                        for command in commands[-2:]
                        for part in command
                    )
                    else approval()["rollback_revision"]
                )
                service = {
                    "status": {
                        "traffic": [{"revisionName": target, "percent": 100}]
                    }
                }
                return CompletedProcess(arguments, 0, json.dumps(service), "")
            return CompletedProcess(arguments, 0, "{}", "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mobile = root / "apps" / "mobile_api"
            mobile.mkdir(parents=True)
            (mobile / ".dockerignore").write_text(
                ".env.yaml\n.env\n.env.*\n*.json\n*.pem\n*.key\n"
                "*approval*\n*state*\n__pycache__/\ntests/\n",
                encoding="utf-8",
            )
            artifact = root / "shared_lib" / "dist" / "shared_lib-0.0.1.tar.gz"
            artifact.parent.mkdir(parents=True)
            with tarfile.open(artifact, "w:gz") as archive:
                info = tarfile.TarInfo(
                    "shared_lib-0.0.1/shared_module/mobile_api.py"
                )
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))
            state_path = root / "private" / "state.json"
            candidate = execute(
                "candidate", approval(), DATABASE_URL, state_path, root, runner
            )
            self.assertEqual(candidate.phase, "candidate_ready")
            self.assertEqual(load_state(state_path), candidate)
            command_count = len(commands)
            recovered = execute(
                "recover", approval(), DATABASE_URL, state_path, root, runner
            )
            self.assertEqual(recovered.phase, "candidate_ready")
            recovery_commands = commands[command_count:]
            self.assertFalse(any(command[:2] == ["gcloud", "builds"] for command in recovery_commands))
            self.assertFalse(any(command[:3] == ["gcloud", "run", "deploy"] for command in recovery_commands))
            promoted = execute(
                "promote", approval(), DATABASE_URL, state_path, root, runner
            )
            self.assertEqual(promoted.phase, "promoted")
            rolled_back = execute(
                "rollback", approval(), DATABASE_URL, state_path, root, runner
            )
            self.assertEqual(rolled_back.phase, "rolled_back")
            self.assertTrue(any("--no-traffic" in command for command in commands))
            self.assertFalse((mobile / "dist" / artifact.name).exists())

    def test_state_refuses_unrelated_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            first = OperatorState(COMMIT, DIGEST, "candidate", "rollback", "candidate_ready")
            save_state(path, first)
            with self.assertRaises(OperatorError):
                save_state(
                    path,
                    OperatorState("c" * 40, DIGEST, "candidate", "rollback", "promoted"),
                )


if __name__ == "__main__":
    unittest.main()
