"""Fictional Apple credential preparation; no actual database/provider/key I/O."""

import base64
import importlib
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from cryptography.fernet import Fernet
from shared_module.apple_token_revocation import AppleTokenRevoker
from shared_module.mobile_api import secret_hash
from shared_module.portal_data import erasure_provider_execution as execution
from shared_module.portal_data.erasure_fulfillment import _digest
from shared_module.portal_data.erasure_person_fulfillment import PersonIdentitySnapshot
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

JOB = "00000000-0000-4000-8000-000000000001"
ITEM = "00000000-0000-4000-8000-000000000002"
GEN = "00000000-0000-4000-8000-000000000003"
IDENTITY_GEN = "00000000-0000-4000-8000-000000000004"
NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)
TOKEN = "fictional-private-refresh-token"


class ApplePreparationTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module(
            "shared_module.portal_data.erasure_apple_preparation"
        )
        self.connection = MagicMock(spec=Connection)
        self.connection.in_transaction.return_value = True
        self.connection.get_transaction.return_value.is_active = True
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.connection = SimpleNamespace(
            dbapi_connection=SimpleNamespace(autocommit=False)
        )
        self.connection.scalars.return_value = ("0018_erasure_privacy_mutation",)
        self.connection.scalar.return_value = False
        self.job = dict(
            id=UUID(JOB),
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=11,
            expected_generation=UUID(GEN),
            scope_version=1,
            scope_hash="a" * 64,
            status="verified",
            updated_at=NOW,
            irreversible_started_at=NOW,
        )
        self.item = dict(
            id=UUID(ITEM),
            job_id=UUID(JOB),
            stage="provider_revocation",
            expected_generation=UUID(GEN),
            created_at=NOW,
            binding_hash=_digest(["pending_item_v1", JOB, "a" * 64, "provider"]),
        )
        self.identity = dict(
            id=11,
            provider="apple",
            person_id=None,
            status="pending",
            generation=GEN,
            digest="b" * 64,
        )
        self.credential = dict(
            id=21,
            auth_identity_id=11,
            encrypted_refresh_token=b"fictional-ciphertext",
            refresh_token_hash=secret_hash(TOKEN),
            status="active",
        )
        self.credentials = [self.credential]
        self.connection.execute.side_effect = self.query
        self.cipher = Mock(open=Mock(return_value=TOKEN.encode()))
        self.transport = Mock(return_value=(200, b""))
        self.revoker = AppleTokenRevoker(transport=self.transport)
        self.args = dict(
            provider_cipher=self.cipher,
            client_id="fictional.apple",
            client_secret="fictional-private-client-secret",
            revoker=self.revoker,
        )
        self.prepare = self.module.AppleErasurePreparation(**self.args)

    def query(self, statement, parameters=None):
        result = MagicMock()
        sql = str(statement)
        if "FROM ntubtob.auth_identities" in sql:
            result.mappings.return_value.first.return_value = self.identity
        elif "FROM ntubtob.apple_provider_credentials" in sql:
            result.mappings.return_value.all.return_value = self.credentials
        return result

    def person(self, provider="apple"):
        self.job.update(target_kind="person", person_id=7, auth_identity_id=None)
        self.identity.update(
            person_id=7, status="linked", provider=provider, generation=IDENTITY_GEN
        )
        self.item["binding_hash"] = _digest(
            ["person_item_v1", JOB, self.job["scope_hash"], "provider:11"]
        )
        return PersonIdentitySnapshot(11, provider, IDENTITY_GEN, "b" * 64, None)

    def call(self, identity=None):
        return self.prepare(self.connection, self.job, self.item, identity)

    def assert_no_effect(self):
        self.cipher.open.assert_not_called()
        self.transport.assert_not_called()

    def test_constructor_and_preparation_do_not_dispatch(self):
        self.connection.execute.assert_not_called()
        self.assert_no_effect()
        prepared = self.call()
        self.assertIs(type(prepared), execution.PreparedProviderEffect)
        self.assertEqual(prepared.binding_hash, self.item["binding_hash"])
        self.assertEqual(prepared.scope_hash, self.job["scope_hash"])
        self.assertEqual(prepared.expected_generation, GEN)
        self.cipher.open.assert_called_once_with(b"fictional-ciphertext")
        self.transport.assert_not_called()
        self.assertNotIn("private", repr(prepared))
        # The returned callable must not use a closed/replaced connection.
        self.connection.execute.side_effect = AssertionError("no SQL after preparation")
        self.connection.scalar.side_effect = AssertionError("no SQL after preparation")
        self.assertEqual(prepared.invoke(), "succeeded")
        self.transport.assert_called_once()
        for name in ("begin", "begin_nested", "commit", "rollback", "close"):
            getattr(self.connection, name).assert_not_called()

    def test_person_identity_generation_is_not_person_generation(self):
        snapshot = self.person()
        prepared = self.call(snapshot)
        self.assertEqual(prepared.expected_generation, GEN)
        self.assertEqual(prepared.invoke(), "succeeded")
        self.cipher.open.assert_called_once()

    def test_memoryview_and_existing_fernet_open_are_supported(self):
        fernet = Fernet(base64.urlsafe_b64encode(b"F" * 32))
        cipher = SimpleNamespace(open=fernet.decrypt)
        self.prepare = self.module.AppleErasurePreparation(
            **dict(self.args, provider_cipher=cipher)
        )
        for binary in (bytes, memoryview):
            self.credential["encrypted_refresh_token"] = binary(
                fernet.encrypt(TOKEN.encode())
            )
            self.assertEqual(self.call().invoke(), "succeeded")
        self.assertEqual(self.transport.call_count, 2)

    def test_real_fernet_wrong_key_and_tamper_are_manual_without_http(self):
        fernet = Fernet(base64.urlsafe_b64encode(b"F" * 32))
        self.prepare = self.module.AppleErasurePreparation(
            **dict(self.args, provider_cipher=SimpleNamespace(open=fernet.decrypt))
        )
        encrypted = fernet.encrypt(TOKEN.encode())
        wrong = Fernet(base64.urlsafe_b64encode(b"W" * 32))
        for value in (encrypted[:-8] + b"AAAAAAAA", wrong.encrypt(TOKEN.encode())):
            self.credential["encrypted_refresh_token"] = value
            self.assertEqual(self.call().invoke(), "manual_action_needed")
        self.transport.assert_not_called()

    def test_boolean_current_person_fk_is_not_an_integer_binding(self):
        snapshot = self.person()
        self.job["person_id"] = 1
        self.identity["person_id"] = True
        with self.assertRaises(self.module.ApplePreparationRejected):
            self.call(snapshot)
        self.assert_no_effect()

    def test_only_actual_apple_absence_returns_missing(self):
        self.credentials = []
        for snapshot in (None, self.person()):
            if snapshot is None:
                self.job.update(
                    target_kind="pending_identity", person_id=None, auth_identity_id=11
                )
                self.identity.update(person_id=None, status="pending", generation=GEN)
                self.item["binding_hash"] = _digest(
                    ["pending_item_v1", JOB, "a" * 64, "provider"]
                )
            else:
                snapshot = self.person()
            self.assertEqual(self.call(snapshot).invoke(), "credential_missing")
        self.assert_no_effect()

    def test_non_apple_is_manual_without_querying_apple_credential(self):
        for provider in ("line", "google"):
            self.connection.execute.reset_mock()
            self.credentials = []
            self.assertEqual(
                self.call(self.person(provider)).invoke(), "manual_action_needed"
            )
            self.assertFalse(
                any(
                    "FROM ntubtob.apple_provider_credentials" in str(call.args[0])
                    for call in self.connection.execute.call_args_list
                )
            )
        self.assert_no_effect()

    def test_revoked_local_flag_is_not_provider_success(self):
        self.credential["status"] = "revoked"
        self.transport.return_value = (400, b"")
        self.assertEqual(self.call().invoke(), "manual_action_needed")
        self.transport.assert_called_once()

    def test_unusable_present_credential_is_manual_not_missing(self):
        original = dict(self.credential)
        for field, value in (
            ("encrypted_refresh_token", None),
            ("encrypted_refresh_token", "private"),
            ("encrypted_refresh_token", b""),
            ("encrypted_refresh_token", b"x" * 65537),
            ("refresh_token_hash", "f" * 64),
            ("refresh_token_hash", None),
            ("refresh_token_hash", "not-a-hash"),
        ):
            self.credential.clear()
            self.credential.update(original, **{field: value})
            with self.subTest(field=field, value_type=type(value).__name__):
                self.assertEqual(self.call().invoke(), "manual_action_needed")
        self.credential.clear()
        self.credential.update(original)
        for plain in (
            None,
            "private",
            b"",
            b"\xff",
            b"a\nsecret",
            "私密".encode(),
            b"x" * 16385,
        ):
            self.cipher.open.return_value = plain
            self.assertEqual(self.call().invoke(), "manual_action_needed")
        self.cipher.open.side_effect = RuntimeError(
            "fictional private bad-key ciphertext"
        )
        self.assertEqual(self.call().invoke(), "manual_action_needed")
        self.transport.assert_not_called()

    def test_credential_fk_cardinality_and_status_mismatch_reject(self):
        for rows in (
            [dict(self.credential, auth_identity_id=12)],
            [dict(self.credential, id=True)],
            [dict(self.credential, status="unexpected")],
            [self.credential, self.credential],
        ):
            self.credentials = rows
            with self.assertRaises(self.module.ApplePreparationRejected):
                self.call()
        self.assert_no_effect()

    def test_bad_job_item_and_generation_bindings_reject_before_decrypt(self):
        variants = (
            ("job", "id", "invalid"),
            ("job", "scope_version", True),
            ("job", "status", "requested"),
            ("job", "scope_hash", "f" * 64),
            ("job", "expected_generation", IDENTITY_GEN),
            ("job", "auth_identity_id", True),
            ("job", "person_id", 7),
            ("item", "job_id", ITEM),
            ("item", "id", "invalid"),
            ("item", "stage", "online_erasure"),
            ("item", "expected_generation", IDENTITY_GEN),
            ("item", "binding_hash", "f" * 64),
        )
        for target, key, value in variants:
            mapping = self.job if target == "job" else self.item
            original = mapping[key]
            mapping[key] = value
            with self.subTest(target=target, key=key):
                with self.assertRaises(self.module.ApplePreparationRejected):
                    self.call()
            mapping[key] = original
        self.assert_no_effect()

    def test_current_identity_remap_rebuild_or_snapshot_drift_rejects(self):
        snapshot = self.person()
        original = dict(self.identity)
        for key, value in (
            ("id", 12),
            ("person_id", 8),
            ("generation", GEN),
            ("provider", "line"),
            ("digest", "c" * 64),
            ("status", "pending"),
        ):
            self.identity = dict(original, **{key: value})
            with self.subTest(key=key):
                with self.assertRaises(self.module.ApplePreparationRejected):
                    self.call(snapshot)
        self.identity = original
        for wrong in (
            None,
            object(),
            replace(snapshot, identity_id=12),
            replace(snapshot, generation=GEN),
            replace(snapshot, digest="c" * 64),
        ):
            with self.assertRaises(self.module.ApplePreparationRejected):
                self.call(wrong)
        self.assert_no_effect()

    def test_pending_provider_or_generation_change_rejects(self):
        original = dict(self.identity)
        for key, value in (
            ("provider", "line"),
            ("generation", IDENTITY_GEN),
            ("person_id", 7),
            ("status", "linked"),
        ):
            self.identity = dict(original, **{key: value})
            with self.assertRaises(self.module.ApplePreparationRejected):
                self.call()
        self.identity = None
        with self.assertRaises(self.module.ApplePreparationRejected):
            self.call()
        self.assert_no_effect()

    def test_sql_failure_is_unavailable_not_absence_or_private_message(self):
        self.connection.execute.side_effect = RuntimeError(
            "fictional private driver details"
        )
        with self.assertRaises(self.module.ApplePreparationUnavailable) as caught:
            self.call()
        self.assertEqual(str(caught.exception), "apple_preparation_unavailable")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assert_no_effect()

    def test_transaction_isolation_schema_and_rls_are_checked(self):
        for field, value in (
            ("transaction", False),
            ("autocommit", True),
            ("isolation", "REPEATABLE READ"),
            ("schema", ("unknown",)),
            ("rls", True),
            ("rls", None),
        ):
            if field == "transaction":
                self.connection.in_transaction.return_value = value
            elif field == "autocommit":
                self.connection.connection.dbapi_connection.autocommit = value
            elif field == "isolation":
                self.connection.get_isolation_level.return_value = value
            elif field == "schema":
                self.connection.scalars.return_value = value
            else:
                self.connection.scalar.return_value = value
            with self.subTest(field=field):
                with self.assertRaises(self.module.ApplePreparationRejected):
                    self.call()
            self.connection.in_transaction.return_value = True
            self.connection.connection.dbapi_connection.autocommit = False
            self.connection.get_isolation_level.return_value = "READ COMMITTED"
            self.connection.scalars.return_value = ("0018_erasure_privacy_mutation",)
            self.connection.scalar.return_value = False
        self.assert_no_effect()

    def test_invoke_is_one_shot_even_for_unknown_or_local_classification(self):
        for response in ((200, b""), (500, b"private")):
            self.transport.return_value = response
            prepared = self.call()
            try:
                prepared.invoke()
            except Exception:
                pass
            calls = self.transport.call_count
            with self.assertRaises(self.module.ApplePreparationUnavailable):
                prepared.invoke()
            self.assertEqual(self.transport.call_count, calls)
        self.credentials = []
        prepared = self.call()
        self.assertEqual(prepared.invoke(), "credential_missing")
        with self.assertRaises(self.module.ApplePreparationUnavailable):
            prepared.invoke()

    def test_concurrent_invoke_dispatches_only_once(self):
        started, release = threading.Event(), threading.Event()

        def transport(*args):
            started.set()
            self.assertTrue(release.wait(2))
            return 200, b""

        self.transport.side_effect = transport
        prepared = self.call()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(prepared.invoke)
            try:
                self.assertTrue(started.wait(2))
                second = pool.submit(prepared.invoke)
                with self.assertRaises(self.module.ApplePreparationUnavailable):
                    second.result(timeout=2)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=2), "succeeded")
        self.transport.assert_called_once()

    def test_configuration_is_explicit_and_never_opens_cipher(self):
        for changes in (
            {"provider_cipher": object()},
            {"client_id": ""},
            {"client_id": "a b"},
            {"client_secret": "private\nsecret"},
            {"client_secret": "x" * 8193},
            {"revoker": Mock()},
        ):
            with self.assertRaises(self.module.ApplePreparationRejected):
                self.module.AppleErasurePreparation(**dict(self.args, **changes))
        self.assert_no_effect()

    def test_real_executor_retains_fence_and_uncertain_commit_contract(self):
        for failed_commit in (None, 1, 2):
            self.transport.reset_mock()
            state = {"live": 0, "commits": 0}

            @contextmanager
            def transaction():
                state["live"] += 1
                try:
                    yield
                    if state["commits"] + 1 == failed_commit:
                        raise RuntimeError("fictional private commit unknown")
                    state["commits"] += 1
                finally:
                    state["live"] -= 1

            @contextmanager
            def session(engine):
                yield Mock(begin=transaction)

            def transport(*args):
                self.assertEqual(state, {"live": 0, "commits": 1})
                return 200, b""

            self.transport.side_effect = transport
            connect = Mock(side_effect=AssertionError("no database I/O"))
            engine = create_engine("postgresql+psycopg2://", creator=connect)
            try:
                with (
                    patch.object(execution, "Session", session),
                    patch.object(
                        execution, "_connection", return_value=self.connection
                    ),
                    patch.object(
                        execution, "_locked", return_value=(self.job, self.item)
                    ),
                    patch.object(execution, "_target"),
                ):
                    result = execution.ProviderErasureExecutor(
                        engine, self.prepare, clock=lambda: NOW
                    ).execute(job_id=JOB, item_id=ITEM)
            finally:
                engine.dispose()
            connect.assert_not_called()
            self.assertEqual(self.transport.call_count, 0 if failed_commit == 1 else 1)
            if failed_commit == 1:
                self.assertEqual(result.classification, "not_dispatched")
            elif failed_commit == 2:
                self.assertEqual(result.classification, "outcome_unknown")
                self.assertEqual(result.effect_result, "succeeded")
            else:
                self.assertEqual(result.classification, "confirmed")
            self.assertNotIn("private", repr(result))


if __name__ == "__main__":
    unittest.main()
