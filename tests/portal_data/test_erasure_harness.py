"""No-connection regressions for disposable retained-0014 test cleanup."""

import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.engine import make_url

from tests.portal_data import _account_deletion_test_harness as deletion
from tests.portal_data import _apple_lifecycle_test_harness as apple
from tests.portal_data import _erasure_ledger_test_harness as ledger
from tests.portal_data import _event_guest_lifecycle_test_harness as events
from tests.portal_data import _persistent_admin_authority_test_harness as authority
from tests.portal_data import test_migration_readiness as readiness

REVISION = "0014_account_erasure_ledger"
PREVIOUS = "0013_account_deletion_requests"
LOCAL = "postgresql://fictional@127.0.0.1:65432/ntubtob_portal_local"
OBJECTS = (
    ("table", "account_erasure_jobs", "r"),
    ("table", "account_erasure_steps", "r"),
    ("function", "guard_erasure_job", "trigger"),
    ("function", "reject_erasure_evidence_mutation", "trigger"),
)


class ErasureHarnessTests(unittest.TestCase):
    def test_empty_native_heads_downgrade_on_same_transaction_before_old_inventory(
        self,
    ):
        for start in ("0019_erasure_admin_recovery", "0020_erasure_intake"):
            with self.subTest(start=start):
                engine, connection = self.fixture(
                    start,
                    generations=ledger.GENERATION_OBJECTS,
                    cancellations=ledger.CANCELLATION_OBJECTS,
                    attempts=ledger.ATTEMPT_OBJECTS,
                    items=ledger.ITEM_OBJECTS,
                )
                connection.scalars.return_value.all.side_effect = [
                    (start,),
                    (ledger.PRIVACY_REVISION,),
                ]
                order = []

                def downgrade(config, target):
                    self.assertIs(config.attributes["connection"], connection)
                    self.assertEqual(target, ledger.PRIVACY_REVISION)
                    connection.begin.assert_called_once_with()
                    self.assertEqual(self.ddl(connection), [])
                    order.append("native")

                def inventory(actual_connection, revision):
                    self.assertIs(actual_connection, connection)
                    self.assertEqual(revision, ledger.PRIVACY_REVISION)
                    self.assertEqual(order, ["native"])
                    order.append("inventory")
                    return True

                with (
                    patch("alembic.command.downgrade", side_effect=downgrade) as native,
                    patch.object(
                        ledger, "_sealed_plan_inventory", side_effect=inventory
                    ),
                    patch.object(ledger, "_privacy_inventory", return_value=True),
                    patch.object(ledger, "_remove_privacy_schema"),
                ):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                native.assert_called_once()
                self.assertEqual(order, ["native", "inventory"])
                self.assertIn(
                    "WHERE version_num = '0018_erasure_privacy_mutation'",
                    self.ddl(connection)[-1],
                )
                self.assertNotIn("CASCADE", " ".join(self.ddl(connection)))
                connection.commit.assert_not_called()
                engine.begin.assert_not_called()

    def test_native_retention_rejection_never_reaches_legacy_cleanup(self):
        for start, reason in (
            ("0020_erasure_intake", "intake_history_retained"),
            ("0020_erasure_intake", "intake_unfiltered_required"),
            ("0020_erasure_intake", "recovery_history_retained"),
            ("0019_erasure_admin_recovery", "recovery_history_retained"),
        ):
            with self.subTest(start=start, reason=reason):
                engine, connection = self.fixture(start)
                with (
                    patch(
                        "alembic.command.downgrade", side_effect=RuntimeError(reason)
                    ) as native,
                    patch.object(ledger, "_sealed_plan_inventory") as inventory,
                    self.assertRaisesRegex(RuntimeError, reason),
                ):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                native.assert_called_once()
                inventory.assert_not_called()
                self.assertEqual(self.ddl(connection), [])
                self.assertIs(
                    connection.begin.return_value.__exit__.call_args.args[0],
                    RuntimeError,
                )

    def test_native_downgrade_must_report_exact_single_0018_marker(self):
        for after in (
            (),
            ("0019_erasure_admin_recovery",),
            ("0020_erasure_intake",),
            ("0021_future",),
            (ledger.PRIVACY_REVISION, "other"),
        ):
            with self.subTest(after=after):
                engine, connection = self.fixture("0020_erasure_intake")
                connection.scalars.return_value.all.side_effect = [
                    ("0020_erasure_intake",),
                    after,
                ]
                with (
                    patch("alembic.command.downgrade") as native,
                    patch.object(ledger, "_sealed_plan_inventory") as inventory,
                    self.assertRaisesRegex(RuntimeError, "native downgrade revision"),
                ):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                native.assert_called_once()
                inventory.assert_not_called()
                self.assertEqual(self.ddl(connection), [])

    def test_native_dispatch_rejects_unknown_multibranch_and_nontransactional_driver(
        self,
    ):
        for revision, autocommit in (
            ("0021_future", False),
            ("0020_erasure_intake_extra", False),
            (("0020_erasure_intake", "0019_erasure_admin_recovery"), False),
            ("0020_erasure_intake", True),
            ("0020_erasure_intake", None),
        ):
            with self.subTest(revision=revision, autocommit=autocommit):
                engine, connection = self.fixture(revision)
                connection.connection.dbapi_connection.autocommit = autocommit
                with patch("alembic.command.downgrade") as native:
                    with self.assertRaises(RuntimeError):
                        ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                            engine
                        )
                native.assert_not_called()
                self.assertEqual(self.ddl(connection), [])

    def test_upstream_dispatches_exact_native_heads_and_never_falls_through_refusal(
        self,
    ):
        for module, entrypoint, callback, after in (
            (
                deletion,
                "remove_retained_account_deletion_requests_from_isolated_test_database",
                "remove_retained_erasure_ledger_from_isolated_test_database",
                PREVIOUS,
            ),
            (
                authority,
                "remove_retained_admin_authority_from_isolated_test_database",
                "remove_retained_account_deletion_requests_from_isolated_test_database",
                "0012_persistent_admin_authority",
            ),
            (
                events,
                "prepare_event_guest_lifecycle_downgrade_for_isolated_test_database",
                "remove_retained_admin_authority_from_isolated_test_database",
                "0011_event_notification_guest_lifecycle",
            ),
        ):
            for start in ("0019_erasure_admin_recovery", "0020_erasure_intake"):
                for rejected in (False, True):
                    with self.subTest(
                        module=module.__name__, start=start, rejected=rejected
                    ):
                        engine, connection = self.fixture(start)
                        connection.scalars.return_value.all.side_effect = [
                            (start,),
                            (after,),
                        ]
                        inspector = MagicMock()
                        inspector.has_table.return_value = True
                        with (
                            patch.object(module, "inspect", return_value=inspector),
                            patch.object(
                                module,
                                callback,
                                side_effect=(
                                    RuntimeError("history_retained")
                                    if rejected
                                    else None
                                ),
                            ) as lower,
                        ):
                            if rejected:
                                with self.assertRaisesRegex(
                                    RuntimeError, "history_retained"
                                ):
                                    getattr(module, entrypoint)(engine)
                                engine.begin.assert_not_called()
                            else:
                                getattr(module, entrypoint)(engine)
                                engine.begin.assert_called_once_with()
                        lower.assert_called_once_with(engine)

    def test_sealed_plan_missing_partial_future_inventory_never_reaches_ddl(self):
        for revision, rows in (
            (ledger.PRIVACY_REVISION, ()),
            (ledger.PRIVACY_REVISION, tuple(ledger.PLAN_OBJECTS)[:-1]),
            ("0019_unknown", tuple(ledger.PLAN_OBJECTS)),
            ("0012_persistent_admin_authority", tuple(ledger.PLAN_OBJECTS)),
            (
                ledger.PRIVACY_REVISION,
                (*ledger.PLAN_OBJECTS, next(iter(ledger.PLAN_OBJECTS))),
            ),
        ):
            with self.subTest(revision=revision, size=len(rows)):
                connection = MagicMock()
                connection.execute.return_value.all.return_value = rows
                with self.assertRaisesRegex(RuntimeError, "complete exact"):
                    ledger._sealed_plan_inventory(connection, revision)
                self.assertEqual(self.ddl(connection), [])

    def test_sealed_plan_is_dropped_before_privacy_and_parent_without_cascade(self):
        engine, connection = self.fixture(
            ledger.PRIVACY_REVISION,
            generations=ledger.GENERATION_OBJECTS,
            cancellations=ledger.CANCELLATION_OBJECTS,
            attempts=ledger.ATTEMPT_OBJECTS,
            items=ledger.ITEM_OBJECTS,
        )
        with (
            patch.object(ledger, "_sealed_plan_inventory", return_value=True),
            patch.object(ledger, "_privacy_inventory", return_value=True),
            patch.object(ledger, "_remove_privacy_schema") as privacy,
        ):
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        statements = self.ddl(connection)
        self.assertEqual(
            statements[:4],
            [
                "DROP TRIGGER erasure_sealed_plan_job_binding ON ntubtob.account_erasure_jobs",
                "DROP TABLE ntubtob.account_erasure_sealed_plans",
                "DROP FUNCTION ntubtob.guard_erasure_sealed_plan()",
                "DROP FUNCTION ntubtob.guard_erasure_sealed_plan_job_binding()",
            ],
        )
        privacy.assert_called_once_with(connection)
        self.assertNotIn("CASCADE", " ".join(statements))

    def fixture(
        self,
        revision=REVISION,
        objects=OBJECTS,
        marker=True,
        generations=(),
        cancellations=(),
        attempts=(),
        items=(),
    ):
        engine = MagicMock()
        engine.url = make_url(LOCAL)
        connection = engine.connect.return_value.__enter__.return_value
        connection.scalar.return_value = marker
        connection.scalars.return_value.all.return_value = (
            (revision,) if isinstance(revision, str) else revision
        )
        connection.execute.return_value.all.return_value = list(objects)
        connection.execute.side_effect = lambda statement: (
            MagicMock(all=lambda: [])
            if "privacy_inventory" in str(statement)
            or "sealed_plan_inventory" in str(statement)
            else (
                MagicMock(all=lambda: list(items))
                if "item_inventory" in str(statement)
                else (
                    MagicMock(all=lambda: list(cancellations))
                    if "cancellation_inventory" in str(statement)
                    else (
                        MagicMock(all=lambda: list(attempts))
                        if "attempt_inventory" in str(statement)
                        else (
                            MagicMock(all=lambda: list(generations))
                            if "generation_inventory" in str(statement)
                            else connection.execute.return_value
                        )
                    )
                )
            )
        )
        connection.execute.return_value.rowcount = 1
        connection.connection.dbapi_connection.autocommit = False
        return engine, connection

    def test_complete_items_removed_before_parent_and_unknown_inventory_rejected(self):
        inventory = (
            ("table", "account_erasure_items", "r"),
            ("table", "account_erasure_item_events", "r"),
            ("function", "guard_erasure_item", "trigger"),
            ("function", "guard_erasure_item_event", "trigger"),
            ("trigger", "erasure_item_insert_guard", "7"),
            ("trigger", "erasure_item_immutable", "58"),
            ("trigger", "erasure_item_event_insert_guard", "7"),
            ("trigger", "erasure_item_event_append_only", "58"),
        )
        for items in (inventory, inventory[:-1], ()):
            engine, connection = self.fixture(
                "0017_erasure_work_items",
                generations=ledger.GENERATION_OBJECTS,
                cancellations=ledger.CANCELLATION_OBJECTS,
                attempts=ledger.ATTEMPT_OBJECTS,
                items=items,
            )
            if items != inventory:
                with self.assertRaises(RuntimeError):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                self.assertEqual(self.ddl(connection), [])
                continue
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
            statements = self.ddl(connection)
            self.assertEqual(
                statements[:2],
                [
                    "DROP TABLE ntubtob.account_erasure_item_events",
                    "DROP TABLE ntubtob.account_erasure_items",
                ],
            )
            self.assertNotIn("CASCADE", " ".join(statements))

    def test_0016_and_retained_pair_are_removed_by_existing_table_drop(self):
        for revision in (
            "0016_erasure_cancellation",
            "0015_account_generations",
            REVISION,
            PREVIOUS,
        ):
            engine, connection = self.fixture(
                revision,
                generations=ledger.GENERATION_OBJECTS,
                cancellations=ledger.CANCELLATION_OBJECTS,
            )
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
            statements = self.ddl(connection)
            self.assertIn("DROP TABLE ntubtob.account_erasure_jobs", statements)
            self.assertNotIn("cancelled_at", " ".join(statements))
            self.assertNotIn("CASCADE", " ".join(statements))

    def test_complete_attempt_inventory_is_dropped_before_job(self):
        engine, connection = self.fixture(
            "0016_erasure_cancellation",
            generations=ledger.GENERATION_OBJECTS,
            cancellations=ledger.CANCELLATION_OBJECTS,
            attempts=ledger.ATTEMPT_OBJECTS,
        )
        ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        statements = self.ddl(connection)
        self.assertEqual(
            statements[0], "DROP TABLE ntubtob.account_erasure_request_attempts"
        )
        self.assertEqual(
            statements[1], "DROP FUNCTION ntubtob.guard_erasure_request_attempt()"
        )
        self.assertNotIn("CASCADE", " ".join(statements))

    def test_partial_or_unexpected_attempt_inventory_never_mutates(self):
        objects = tuple(ledger.ATTEMPT_OBJECTS)
        variants = [objects[:i] + objects[i + 1 :] for i in range(len(objects))]
        variants += [
            objects + (objects[0],),
            (("table", "account_erasure_request_attempts", "v"),),
        ]
        for objects in variants:
            engine, connection = self.fixture(
                "0016_erasure_cancellation",
                generations=ledger.GENERATION_OBJECTS,
                cancellations=ledger.CANCELLATION_OBJECTS,
                attempts=objects,
            )
            with self.assertRaises(RuntimeError):
                ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                    engine
                )
            self.assertEqual(self.ddl(connection), [])

    def test_cancellation_partial_wrong_nullable_type_stale_or_missing_rejects(self):
        for revision, columns, generations in (
            ("0016_erasure_cancellation", (), ledger.GENERATION_OBJECTS),
            ("0016_erasure_cancellation", ledger.CANCELLATION_OBJECTS, ()),
            (REVISION, ledger.CANCELLATION_OBJECTS[:1], ledger.GENERATION_OBJECTS),
            (
                REVISION,
                (("cancelled_at", "unexpected"), ledger.CANCELLATION_OBJECTS[1]),
                ledger.GENERATION_OBJECTS,
            ),
            (
                "0012_persistent_admin_authority",
                ledger.CANCELLATION_OBJECTS,
                ledger.GENERATION_OBJECTS,
            ),
            (REVISION, ledger.CANCELLATION_OBJECTS * 2, ledger.GENERATION_OBJECTS),
        ):
            engine, connection = self.fixture(
                revision, generations=generations, cancellations=columns
            )
            with self.assertRaises(RuntimeError):
                ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                    engine
                )
            self.assertEqual(self.ddl(connection), [])

    def statements(self, connection):
        return [str(call.args[0]) for call in connection.execute.call_args_list]

    def ddl(self, connection):
        return [
            sql
            for sql in self.statements(connection)
            if sql.startswith(("DROP", "UPDATE", "ALTER", "TRUNCATE"))
        ]

    def test_exact_0014_drops_children_then_roots_functions_then_marker(self):
        engine, connection = self.fixture()
        ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        statements = self.ddl(connection)
        self.assertEqual(
            statements[:4],
            [
                "DROP TABLE ntubtob.account_erasure_steps",
                "DROP TABLE ntubtob.account_erasure_jobs",
                "DROP FUNCTION ntubtob.guard_erasure_job()",
                "DROP FUNCTION ntubtob.reject_erasure_evidence_mutation()",
            ],
        )
        self.assertEqual(len(statements), 5)
        self.assertIn(
            "SET version_num = '0013_account_deletion_requests'", statements[-1]
        )
        self.assertIn(
            "WHERE version_num = '0014_account_erasure_ledger'", statements[-1]
        )
        self.assertNotIn("CASCADE", " ".join(statements))
        self.assertIn("FOR UPDATE", str(connection.scalars.call_args.args[0]))
        connection.begin.assert_called_once_with()
        engine.begin.assert_not_called()

    def test_0015_and_retained_generations_removed_before_ledger(self):
        for revision in ("0015_account_generations", REVISION, PREVIOUS):
            engine, connection = self.fixture(
                revision, generations=ledger.GENERATION_OBJECTS
            )
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
            statements = self.ddl(connection)
            self.assertIn(
                "DROP TRIGGER person_account_generation_guard ON ntubtob.people",
                statements[0],
            )
            self.assertIn("DROP COLUMN account_generation", statements[4])
            self.assertIn("DROP TABLE ntubtob.account_erasure_steps", statements[6])
            self.assertNotIn("CASCADE", " ".join(statements))

    def test_incomplete_or_stale_generation_inventory_never_mutates(self):
        for revision, generations in (
            ("0015_account_generations", ()),
            (REVISION, ledger.GENERATION_OBJECTS[:-1]),
            ("0012_persistent_admin_authority", ledger.GENERATION_OBJECTS),
        ):
            engine, connection = self.fixture(revision, generations=generations)
            with self.assertRaises(RuntimeError):
                ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                    engine
                )
            self.assertEqual(self.ddl(connection), [])

    def test_each_missing_wrong_or_duplicate_generation_object_rejected(self):
        objects = ledger.GENERATION_OBJECTS
        for index in range(len(objects)):
            variants = (
                objects[:index] + objects[index + 1 :],
                objects + (objects[index],),
                objects[:index]
                + ((objects[index][0], objects[index][1], "unexpected"),)
                + objects[index + 1 :],
            )
            for variant in variants:
                engine, connection = self.fixture(
                    "0015_account_generations", generations=variant
                )
                with self.assertRaises(RuntimeError):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                self.assertEqual(self.ddl(connection), [])

    def test_generation_drop_failure_never_rewinds_or_removes_ledger(self):
        engine, connection = self.fixture(
            "0015_account_generations", generations=ledger.GENERATION_OBJECTS
        )
        original = connection.execute.side_effect

        def execute(statement):
            if str(statement).startswith("ALTER TABLE ntubtob.people"):
                raise RuntimeError("fictional restrictive dependency")
            return original(statement)

        connection.execute.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, "restrictive dependency"):
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        self.assertFalse(
            any(s.startswith(("DROP TABLE", "UPDATE")) for s in self.ddl(connection))
        )
        self.assertIs(
            connection.begin.return_value.__exit__.call_args.args[0], RuntimeError
        )

    def test_exact_0013_retained_objects_are_removed_without_marker_rewrite(self):
        engine, connection = self.fixture(PREVIOUS)
        ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        self.assertEqual(len(self.ddl(connection)), 4)
        self.assertNotIn("UPDATE", " ".join(self.ddl(connection)))

    def test_known_older_or_fresh_empty_schema_is_noop(self):
        for revision, marker in (
            (PREVIOUS, True),
            ("0012_persistent_admin_authority", True),
            ("0001_legacy_baseline", True),
            ((), False),
        ):
            with self.subTest(revision=revision):
                engine, connection = self.fixture(revision, (), marker)
                ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                    engine
                )
                self.assertEqual(self.ddl(connection), [])

    def test_unknown_empty_multibranch_or_stale_marker_never_drops(self):
        for revision, marker, objects in (
            ("0015_unknown", True, OBJECTS),
            ("0015_unknown", True, ()),
            ((), True, OBJECTS),
            ((REVISION, "branch"), True, OBJECTS),
            ("0012_persistent_admin_authority", True, OBJECTS),
            ((), False, OBJECTS),
            (REVISION, True, ()),
        ):
            with self.subTest(revision=revision, marker=marker):
                engine, connection = self.fixture(revision, objects, marker)
                with self.assertRaises(RuntimeError):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                self.assertEqual(self.ddl(connection), [])

    def test_partial_wrong_kind_and_overloaded_objects_never_drop(self):
        variants = [
            OBJECTS[:index] + OBJECTS[index + 1 :] for index in range(len(OBJECTS))
        ]
        variants.extend(
            (
                OBJECTS + (("function", "guard_erasure_job", "unexpected"),),
                (("table", "account_erasure_jobs", "v"),) + OBJECTS[1:],
            )
        )
        for revision in (REVISION, PREVIOUS):
            for objects in variants:
                with self.subTest(revision=revision, objects=objects):
                    engine, connection = self.fixture(revision, objects)
                    with self.assertRaises(RuntimeError):
                        ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                            engine
                        )
                    self.assertEqual(self.ddl(connection), [])

    def test_url_overrides_and_non_local_targets_are_rejected_before_connecting(self):
        urls = (
            LOCAL + "?host=remote.example.invalid",
            LOCAL + "?hostaddr=192.0.2.1",
            LOCAL + "?service=not-local",
            LOCAL + "?dbname=production",
            LOCAL + "?application_name=harmless-but-not-allowlisted",
            "postgresql://fictional@remote.example.invalid/ntubtob_portal_local",
            "postgresql://fictional@localhost/production",
            "sqlite:///ntubtob_portal_local",
        )
        for url in urls:
            with self.subTest(url=url):
                engine = MagicMock()
                engine.url = make_url(url)
                with self.assertRaisesRegex(RuntimeError, "isolated test database"):
                    ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                        engine
                    )
                engine.connect.assert_not_called()
                engine.begin.assert_not_called()

    def test_drop_failure_rolls_back_and_does_not_rewind_marker(self):
        engine, connection = self.fixture()
        result = connection.execute.return_value

        def execute(statement):
            if any(
                name in str(statement)
                for name in (
                    "privacy_inventory",
                    "sealed_plan_inventory",
                    "generation_inventory",
                    "cancellation_inventory",
                    "attempt_inventory",
                    "item_inventory",
                )
            ):
                return MagicMock(all=lambda: [])
            if str(statement) == "DROP TABLE ntubtob.account_erasure_jobs":
                raise RuntimeError("fictional restrictive dependency")
            return result

        connection.execute.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, "restrictive dependency"):
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        self.assertEqual(len(self.ddl(connection)), 2)
        self.assertFalse(
            any(sql.startswith("UPDATE") for sql in self.statements(connection))
        )
        self.assertIs(
            connection.begin.return_value.__exit__.call_args.args[0], RuntimeError
        )
        connection.commit.assert_not_called()

    def test_real_autocommit_or_unknown_driver_state_rejected_before_ddl(self):
        for autocommit in (True, None):
            engine, connection = self.fixture()
            connection.connection.dbapi_connection.autocommit = autocommit
            with (
                self.subTest(autocommit=autocommit),
                self.assertRaisesRegex(RuntimeError, "transactional connection"),
            ):
                ledger.remove_retained_erasure_ledger_from_isolated_test_database(
                    engine
                )
            self.assertEqual(self.ddl(connection), [])

    def test_unexpected_marker_update_count_rolls_back(self):
        engine, connection = self.fixture()
        connection.execute.return_value.rowcount = 0
        with self.assertRaisesRegex(RuntimeError, "marker changed"):
            ledger.remove_retained_erasure_ledger_from_isolated_test_database(engine)
        self.assertIs(
            connection.begin.return_value.__exit__.call_args.args[0], RuntimeError
        )

    def test_receipt_cleanup_orders_0014_before_0013_and_rechecks_marker(self):
        for starting_revision in (
            "0018_erasure_privacy_mutation",
            "0017_erasure_work_items",
            "0016_erasure_cancellation",
            "0015_account_generations",
            REVISION,
            PREVIOUS,
        ):
            engine, connection = self.fixture(starting_revision)
            connection.scalars.return_value.all.side_effect = [
                (starting_revision,),
                (PREVIOUS,),
            ]
            inspector = MagicMock()
            inspector.has_table.return_value = True
            order = []
            context = engine.begin.return_value
            engine.begin.side_effect = lambda: (order.append("0013") or context)
            with (
                patch.object(deletion, "inspect", return_value=inspector),
                patch.object(
                    deletion,
                    "remove_retained_erasure_ledger_from_isolated_test_database",
                    side_effect=lambda _engine: order.append("0014"),
                ) as cleanup,
            ):
                deletion.remove_retained_account_deletion_requests_from_isolated_test_database(
                    engine
                )
            self.assertEqual(order, ["0014", "0013"])
            cleanup.assert_called_once_with(engine)

    def test_admin_and_event_cleanup_route_exact_0014_through_existing_chain(self):
        for module, cleanup_name, callback_name, after in (
            (
                authority,
                "remove_retained_admin_authority_from_isolated_test_database",
                "remove_retained_account_deletion_requests_from_isolated_test_database",
                "0012_persistent_admin_authority",
            ),
            (
                events,
                "prepare_event_guest_lifecycle_downgrade_for_isolated_test_database",
                "remove_retained_admin_authority_from_isolated_test_database",
                "0011_event_notification_guest_lifecycle",
            ),
        ):
            engine, connection = self.fixture("0018_erasure_privacy_mutation")
            connection.scalars.return_value.all.side_effect = [
                ("0018_erasure_privacy_mutation",),
                (after,),
            ]
            inspector = MagicMock()
            inspector.has_table.return_value = True
            with (
                patch.object(module, "inspect", return_value=inspector),
                patch.object(module, callback_name) as callback,
            ):
                getattr(module, cleanup_name)(engine)
            callback.assert_called_once_with(engine)
            engine.begin.assert_called_once_with()

    def test_readiness_reset_cleans_retained_ledger_before_legacy_reset(self):
        case = readiness.MigrationReadinessPostgresTests(
            "test_clean_artifact_creates_marker_and_fail_closed_rls"
        )
        case.engine = MagicMock()
        order = []
        context = case.engine.begin.return_value
        case.engine.begin.side_effect = lambda: (order.append("legacy") or context)
        with patch.object(
            readiness,
            "remove_retained_erasure_ledger_from_isolated_test_database",
            side_effect=lambda _engine: order.append("0014"),
        ) as cleanup:
            case._reset_to_clean_baseline()
        self.assertEqual(order, ["0014", "legacy"])
        cleanup.assert_called_once_with(case.engine)

    def test_readiness_does_not_fall_through_to_legacy_reset_on_guard_failure(self):
        case = readiness.MigrationReadinessPostgresTests(
            "test_clean_artifact_creates_marker_and_fail_closed_rls"
        )
        case.engine = MagicMock()
        with patch.object(
            readiness,
            "remove_retained_erasure_ledger_from_isolated_test_database",
            side_effect=RuntimeError("unknown revision"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unknown revision"):
                case._reset_to_clean_baseline()
        case.engine.begin.assert_not_called()

    def test_existing_destructive_harness_entrypoints_reject_query_overrides(self):
        for module, name in (
            (apple, "remove_retained_apple_evidence_from_isolated_test_database"),
            (
                deletion,
                "remove_retained_account_deletion_requests_from_isolated_test_database",
            ),
            (authority, "remove_retained_admin_authority_from_isolated_test_database"),
            (
                events,
                "prepare_event_guest_lifecycle_downgrade_for_isolated_test_database",
            ),
        ):
            engine = MagicMock()
            engine.url = make_url(LOCAL + "?service=not-local")
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(RuntimeError, "isolated test database"),
            ):
                getattr(module, name)(engine)
            engine.connect.assert_not_called()
            engine.begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
