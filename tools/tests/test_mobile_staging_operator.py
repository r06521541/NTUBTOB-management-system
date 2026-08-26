from __future__ import annotations

import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, Mock, patch

from alembic import command
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from tools.mobile_staging_contract import (
    FORWARD_REVISIONS,
    PRODUCTION_PROJECT,
    REVISION,
    DatabaseIdentity,
    StagingContractError,
    load_approval,
    redacted_manifest,
)
from tools.mobile_staging_data import (
    EXPECTED_TABLES,
    NOTIFICATION_TABLES,
    REVISION_TABLES,
    _alembic_config,
    _bootstrap_empty_database,
    _classify_role_lifecycle,
    _database_state,
    _execute_officer_transition,
    _mobile_principal_state,
    _upgrade_known_database,
    attendance_repair_inventory,
)
from tools.mobile_staging_data import execute as execute_staging_data
from tools.mobile_staging_data import (
    execute_attendance_repair,
    execute_fixture_lifecycle_reset,
    execute_runtime_residue_repair,
    fixture_lifecycle_inventory,
    grant_officer,
    inventory,
)
from tools.mobile_staging_data import main as staging_data_main
from tools.mobile_staging_data import (
    mobile_principal_inventory,
    officer_inventory,
    plan,
    recover,
    restore_basic,
    runtime_residue_inventory,
)
from tools.mobile_staging_operator import (
    OperatorError,
    _traffic_is_exact,
    build_command,
    deploy_command,
    execute,
    normalize_digest,
    validate_build_context,
    validate_candidate,
)
from tools.mobile_staging_preflight import cloud_inventory, database_inventory
from tools.mobile_staging_seed import ANCHOR, FIXTURE_REPLY_AT
from tools.mobile_staging_seed import REVISION as SEED_REVISION
from tools.mobile_staging_seed import cleanup

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
TEST_DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL")


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
        "mobile_api_google_audiences": ("staging-web.apps.googleusercontent.com"),
    }


def database_approval(database_url: str) -> dict:
    value = approval()
    value["database_provider"] = "local"
    value["database_resource_id"] = "local-rehearsal"
    value["database_identity_sha256"] = DatabaseIdentity.from_url(
        database_url
    ).fingerprint
    value["production_database_identity_sha256"] = hashlib.sha256(
        b"separate-production-database"
    ).hexdigest()
    return value


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
    environment.append(
        {
            "name": "MOBILE_API_GOOGLE_AUDIENCES",
            "value": "staging-web.apps.googleusercontent.com",
        }
    )
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
        [
            {
                "revisionName": "mobile-api-staging-candidate1",
                "percent": 100,
            }
        ]
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
    def test_staging_revision_contract_matches_mobile_api_readiness(self):
        self.assertEqual(REVISION, "0008_mobile_notification_delivery")
        self.assertEqual(SEED_REVISION, REVISION)
        self.assertEqual(
            FORWARD_REVISIONS,
            (
                "0005_mobile_auth_api_foundation",
                "0006_staging_broker_operation_journal",
            ),
        )
        self.assertEqual(set(REVISION_TABLES), {*FORWARD_REVISIONS, REVISION})
        self.assertEqual(REVISION_TABLES[REVISION], EXPECTED_TABLES)
        self.assertEqual(
            NOTIFICATION_TABLES,
            {
                "mobile_notifications",
                "mobile_notification_recipients",
                "mobile_notification_publish_audits",
                "mobile_notification_deliveries",
                "mobile_device_registrations",
            },
        )

    def test_revision_specific_table_sets_and_unknown_revision_fail_closed(self):
        for revision_name, tables in REVISION_TABLES.items():
            with self.subTest(revision=revision_name):
                connection = Mock()
                connection.scalar.return_value = True
                connection.scalars.side_effect = [(revision_name,), tuple(tables)]
                with patch(
                    "tools.mobile_staging_data._canonical_fixture_fingerprint",
                    return_value=("clean", ("clean",)),
                ):
                    state = _database_state(connection)
                self.assertEqual(state["revision"], revision_name)
                self.assertEqual(
                    state["database_state"],
                    "ready" if revision_name == REVISION else "upgrade_pending",
                )

        unknown = Mock()
        unknown.scalar.return_value = True
        unknown.scalars.return_value = ("0007_mobile_notifications",)
        with self.assertRaisesRegex(StagingContractError, "revision is unknown"):
            _database_state(unknown)

        drifted = Mock()
        drifted.scalar.return_value = True
        drifted.scalars.side_effect = [
            (FORWARD_REVISIONS[0],),
            tuple(REVISION_TABLES[FORWARD_REVISIONS[0]] | {"unknown_table"}),
        ]
        with self.assertRaisesRegex(StagingContractError, "schema is partial"):
            _database_state(drifted)

    def test_read_only_preflight_classifies_current_and_forward_revisions(self):
        for revision_name in (*FORWARD_REVISIONS, REVISION):
            with self.subTest(revision=revision_name):
                connection = MagicMock()
                transaction = Mock()
                connection.begin.return_value = transaction
                connection.scalar.return_value = 0
                engine = MagicMock()
                engine.connect.return_value.__enter__.return_value = connection
                state = {
                    "revision": revision_name,
                    "database_state": (
                        "ready" if revision_name == REVISION else "upgrade_pending"
                    ),
                    "fixture_state": "clean",
                }
                with patch(
                    "tools.mobile_staging_preflight._database_state",
                    return_value=state,
                ):
                    result = database_inventory(
                        engine,
                        DATABASE_URL,
                        STAGING_HASH,
                        PRODUCTION_HASH,
                        PROVIDER,
                        RESOURCE,
                    )
                self.assertEqual(result["revision"], revision_name)
                self.assertEqual(
                    result["revision_state"],
                    "current" if revision_name == REVISION else "upgrade_pending",
                )
                transaction.rollback.assert_called_once_with()

        unknown = MagicMock()
        with self.assertRaisesRegex(StagingContractError, "not recognized"):
            with patch(
                "tools.mobile_staging_preflight._database_state",
                side_effect=StagingContractError(
                    "Staging database revision is not recognized"
                ),
            ):
                database_inventory(
                    unknown,
                    DATABASE_URL,
                    STAGING_HASH,
                    PRODUCTION_HASH,
                    PROVIDER,
                    RESOURCE,
                )

    def test_forward_upgrade_requires_exact_pre_and_post_state(self):
        connection = Mock()
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection
        prestate = {
            "revision": FORWARD_REVISIONS[0],
            "database_state": "upgrade_pending",
            "fixture_state": "seeded",
            "fixture_fingerprint": ("seeded", "same"),
        }
        poststate = {
            "revision": REVISION,
            "database_state": "ready",
            "fixture_state": "seeded",
            "fixture_fingerprint": ("seeded", "same"),
        }
        with patch(
            "tools.mobile_staging_data._database_state",
            side_effect=[prestate, poststate],
        ), patch(
            "tools.mobile_staging_data._alembic_config", return_value="config"
        ), patch(
            "tools.mobile_staging_data.command.upgrade"
        ) as upgrade:
            _upgrade_known_database(engine, Path.cwd(), FORWARD_REVISIONS[0], "seeded")
        upgrade.assert_called_once_with("config", REVISION)

        with self.assertRaisesRegex(StagingContractError, "not approved"):
            _upgrade_known_database(engine, Path.cwd(), REVISION, "seeded")

    def test_forward_upgrade_value_drift_makes_zero_upgrade_calls(self):
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = Mock()
        with patch(
            "tools.mobile_staging_data._database_state",
            side_effect=StagingContractError("fixture people are drifted"),
        ), patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "people are drifted"):
                _upgrade_known_database(
                    engine, Path.cwd(), FORWARD_REVISIONS[0], "seeded", "subject"
                )
        upgrade.assert_not_called()

    def test_forward_upgrade_table_drift_makes_zero_upgrade_calls(self):
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = Mock()
        with patch(
            "tools.mobile_staging_data._database_state",
            side_effect=StagingContractError("schema is partial or drifted"),
        ), patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "schema is partial"):
                _upgrade_known_database(
                    engine, Path.cwd(), FORWARD_REVISIONS[1], "clean", "subject"
                )
        upgrade.assert_not_called()

    def test_forward_upgrade_requires_unchanged_semantic_fingerprint(self):
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = Mock()
        before = {
            "revision": FORWARD_REVISIONS[0],
            "database_state": "upgrade_pending",
            "fixture_state": "seeded",
            "fixture_fingerprint": ("seeded", "before"),
        }
        after = {
            "revision": REVISION,
            "database_state": "ready",
            "fixture_state": "seeded",
            "fixture_fingerprint": ("seeded", "after"),
        }
        with patch(
            "tools.mobile_staging_data._database_state", side_effect=[before, after]
        ), patch(
            "tools.mobile_staging_data._alembic_config", return_value="config"
        ), patch(
            "tools.mobile_staging_data.command.upgrade"
        ) as upgrade:
            with self.assertRaisesRegex(StagingContractError, "postcheck failed"):
                _upgrade_known_database(
                    engine, Path.cwd(), FORWARD_REVISIONS[0], "seeded", "subject"
                )
        upgrade.assert_called_once_with("config", REVISION)

    def test_clean_legacy_value_drift_makes_zero_upgrade_calls(self):
        connection = Mock()
        connection.scalar.return_value = True
        connection.scalars.side_effect = [
            (FORWARD_REVISIONS[0],),
            tuple(REVISION_TABLES[FORWARD_REVISIONS[0]]),
        ]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection
        with patch(
            "tools.mobile_staging_data._fixture_state", return_value="clean"
        ), patch(
            "tools.mobile_staging_data._canonical_legacy_fingerprint",
            side_effect=StagingContractError("legacy ballparks are drifted"),
        ), patch(
            "tools.mobile_staging_data.command.upgrade"
        ) as upgrade:
            with self.assertRaisesRegex(StagingContractError, "ballparks are drifted"):
                _upgrade_known_database(
                    engine, Path.cwd(), FORWARD_REVISIONS[0], "clean", "subject"
                )
        upgrade.assert_not_called()

    def test_seeded_identity_timestamp_drift_makes_zero_upgrade_calls(self):
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = Mock()
        with patch(
            "tools.mobile_staging_data._database_state",
            side_effect=StagingContractError("fixture identities are drifted"),
        ), patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "identities are drifted"):
                _upgrade_known_database(
                    engine, Path.cwd(), FORWARD_REVISIONS[1], "seeded", "subject"
                )
        upgrade.assert_not_called()

    def test_role_lifecycle_accepts_legacy_and_later_generations(self):
        legacy_grant = {
            "id": -119001,
            "action": "access_changed",
            "actor_person_id": None,
            "target_person_id": -112001,
            "auth_identity_id": -112001,
            "before_state": {
                "access_level": "basic",
                "fixture": "TASK-112/TASK-118",
            },
            "after_state": {"access_level": "officer", "fixture": "TASK-119"},
            "reason": "TASK-119 fictional Officer grant",
            "request_id": "task-119-fictional-officer-grant",
        }
        legacy_restore = {
            "id": -119002,
            "action": "access_changed",
            "actor_person_id": None,
            "target_person_id": -112001,
            "auth_identity_id": -112001,
            "before_state": {"access_level": "officer", "fixture": "TASK-119"},
            "after_state": {
                "access_level": "basic",
                "fixture": "TASK-112/TASK-118",
            },
            "reason": "TASK-119 fictional Officer restore",
            "request_id": "task-119-fictional-officer-restore",
        }
        later_grant = {
            "id": 2,
            "action": "access_changed",
            "actor_person_id": None,
            "target_person_id": -112001,
            "auth_identity_id": -112001,
            "before_state": {
                "access_level": "basic",
                "fixture": "TASK-126",
                "version": 3,
            },
            "after_state": {
                "access_level": "officer",
                "fixture": "TASK-126",
                "version": 4,
            },
            "reason": "TASK-126 fictional fixture lifecycle grant",
            "request_id": "task-126-fixture-lifecycle-v3-grant",
        }
        later_restore = {
            "id": 3,
            "action": "access_changed",
            "actor_person_id": None,
            "target_person_id": -112001,
            "auth_identity_id": -112001,
            "before_state": {
                "access_level": "officer",
                "fixture": "TASK-126",
                "version": 4,
            },
            "after_state": {
                "access_level": "basic",
                "fixture": "TASK-126",
                "version": 5,
            },
            "reason": "TASK-126 fictional fixture lifecycle restore",
            "request_id": "task-126-fixture-lifecycle-v4-restore",
        }

        cases = (
            ({"portal_access_level": "basic", "version": 1}, [], "baseline"),
            (
                {"portal_access_level": "officer", "version": 2},
                [legacy_grant],
                "granted",
            ),
            (
                {"portal_access_level": "basic", "version": 3},
                [legacy_grant, legacy_restore],
                "restored",
            ),
            (
                {"portal_access_level": "officer", "version": 4},
                [legacy_grant, legacy_restore, later_grant],
                "granted",
            ),
            (
                {"portal_access_level": "basic", "version": 5},
                [legacy_grant, legacy_restore, later_grant, later_restore],
                "restored",
            ),
        )
        for person, audits, expected in cases:
            with self.subTest(version=person["version"]):
                self.assertEqual(_classify_role_lifecycle(person, audits), expected)

        invalid = dict(later_grant, request_id="task-126-wrong")
        with self.assertRaisesRegex(StagingContractError, "lifecycle audit"):
            _classify_role_lifecycle(
                {"portal_access_level": "officer", "version": 4},
                [legacy_grant, legacy_restore, invalid],
            )
        invalid = dict(later_restore, before_state={"access_level": "officer"})
        with self.assertRaisesRegex(StagingContractError, "lifecycle audit"):
            _classify_role_lifecycle(
                {"portal_access_level": "basic", "version": 5},
                [legacy_grant, legacy_restore, later_grant, invalid],
            )
        for invalid_chain in (
            [legacy_restore, legacy_grant],
            [legacy_grant, legacy_grant],
            [legacy_grant, legacy_restore, later_grant, later_grant],
        ):
            with self.subTest(invalid_chain=invalid_chain):
                with self.assertRaisesRegex(StagingContractError, "lifecycle audit"):
                    _classify_role_lifecycle(
                        {"portal_access_level": "basic", "version": 5},
                        invalid_chain,
                    )

    def test_fixture_lifecycle_reset_requires_candidate_approval(self):
        with self.assertRaisesRegex(StagingContractError, "candidate approval"):
            execute_fixture_lifecycle_reset(
                approval(phase="build"), DATABASE_URL, "fake-private-subject"
            )

    def test_fixture_lifecycle_cli_is_mutually_exclusive_and_redacted(self):
        private_subject = "fake-private-fixture-subject"
        result = {"database_identity_sha256": STAGING_HASH, "state": "ready_basic"}
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval()), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "MOBILE_STAGING_DATABASE_URL": DATABASE_URL,
                    "MOBILE_STAGING_PROVIDER_SUBJECT": private_subject,
                },
                clear=False,
            ), patch(
                "tools.mobile_staging_data.fixture_lifecycle_inventory",
                return_value=result,
            ), patch(
                "sys.stdout", new_callable=io.StringIO
            ) as output:
                self.assertEqual(
                    staging_data_main(
                        [
                            "--approval",
                            str(approval_path),
                            "--inspect-fixture-lifecycle",
                        ]
                    ),
                    0,
                )
                self.assertEqual(json.loads(output.getvalue()), result)
                self.assertNotIn(private_subject, output.getvalue())
                self.assertEqual(
                    staging_data_main(
                        [
                            "--approval",
                            str(approval_path),
                            "--inspect-fixture-lifecycle",
                            "--reset-fixture-lifecycle",
                        ]
                    ),
                    2,
                )

    def test_mobile_principal_states_are_mutually_exclusive_and_exhaustive(self):
        person = {
            "portal_access_level": "officer",
            "portal_status": "active",
            "version": 2,
        }
        cases = (
            ("no_active_sessions", (0, 0, 0, 0)),
            ("expected_only", (2, 2, 0, 0)),
            ("mixed_principals", (3, 2, 0, 1)),
            ("other_only", (2, 0, 0, 2)),
            ("binding_drift", (2, 1, 1, 0)),
        )
        for expected_state, counts in cases:
            with self.subTest(state=expected_state):
                result = _mobile_principal_state(
                    person,
                    dict(
                        zip(
                            (
                                "total",
                                "expected_tuple",
                                "expected_person_binding_mismatch",
                                "other_principal",
                            ),
                            counts,
                        )
                    ),
                )
                self.assertEqual(result["state"], expected_state)
                self.assertTrue(result["expected_person_match"])
        with self.assertRaisesRegex(StagingContractError, "not exhaustive"):
            _mobile_principal_state(
                person,
                {
                    "total": 2,
                    "expected_tuple": 1,
                    "expected_person_binding_mismatch": 0,
                    "other_principal": 0,
                },
            )

    def test_mobile_principal_role_status_and_version_must_all_match(self):
        sessions = {
            "total": 1,
            "expected_tuple": 1,
            "expected_person_binding_mismatch": 0,
            "other_principal": 0,
        }
        for person in (
            None,
            {
                "portal_access_level": "basic",
                "portal_status": "active",
                "version": 2,
            },
            {
                "portal_access_level": "officer",
                "portal_status": "disabled",
                "version": 2,
            },
            {
                "portal_access_level": "officer",
                "portal_status": "active",
                "version": 3,
            },
        ):
            with self.subTest(person=person):
                self.assertFalse(
                    _mobile_principal_state(person, sessions)["expected_person_match"]
                )

    def test_mobile_principal_inventory_requires_candidate_and_redacts_errors(self):
        with self.assertRaisesRegex(StagingContractError, "candidate approval"):
            mobile_principal_inventory(approval(phase="build"), DATABASE_URL)
        engine = Mock()
        engine.connect.side_effect = SQLAlchemyError(DATABASE_URL)
        with patch("tools.mobile_staging_data.create_engine", return_value=engine):
            with self.assertRaisesRegex(
                StagingContractError, "inventory failed safely"
            ) as caught:
                mobile_principal_inventory(approval(), DATABASE_URL)
        self.assertNotIn("fake-password", str(caught.exception))
        engine.dispose.assert_called_once()

    def test_mobile_principal_cli_is_subject_free_and_output_is_aggregate_only(self):
        forbidden = (
            "session_id",
            "provider_subject",
            "installation",
            "token",
            "attempt",
            "assertion",
            "idempotency",
            "hash",
            "encrypted",
        )
        result = {
            "state": "expected_only",
            "expected_person_match": True,
            "expected_person": {
                "access_level": "officer",
                "status": "active",
                "version": 2,
            },
            "active_sessions": {
                "total": 2,
                "expected_tuple": 2,
                "expected_person_binding_mismatch": 0,
                "other_principal": 0,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval()), encoding="utf-8")
            with patch.dict(
                os.environ,
                {"MOBILE_STAGING_DATABASE_URL": DATABASE_URL},
                clear=True,
            ), patch(
                "tools.mobile_staging_data.mobile_principal_inventory",
                return_value=result,
            ) as inventory_mock, patch(
                "sys.stdout", new_callable=io.StringIO
            ) as output:
                self.assertEqual(
                    staging_data_main(
                        [
                            "--approval",
                            str(approval_path),
                            "--inspect-mobile-principal",
                        ]
                    ),
                    0,
                )
        inventory_mock.assert_called_once_with(approval(), DATABASE_URL)
        encoded = output.getvalue().lower()
        for value in forbidden:
            self.assertNotIn(value, encoded)
        source = inspect.getsource(mobile_principal_inventory).lower()
        for value in (
            "session_id",
            "installation_id",
            "token_hash",
            "attempt_id",
            "assertion_hash",
            "idempotency",
            "encrypted_successor",
            "provider_subject",
        ):
            self.assertNotIn(value, source)

    def test_database_identity_rejects_surrounding_database_whitespace(self):
        for database in ("%20postgres", "postgres%20"):
            with self.subTest(database=database), self.assertRaisesRegex(
                StagingContractError, "Database target is malformed"
            ):
                DatabaseIdentity.from_url(
                    f"postgresql://user:password@staging-db.invalid:5432/{database}",
                    PROVIDER,
                    RESOURCE,
                )

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
        self.assertEqual(manifest["revision"], REVISION)

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

    def test_google_audience_allowlist_is_bounded_exact_and_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approval.json"
            for invalid in (
                "",
                "not-a-google-client",
                "a.apps.googleusercontent.com," * 5,
                "duplicate.apps.googleusercontent.com,duplicate.apps.googleusercontent.com",
            ):
                value = approval()
                value["mobile_api_google_audiences"] = invalid
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(invalid=invalid):
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
                "database_state": "ready",
                "revision": REVISION,
                "fixture_state": "seeded",
            },
        ):
            self.assertEqual(recover(approval(), DATABASE_URL)["outcome"], "completed")

    def test_remote_inventory_errors_are_redacted(self):
        engine = Mock()
        engine.connect.side_effect = SQLAlchemyError(DATABASE_URL)
        with patch("tools.mobile_staging_data.create_engine", return_value=engine):
            with self.assertRaisesRegex(
                StagingContractError, "inventory failed safely"
            ) as caught:
                inventory(approval(), DATABASE_URL)
        self.assertNotIn("fake-password", str(caught.exception))
        engine.dispose.assert_called_once()

    def test_attendance_repair_requires_exact_candidate_state(self):
        with patch(
            "tools.mobile_staging_data.attendance_repair_inventory",
            return_value={
                "database_identity_sha256": STAGING_HASH,
                "state": "required",
                "hidden_rows": 1,
            },
        ):
            with self.assertRaisesRegex(StagingContractError, "not exact"):
                execute_attendance_repair(approval(), DATABASE_URL)

    def test_officer_transition_retries_only_its_exact_terminal_state(self):
        granted = {"database_identity_sha256": STAGING_HASH, "state": "granted"}
        with patch("tools.mobile_staging_data.officer_inventory", return_value=granted):
            self.assertEqual(
                grant_officer(approval(), DATABASE_URL, "fake-private-subject"),
                {**granted, "changed": False},
            )
        with patch(
            "tools.mobile_staging_data.officer_inventory",
            return_value={
                "database_identity_sha256": STAGING_HASH,
                "state": "baseline",
            },
        ):
            with self.assertRaisesRegex(StagingContractError, "not exact"):
                restore_basic(approval(), DATABASE_URL, "fake-private-subject")

    def test_officer_transition_requires_candidate_approval(self):
        with self.assertRaisesRegex(StagingContractError, "candidate approval"):
            _execute_officer_transition(
                approval(phase="build"), DATABASE_URL, "fake-private-subject", "grant"
            )

    def test_officer_transition_requires_private_subject_before_any_read(self):
        with patch("tools.mobile_staging_data.officer_inventory") as inventory_mock:
            with self.assertRaisesRegex(StagingContractError, "Private tester input"):
                grant_officer(approval(), DATABASE_URL, "")
        inventory_mock.assert_not_called()

    def test_officer_cli_redacts_private_subject_from_output(self):
        private_subject = "fake-private-tester-subject"
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval()), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "MOBILE_STAGING_DATABASE_URL": DATABASE_URL,
                    "MOBILE_STAGING_PROVIDER_SUBJECT": private_subject,
                },
                clear=False,
            ), patch(
                "tools.mobile_staging_data.officer_inventory",
                return_value={
                    "database_identity_sha256": STAGING_HASH,
                    "state": "baseline",
                },
            ), patch(
                "sys.stdout", new_callable=io.StringIO
            ) as output:
                self.assertEqual(
                    staging_data_main(
                        ["--approval", str(approval_path), "--inspect-officer"]
                    ),
                    0,
                )
        self.assertNotIn(private_subject, output.getvalue())

    def test_runtime_residue_cli_redacts_private_subject_from_output(self):
        private_subject = "fake-private-tester-subject"
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval()), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "MOBILE_STAGING_DATABASE_URL": DATABASE_URL,
                    "MOBILE_STAGING_PROVIDER_SUBJECT": private_subject,
                },
                clear=False,
            ), patch(
                "tools.mobile_staging_data.runtime_residue_inventory",
                return_value={
                    "database_identity_sha256": STAGING_HASH,
                    "state": "required",
                    "residue_rows": 2,
                },
            ), patch(
                "sys.stdout", new_callable=io.StringIO
            ) as output:
                self.assertEqual(
                    staging_data_main(
                        ["--approval", str(approval_path), "--inspect-runtime-residue"]
                    ),
                    0,
                )
        self.assertNotIn(private_subject, output.getvalue())

    def test_runtime_residue_repair_requires_candidate_approval(self):
        with self.assertRaisesRegex(StagingContractError, "candidate approval"):
            execute_runtime_residue_repair(
                approval(phase="build"), DATABASE_URL, "fake-private-subject"
            )

    def test_generic_plan_does_not_require_private_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval()), encoding="utf-8")
            with patch.dict(
                os.environ,
                {"MOBILE_STAGING_DATABASE_URL": DATABASE_URL},
                clear=True,
            ), patch(
                "tools.mobile_staging_data.plan",
                return_value={"mutation": "none-dry-run"},
            ), patch(
                "sys.stdout", new_callable=io.StringIO
            ):
                self.assertEqual(
                    staging_data_main(["--approval", str(approval_path)]), 0
                )

    def test_plain_alembic_cli_keeps_remote_database_gate(self):
        environment = dict(os.environ)
        environment["PORTAL_DATA_DATABASE_URL"] = DATABASE_URL
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            cwd=Path.cwd(),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("isolated local database", output)
        self.assertNotIn("fake-password", output)

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
    def test_staging_build_uses_cloud_logging_for_user_specified_service_account(
        self,
    ):
        configuration = Path("apps/mobile_api/cloudbuild.staging.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("options:\n  logging: CLOUD_LOGGING_ONLY\n", configuration)
        self.assertNotIn("logsBucket:", configuration)
        self.assertNotIn("GCS_ONLY", configuration)

    def test_build_and_candidate_are_separate_and_scoped(self):
        build = build_command(approval(phase="build"))
        update_deploy = deploy_command(approval())
        bootstrap_deploy = deploy_command(approval(mode="bootstrap"))
        self.assertIn(
            "projects/ntubtob-mobile-staging/serviceAccounts/"
            + approval()["build_service_account"],
            build,
        )
        self.assertNotIn("run", build)
        self.assertNotIn("builds", update_deploy)
        self.assertIn("--no-traffic", update_deploy)
        self.assertNotIn("--no-traffic", bootstrap_deploy)
        self.assertNotIn("--no-allow-unauthenticated", update_deploy)
        self.assertIn("--no-allow-unauthenticated", bootstrap_deploy)
        self.assertIn("--ingress", bootstrap_deploy)
        self.assertIn("--min-instances", bootstrap_deploy)
        self.assertIn("--max-instances", bootstrap_deploy)
        env_value = update_deploy[update_deploy.index("--set-env-vars") + 1]
        self.assertTrue(env_value.startswith("^|^"))
        self.assertIn("MOBILE_API_AUDIENCE=1234567890", env_value)
        self.assertIn(
            "MOBILE_API_GOOGLE_AUDIENCES=staging-web.apps.googleusercontent.com",
            env_value,
        )
        multiple = approval()
        multiple["mobile_api_google_audiences"] = (
            "android.apps.googleusercontent.com,web.apps.googleusercontent.com"
        )
        multiple_env = deploy_command(multiple)[
            deploy_command(multiple).index("--set-env-vars") + 1
        ]
        self.assertIn(
            "MOBILE_API_GOOGLE_AUDIENCES="
            "android.apps.googleusercontent.com,web.apps.googleusercontent.com",
            multiple_env,
        )
        self.assertNotIn("--min", bootstrap_deploy)
        self.assertNotIn("--max", bootstrap_deploy)

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
        drifted = revision()
        next(
            item
            for item in drifted["spec"]["containers"][0]["env"]
            if item["name"] == "MOBILE_API_GOOGLE_AUDIENCES"
        )["value"] = "other.apps.googleusercontent.com"
        with self.assertRaisesRegex(OperatorError, "Google audience"):
            validate_candidate(approval(), drifted, service())
        update_with_retained_candidate = service()
        update_with_retained_candidate["status"]["traffic"].append(
            {"revisionName": "mobile-api-staging-candidate1", "percent": 0}
        )
        validate_candidate(approval(), revision(), update_with_retained_candidate)
        with self.assertRaises(OperatorError):
            validate_candidate(approval(), revision(), service(candidate_percent=100))
        with self.assertRaises(OperatorError):
            validate_candidate(
                approval(mode="bootstrap"),
                revision(IMAGE + "@" + DIGEST),
                {**service("bootstrap"), "status": {"traffic": []}},
            )

    def test_traffic_convergence_allows_only_the_known_zero_percent_peer(self):
        candidate = "mobile-api-staging-candidate1"
        baseline = "mobile-api-staging-baseline1"
        self.assertTrue(
            _traffic_is_exact(
                [
                    {"revisionName": candidate, "percent": 100},
                    {"revisionName": baseline, "percent": 0},
                ],
                candidate,
                {baseline},
            )
        )
        for traffic in (
            [
                {"revisionName": candidate, "percent": 100},
                {"revisionName": baseline, "percent": 1},
            ],
            [
                {"revisionName": candidate, "percent": 100},
                {"revisionName": "mobile-api-staging-unknown", "percent": 0},
            ],
            [
                {"revisionName": candidate, "percent": 100},
                {"revisionName": candidate, "percent": 0},
            ],
            [
                {
                    "revisionName": candidate,
                    "percent": 100,
                    "latestRevision": True,
                },
                {"revisionName": baseline, "percent": 0},
            ],
            [
                {
                    "revisionName": candidate,
                    "percent": 100,
                    "tag": "candidate-tag",
                },
                {"revisionName": baseline, "percent": 0},
            ],
            [
                {"revisionName": candidate, "percent": 100},
                {
                    "revisionName": baseline,
                    "percent": 0,
                    "url": "https://tagged.invalid",
                },
            ],
        ):
            with self.subTest(traffic=traffic):
                self.assertFalse(_traffic_is_exact(traffic, candidate, {baseline}))

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


@unittest.skipUnless(TEST_DATABASE_URL, "isolated PostgreSQL URL is required")
class EmptyDatabaseBootstrapIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL)
        cls.approval = database_approval(TEST_DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        _bootstrap_empty_database(self.engine, Path.cwd())

    def _downgrade_current_schema(self, revision):
        _bootstrap_empty_database(self.engine, Path.cwd())
        with self.engine.begin() as connection:
            command.downgrade(_alembic_config(Path.cwd(), connection), revision)

    def _seed_mobile_runtime_history(
        self,
        *,
        cross_principal=False,
        session_id="task120-fixture-session",
        identity_id=-112001,
        exchange_provider="line",
    ):
        person_id = 1 if cross_principal else -112001
        label = session_id.rsplit("-", 1)[-1]
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions "
                    "(id, auth_identity_id, person_id, installation_id_hash, platform, "
                    "status, access_epoch, refresh_family_expires_at, revoked_at, "
                    "created_at, updated_at) VALUES "
                    "(:session, :identity, :person, :installation, "
                    "'android', 'revoked', 1, '2030-01-02T00:00:00Z', "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', "
                    "'2030-01-01T00:00:00Z')"
                ),
                {
                    "session": session_id,
                    "identity": identity_id,
                    "person": person_id,
                    "installation": f"fake-installation-{label}",
                },
            )

            for number in range(8):
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.mobile_refresh_tokens "
                        "(session_id, token_hash, generation, status, issued_at, "
                        "expires_at, revoked_at) VALUES "
                        "(:session, :token, :generation, 'revoked', "
                        "'2030-01-01T00:00:00Z', '2030-01-02T00:00:00Z', "
                        "'2030-01-01T00:00:00Z')"
                    ),
                    {
                        "session": session_id,
                        "token": f"fake-refresh-{label}-{number}",
                        "generation": number + 1,
                    },
                )
            for number in range(7):
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.mobile_refresh_attempts "
                        "(session_id, attempt_id_hash, request_hash, encrypted_successor, "
                        "expires_at, created_at) VALUES "
                        "(:session, :attempt, :request, :payload, "
                        "'2030-01-02T00:00:00Z', '2030-01-01T00:00:00Z')"
                    ),
                    {
                        "session": session_id,
                        "attempt": f"fake-attempt-{label}-{number}",
                        "request": f"fake-request-{label}-{number}",
                        "payload": b"fake-test-payload",
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_auth_exchanges "
                    "(provider, assertion_hash, login_attempt_hash, session_id, "
                    "expires_at, created_at) VALUES "
                    "(:provider, :assertion, :attempt, :session, "
                    "'2030-01-02T00:00:00Z', "
                    "'2030-01-01T00:00:00Z')"
                ),
                {
                    "assertion": f"fake-assertion-{label}",
                    "attempt": f"fake-login-attempt-{label}",
                    "provider": exchange_provider,
                    "session": session_id,
                },
            )
            for number in range(2):
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.mobile_idempotency_records "
                        "(session_id, person_id, method, route, key_hash, request_hash, "
                        "state, response_status, response_body, expires_at, created_at, "
                        "updated_at) VALUES "
                        "(:session, :person, 'PUT', '/api/v1/fake', "
                        ":key, :request, 'completed', 200, '{}'::json, "
                        "'2030-01-02T00:00:00Z', '2030-01-01T00:00:00Z', "
                        "'2030-01-01T00:00:00Z')"
                    ),
                    {
                        "person": person_id,
                        "session": session_id,
                        "key": f"fake-key-{label}-{number}",
                        "request": f"fake-idempotency-request-{label}-{number}",
                    },
                )

    def _seed_google_recovery_history(self):
        subject = "fake-google-recovery-subject"
        pending_request = (
            "identity-pending-"
            + hashlib.sha256(f"google:{subject}".encode("utf-8")).hexdigest()[:32]
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(id, provider, provider_subject, person_id, status, created_at, "
                    "updated_at) VALUES (-112004, 'google', :subject, -112001, "
                    "'linked', '2029-12-31T23:59:58Z', '2029-12-31T23:59:59Z')"
                ),
                {"subject": subject},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.identity_review_threads "
                    "(id, auth_identity_id, status, last_applicant_message_at, "
                    "last_activity_at, closed_at, redacted_at, created_at, updated_at) "
                    "VALUES (-157001, -112004, 'closed', NULL, "
                    "'2029-12-31T23:59:59Z', '2029-12-31T23:59:59Z', NULL, "
                    "'2029-12-31T23:59:58Z', '2029-12-31T23:59:59Z')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.access_audit "
                    "(id, action, actor_person_id, target_person_id, auth_identity_id, "
                    "before_state, after_state, reason, request_id, created_at) VALUES "
                    "(-157001, 'identity_pending', NULL, NULL, -112004, NULL, "
                    '\'{"status": "pending"}\'::json, '
                    "'Google identity awaiting self-link confirmation', :pending, "
                    "'2029-12-31T23:59:58Z'), "
                    "(-157002, 'identity_linked', -112001, -112001, -112004, "
                    '\'{"status": "pending"}\'::json, '
                    '\'{"status": "linked", "source_provider": "line", '
                    '"target_provider": "google", '
                    '"outcome": "recovery_link"}\'::json, '
                    "'Self-service cross-provider identity link', "
                    "'identity-self-link-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                    "'2029-12-31T23:59:59Z')"
                ),
                {"pending": pending_request},
            )
        self._seed_mobile_runtime_history(
            session_id="task157-google-recovery-session",
            identity_id=-112001,
            exchange_provider="google",
        )

    def _insert_runtime_residue(self, *, near_miss=False, additional=False):
        first_timestamp = (
            "2026-08-19T16:33:02.723957Z"
            if near_miss
            else "2026-08-19T16:33:02.723958Z"
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(id, game_id, user_id, member_id, person_id, reply, updated_at) "
                    "VALUES (3, -112001, NULL, NULL, -112001, 5, :first), "
                    "(4, -112001, NULL, NULL, -112001, 1, "
                    "'2026-08-19T16:36:23.695486Z')"
                ),
                {"first": first_timestamp},
            )
            if additional:
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.game_attendance_replies "
                        "(id, game_id, person_id, reply, updated_at) VALUES "
                        "(5, -112001, -112001, 1, '2026-08-19T16:36:24Z')"
                    )
                )

    def _mobile_history_snapshot(self):
        with self.engine.connect() as connection:
            return {
                table: connection.execute(
                    text(f"SELECT * FROM ntubtob.{table} ORDER BY id")
                ).all()
                for table in (
                    "mobile_sessions",
                    "mobile_refresh_tokens",
                    "mobile_refresh_attempts",
                    "mobile_auth_exchanges",
                    "mobile_idempotency_records",
                )
            }

    def _seed_terminal_broker_history(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.staging_broker_operations "
                    "(operation_id, operation, target_state, inspect_fingerprint, "
                    "lifecycle_state, inspected_at, confirmed_at, "
                    "mutation_issued_at, completed_at, created_at, updated_at) "
                    "VALUES ('task157-terminal-operation', 'grant', "
                    "'ready_officer', :fingerprint, 'postcheck_complete', "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:01Z', "
                    "'2030-01-01T00:00:02Z', '2030-01-01T00:00:03Z', "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:03Z')"
                ),
                {"fingerprint": "a" * 64},
            )

    def _broker_history_snapshot(self):
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT * FROM ntubtob.staging_broker_operations "
                    "ORDER BY operation_id"
                )
            ).all()

    def _grant_officer_with_mobile_history(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        grant_officer(self.approval, TEST_DATABASE_URL, "fake-private-tester-subject")

    def _assert_officer_state_unchanged(self):
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT portal_access_level, version FROM ntubtob.people "
                        "WHERE id=-112001"
                    )
                ).one(),
                ("officer", 2),
            )

    def _insert_principal_session(
        self, session_id, person_id, identity_id, *, status="active"
    ):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_sessions "
                    "(id, auth_identity_id, person_id, installation_id_hash, platform, "
                    "status, access_epoch, refresh_family_expires_at, revoked_at, "
                    "created_at, updated_at) VALUES "
                    "(:session, :identity, :person, :installation, 'android', "
                    ":status, 1, '2030-01-02T00:00:00Z', :revoked_at, "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z')"
                ),
                {
                    "session": session_id,
                    "identity": identity_id,
                    "person": person_id,
                    "installation": f"fake-installation-{session_id}",
                    "status": status,
                    "revoked_at": (
                        "2030-01-01T00:00:00Z" if status == "revoked" else None
                    ),
                },
            )

    def _prepare_granted_principal_fixture(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        grant_officer(self.approval, TEST_DATABASE_URL, "fake-private-tester-subject")

    def test_mobile_principal_inventory_classifies_active_sessions_without_writes(self):
        self._prepare_granted_principal_fixture()
        empty = mobile_principal_inventory(self.approval, TEST_DATABASE_URL)
        self.assertEqual(empty["state"], "no_active_sessions")
        self.assertTrue(empty["expected_person_match"])

        self._insert_principal_session("expected-one", -112001, -112001)
        self._insert_principal_session("expected-two", -112001, -112001)
        self._insert_principal_session(
            "revoked-other", -112003, -112003, status="revoked"
        )
        with self.engine.connect() as connection:
            before = connection.execute(
                text(
                    "SELECT id, auth_identity_id, person_id, status, access_epoch, "
                    "created_at, updated_at FROM ntubtob.mobile_sessions ORDER BY id"
                )
            ).all()
        expected = mobile_principal_inventory(self.approval, TEST_DATABASE_URL)
        self.assertEqual(expected["state"], "expected_only")
        self.assertEqual(
            expected["active_sessions"],
            {
                "total": 2,
                "expected_tuple": 2,
                "expected_person_binding_mismatch": 0,
                "other_principal": 0,
            },
        )
        with self.engine.connect() as connection:
            after = connection.execute(
                text(
                    "SELECT id, auth_identity_id, person_id, status, access_epoch, "
                    "created_at, updated_at FROM ntubtob.mobile_sessions ORDER BY id"
                )
            ).all()
        self.assertEqual(after, before)

        self._insert_principal_session("other-one", -112002, -112002)
        mixed = mobile_principal_inventory(self.approval, TEST_DATABASE_URL)
        self.assertEqual(mixed["state"], "mixed_principals")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_sessions SET status='revoked', "
                    "revoked_at='2030-01-01T00:00:00Z' "
                    "WHERE person_id=-112001"
                )
            )
        other = mobile_principal_inventory(self.approval, TEST_DATABASE_URL)
        self.assertEqual(other["state"], "other_only")

    def test_mobile_principal_inventory_reports_binding_drift(self):
        self._prepare_granted_principal_fixture()
        self._insert_principal_session("binding-drift", -112001, -112002)
        result = mobile_principal_inventory(self.approval, TEST_DATABASE_URL)
        self.assertEqual(result["state"], "binding_drift")
        self.assertEqual(
            result["active_sessions"],
            {
                "total": 1,
                "expected_tuple": 0,
                "expected_person_binding_mismatch": 1,
                "other_principal": 0,
            },
        )

    def test_true_empty_bootstrap_injected_migration_seed_recover_and_cleanup(self):
        before = recover(self.approval, TEST_DATABASE_URL)
        self.assertEqual(before["outcome"], "not_started")
        self.assertIsNone(before["revision"])

        result = execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["revision"], REVISION)

        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.members")), 2
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT id, person_id FROM ntubtob.members ORDER BY id")
                ).all(),
                [(9201, 1), (9202, None)],
            )
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.people")), 4
            )

        cleanup(self.engine, "fake-private-tester-subject")
        cleaned = recover(self.approval, TEST_DATABASE_URL)
        self.assertEqual(cleaned["outcome"], "seed_pending")
        self.assertEqual(cleaned["fixture_state"], "clean")

    def test_unknown_rows_fail_recovery_without_retry(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.ballparks (id, name) "
                    "VALUES (999999, 'unknown drift')"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "drifted"):
            recover(self.approval, TEST_DATABASE_URL)

    def test_failed_migration_transaction_recovers_as_empty(self):
        with patch(
            "tools.mobile_staging_data.command.upgrade",
            side_effect=CommandError("fake migration failure"),
        ):
            with self.assertRaisesRegex(
                StagingContractError, "bootstrap failed safely"
            ):
                _bootstrap_empty_database(self.engine, Path.cwd())
        state = recover(self.approval, TEST_DATABASE_URL)
        self.assertEqual(state["outcome"], "not_started")
        self.assertEqual(state["database_state"], "empty")

    def test_exact_0005_and_0006_forward_upgrade_preserve_fixture_state(self):
        for previous_revision in FORWARD_REVISIONS:
            with self.subTest(previous_revision=previous_revision):
                with self.engine.begin() as connection:
                    connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
                self._downgrade_current_schema(previous_revision)
                before = recover(self.approval, TEST_DATABASE_URL)
                self.assertEqual(before["outcome"], "upgrade_pending")
                self.assertEqual(before["revision"], previous_revision)
                self.assertEqual(before["fixture_state"], "clean")

                result = execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
                self.assertEqual(result["outcome"], "completed")
                self.assertEqual(result["revision"], REVISION)

    def test_exact_0006_forward_upgrade_preserves_seeded_fixture(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
        before = recover(self.approval, TEST_DATABASE_URL)
        self.assertEqual(before["outcome"], "upgrade_pending")
        self.assertEqual(before["fixture_state"], "seeded")

        after = execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self.assertEqual(after["outcome"], "completed")
        self.assertEqual(after["revision"], REVISION)
        self.assertEqual(after["fixture_state"], "seeded")

    def test_forward_upgrade_preserves_restored_officer_lifecycle(self):
        for previous_revision in FORWARD_REVISIONS:
            with self.subTest(previous_revision=previous_revision):
                with self.engine.begin() as connection:
                    connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
                _bootstrap_empty_database(self.engine, Path.cwd())
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
                grant_officer(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                )
                restore_basic(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                )
                with self.engine.begin() as connection:
                    command.downgrade(
                        _alembic_config(Path.cwd(), connection), previous_revision
                    )
                with self.engine.connect() as connection:
                    audits_before = connection.execute(
                        text("SELECT * FROM ntubtob.access_audit ORDER BY id")
                    ).all()
                    tester_updated_at_before = connection.scalar(
                        text(
                            "SELECT updated_at FROM ntubtob.people " "WHERE id=-112001"
                        )
                    )

                before = recover(self.approval, TEST_DATABASE_URL)
                self.assertEqual(before["outcome"], "upgrade_pending")
                self.assertEqual(before["revision"], previous_revision)
                after = execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
                self.assertEqual(after["outcome"], "completed")
                with self.engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(
                            text("SELECT * FROM ntubtob.access_audit ORDER BY id")
                        ).all(),
                        audits_before,
                    )
                    self.assertEqual(
                        connection.execute(
                            text(
                                "SELECT portal_access_level, version FROM "
                                "ntubtob.people WHERE id=-112001"
                            )
                        ).one(),
                        ("basic", 3),
                    )
                    self.assertEqual(
                        connection.scalar(
                            text(
                                "SELECT updated_at FROM ntubtob.people "
                                "WHERE id=-112001"
                            )
                        ),
                        tester_updated_at_before,
                    )

    def test_forward_upgrade_rejects_unknown_access_audit_before_alembic(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.access_audit "
                    "(action, before_state, after_state, reason, request_id, "
                    "created_at) VALUES ('access_changed', '{}'::json, '{}'::json, "
                    "'unknown drift', 'task-157-unknown-drift', now())"
                )
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "access_audit"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_forward_upgrade_rejects_tester_timestamp_without_matching_audit(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        grant_officer(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET updated_at=updated_at + "
                    "interval '1 second' WHERE id=-112001"
                )
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "people are drifted"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_forward_upgrade_preserves_active_officer_lifecycle(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        grant_officer(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
        after = execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self.assertEqual(after["outcome"], "completed")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT portal_access_level, version FROM "
                        "ntubtob.people WHERE id=-112001"
                    )
                ).one(),
                ("officer", 2),
            )

    def test_forward_upgrade_preserves_exact_mobile_history(self):
        for previous_revision in FORWARD_REVISIONS:
            with self.subTest(previous_revision=previous_revision):
                with self.engine.begin() as connection:
                    connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
                _bootstrap_empty_database(self.engine, Path.cwd())
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
                self._seed_mobile_runtime_history()
                with self.engine.begin() as connection:
                    command.downgrade(
                        _alembic_config(Path.cwd(), connection), previous_revision
                    )
                mobile_before = self._mobile_history_snapshot()

                before = recover(self.approval, TEST_DATABASE_URL)
                self.assertEqual(before["outcome"], "upgrade_pending")
                self.assertEqual(before["revision"], previous_revision)
                after = execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
                self.assertEqual(after["outcome"], "completed")
                self.assertEqual(self._mobile_history_snapshot(), mobile_before)

    def test_forward_upgrade_rejects_cross_principal_mobile_history(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history(cross_principal=True)
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "mobile history"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_0006_forward_upgrade_preserves_terminal_broker_history(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
        self._seed_terminal_broker_history()
        broker_before = self._broker_history_snapshot()

        before = recover(self.approval, TEST_DATABASE_URL)
        self.assertEqual(before["outcome"], "upgrade_pending")
        after = execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self.assertEqual(after["outcome"], "completed")
        self.assertEqual(self._broker_history_snapshot(), broker_before)

    def test_forward_upgrade_rejects_nonterminal_broker_history(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.staging_broker_operations "
                    "(operation_id, operation, target_state, inspect_fingerprint, "
                    "lifecycle_state, inspected_at, created_at, updated_at) "
                    "VALUES ('task157-pending-operation', 'inspect', "
                    "'ready_basic', :fingerprint, 'inspected', "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', "
                    "'2030-01-01T00:00:00Z')"
                ),
                {"fingerprint": "b" * 64},
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "not terminal"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_clean_forward_upgrade_rejects_terminal_broker_history(self):
        self._downgrade_current_schema(FORWARD_REVISIONS[1])
        self._seed_terminal_broker_history()
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "not terminal"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_seeded_forward_upgrade_rejects_value_drift_before_alembic(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET display_name='drifted' "
                    "WHERE id=-112002"
                )
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "people are drifted"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                FORWARD_REVISIONS[1],
            )

    def test_clean_forward_upgrade_rejects_legacy_value_drift_before_alembic(self):
        self._downgrade_current_schema(FORWARD_REVISIONS[0])
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.ballparks SET name='drifted' WHERE id=9301")
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "ballparks are drifted"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_seeded_forward_upgrade_rejects_identity_timestamp_drift(self):
        _bootstrap_empty_database(self.engine, Path.cwd())
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            command.downgrade(
                _alembic_config(Path.cwd(), connection), FORWARD_REVISIONS[1]
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET created_at=created_at + "
                    "interval '1 second' WHERE id=-112002"
                )
            )
        with patch("tools.mobile_staging_data.command.upgrade") as upgrade:
            with self.assertRaisesRegex(StagingContractError, "identities are drifted"):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        upgrade.assert_not_called()

    def test_0007_and_known_revision_table_drift_fail_closed(self):
        self._downgrade_current_schema("0007_mobile_notifications")
        with self.assertRaisesRegex(StagingContractError, "revision is unknown"):
            recover(self.approval, TEST_DATABASE_URL)

        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA ntubtob CASCADE"))
        self._downgrade_current_schema(FORWARD_REVISIONS[1])
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE ntubtob.unknown_drift (id int)"))
        with self.assertRaisesRegex(StagingContractError, "schema is partial"):
            recover(self.approval, TEST_DATABASE_URL)

    def test_failed_forward_upgrade_rolls_back_to_exact_prestate(self):
        self._downgrade_current_schema(FORWARD_REVISIONS[0])
        with patch(
            "tools.mobile_staging_data.command.upgrade",
            side_effect=CommandError("fake forward migration failure"),
        ):
            with self.assertRaisesRegex(
                StagingContractError, "forward upgrade failed safely"
            ):
                execute_staging_data(
                    self.approval,
                    TEST_DATABASE_URL,
                    "fake-private-tester-subject",
                    Path.cwd(),
                )
        recovered = recover(self.approval, TEST_DATABASE_URL)
        self.assertEqual(recovered["outcome"], "upgrade_pending")
        self.assertEqual(recovered["revision"], FORWARD_REVISIONS[0])

    def test_attendance_repair_makes_runtime_reply_authoritative(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.game_attendance_replies SET updated_at=:old "
                    "WHERE id BETWEEN -112003 AND -112001"
                ),
                {"old": ANCHOR},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) VALUES "
                    "(-112001, -112001, 5, '2026-08-19T15:39:23.883620Z'), "
                    "(-112001, -112001, 5, '2026-08-19T15:44:55.572527Z')"
                )
            )
        before = attendance_repair_inventory(self.approval, TEST_DATABASE_URL)
        self.assertEqual(before["state"], "required")
        self.assertEqual(before["hidden_rows"], 2)
        repaired = execute_attendance_repair(self.approval, TEST_DATABASE_URL)
        self.assertEqual(repaired["removed_hidden_rows"], 2)
        self.assertEqual(
            execute_attendance_repair(self.approval, TEST_DATABASE_URL)[
                "removed_hidden_rows"
            ],
            0,
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) "
                    "VALUES (-112001, -112001, 5, '2026-08-19T01:00:00Z')"
                )
            )
            latest = connection.execute(
                text(
                    "SELECT reply, updated_at FROM ntubtob.game_attendance_replies "
                    "WHERE game_id=-112001 AND person_id=-112001 "
                    "ORDER BY updated_at DESC, id DESC LIMIT 1"
                )
            ).one()
            fixture_at = connection.scalar(
                text(
                    "SELECT updated_at FROM ntubtob.game_attendance_replies "
                    "WHERE id=-112001"
                )
            )
        self.assertEqual(latest.reply, 5)
        self.assertEqual(fixture_at, FIXTURE_REPLY_AT)
        self.assertGreater(latest.updated_at, fixture_at)

    def test_attendance_repair_rejects_near_miss_timestamp_before_mutation(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.game_attendance_replies SET updated_at=:old "
                    "WHERE id BETWEEN -112003 AND -112001"
                ),
                {"old": ANCHOR},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) VALUES "
                    "(-112001, -112001, 5, '2026-08-19T15:39:14Z'), "
                    "(-112001, -112001, 5, '2026-08-19T15:44:55.572527Z')"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "inventory failed safely"):
            attendance_repair_inventory(self.approval, TEST_DATABASE_URL)
        with self.assertRaisesRegex(StagingContractError, "inventory failed safely"):
            execute_attendance_repair(self.approval, TEST_DATABASE_URL)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.game_attendance_replies "
                        "WHERE person_id=-112001 AND game_id=-112001"
                    )
                ),
                3,
            )

    def test_runtime_residue_repair_is_exact_retry_safe_and_preserves_mobile_history(
        self,
    ):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        self._insert_runtime_residue()
        before = runtime_residue_inventory(
            self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
        )
        self.assertEqual((before["state"], before["residue_rows"]), ("required", 2))
        repaired = execute_runtime_residue_repair(
            self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
        )
        self.assertEqual(
            (repaired["state"], repaired["removed_residue_rows"]),
            ("repaired", 2),
        )
        self.assertEqual(
            execute_runtime_residue_repair(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["removed_residue_rows"],
            0,
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT id FROM ntubtob.game_attendance_replies " "ORDER BY id"
                    )
                )
                .scalars()
                .all(),
                [-112003, -112002, -112001, 9601, 9602, 9603, 9604],
            )
            self.assertEqual(
                tuple(
                    connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))
                    for table in (
                        "mobile_sessions",
                        "mobile_refresh_tokens",
                        "mobile_refresh_attempts",
                        "mobile_auth_exchanges",
                        "mobile_idempotency_records",
                    )
                ),
                (1, 8, 7, 1, 2),
            )
        self.assertEqual(
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["state"],
            "baseline",
        )
        self.assertTrue(
            grant_officer(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"]
        )
        self.assertTrue(
            restore_basic(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"]
        )

    def test_officer_restore_accepts_dynamic_owned_mobile_history(self):
        self._grant_officer_with_mobile_history()
        self._seed_mobile_runtime_history(session_id="task120-officer-session-2")
        before = self._mobile_history_snapshot()
        restored = restore_basic(
            self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
        )
        self.assertEqual((restored["state"], restored["changed"]), ("restored", True))
        self.assertEqual(self._mobile_history_snapshot(), before)

    def test_officer_restore_rejects_cross_principal_mobile_session(self):
        self._grant_officer_with_mobile_history()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_sessions SET person_id=1 "
                    "WHERE id='task120-fixture-session'"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "mobile history is drifted"):
            restore_basic(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        self._assert_officer_state_unchanged()

    def test_officer_lifecycle_accepts_exact_same_person_google_recovery(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_google_recovery_history()
        self._seed_mobile_runtime_history(
            session_id="task157-google-login-session",
            identity_id=-112004,
            exchange_provider="google",
        )
        with self.engine.connect() as connection:
            identity_before = connection.execute(
                text("SELECT * FROM ntubtob.auth_identities ORDER BY id")
            ).all()
            thread_before = connection.execute(
                text("SELECT * FROM ntubtob.identity_review_threads ORDER BY id")
            ).all()
        mobile_before = self._mobile_history_snapshot()

        self.assertTrue(
            grant_officer(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"]
        )
        self.assertTrue(
            restore_basic(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"]
        )

        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT * FROM ntubtob.auth_identities ORDER BY id")
                ).all(),
                identity_before,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT * FROM ntubtob.identity_review_threads ORDER BY id")
                ).all(),
                thread_before,
            )
        self.assertEqual(self._mobile_history_snapshot(), mobile_before)

    def test_partial_google_recovery_graph_is_rejected(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(id, provider, provider_subject, person_id, status, created_at, "
                    "updated_at) VALUES (-112004, 'google', 'fake-google-partial', "
                    "-112001, 'linked', '2030-01-01T00:00:00Z', "
                    "'2030-01-01T00:00:00Z')"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "Google recovery graph"):
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )

    def test_cross_person_google_recovery_graph_is_rejected(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_google_recovery_history()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=1 " "WHERE id=-112004"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "Google recovery graph"):
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )

    def test_duplicate_google_identity_is_rejected(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_google_recovery_history()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(id, provider, provider_subject, person_id, status, created_at, "
                    "updated_at) VALUES (-112005, 'google', "
                    "'fake-google-duplicate', -112001, 'linked', "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z')"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "Google recovery graph"):
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )

    def test_google_recovery_unknown_review_message_is_rejected(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_google_recovery_history()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.identity_review_messages "
                    "(id, thread_id, sender_role, sender_person_id, body, "
                    "body_redacted, created_at) VALUES "
                    "(-157001, -157001, 'applicant', NULL, "
                    "'fictional unexpected message', false, "
                    "'2030-01-01T00:00:00Z')"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "Google recovery graph"):
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )

    def test_officer_restore_rejects_cross_principal_mobile_idempotency(self):
        self._grant_officer_with_mobile_history()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_idempotency_records SET person_id=1 "
                    "WHERE session_id='task120-fixture-session'"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "mobile history is drifted"):
            restore_basic(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        self._assert_officer_state_unchanged()

    def test_runtime_residue_repair_rejects_near_miss_additional_and_cross_principal_history(
        self,
    ):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        self._insert_runtime_residue(near_miss=True)
        with self.assertRaisesRegex(StagingContractError, "inventory failed safely"):
            runtime_residue_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        with self.assertRaisesRegex(StagingContractError, "inventory failed safely"):
            execute_runtime_residue_repair(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.game_attendance_replies "
                        "WHERE id IN (3, 4)"
                    )
                ),
                2,
            )

        with self.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ntubtob.game_attendance_replies WHERE id IN (3, 4)")
            )
        self._insert_runtime_residue(additional=True)
        with self.assertRaisesRegex(StagingContractError, "inventory failed safely"):
            runtime_residue_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM ntubtob.game_attendance_replies "
                    "WHERE id IN (3, 4, 5)"
                )
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_sessions SET person_id=1 "
                    "WHERE id='task120-fixture-session'"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "inventory failed safely"):
            runtime_residue_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )

    def test_runtime_residue_repair_rolls_back_when_postcheck_is_not_baseline(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        self._insert_runtime_residue()
        with patch(
            "tools.mobile_staging_data._officer_fixture_state",
            return_value="runtime_residue",
        ):
            with self.assertRaisesRegex(StagingContractError, "failed safely"):
                execute_runtime_residue_repair(
                    self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
                )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.game_attendance_replies "
                        "WHERE id IN (3, 4)"
                    )
                ),
                2,
            )

    def test_runtime_residue_repair_does_not_admit_orphan_mobile_children(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        self._insert_runtime_residue()
        with self.assertRaises(SQLAlchemyError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.mobile_refresh_tokens "
                        "(session_id, token_hash, generation, status, issued_at, "
                        "expires_at) VALUES ('missing-task120-session', "
                        "'fake-orphan-token', 1, 'current', "
                        "'2030-01-01T00:00:00Z', '2030-01-02T00:00:00Z')"
                    )
                )
        self.assertEqual(
            runtime_residue_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["state"],
            "required",
        )

    def test_officer_fixture_grant_restore_and_retries_are_append_only(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self.assertEqual(
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["state"],
            "baseline",
        )
        granted = grant_officer(
            self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
        )
        self.assertEqual((granted["state"], granted["changed"]), ("granted", True))
        self.assertFalse(
            grant_officer(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"]
        )
        restored = restore_basic(
            self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
        )
        self.assertEqual((restored["state"], restored["changed"]), ("restored", True))
        self.assertFalse(
            restore_basic(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"]
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT id, request_id FROM ntubtob.access_audit "
                        "WHERE id < 0 ORDER BY id"
                    )
                ).all(),
                [
                    (-119002, "task-119-fictional-officer-restore"),
                    (-119001, "task-119-fictional-officer-grant"),
                ],
            )
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT portal_access_level, portal_status, version "
                        "FROM ntubtob.people WHERE id=-112001"
                    )
                ).one(),
                ("basic", "active", 3),
            )

    def test_officer_fixture_unknown_audit_drift_fails_closed(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.access_audit "
                    "(action, target_person_id, before_state, after_state, reason, "
                    "request_id, created_at) VALUES "
                    "('access_changed', -112001, '{}'::json, '{}'::json, "
                    "'unknown fixture drift', 'task-119-unknown-drift', now())"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "audit.*drifted"):
            officer_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )

    def test_officer_subject_mismatch_denies_before_mutation(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET provider_subject="
                    "'different-private-subject' WHERE id=-112001"
                )
            )
        with self.assertRaisesRegex(StagingContractError, "identity is drifted"):
            grant_officer(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT portal_access_level, version FROM ntubtob.people "
                        "WHERE id=-112001"
                    )
                ).one(),
                ("basic", 1),
            )

    def test_fixture_lifecycle_repeats_and_preserves_historical_rows(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        grant_officer(self.approval, TEST_DATABASE_URL, "fake-private-tester-subject")
        restore_basic(self.approval, TEST_DATABASE_URL, "fake-private-tester-subject")
        with self.engine.connect() as connection:
            legacy_audits = connection.execute(
                text("SELECT * FROM ntubtob.access_audit ORDER BY id")
            ).all()

        grant_officer(self.approval, TEST_DATABASE_URL, "fake-private-tester-subject")
        self.assertTrue(
            mobile_principal_inventory(self.approval, TEST_DATABASE_URL)[
                "expected_person_match"
            ]
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.game_attendance_replies SET reply=4 "
                    "WHERE id=-112001"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) VALUES "
                    "(-112001, -112001, 5, '1999-01-01T00:00:00Z'), "
                    "(-112002, -112003, 1, '2041-01-01T00:00:00Z')"
                )
            )
        mobile_before = self._mobile_history_snapshot()
        self.assertEqual(
            fixture_lifecycle_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["state"],
            "reset_required",
        )

        reset = execute_fixture_lifecycle_reset(
            self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
        )
        self.assertEqual((reset["state"], reset["changed"]), ("ready_basic", True))
        self.assertEqual(
            execute_fixture_lifecycle_reset(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )["changed"],
            False,
        )
        self.assertEqual(self._mobile_history_snapshot(), mobile_before)
        with self.engine.connect() as connection:
            after_audits = connection.execute(
                text("SELECT * FROM ntubtob.access_audit ORDER BY id")
            ).all()
            self.assertEqual(after_audits[: len(legacy_audits)], legacy_audits)
            person = connection.execute(
                text(
                    "SELECT portal_access_level, version FROM ntubtob.people "
                    "WHERE id=-112001"
                )
            ).one()
            self.assertEqual(person, ("basic", 5))
            replies = connection.execute(
                text(
                    "SELECT id, game_id, user_id, member_id, person_id, reply "
                    "FROM ntubtob.game_attendance_replies "
                    "WHERE person_id = ANY(:ids) OR game_id = ANY(:ids) ORDER BY id"
                ),
                {"ids": [-112003, -112002, -112001]},
            ).all()
            self.assertEqual(
                replies,
                [
                    (-112003, -112002, None, None, -112003, 5),
                    (-112002, -112001, None, None, -112002, 2),
                    (-112001, -112001, None, None, -112001, 1),
                ],
            )

    def test_fixture_lifecycle_rejects_partial_ownership_without_mutation(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) "
                    "VALUES (9401, -112001, 1, now())"
                )
            )
        with self.engine.connect() as connection:
            before = connection.execute(
                text(
                    "SELECT id, game_id, person_id, reply, updated_at "
                    "FROM ntubtob.game_attendance_replies ORDER BY id"
                )
            ).all()
        with self.assertRaisesRegex(StagingContractError, "attendance ownership"):
            fixture_lifecycle_inventory(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        with self.assertRaisesRegex(StagingContractError, "attendance ownership"):
            execute_fixture_lifecycle_reset(
                self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
            )
        with self.engine.connect() as connection:
            after = connection.execute(
                text(
                    "SELECT id, game_id, person_id, reply, updated_at "
                    "FROM ntubtob.game_attendance_replies ORDER BY id"
                )
            ).all()
        self.assertEqual(after, before)

    def test_fixture_lifecycle_postcheck_failure_rolls_back_every_owned_table(self):
        execute_staging_data(
            self.approval,
            TEST_DATABASE_URL,
            "fake-private-tester-subject",
            Path.cwd(),
        )
        self._seed_mobile_runtime_history()
        grant_officer(self.approval, TEST_DATABASE_URL, "fake-private-tester-subject")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.game_attendance_replies "
                    "(game_id, person_id, reply, updated_at) "
                    "VALUES (-112001, -112001, 5, now())"
                )
            )
        with self.engine.connect() as connection:
            before = {
                "person": connection.execute(
                    text("SELECT * FROM ntubtob.people WHERE id=-112001")
                ).all(),
                "attendance": connection.execute(
                    text("SELECT * FROM ntubtob.game_attendance_replies ORDER BY id")
                ).all(),
                "audit": connection.execute(
                    text("SELECT * FROM ntubtob.access_audit ORDER BY id")
                ).all(),
            }
        mobile_before = self._mobile_history_snapshot()
        with patch(
            "tools.mobile_staging_data._attendance_is_canonical", return_value=False
        ):
            with self.assertRaisesRegex(StagingContractError, "failed safely"):
                execute_fixture_lifecycle_reset(
                    self.approval, TEST_DATABASE_URL, "fake-private-tester-subject"
                )
        with self.engine.connect() as connection:
            after = {
                "person": connection.execute(
                    text("SELECT * FROM ntubtob.people WHERE id=-112001")
                ).all(),
                "attendance": connection.execute(
                    text("SELECT * FROM ntubtob.game_attendance_replies ORDER BY id")
                ).all(),
                "audit": connection.execute(
                    text("SELECT * FROM ntubtob.access_audit ORDER BY id")
                ).all(),
            }
        self.assertEqual(after, before)
        self.assertEqual(self._mobile_history_snapshot(), mobile_before)


if __name__ == "__main__":
    unittest.main()
