"""Nonblocking intake contracts; no database or provider calls."""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError


class IntakeContractTests(unittest.TestCase):
    def test_intake_constructor_never_requests_human_review(self):
        from shared_module.portal_data.erasure_intake import ErasureIntakeRepository
        from sqlalchemy.engine import Engine

        engine = Mock(spec=Engine)
        policy = Mock(side_effect=AssertionError("no construction I/O"))
        repository = ErasureIntakeRepository(
            engine,
            b"F" * 32,
            policy_source=policy,
            verifier=lambda value: None,
            audience="fictional",
            clock=lambda: datetime(2035, 1, 1, tzinfo=timezone.utc),
        )
        self.assertIs(repository.engine, engine)
        policy.assert_not_called()

    def test_candidate_schema_has_no_placeholder_execution_scope(self):
        from shared_module.portal_data.erasure_intake_models import (
            account_erasure_intakes,
        )

        self.assertNotIn("scope_hash", account_erasure_intakes.c)
        self.assertNotIn("scope_version", account_erasure_intakes.c)
        self.assertIn("materialized_job_id", account_erasure_intakes.c)
        self.assertEqual(
            next(
                iter(account_erasure_intakes.c.materialized_job_id.foreign_keys)
            ).ondelete,
            "RESTRICT",
        )
        constraint = next(
            c
            for c in account_erasure_intakes.constraints
            if c.name == "ck_erasure_intake_materialized"
        )
        self.assertIn("materialized_job_id IS NOT NULL", str(constraint.sqltext))

    def test_existing_nonrequested_legacy_receipt_cannot_be_bypassed(self):
        # The historical DB CHECK currently permits requested only. Keep the
        # defensive boundary without weakening that CHECK in a fixture.
        from shared_module.portal_data import erasure_intake as module
        from sqlalchemy.engine import Engine

        policy = Mock()
        repository = module.ErasureIntakeRepository(
            Mock(spec=Engine),
            b"F" * 32,
            policy_source=policy,
            verifier=lambda value: None,
            audience="fictional",
        )
        connection = Mock()
        person = {"id": 17, "account_generation": str(uuid4())}
        with (
            patch.object(module, "target_row", return_value=None),
            patch.object(module, "_row", return_value={"status": "completed"}),
            self.assertRaisesRegex(
                module.ErasureRequestRejected, "legacy_request_unavailable"
            ),
        ):
            repository._admit(
                connection,
                {"id": 18},
                person,
                datetime(2035, 1, 1, tzinfo=timezone.utc),
            )
        connection.execute.assert_not_called()
        policy.assert_not_called()

    def test_component_intake_is_explicit_strict_boolean_and_construction_only(self):
        from shared_module.portal_data.erasure_components import (
            build_erasure_components,
        )
        from shared_module.portal_data.erasure_intake import ErasureIntakeRepository

        from shared_lib.tests.test_erasure_components import ErasureComponentsTests

        fixture = ErasureComponentsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        historical = build_erasure_components(**fixture.args)
        self.assertIsNone(historical.intake_materializer)
        with self.assertRaisesRegex(ValueError, "intake_not_enabled"):
            historical.materialize(job_id=str(uuid4()), identity_id=1)
        enabled = build_erasure_components(**fixture.args, intake_enabled=True)
        self.assertIs(type(enabled.service.repository), ErasureIntakeRepository)
        self.assertIs(enabled.service.repository, enabled.service.restricted_repository)
        for value in (None, 0, 1, "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_erasure_components(**fixture.args, intake_enabled=value)
        for callback in (
            fixture.connect,
            fixture.policy,
            fixture.review,
            fixture.provider.verify,
        ):
            callback.assert_not_called()

    def test_receipt_routing_is_revision_exact_materialized_and_rls_closed(self):
        from shared_module.portal_data import erasure_intake_routing as module

        connection = Mock()
        identifier = str(uuid4())
        self.assertEqual(
            module.receipt_table(
                connection, identifier, ("0019_erasure_admin_recovery",)
            ),
            module.JOBS,
        )
        connection.execute.assert_not_called()
        connection.scalar.assert_not_called()
        for filtered in (True, None):
            connection.scalar.return_value = filtered
            with self.assertRaisesRegex(SQLAlchemyError, "unfiltered_intake_required"):
                module.receipt_table(connection, identifier, (module.REVISION,))
        connection.scalar.return_value = False
        for status, target in (
            ("requested", module.INTAKES),
            ("verified", module.INTAKES),
            ("cancelled", module.INTAKES),
            ("materialized", module.JOBS),
        ):
            connection.execute.return_value.first.return_value = (status, identifier)
            self.assertEqual(
                module.receipt_table(connection, identifier, (module.REVISION,)), target
            )
        connection.execute.return_value.first.return_value = ("materialized", None)
        with self.assertRaisesRegex(
            SQLAlchemyError, "intake_materialization_unavailable"
        ):
            module.receipt_table(connection, identifier, (module.REVISION,))


if __name__ == "__main__":
    unittest.main()
