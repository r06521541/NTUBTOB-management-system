"""Candidate0019 admission; historical safety assertions remain unchanged.

Intake/guard cases upgrade inside their original rollback-only connection.
Committed executor fixtures retain real independent transaction/commit evidence;
their native empty-only0019 downgrade MUST succeed before any historical cleanup.
The nine composition scenarios instead clone a fresh candidate template per case;
they never rewind shared schema or remove individual immutable evidence rows.
No suspension operation is created here and no last-admin exception is granted.
Provider, policy and custody ports remain explicitly fictional, not live evidence.
"""

import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.portal_data import test_erasure_components_integration as components
from tests.portal_data import test_erasure_fulfillment as pending
from tests.portal_data import test_erasure_guard as guard
from tests.portal_data import test_erasure_legacy_execution as legacy
from tests.portal_data import test_erasure_person_fulfillment as person
from tests.portal_data import test_erasure_plan_store as custody
from tests.portal_data import test_erasure_privacy_execution as privacy
from tests.portal_data import test_erasure_provider_execution as provider
from tests.portal_data import test_erasure_request as request
from tests.portal_data import test_erasure_restricted_request as restricted
from tests.portal_data import test_erasure_structured_execution as structured
from tests.portal_data import test_erasure_verification as verification
from tests.portal_data._fresh_erasure_database import FreshErasureDatabases
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

CANDIDATE = "0019_erasure_admin_recovery"
PREVIOUS = "0018_erasure_privacy_mutation"
MODULES = (
    "erasure_request",
    "erasure_restricted_request",
    "erasure_verification",
    "erasure_guard",
    "erasure_plan_store",
    "erasure_fulfillment",
    "erasure_person_fulfillment",
    "erasure_provider_execution",
    "erasure_legacy_execution",
    "erasure_structured_execution",
    "erasure_privacy_execution",
)


def _migrate(connection, revision, *, downgrade=False):
    config = Config(str(pending.ledger.ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    (command.downgrade if downgrade else command.upgrade)(config, revision)


class _RollbackCandidate:
    def setUp(self):
        super().setUp()
        connection = getattr(self, "connection", None)
        if connection is None:
            connection = self.fixture.connection
        self.assertTrue(connection.in_transaction())
        _migrate(connection, CANDIDATE)
        self.assertEqual(
            tuple(
                connection.scalars(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                )
            ),
            (CANDIDATE,),
        )


class _CommittedCandidate:
    """Never let old fixture cleanup discard unexpected0019 operation history."""

    def setUp(self):
        self._candidate_active = False
        self._candidate_cleanup_refused = False
        super().setUp()
        with self.engine.begin() as connection:
            _migrate(connection, CANDIDATE)
        self._candidate_active = True

    def addCleanup(self, function, *args, **kwargs):
        # Every inherited cleanup is gated, including separately registered row
        # cleanup callbacks. A refused downgrade is recorded once; no old cleanup
        # callback or retry follows it. Closing the pool is still safe.
        super().addCleanup(self._candidate_cleanup, function, args, kwargs)

    def _candidate_cleanup(self, function, args, kwargs):
        if self._candidate_cleanup_refused:
            return
        if self._candidate_active:
            try:
                with self.engine.begin() as connection:
                    _migrate(connection, PREVIOUS, downgrade=True)
            except Exception:
                self._candidate_cleanup_refused = True
                self.engine.dispose()
                raise
            self._candidate_active = False
        function(*args, **kwargs)


# Keep all inherited negative assertions, including stale proof/generation,
# filtered RLS, cancelled intent, custody failure and transaction rollback.
class CandidateRequestTests(_RollbackCandidate, request.RequestPostgresTests):
    pass


class CandidateRequestCustodyTests(
    _RollbackCandidate, request.RequestCustodyPostgresTests
):
    pass


class CandidateRestrictedTests(
    _RollbackCandidate, restricted.RestrictedRequestPostgresTests
):
    pass


class CandidateRestrictedCustodyTests(
    _RollbackCandidate, restricted.RestrictedCustodyPostgresTests
):
    pass


class CandidateVerificationTests(
    _RollbackCandidate, verification.ErasureVerificationPostgresTests
):
    pass


class CandidateGuardTests(_RollbackCandidate, guard.ErasureGuardPostgresTests):
    pass


class CandidateSealedSchemaTests(
    _RollbackCandidate, custody.SealedPlanSchemaPostgresTests
):
    pass


# These tests really commit their fences before fake provider/custody effects.
# Their existing observers and restart assertions are not replaced with savepoints.
class CandidateProviderTests(
    _CommittedCandidate, provider.ProviderExecutionPostgresTests
):
    pass


class CandidateLegacyTests(_CommittedCandidate, legacy.LegacyExecutionPostgresTests):
    pass


class CandidateStructuredTests(
    _CommittedCandidate, structured.StructuredExecutionPostgresTests
):
    pass


class CandidatePrivacyTests(_CommittedCandidate, privacy.PrivacyExecutionPostgresTests):
    pass


class CandidatePendingTests(
    _CommittedCandidate, pending.PendingFulfillmentPostgresTests
):
    pass


class CandidatePersonTests(_CommittedCandidate, person.PersonFulfillmentPostgresTests):
    pass


class CandidateAdminTests(
    _CommittedCandidate, person.PersonAdminFulfillmentPostgresTests
):
    pass


class CandidateLastAdminIntakeTests(
    _CommittedCandidate, person.LastAdminIntakePostgresTests
):
    pass


class CandidateComponentsTests(components.ErasureComponentsIntegrationTests):
    """Same nine committed scenarios, each in its own fresh candidate database."""

    @classmethod
    def setUpClass(cls):
        cls.databases = FreshErasureDatabases(pending.ledger.DATABASE_URL)
        cls.addClassCleanup(cls.close_databases)

        def initialize(engine):
            with engine.begin() as connection:
                connection.execute(text(LEGACY_FIXTURE_SQL))
                _migrate(connection, CANDIDATE)

        cls.databases.create_template(initialize)

    @classmethod
    def close_databases(cls):
        errors = cls.databases.close()
        if errors:
            raise AssertionError("fresh_database_cleanup_incomplete", errors)

    def create_fixture_engine(self):
        engine = self.databases.clone()
        self.addCleanup(self.databases.release, engine)
        return engine

    def prepare_fixture_schema(self):
        with self.engine.connect() as connection:
            self.assertEqual(
                tuple(
                    connection.scalars(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    )
                ),
                (CANDIDATE,),
            )

    def cleanup_fixture(self):
        # Row/evidence cleanup is unnecessary in this fixture's owned database.
        # Preserve real independent commits; release drops only the generated DB.
        transaction = getattr(self.fixture, "transaction", None)
        connection = getattr(self.fixture, "connection", None)
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        if connection is not None and not connection.closed:
            connection.close()


class CandidateRequestUnitTests(request.RequestTests):
    def setUp(self):
        super().setUp()
        self.connection.scalars.return_value.all.return_value = [CANDIDATE]

    def test_retained_cancelled_job_on_old_revision_cannot_renew(self):
        # This historical case specifically concerns pre-cancellation0015, not
        # the candidate's supported detached-cancelled-intent renewal behavior.
        self.connection.scalars.return_value.all.return_value = [
            "0015_account_generations"
        ]
        super().test_retained_cancelled_job_on_old_revision_cannot_renew()


class CandidateVerificationUnitTests(verification.ErasureVerificationTests):
    def setUp(self):
        super().setUp()
        self.connection.scalars.return_value.all.return_value = [CANDIDATE]


class CandidateGuardUnitTests(guard.ErasureGuardTests):
    def fixture(self, **values):
        session, connection = super().fixture(**values)
        connection.scalars.return_value.all.return_value = [CANDIDATE]
        return session, connection


class CandidatePlanStoreUnitTests(custody.PlanStoreTests):
    def configure(self):
        super().configure()
        self.connection.scalars.return_value.__iter__.side_effect = lambda: iter(
            (CANDIDATE,)
        )
        self.connection.scalars.return_value.all.return_value = [CANDIDATE]


class CandidateAdmissionContractTests(unittest.TestCase):
    def test_fresh_components_preserves_every_original_scenario(self):
        loader = unittest.TestLoader()
        expected = loader.getTestCaseNames(components.ErasureComponentsIntegrationTests)
        self.assertEqual(len(expected), 9)
        self.assertEqual(loader.getTestCaseNames(CandidateComponentsTests), expected)
        self.assertFalse(issubclass(CandidateComponentsTests, _CommittedCandidate))

    def test_fresh_components_checks_revision_without_rewinding_schema(self):
        case = CandidateComponentsTests("runTest")
        case.engine = MagicMock()
        connection = case.engine.connect.return_value.__enter__.return_value
        connection.scalars.return_value = (CANDIDATE,)
        with (
            patch(__name__ + "._migrate") as migrate,
            patch.object(
                components, "remove_retained_erasure_ledger_from_isolated_test_database"
            ) as rewind,
        ):
            case.prepare_fixture_schema()
        migrate.assert_not_called()
        rewind.assert_not_called()

    def test_fresh_components_cleanup_only_closes_fixture_connection(self):
        case = CandidateComponentsTests("runTest")
        case.engine = Mock()
        case.fixture = Mock()
        case.fixture.transaction.is_active = True
        case.fixture.connection.closed = False
        case.cleanup_fixture()
        case.fixture.transaction.rollback.assert_called_once()
        case.fixture.connection.close.assert_called_once()
        case.engine.begin.assert_not_called()

    def test_every_revision_predicate_adds_exact_candidate_not_unknown_or_multihead(
        self,
    ):
        root = (
            Path(__file__).resolve().parents[2] / "shared_lib/shared_module/portal_data"
        )
        for name in MODULES:
            with self.subTest(module=name):
                predicates = []
                for node in ast.walk(
                    ast.parse((root / (name + ".py")).read_text(encoding="utf-8"))
                ):
                    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                        continue
                    try:
                        values = ast.literal_eval(node.comparators[0])
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(values, tuple):
                        continue
                    if values == (PREVIOUS,):
                        accepted = (values,)
                    elif (PREVIOUS,) in values:
                        accepted = values
                    else:
                        continue
                    predicates.append(accepted)
                    self.assertIn((CANDIDATE,), accepted, (name, node.lineno))
                    self.assertIn((PREVIOUS,), accepted)
                    self.assertNotIn((), accepted)
                    self.assertNotIn(("0020_unknown",), accepted)
                    self.assertNotIn((CANDIDATE, PREVIOUS), accepted)
                    self.assertNotIn((CANDIDATE, CANDIDATE), accepted)
                    self.assertTrue(
                        all(type(row) is tuple and len(row) == 1 for row in accepted)
                    )
                self.assertTrue(predicates, name)

    def test_refused_downgrade_never_runs_old_cleanup_or_retries(self):
        case = CandidatePersonTests("runTest")
        case.engine = Mock()
        case.engine.begin.return_value = Mock(
            __enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False)
        )
        case._candidate_active = True
        case._candidate_cleanup_refused = False
        cleanup = Mock()
        with patch(
            __name__ + "._migrate",
            side_effect=RuntimeError("recovery_history_retained"),
        ) as migrate:
            with self.assertRaisesRegex(RuntimeError, "recovery_history_retained"):
                case._candidate_cleanup(cleanup, (), {})
            case._candidate_cleanup(cleanup, (), {})
        cleanup.assert_not_called()
        migrate.assert_called_once()
        case.engine.dispose.assert_called_once()

    def test_cleanup_requires_native_downgrade_before_original_callback(self):
        case = CandidatePersonTests("runTest")
        connection = Mock()
        case.engine = Mock()
        case.engine.begin.return_value = Mock(
            __enter__=Mock(return_value=connection), __exit__=Mock(return_value=False)
        )
        case._candidate_active = True
        case._candidate_cleanup_refused = False
        order = []
        with patch(
            __name__ + "._migrate",
            side_effect=lambda *a, **k: order.append("downgrade"),
        ) as migrate:
            case._candidate_cleanup(lambda: order.append("cleanup"), (), {})
        self.assertEqual(order, ["downgrade", "cleanup"])
        migrate.assert_called_once_with(connection, PREVIOUS, downgrade=True)
        self.assertFalse(case._candidate_active)


if __name__ == "__main__":
    unittest.main()
