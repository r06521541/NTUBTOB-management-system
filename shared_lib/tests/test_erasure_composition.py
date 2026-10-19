"""Fictional same-connection plan composition; no database or provider calls."""

import importlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from shared_module.account_erasure_scope import LegacyErasureScope
from shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_module.portal_data import erasure_fulfillment as fulfillment
from shared_module.portal_data.erasure_person_fulfillment import (
    PersonIdentitySnapshot,
    PersonSnapshot,
)
from shared_module.portal_data.erasure_request import CapturedErasureRequestPlan
from shared_module.portal_data.erasure_structured_execution import StructuredInventory
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

JOB = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def connection_fixture():
    connection = MagicMock(spec=Connection)
    connection.in_transaction.return_value = True
    connection.get_transaction.return_value.is_active = True
    connection.get_isolation_level.return_value = "READ COMMITTED"
    connection.connection = SimpleNamespace(
        dbapi_connection=SimpleNamespace(autocommit=False)
    )
    connection.scalars.return_value = ("0018_erasure_privacy_mutation",)
    connection.scalar.return_value = False
    return connection


class InitialPolicyTests(unittest.TestCase):
    def test_approved_initial_deadlines_normalize_request_to_utc(self):
        module = importlib.import_module(
            "shared_module.portal_data.erasure_composition"
        )
        local_request = NOW.astimezone(timezone(timedelta(hours=8)))
        policy = module.ErasurePlanPolicy.initial_request(local_request)
        self.assertEqual(policy.retention_policy_version, 20261019)
        self.assertEqual(policy.fulfillment_due_at, NOW + timedelta(days=30))
        self.assertEqual(policy.receipt_expires_at, NOW + timedelta(days=180))
        self.assertEqual(policy.evidence_expires_at, policy.receipt_expires_at)
        self.assertIs(policy.fulfillment_due_at.tzinfo, timezone.utc)

    def test_invalid_or_unrepresentable_request_time_has_fixed_failure(self):
        module = importlib.import_module(
            "shared_module.portal_data.erasure_composition"
        )
        for value in (
            None,
            "private-invalid-time",
            NOW.replace(tzinfo=None),
            datetime.max.replace(tzinfo=timezone.utc),
        ):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(module.ErasurePlanRejected) as caught:
                    module.ErasurePlanPolicy.initial_request(value)
                self.assertEqual(str(caught.exception), "plan_capture_rejected")


class CaptureConnectionTests(unittest.TestCase):
    def test_actual_connection_branch_preserves_object_and_all_guards(self):
        connection = connection_fixture()
        with patch.object(fulfillment, "acquire_admin_event_locks") as locks:
            self.assertIs(fulfillment._connection(connection), connection)
        locks.assert_called_once_with(connection)
        self.assertEqual(connection.execute.call_count, 2)
        self.assertEqual(connection.scalar.call_count, len(fulfillment.LOCK_TABLES) + 3)
        connection.begin.assert_not_called()
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
        connection.close.assert_not_called()

    def test_connection_requires_existing_active_transaction(self):
        for active, transaction_active in ((False, True), (True, False)):
            connection = connection_fixture()
            connection.in_transaction.return_value = active
            connection.get_transaction.return_value.is_active = transaction_active
            with self.subTest(active=active, transaction_active=transaction_active):
                with self.assertRaisesRegex(ValueError, "clean_transaction_required"):
                    fulfillment._connection(connection)
                connection.execute.assert_not_called()

    def test_session_path_keeps_cleanliness_and_exact_connection(self):
        session = MagicMock(spec=Session)
        session.in_transaction.return_value = True
        session.new, session.dirty, session.deleted = (), (), ()
        connection = connection_fixture()
        session.connection.return_value = connection
        with patch.object(fulfillment, "acquire_admin_event_locks"):
            self.assertIs(fulfillment._connection(session), connection)
        for field in ("new", "dirty", "deleted"):
            setattr(session, field, (object(),))
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "clean_transaction_required"):
                    fulfillment._connection(session)
            setattr(session, field, ())
        session.in_transaction.return_value = False
        with self.assertRaisesRegex(ValueError, "clean_transaction_required"):
            fulfillment._connection(session)
        session.flush.assert_not_called()
        session.commit.assert_not_called()

    def test_connection_never_weakens_isolation_autocommit_revision_or_rls(self):
        variants = (
            ("isolation", "REPEATABLE READ", "read_committed_required"),
            ("autocommit", True, "read_committed_required"),
            ("autocommit", None, "read_committed_required"),
            ("revision", (), "schema_not_ready"),
            (
                "revision",
                ("0018_erasure_privacy_mutation", "other"),
                "schema_not_ready",
            ),
            ("revision", ("unknown",), "schema_not_ready"),
            ("rls", True, "unfiltered_tables_required"),
            ("rls", None, "unfiltered_tables_required"),
        )
        for kind, value, reason in variants:
            connection = connection_fixture()
            if kind == "isolation":
                connection.get_isolation_level.return_value = value
            elif kind == "autocommit":
                connection.connection.dbapi_connection.autocommit = value
            elif kind == "revision":
                connection.scalars.return_value = value
            else:
                connection.scalar.return_value = value
            with self.subTest(kind=kind, value=value):
                with patch.object(fulfillment, "acquire_admin_event_locks"):
                    with self.assertRaisesRegex(ValueError, reason):
                        fulfillment._connection(connection)


class TrustedPlanBuilderTests(unittest.TestCase):
    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def setUp(self):
        self.module = importlib.import_module(
            "shared_module.portal_data.erasure_composition"
        )
        self.connection = connection_fixture()
        self.codec = RestoreBindingCodec(
            namespace=OTHER, active_key="fictional", keys={"fictional": b"F" * 32}
        )
        self.audiences = {"apple": "fictional.apple", "line": "fictional.line"}
        self.policy = self.module.ErasurePlanPolicy(
            retention_policy_version=1,
            fulfillment_due_at=NOW + timedelta(hours=1),
            receipt_expires_at=NOW + timedelta(hours=2),
            evidence_expires_at=NOW + timedelta(hours=3),
        )
        self.review_source = Mock(return_value=())
        self.policy_source = Mock(return_value=self.policy)
        self.builder = self.module.TrustedErasurePlanBuilder(
            review_source=self.review_source,
            policy_source=self.policy_source,
            restore_codec=self.codec,
            provider_audiences=self.audiences,
        )
        self.binding = self.codec.bind(
            provider="apple",
            audience=self.audiences["apple"],
            subject="fictional-private-subject",
            generation=GEN,
        )
        self.pending = fulfillment.PendingIdentitySnapshot(
            11, GEN, "a" * 64, (("access_audit", ()),), self.binding
        )
        self.person = PersonSnapshot(
            7,
            GEN,
            "b" * 64,
            (PersonIdentitySnapshot(11, "apple", OTHER, "c" * 64, self.binding),),
            (),
            (),
            LegacyErasureScope((), (), ()),
            StructuredInventory(7, ((11, OTHER),), (), ()),
            (),
            (),
        )
        self.row = {
            "provider": "apple",
            "person_id": None,
            "status": "pending",
            "generation": GEN,
            "provider_subject": "fictional-private-subject",
        }
        self.connection.execute.return_value.mappings.return_value.first.return_value = (
            self.row
        )
        self.checked = self.start_patch(
            patch.object(self.module, "_connection", side_effect=lambda value: value)
        )
        self.pending_capture = self.start_patch(
            patch.object(
                self.module, "capture_pending_snapshot", return_value=self.pending
            )
        )
        self.person_capture = self.start_patch(
            patch.object(
                self.module, "capture_person_snapshot", return_value=self.person
            )
        )
        self.import_review = self.start_patch(
            patch.object(self.module, "import_person_review", return_value=())
        )

    def values(self, **overrides):
        values = dict(
            connection=self.connection,
            job_id=JOB,
            person_id=None,
            identity_id=11,
            target_generation=GEN,
            requested_at=NOW,
        )
        values.update(overrides)
        return values

    def assert_no_transaction_management(self):
        for name in ("begin", "begin_nested", "commit", "rollback", "close"):
            getattr(self.connection, name).assert_not_called()

    def test_pending_same_connection_explicit_review_binding_and_hash(self):
        result = self.builder(**self.values())
        self.assertIs(type(result), CapturedErasureRequestPlan)
        self.assertIs(result.snapshot, self.pending)
        self.assertEqual(result.metadata.scope_hash, self.pending.scope_hash)
        self.assertEqual(result.metadata.scope_version, fulfillment.SCOPE_VERSION)
        self.assertEqual(
            result.metadata.evidence_expires_at, self.policy.evidence_expires_at
        )
        self.review_source.assert_called_once_with(**self.values())
        self.policy_source.assert_called_once_with(**self.values())
        self.pending_capture.assert_called_once_with(
            self.connection, 11, reviewed_audits=(), restore_binding=self.binding
        )
        self.person_capture.assert_not_called()
        self.import_review.assert_not_called()
        self.assertNotIn("fictional-private-subject", repr(result))
        self.assert_no_transaction_management()

    def test_person_uses_importer_and_existing_multi_identity_capture(self):
        self.review_source.return_value = b"fictional-authorized-private-review"
        result = self.builder(**self.values(person_id=7))
        self.import_review.assert_called_once_with(
            self.connection,
            payload=self.review_source.return_value,
            person_id=7,
            generation=GEN,
        )
        self.person_capture.assert_called_once_with(
            self.connection,
            7,
            reviewed_dispositions=(),
            restore_codec=self.codec,
            provider_audiences=self.audiences,
        )
        self.assertIs(result.snapshot, self.person)
        self.assertEqual(result.metadata.scope_hash, self.person.scope_hash)
        self.pending_capture.assert_not_called()
        self.assert_no_transaction_management()

    def test_absent_or_wrong_review_never_becomes_empty_approval(self):
        for person_id, values in (
            (None, (None, [], b"", False)),
            (7, (None, (), b"", False)),
        ):
            for review in values:
                with self.subTest(person_id=person_id, review=review):
                    self.review_source.return_value = review
                    with self.assertRaises(self.module.ErasurePlanRejected):
                        self.builder(**self.values(person_id=person_id))
        self.pending_capture.assert_not_called()
        self.person_capture.assert_not_called()
        self.import_review.assert_not_called()

    def test_wrong_target_generation_or_initiating_identity_never_returns_plan(self):
        for snapshot in (
            replace(self.pending, generation=OTHER),
            replace(self.pending, identity_id=12),
            self.person,
        ):
            with self.subTest(kind=type(snapshot).__name__):
                self.pending_capture.return_value = snapshot
                with self.assertRaises(self.module.ErasurePlanRejected):
                    self.builder(**self.values())
        self.review_source.return_value = b"fictional-authorized-review"
        for snapshot in (
            replace(self.person, generation=OTHER),
            replace(self.person, person_id=8),
            replace(self.person, identities=()),
            self.pending,
        ):
            self.person_capture.return_value = snapshot
            with self.assertRaises(self.module.ErasurePlanRejected):
                self.builder(**self.values(person_id=7))

    def test_pending_restore_binding_requires_actual_apple_pending_exact_generation(
        self,
    ):
        variants = [None]
        for key, value in (
            ("provider", "line"),
            ("person_id", 7),
            ("status", "linked"),
            ("generation", OTHER),
            ("provider_subject", None),
        ):
            variants.append(dict(self.row, **{key: value}))
        for row in variants:
            self.connection.execute.return_value.mappings.return_value.first.return_value = (
                row
            )
            with self.subTest(row=row):
                with self.assertRaises(self.module.ErasurePlanRejected):
                    self.builder(**self.values())
        self.pending_capture.assert_not_called()

    def test_existing_or_unknown_job_never_recaptures(self):
        for value in (True, None):
            self.connection.scalar.return_value = value
            with self.subTest(value=value):
                with self.assertRaises(self.module.ErasurePlanRejected):
                    self.builder(**self.values())
        self.review_source.assert_not_called()
        self.policy_source.assert_not_called()
        self.pending_capture.assert_not_called()
        self.person_capture.assert_not_called()

    def test_real_pending_capture_checks_explicit_audit_rows_not_default_empty(self):
        self.pending_capture.side_effect = fulfillment.capture_pending_snapshot
        audit_rows = ((5, "d" * 64),)
        with (
            patch.object(
                fulfillment,
                "_identity",
                return_value={"generation": GEN, "digest": "a" * 64},
            ),
            patch.object(
                fulfillment, "_inventory", return_value=(("access_audit", audit_rows),)
            ),
        ):
            # An explicit empty review is not sufficient for nonempty inventory.
            with self.assertRaises(self.module.ErasurePlanRejected):
                self.builder(**self.values())
            self.review_source.return_value = audit_rows
            result = self.builder(**self.values())
        self.assertEqual(result.snapshot.rows, (("access_audit", audit_rows),))
        self.assertEqual(result.metadata.scope_hash, result.snapshot.scope_hash)
        self.assert_no_transaction_management()

    def test_real_person_capture_derives_each_binding_on_same_connection(self):
        from shared_module.portal_data import (
            erasure_person_fulfillment as person_module,
        )
        from shared_module.portal_data import erasure_review_input as review_module

        self.person_capture.side_effect = person_module.capture_person_snapshot
        self.import_review.side_effect = review_module.import_person_review
        self.review_source.return_value = json.dumps(
            {
                "version": 1,
                "person_id": 7,
                "generation": GEN,
                "dispositions": [],
            }
        ).encode()
        identities = ((11, "apple", OTHER, "a" * 64), (12, "line", JOB, "b" * 64))
        roots = ((GEN, "c" * 64), identities)
        subjects = {11: "fictional-private-apple", 12: "fictional-private-line"}
        observed = []

        def scalar(statement, parameters=None):
            if "SELECT provider_subject" in str(statement):
                observed.append(parameters["id"])
                return subjects[parameters["id"]]
            return False

        self.connection.scalar.side_effect = scalar
        inventory = (
            (),
            LegacyErasureScope((), (), ()),
            StructuredInventory(7, ((11, OTHER), (12, JOB)), (), ()),
            (),
        )
        with (
            patch.object(
                person_module, "_capture_roots", return_value=roots
            ) as capture_roots,
            patch.object(
                review_module, "_capture_roots", return_value=roots
            ) as review_roots,
            patch.object(review_module, "_lock"),
            patch.object(person_module, "_inventory", return_value=inventory),
            patch.object(person_module, "_check_reviews"),
        ):
            result = self.builder(**self.values(person_id=7))
        self.assertEqual(observed, [11, 12])
        self.assertEqual(len(result.snapshot.identities), 2)
        for identity in result.snapshot.identities:
            self.assertTrue(
                self.codec.matches(
                    identity.restore_binding,
                    provider=identity.provider,
                    audience=self.audiences[identity.provider],
                    subject=subjects[identity.identity_id],
                    generation=identity.generation,
                )
            )
        self.assertTrue(
            all(
                call.args[0] is self.connection for call in capture_roots.call_args_list
            )
        )
        review_roots.assert_called_once_with(self.connection, 7)
        self.assertEqual(result.metadata.scope_hash, result.snapshot.scope_hash)
        self.assertNotIn("fictional-private", repr(result))
        self.assert_no_transaction_management()

    def test_policy_is_explicit_validated_and_cannot_supply_hash(self):
        for policy in (
            None,
            True,
            {},
            replace(self.policy, retention_policy_version=True),
            replace(self.policy, retention_policy_version=2**31),
            replace(self.policy, fulfillment_due_at=NOW),
            replace(self.policy, receipt_expires_at=NOW),
            replace(self.policy, evidence_expires_at=NOW),
            replace(self.policy, receipt_expires_at=NOW.replace(tzinfo=None)),
        ):
            self.policy_source.return_value = policy
            with self.subTest(policy_type=type(policy).__name__):
                with self.assertRaises(self.module.ErasurePlanRejected):
                    self.builder(**self.values())

    def test_invalid_binding_rejects_before_trusted_callbacks(self):
        for changes in (
            {"job_id": "invalid"},
            {"job_id": JOB.upper().replace("00000000", "AAAAAAAA", 1)},
            {"target_generation": "invalid"},
            {"identity_id": True},
            {"identity_id": 0},
            {"person_id": True},
            {"person_id": 2**63},
            {"requested_at": NOW.replace(tzinfo=None)},
            {"connection": object()},
        ):
            with self.subTest(fields=tuple(changes)):
                with self.assertRaises(self.module.ErasurePlanRejected):
                    self.builder(**self.values(**changes))
        self.review_source.assert_not_called()
        self.policy_source.assert_not_called()

    def test_trusted_source_or_capture_failure_is_fixed_without_private_values(self):
        for target in (self.review_source, self.policy_source, self.pending_capture):
            target.side_effect = RuntimeError(
                "fictional-private-subject private review"
            )
            with self.assertRaises(self.module.ErasurePlanUnavailable) as raised:
                self.builder(**self.values())
            self.assertEqual(str(raised.exception), "plan_capture_unavailable")
            self.assertTrue(raised.exception.__suppress_context__)
            target.side_effect = None
        self.assert_no_transaction_management()

    def test_configuration_has_no_defaults_or_mutable_audience_alias(self):
        self.audiences["apple"] = "different-audience"
        result = self.builder(**self.values())
        self.assertEqual(result.snapshot.restore_binding, self.binding)
        self.assertEqual(
            self.pending_capture.call_args.kwargs["restore_binding"], self.binding
        )
        for changes in (
            {"review_source": None},
            {"policy_source": None},
            {"restore_codec": object()},
            {"provider_audiences": {}},
            {"provider_audiences": {"unknown": "x"}},
            {"provider_audiences": {"apple": ""}},
        ):
            values = dict(
                review_source=self.review_source,
                policy_source=self.policy_source,
                restore_codec=self.codec,
                provider_audiences={"apple": "fictional.apple"},
            )
            values.update(changes)
            with self.assertRaises(self.module.ErasurePlanRejected):
                self.module.TrustedErasurePlanBuilder(**values)


if __name__ == "__main__":
    unittest.main()
