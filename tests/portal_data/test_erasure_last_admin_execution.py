"""Exact durable last-admin authority; fresh one-shot fictional database only.

LAST_ADMIN_ERASURE_TEST_DATABASE_URL has no fallback. The database must initially
lack ntubtob. Committed0019 operation/pointer/history are retained; cleanup only
closes/disposes. Main destroys the explicit disposable container after inspection.
Provider/custody ports remain fictional; this is not live recovery or resume.
"""

import os
import unittest
from datetime import timedelta
from unittest.mock import Mock, call, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from shared_lib.shared_module.account_erasure_scope import LegacyErasureScope
from shared_lib.shared_module.erasure_restore_binding import RestoreBinding
from shared_lib.shared_module.portal_data import erasure_person_fulfillment as module
from shared_lib.shared_module.portal_data.erasure_management_guard import (
    AppliedAdminSuspension,
    ManagementGuardUnavailable,
    ManagementWritesSuspended,
    require_management_writes_available,
)
from shared_lib.shared_module.portal_data.erasure_structured_execution import (
    StructuredInventory,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_person_fulfillment as fixture
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

DATABASE_URL = os.environ.get("LAST_ADMIN_ERASURE_TEST_DATABASE_URL")
JOB = "11111111-1111-4111-8111-111111111111"
GENERATION = "22222222-2222-4222-8222-222222222222"
OPERATION = "33333333-3333-4333-8333-333333333333"
BINDING = dict(job_id=JOB, generation=GENERATION, scope_hash="a" * 64)


class LastAdminBindingTests(unittest.TestCase):
    def setUp(self):
        self.connection = Mock()
        self.connection.scalar.return_value = False
        self.connection.execute.return_value.all.return_value = [(1, "persistent", 11)]

    def check(self):
        return module._require_admin_survivor(self.connection, 7, **BINDING)

    def reader(self, **kwargs):
        return patch.object(
            module, "read_applied_admin_suspension", create=True, **kwargs
        )

    def test_exact_zero_reads_same_connection_and_all_required_bindings_every_time(
        self,
    ):
        applied = AppliedAdminSuspension(OPERATION, JOB, GENERATION, "a" * 64, 11)
        with (
            patch.object(module, "Session"),
            patch.object(
                module.IdentityLifecycleRepository,
                "_reachable_persistent_admin_count",
                return_value=0,
            ),
            self.reader(return_value=applied) as reader,
        ):
            self.check()
            self.check()
        self.assertEqual(reader.call_args_list, [call(self.connection, **BINDING)] * 2)

    def test_positive_survivor_never_needs_or_uses_a_recovery_approval(self):
        with (
            patch.object(module, "Session"),
            patch.object(
                module.IdentityLifecycleRepository,
                "_reachable_persistent_admin_count",
                return_value=1,
            ),
            self.reader() as reader,
        ):
            self.check()
        reader.assert_not_called()

    def test_invalid_or_failed_count_cannot_fall_back_to_recovery(self):
        for value in (None, False, True, -1, 0.0, "0"):
            with (
                self.subTest(value=value),
                patch.object(module, "Session"),
                patch.object(
                    module.IdentityLifecycleRepository,
                    "_reachable_persistent_admin_count",
                    return_value=value,
                ),
                self.reader() as reader,
                self.assertRaisesRegex(ValueError, "^admin_authority_unavailable$"),
            ):
                self.check()
            reader.assert_not_called()
        with (
            patch.object(module, "Session"),
            patch.object(
                module.IdentityLifecycleRepository,
                "_reachable_persistent_admin_count",
                side_effect=module.AuthorizationError("fictional-private-error"),
            ),
            self.reader() as reader,
            self.assertRaisesRegex(
                ValueError, "^admin_authority_unavailable$"
            ) as caught,
        ):
            self.check()
        reader.assert_not_called()
        self.assertIsNone(caught.exception.__cause__)

    def test_unavailable_or_wrong_durable_binding_is_fixed_recovery_required(self):
        with (
            patch.object(module, "Session"),
            patch.object(
                module.IdentityLifecycleRepository,
                "_reachable_persistent_admin_count",
                return_value=0,
            ),
            self.reader(
                side_effect=ManagementGuardUnavailable("fictional-private-binding")
            ) as reader,
            self.assertRaisesRegex(ValueError, "^admin_recovery_required$") as caught,
        ):
            self.check()
        reader.assert_called_once_with(self.connection, **BINDING)
        self.assertIsNone(caught.exception.__cause__)

    def test_execution_context_arguments_are_mandatory_but_capture_never_reads_approval(
        self,
    ):
        for function in (module._roots, module._require_admin_survivor):
            with self.subTest(function=function.__name__), self.assertRaises(TypeError):
                function(self.connection, 7)
        self.connection.execute.side_effect = [
            Mock(**{"first.return_value": (GENERATION, "digest", "admin")}),
            Mock(**{"all.return_value": [(1, "persistent", 11)]}),
            [(8, "apple", GENERATION, "identity-digest")],
        ]
        with self.reader() as reader:
            self.assertEqual(
                module._capture_roots(self.connection, 7)[0], (GENERATION, "digest")
            )
        reader.assert_not_called()

    def context(self):
        identity = module.PersonIdentitySnapshot(
            8,
            "apple",
            GENERATION,
            "identity-digest",
            RestoreBinding(1, "fictional", "b" * 64),
        )
        snapshot = module.PersonSnapshot(
            7,
            GENERATION,
            "digest",
            (identity,),
            tuple((table, ()) for table in module.ROW_TABLES),
            (),
            LegacyErasureScope((), (), ()),
            StructuredInventory(7, (), (), ()),
            (),
            (),
        )
        job = dict(
            status="verified",
            target_kind="person",
            person_id=7,
            auth_identity_id=None,
            expected_generation=GENERATION,
            scope_version=1,
            scope_hash=snapshot.scope_hash,
            verified_at=fixture.NOW,
        )
        self.connection.execute.return_value.mappings.return_value.first.return_value = (
            job
        )
        self.connection.execute.return_value.mappings.return_value.all.return_value = []
        executor = module.PersonFulfillment(Mock(spec=Engine), Mock(), Mock())
        return snapshot, job, executor

    def test_original_job_status_and_binding_fail_before_roots_or_approval(self):
        for field, value, reason in (
            ("status", "requested", "verified_job_required"),
            ("status", "cancelled", "verified_job_required"),
            ("status", "online_completed", "receipt_read_required"),
            ("person_id", 9, "scope_changed"),
            ("expected_generation", JOB, "scope_changed"),
            ("scope_hash", "f" * 64, "scope_changed"),
        ):
            with self.subTest(field=field, value=value):
                snapshot, job, executor = self.context()
                job[field] = value
                with patch.object(module, "_roots") as roots, self.reader() as reader:
                    with self.assertRaisesRegex(ValueError, "^" + reason + "$"):
                        executor._context_on(self.connection, JOB, snapshot)
                roots.assert_not_called()
                reader.assert_not_called()

    def test_both_execution_roots_checks_receive_original_validated_context(self):
        snapshot, _, executor = self.context()
        roots_result = (
            (GENERATION, "digest"),
            ((8, "apple", GENERATION, "identity-digest"),),
        )
        with (
            patch.object(module, "_roots", return_value=roots_result) as roots,
            patch.object(
                module,
                "_inventory",
                return_value=(
                    snapshot.rows,
                    snapshot.legacy,
                    snapshot.structured,
                    snapshot.local_ids,
                ),
            ),
            patch.object(module, "_specs", return_value={}),
        ):
            executor._context_on(self.connection, JOB, snapshot)
        self.assertEqual(
            roots.call_args_list,
            [
                call(
                    self.connection,
                    7,
                    job_id=JOB,
                    generation=GENERATION,
                    scope_hash=snapshot.scope_hash,
                )
            ]
            * 2,
        )


def _migrate(connection, revision):
    config = Config(str(fixture.ledger.ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


def _prepare_new_database(url):
    engine = create_engine(
        require_local_database_url(url), connect_args={"connect_timeout": 5}
    )
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT to_regnamespace('ntubtob')")) is not None:
                raise RuntimeError("fresh last-admin database required")
            connection.execute(text(LEGACY_FIXTURE_SQL))
            _migrate(connection, "0018_erasure_privacy_mutation")
    finally:
        engine.dispose()


def _require_empty_fixture(engine):
    # The old fixture reset is unnecessary after the mandatory fresh-schema
    # check. Replace only that test reset with read-only emptiness evidence.
    with engine.connect() as connection:
        if (
            connection.scalar(text("SELECT count(*) FROM ntubtob.account_erasure_jobs"))
            != 0
            or connection.scalar(
                text(
                    "SELECT to_regclass('ntubtob.account_erasure_admin_recovery_operations')"
                )
            )
            is not None
        ):
            raise RuntimeError("fresh last-admin fixture required")


@unittest.skipUnless(DATABASE_URL, "fresh last-admin database URL not configured")
class LastAdminExecutionPostgresTests(
    fixture._PersonFulfillmentFixture, unittest.TestCase
):
    configure_target = fixture.LastAdminIntakePostgresTests.configure_target

    def setUp(self):
        url = require_local_database_url(DATABASE_URL)
        _prepare_new_database(url)
        with (
            patch.object(fixture.ledger, "DATABASE_URL", url),
            patch.object(
                fixture,
                "remove_retained_erasure_ledger_from_isolated_test_database",
                _require_empty_fixture,
            ),
        ):
            super().setUp()
        with self.engine.begin() as connection:
            _migrate(connection, "0019_erasure_admin_recovery")

    def cleanup_fixture(self):
        # No old cleanup, downgrade, history deletion or authority restoration.
        connection = getattr(getattr(self, "fixture", None), "connection", None)
        if connection is not None:
            connection.close()

    def test_exact_approval_purges_last_admin_without_resuming_or_redispatching(self):
        result = self.execute()
        self.assertEqual(result.reason, "admin_recovery_required", result)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.calls, 0)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_items WHERE job_id=:id",
                id=self.job_id,
            ),
            0,
        )
        operation = str(uuid4())
        with self.engine.begin() as connection:
            epoch = connection.scalar(
                text("SELECT epoch FROM ntubtob.portal_authority_state")
            )
            wrong = connection.begin_nested()
            try:
                with self.assertRaises(DBAPIError):
                    connection.execute(
                        text(
                            "SELECT ntubtob.suspend_management_for_erasure(CAST(:job AS uuid),CAST(:generation AS uuid),:epoch,CAST(:operation AS uuid))"
                        ),
                        dict(
                            job=self.job_id,
                            generation=str(uuid4()),
                            epoch=epoch,
                            operation=operation,
                        ),
                    )
            finally:
                wrong.rollback()
            connection.execute(
                text(
                    "SELECT ntubtob.suspend_management_for_erasure(CAST(:job AS uuid),CAST(:generation AS uuid),:epoch,CAST(:operation AS uuid))"
                ),
                dict(
                    job=self.job_id,
                    generation=self.snapshot.generation,
                    epoch=epoch,
                    operation=operation,
                ),
            )
            evidence = dict(
                connection.execute(
                    text(
                        "SELECT * FROM ntubtob.account_erasure_admin_recovery_operations"
                    )
                )
                .mappings()
                .one()
            )

        for changed in (
            dict(job_id=str(uuid4())),
            dict(generation=str(uuid4())),
            dict(scope_hash="f" * 64),
        ):
            with (
                self.subTest(changed=tuple(changed)),
                self.engine.begin() as connection,
            ):
                binding = dict(
                    job_id=self.job_id,
                    generation=self.snapshot.generation,
                    scope_hash=self.snapshot.scope_hash,
                )
                binding.update(changed)
                with self.assertRaisesRegex(ValueError, "^admin_recovery_required$"):
                    module._require_admin_survivor(
                        connection, self.fixture.person, **binding
                    )

        # A transient legal cancellation is checked on its own actual transaction;
        # rollback preserves the original verified job for this one-shot scenario.
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_jobs SET status='cancelled',person_id=NULL,cancelled_at=:now,updated_at=:now WHERE id=:id"
                    ),
                    dict(now=fixture.NOW + timedelta(seconds=1), id=self.job_id),
                )
                with self.assertRaisesRegex(ValueError, "^verified_job_required$"):
                    self.executor._context_on(connection, self.job_id, self.snapshot)
            finally:
                transaction.rollback()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.calls, 0)

        # All historical complete-scope/other-owner/shared-content/receipt/replay
        # assertions execute unchanged, against the real committed executor.
        fixture.PersonFulfillmentPostgresTests.test_two_provider_person_online_completion_preserves_other_person_and_shared_content(
            self
        )
        with self.engine.begin() as connection:
            self.assertEqual(
                dict(
                    connection.execute(
                        text(
                            "SELECT * FROM ntubtob.account_erasure_admin_recovery_operations"
                        )
                    )
                    .mappings()
                    .one()
                ),
                evidence,
            )
            self.assertEqual(
                tuple(
                    connection.execute(
                        text(
                            "SELECT epoch,management_suspension_operation_id::text FROM ntubtob.portal_authority_state"
                        )
                    ).one()
                ),
                (epoch + 1, operation),
            )
            with self.assertRaises(ManagementWritesSuspended):
                require_management_writes_available(connection)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.people WHERE portal_access_level='admin'"
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.account_erasure_admin_recovery_operations"
            ),
            1,
        )


class LastAdminFixtureSafetyTests(unittest.TestCase):
    def test_existing_schema_rejects_without_mutation_and_still_disposes(self):
        engine = Mock()
        connection = Mock()
        connection.scalar.return_value = "ntubtob"
        engine.begin.return_value = Mock(
            __enter__=Mock(return_value=connection), __exit__=Mock(return_value=False)
        )
        with (
            patch(__name__ + ".create_engine", return_value=engine),
            patch(__name__ + "._migrate") as migrate,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^fresh last-admin database required$"
            ):
                _prepare_new_database(
                    "postgresql://fictional@127.0.0.1/ntubtob_portal_local"
                )
        connection.execute.assert_not_called()
        migrate.assert_not_called()
        engine.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
