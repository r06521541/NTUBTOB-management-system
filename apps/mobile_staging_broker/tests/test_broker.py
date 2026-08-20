from __future__ import annotations

import importlib
import io
import json
import logging
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from apps.mobile_staging_broker.app import create_app
from apps.mobile_staging_broker.artifacts import artifact_hashes, load_attested_approval
from apps.mobile_staging_broker.broker import (
    Broker,
    BrokerConflict,
    BrokerFailure,
    BrokerManifest,
    InMemoryJournal,
)
from apps.mobile_staging_broker.operator import Task126Operator
from apps.mobile_staging_broker.runtime import build_runtime

ROOT = Path(__file__).resolve().parents[3]
SENTINEL_DSN = "postgresql://sentinel-user:sentinel-password@db.invalid/staging"
SENTINEL_SUBJECT = "sentinel-provider-subject"


def manifest(**changes):
    values = {
        "candidate_approval_sha256": "a" * 64,
        "project": "fictional-mobile-staging",
        "region": "asia-east1",
        "service": "mobile-staging-broker",
        "runtime_identity": "broker-runtime@fictional-mobile-staging.iam.gserviceaccount.com",
        "broker_artifact_sha256": "b" * 64,
        "operator_artifact_sha256": "c" * 64,
        "image_digest": "sha256:" + "d" * 64,
        "database_secret_version": "projects/fictional-mobile-staging/secrets/database-url/versions/7",
        "subject_secret_version": "projects/fictional-mobile-staging/secrets/provider-subject/versions/9",
        "database_identity_sha256": "e" * 64,
    }
    values.update(changes)
    return BrokerManifest.from_mapping(values)


class Secrets:
    def __init__(self, database=(SENTINEL_DSN,), subject=(SENTINEL_SUBJECT,)):
        self.database, self.subject, self.calls = database, subject, []

    def access(self, resource):
        self.calls.append(resource)
        return self.database if resource.endswith("/versions/7") else self.subject


class Operator:
    def __init__(self, states=("ready_basic", "ready_officer")):
        self.states, self.mutations = list(states), []

    def inspect(self, database_url, provider_subject):
        return self.states.pop(0) if self.states else "ready_officer"

    def mutate(self, operation, database_url, provider_subject):
        self.mutations.append(operation)


class ManifestAndSecretTest(unittest.TestCase):
    def test_manifest_rejects_mutable_ambiguous_and_production_configuration(self):
        for change in (
            {"image_digest": "image:latest"},
            {"database_secret_version": "projects/x/secrets/y/versions/latest"},
            {"subject_secret_version": "projects/x/secrets/y/versions/1,2"},
            {"project": "ntubtob-schedule-405614"},
            {"runtime_identity": "owner@example.invalid"},
            {"candidate_approval_sha256": "short"},
            {
                "database_secret_version": "projects/other-staging/secrets/database-url/versions/7"
            },
            {
                "subject_secret_version": "projects/other-staging/secrets/provider-subject/versions/9"
            },
        ):
            with self.subTest(change=change), self.assertRaises(BrokerFailure):
                manifest(**change)

    def test_zero_multiple_and_malformed_payload_records_fail_closed(self):
        for database in (
            (),
            (SENTINEL_DSN, SENTINEL_DSN),
            ("not-a-postgresql-dsn",),
        ):
            with self.subTest(database=database), self.assertRaises(BrokerFailure):
                Broker(
                    manifest(),
                    Secrets(database=database),
                    InMemoryJournal(),
                    Operator(),
                ).execute("grant", "operation-123456")


class StateMachineTest(unittest.TestCase):
    def test_success_and_exact_replay_mutate_once(self):
        journal, operator = InMemoryJournal(), Operator()
        broker = Broker(manifest(), Secrets(), journal, operator)
        first = broker.execute("grant", "operation-123456")
        self.assertEqual(first, broker.execute("grant", "operation-123456"))
        self.assertEqual(operator.mutations, ["grant"])
        self.assertEqual(
            journal.get("operation-123456").lifecycle_state, "postcheck_complete"
        )

    def test_conflicting_replay_fails_before_secret_access(self):
        secrets, journal = Secrets(), InMemoryJournal()
        Broker(manifest(), secrets, journal, Operator()).execute(
            "grant", "operation-123456"
        )
        secrets.calls.clear()
        with self.assertRaises(BrokerConflict):
            Broker(manifest(), secrets, journal, Operator()).execute(
                "restore", "operation-123456"
            )
        self.assertEqual(secrets.calls, [])

    def test_unknown_journal_state_fails_before_secret_access(self):
        secrets, journal = Secrets(), InMemoryJournal()
        journal.inject(
            "operation-123456", "grant", "ready_officer", "f" * 64, "unknown"
        )
        with self.assertRaises(BrokerConflict):
            Broker(manifest(), secrets, journal, Operator()).execute(
                "grant", "operation-123456"
            )
        self.assertEqual(secrets.calls, [])

    def test_crash_before_issue_continues_but_after_issue_only_reconciles(self):
        before = InMemoryJournal()
        before.inject(
            "operation-123456", "grant", "ready_officer", "f" * 64, "confirmed"
        )
        operator = Operator(states=("ready_officer",))
        Broker(manifest(), Secrets(), before, operator).execute(
            "grant", "operation-123456"
        )
        self.assertEqual(operator.mutations, ["grant"])

        after = InMemoryJournal()
        after.inject(
            "operation-123457",
            "grant",
            "ready_officer",
            "f" * 64,
            "mutation_issued",
        )
        operator = Operator(states=("ready_officer",))
        result = Broker(manifest(), Secrets(), after, operator).execute(
            "grant", "operation-123457"
        )
        self.assertEqual(result["lifecycle_state"], "postcheck_complete")
        self.assertEqual(operator.mutations, [])

    def test_postcheck_mismatch_and_stale_reconcile_never_retry(self):
        journal, operator = InMemoryJournal(), Operator(
            states=("ready_basic", "reset_required", "reset_required")
        )
        broker = Broker(manifest(), Secrets(), journal, operator)
        with self.assertRaises(BrokerFailure):
            broker.execute("grant", "operation-123456")
        self.assertEqual(operator.mutations, ["grant"])
        self.assertEqual(
            journal.get("operation-123456").lifecycle_state, "reconcile_required"
        )
        with self.assertRaises(BrokerFailure):
            broker.execute("reconcile", "operation-123456")
        self.assertEqual(operator.mutations, ["grant"])

    def test_nonblocking_gate_rejects_before_secret_access(self):
        entered, release = threading.Event(), threading.Event()

        class Blocking(Operator):
            def inspect(self, database_url, provider_subject):
                entered.set()
                release.wait(5)
                return super().inspect(database_url, provider_subject)

        secrets = Secrets()
        broker = Broker(manifest(), secrets, InMemoryJournal(), Blocking())
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(broker.execute, "grant", "operation-123456")
            self.assertTrue(entered.wait(5))
            count = len(secrets.calls)
            with self.assertRaises(BrokerConflict):
                broker.execute("grant", "operation-123457")
            self.assertEqual(len(secrets.calls), count)
            release.set()
            first.result(5)

    def test_cross_process_cas_has_one_mutation_winner(self):
        barrier = threading.Barrier(2)

        class StatefulOperator(Operator):
            def __init__(self):
                super().__init__()
                self.state = "ready_basic"

            def inspect(self, database_url, provider_subject):
                return self.state

            def mutate(self, operation, database_url, provider_subject):
                super().mutate(operation, database_url, provider_subject)
                self.state = "ready_officer"

        class RacingJournal(InMemoryJournal):
            def compare_and_set(
                self, operation_id, expected_state, next_state, reason_code=None
            ):
                if expected_state == "confirmed":
                    barrier.wait(5)
                return super().compare_and_set(
                    operation_id, expected_state, next_state, reason_code
                )

        journal = RacingJournal()
        operators = [StatefulOperator(), StatefulOperator()]
        brokers = [
            Broker(manifest(), Secrets(), journal, operator) for operator in operators
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(broker.execute, "grant", "operation-123456")
                for broker in brokers
            ]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(5)["classification"])
                except BrokerConflict as error:
                    outcomes.append(error.reason_code)
        self.assertEqual(sorted(outcomes), ["OPERATION_IN_PROGRESS", "PASS"])
        self.assertEqual(sum(len(item.mutations) for item in operators), 1)

    def test_reconcile_reuses_same_journal_row_and_never_mutates(self):
        journal = InMemoryJournal()
        journal.inject(
            "operation-123456",
            "grant",
            "ready_officer",
            "f" * 64,
            "mutation_issued",
        )
        operator = Operator(states=("ready_officer",))
        Broker(manifest(), Secrets(), journal, operator).execute(
            "reconcile", "operation-123456"
        )
        records = journal.snapshot()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operation"], "grant")
        self.assertEqual(operator.mutations, [])


class AttestationTest(unittest.TestCase):
    def test_actual_approval_operator_and_broker_bytes_are_bound(self):
        hashes = artifact_hashes(ROOT)
        bound = manifest(**hashes)
        approval = load_attested_approval(bound, ROOT)
        self.assertEqual(approval["project"], bound.project)
        with self.assertRaises(BrokerFailure):
            load_attested_approval(
                manifest(**{**hashes, "operator_artifact_sha256": "0" * 64}),
                ROOT,
            )

    def test_attestation_fails_before_secret_or_operator_initialization(self):
        hashes = artifact_hashes(ROOT)
        bound = manifest(**hashes)
        environment = {
            "BROKER_CANDIDATE_APPROVAL_SHA256": bound.candidate_approval_sha256,
            "BROKER_PROJECT": bound.project,
            "BROKER_REGION": bound.region,
            "BROKER_SERVICE": bound.service,
            "BROKER_RUNTIME_IDENTITY": bound.runtime_identity,
            "BROKER_ARTIFACT_SHA256": bound.broker_artifact_sha256,
            "BROKER_OPERATOR_ARTIFACT_SHA256": bound.operator_artifact_sha256,
            "BROKER_IMAGE_DIGEST": bound.image_digest,
            "BROKER_DATABASE_SECRET_VERSION": bound.database_secret_version,
            "BROKER_SUBJECT_SECRET_VERSION": bound.subject_secret_version,
            "BROKER_DATABASE_IDENTITY_SHA256": bound.database_identity_sha256,
        }
        with patch.dict("os.environ", environment, clear=True), patch(
            "apps.mobile_staging_broker.runtime.load_attested_approval",
            side_effect=BrokerFailure("ARTIFACT_INVALID"),
        ), patch(
            "apps.mobile_staging_broker.runtime.GoogleSecretAccessor"
        ) as secret_accessor:
            with self.assertRaises(BrokerFailure):
                build_runtime()
        secret_accessor.assert_not_called()


class BoundaryTest(unittest.TestCase):
    def test_bootstrap_import_and_health_do_not_import_runtime(self):
        module_name = "apps.mobile_staging_broker.bootstrap"
        runtime_name = "apps.mobile_staging_broker.runtime"
        existing_runtime = sys.modules.pop(runtime_name, None)
        try:
            sys.modules.pop(module_name, None)
            bootstrap = importlib.import_module(module_name)
            response = bootstrap.app.test_client().get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(runtime_name, sys.modules)
        finally:
            if existing_runtime is not None:
                sys.modules[runtime_name] = existing_runtime

    def test_request_vocabulary_governed_json_and_health_isolation(self):
        broker = Broker(manifest(), Secrets(), InMemoryJournal(), Operator())
        factory = Mock(return_value=broker)
        client = create_app(factory).test_client()
        self.assertEqual(
            client.get("/healthz").get_json(),
            {"service": "mobile-staging-broker", "status": "ok"},
        )
        factory.assert_not_called()
        for payload in (
            {},
            {"operation": "shell", "operation_id": "operation-123456"},
            {"operation": "grant", "operation_id": "short"},
            {
                "operation": "grant",
                "operation_id": "operation-123456",
                "dsn": SENTINEL_DSN,
            },
        ):
            self.assertEqual(
                client.post("/v1/operations", json=payload).status_code, 400
            )
        response = client.post(
            "/v1/operations",
            json={"operation": "grant", "operation_id": "operation-123456"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.get_json()),
            {
                "classification",
                "lifecycle_state",
                "operation",
                "operation_id",
                "reason_code",
                "target_state",
            },
        )

    def test_content_type_size_duplicate_keys_and_trailing_json_are_rejected(self):
        factory = Mock(side_effect=AssertionError("runtime must not initialize"))
        client = create_app(factory).test_client()
        cases = (
            {},
            {
                "data": b'{"operation":"grant","operation_id":"operation-123456"}',
                "content_type": "text/plain",
            },
            {
                "data": (
                    b'{"operation":"grant","operation":"restore",'
                    b'"operation_id":"operation-123456"}'
                ),
                "content_type": "application/json",
            },
            {
                "data": (
                    b'{"operation":"grant",'
                    b'"operation_id":"operation-123456"} trailing'
                ),
                "content_type": "application/json",
            },
            {
                "data": b"{" + b"x" * 300 + b"}",
                "content_type": "application/json",
            },
        )
        for values in cases:
            with self.subTest(values=values):
                response = client.post("/v1/operations", **values)
                self.assertEqual(response.status_code, 400)
        factory.assert_not_called()

    def test_sentinels_never_cross_outputs_logs_exceptions_journal_or_files(self):
        broker = Broker(
            manifest(),
            Secrets(),
            InMemoryJournal(),
            Operator(states=("ready_basic", "reset_required")),
        )
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("broker-sentinel-test")
        logger.addHandler(handler)
        try:
            with tempfile.TemporaryDirectory() as directory, patch(
                "sys.stdout", new_callable=io.StringIO
            ) as stdout, patch("sys.stderr", new_callable=io.StringIO) as stderr:
                with self.assertRaises(BrokerFailure) as caught:
                    broker.execute("grant", "operation-123456")
                material = "\n".join(
                    (
                        stdout.getvalue(),
                        stderr.getvalue(),
                        stream.getvalue(),
                        str(caught.exception),
                        json.dumps(broker.journal.snapshot(), default=str),
                    )
                )
                for path in Path(directory).rglob("*"):
                    if path.is_file():
                        material += path.read_text(encoding="utf-8", errors="ignore")
        finally:
            logger.removeHandler(handler)
        for sentinel in (SENTINEL_DSN, "sentinel-password", SENTINEL_SUBJECT):
            self.assertNotIn(sentinel, material)

    def test_task126_adapter_has_no_arbitrary_dispatch_or_child_output(self):
        data = Mock()
        data.broker_fixture_lifecycle_inventory.return_value = {"state": "ready_basic"}
        adapter = Task126Operator({"owner_approved": True})
        with patch.object(adapter, "_data_module", return_value=data):
            self.assertEqual(
                adapter.inspect(SENTINEL_DSN, SENTINEL_SUBJECT), "ready_basic"
            )
            adapter.mutate("grant", SENTINEL_DSN, SENTINEL_SUBJECT)
            with self.assertRaises(RuntimeError):
                adapter.mutate("shell", SENTINEL_DSN, SENTINEL_SUBJECT)
        data.broker_grant_officer.assert_called_once()
        self.assertEqual(
            [call[0] for call in data.method_calls],
            ["broker_fixture_lifecycle_inventory", "broker_grant_officer"],
        )


if __name__ == "__main__":
    unittest.main()
