"""Offline safety contract; no PostgreSQL connection is made by these tests."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from sqlalchemy.dialects.postgresql import dialect

from tests.portal_data import _fresh_erasure_database as module

BASE = "postgresql+psycopg2://fictional:fictional-secret@127.0.0.1:55433/ntubtob_portal_local"
NAMES = ["ntubtob_erasure_" + str(value) * 32 for value in (1, 2, 3)]
NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)


class FreshErasureDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.engines = []
        self.listeners = {}
        self.connections = {}
        listener = patch(
            "sqlalchemy.event.listen",
            side_effect=lambda engine, name, callback: self.listeners.__setitem__(
                (engine, name), callback
            ),
        )
        listener.start()
        self.addCleanup(listener.stop)
        self.connection = MagicMock()
        self.connection.exec_driver_sql.side_effect = self.execute_ddl
        self.connection.execute.return_value.all.return_value = [(True, None, None)]
        factory = patch.object(module, "create_engine", side_effect=self.make_engine)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        names = patch.object(
            module, "uuid4", side_effect=[UUID(str(i) * 32) for i in (1, 2, 3)]
        )
        names.start()
        self.addCleanup(names.stop)

    def make_engine(self, url, **kwargs):
        engine = MagicMock()
        engine.url = url
        engine.dialect = dialect()
        engine.pool.checkedout.return_value = 0
        engine.connect.return_value.__enter__.return_value = self.connection
        self.connections[engine] = []

        def dispose():
            self.events.append(("dispose", url.database))
            for dbapi, record in self.connections[engine]:
                callback = self.listeners.get((engine, "close"))
                if callback:
                    callback(dbapi, record)
                dbapi.close()
            self.connections[engine].clear()

        engine.dispose.side_effect = dispose
        self.engines.append(engine)
        return engine

    def execute_ddl(self, sql):
        self.events.append(("ddl", sql))

    def backend(self, engine, pid, started=None):
        started = started or datetime(2035, 1, 1, tzinfo=timezone.utc)
        dbapi = MagicMock()
        dbapi.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            pid,
            started,
        )
        record = SimpleNamespace(info={})
        callback = self.listeners.get((engine, "connect"))
        if callback:
            callback(dbapi, record)
        self.connections[engine].append((dbapi, record))
        return dbapi, record

    def session_rows(self, *snapshots):
        snapshots = iter(snapshots)

        def observe(statement, parameters):
            self.events.append(("check", parameters["name"]))
            rows = next(snapshots)
            return SimpleNamespace(
                all=lambda: rows,
                one_or_none=lambda: (True, sum(row[1] is not None for row in rows)),
            )

        self.connection.execute.side_effect = observe

    def manager(self):
        return module.FreshErasureDatabases(BASE)

    def template(self, manager):
        initialize = Mock(
            side_effect=lambda engine: self.events.append(("init", engine.url.database))
        )
        self.assertIsNone(manager.create_template(initialize))
        initialize.assert_called_once_with(self.engines[-1])
        return self.engines[-1]

    def assert_safe(self, error, operation):
        self.assertIsInstance(error, module.FreshDatabaseError)
        self.assertEqual(error.operation, operation)
        self.assertNotIn(BASE, str(error))
        self.assertNotIn("fictional-secret", str(error))
        self.assertNotIn("private-cause", str(error))
        self.assertTrue(error.__suppress_context__)

    def test_constructor_rejects_noncanonical_or_query_targets_before_engine(self):
        invalid = (
            None,
            "",
            BASE + "?host=remote.example",
            BASE + "?options=-csearch_path=public",
            BASE.replace("127.0.0.1", "portal-postgres"),
            BASE.replace("127.0.0.1", "remote.example"),
            BASE.replace("ntubtob_portal_local", "postgres"),
            BASE.replace("postgresql+psycopg2", "sqlite"),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(module.FreshDatabaseError) as caught:
                    module.FreshErasureDatabases(value)
                self.assert_safe(caught.exception, "validate_url")
        self.factory.assert_not_called()

    def test_constructor_uses_validator_fixed_base_and_does_not_connect(self):
        original = module.require_local_database_url
        with patch.object(
            module, "require_local_database_url", wraps=original
        ) as validate:
            manager = self.manager()
        validate.assert_called_once_with(BASE)
        self.assertEqual(
            self.factory.call_args.args[0].database, "ntubtob_portal_local"
        )
        self.assertEqual(self.factory.call_args.kwargs["isolation_level"], "AUTOCOMMIT")
        self.engines[0].connect.assert_not_called()
        self.assertEqual(manager.close(), ())
        self.assertEqual(self.events, [("dispose", "ntubtob_portal_local")])

    def test_template_is_initialized_once_then_clones_are_distinct(self):
        manager = self.manager()
        with self.assertRaises(module.FreshDatabaseError):
            manager.clone()
        self.template(manager)
        first, second = manager.clone(), manager.clone()
        self.assertIsNot(first, second)
        self.assertEqual([engine.url.database for engine in self.engines[1:]], NAMES)
        self.assertEqual(
            self.events[:3],
            [
                ("ddl", f"CREATE DATABASE {NAMES[0]} TEMPLATE template0"),
                ("init", NAMES[0]),
                ("dispose", NAMES[0]),
            ],
        )
        self.assertEqual(
            [entry for entry in self.events if entry[0] == "ddl"],
            [
                (
                    "ddl",
                    f"CREATE DATABASE {name} TEMPLATE {NAMES[0] if i else 'template0'}",
                )
                for i, name in enumerate(NAMES)
            ],
        )
        for call in self.factory.call_args_list[1:]:
            self.assertNotIn("isolation_level", call.kwargs)
        with self.assertRaises(module.FreshDatabaseError):
            manager.create_template(Mock())

    def test_release_disposes_then_checks_owner_and_connections_then_drops(self):
        manager = self.manager()
        self.template(manager)
        clone = manager.clone()
        self.events.clear()
        self.connection.execute.side_effect = lambda statement, parameters: (
            self.events.append(("check", parameters["name"])),
            SimpleNamespace(all=lambda: [(True, None, None)]),
        )[1]
        manager.release(clone)
        self.assertEqual(
            self.events,
            [
                ("dispose", NAMES[1]),
                ("check", NAMES[1]),
                ("ddl", f"DROP DATABASE {NAMES[1]}"),
            ],
        )
        sql = str(self.connection.execute.call_args.args[0])
        self.assertIn("pg_catalog.pg_database", sql)
        self.assertIn("CURRENT_USER", sql)
        self.assertIn("pg_catalog.pg_stat_activity", sql)
        self.assertNotIn("FORCE", self.events[-1][1])
        self.assertNotIn("IF EXISTS", self.events[-1][1])
        with self.assertRaises(module.FreshDatabaseError):
            manager.release(clone)

    def test_release_never_accepts_base_or_foreign_engine_with_matching_url(self):
        manager = self.manager()
        template = self.template(manager)
        foreign = MagicMock(url=template.url)
        for engine in (self.engines[0], foreign, object()):
            with self.subTest(engine=type(engine)):
                with self.assertRaises(module.FreshDatabaseError) as caught:
                    manager.release(engine)
                self.assert_safe(caught.exception, "release_unowned")
        foreign.dispose.assert_not_called()
        self.assertFalse(
            any("DROP" in value for kind, value in self.events if kind == "ddl")
        )

    def test_unknown_create_is_not_dropped_or_retried(self):
        manager = self.manager()
        self.connection.exec_driver_sql.side_effect = RuntimeError(
            "private-cause fictional-secret"
        )
        initialize = Mock()
        with self.assertRaises(module.FreshDatabaseError) as caught:
            manager.create_template(initialize)
        self.assert_safe(caught.exception, "create")
        initialize.assert_not_called()
        self.assertEqual(manager.close(), ())
        self.assertEqual(self.connection.exec_driver_sql.call_count, 1)
        self.connection.execute.assert_not_called()

    def test_engine_failure_keeps_known_database_but_none_is_not_an_owned_engine(self):
        manager = self.manager()
        with patch.object(
            module, "create_engine", side_effect=RuntimeError("private-cause")
        ):
            with self.assertRaises(module.FreshDatabaseError) as caught:
                manager.create_template(Mock())
        self.assert_safe(caught.exception, "engine")
        with self.assertRaises(module.FreshDatabaseError):
            manager.release(None)
        self.assertEqual(manager.close(), ())
        self.assertEqual(self.events[-2], ("ddl", f"DROP DATABASE {NAMES[0]}"))

    def test_failed_initialization_is_not_cloneable_but_known_database_is_cleaned(self):
        manager = self.manager()
        with self.assertRaises(module.FreshDatabaseError) as caught:
            manager.create_template(Mock(side_effect=RuntimeError("private-cause")))
        self.assert_safe(caught.exception, "initialize")
        with self.assertRaises(module.FreshDatabaseError):
            manager.clone()
        self.engines[1].dispose.assert_called_once_with()
        self.assertEqual(manager.close(), ())
        self.assertEqual(self.events[-2], ("ddl", f"DROP DATABASE {NAMES[0]}"))

    def test_drop_preflight_unknown_owner_or_wrong_types_preserves_database(self):
        for rows in (
            [],
            [(False, None, None)],
            [(True, 1)],
            [(True, 1, None)],
            [(1, None, None)],
            [(True, False, NOW)],
            [(True, 1, NOW.replace(tzinfo=None))],
            [(True, None, None), (True, 101, NOW)],
        ):
            with self.subTest(rows=rows):
                # A fresh manager has a fresh internal name, never a caller's name.
                with patch.object(module, "uuid4", return_value=UUID("4" * 32)):
                    manager = self.manager()
                    manager.create_template(Mock())
                engine = self.engines[-1]
                self.connection.execute.return_value.all.return_value = rows
                before = self.connection.exec_driver_sql.call_count
                with self.assertRaises(module.FreshDatabaseError) as caught:
                    manager.release(engine)
                self.assert_safe(caught.exception, "drop_preflight")
                errors = manager.close()
                self.assertEqual(errors, (caught.exception,))
                self.assertEqual(self.connection.exec_driver_sql.call_count, before)

    def test_cleanup_attempts_clones_before_template_and_keeps_secondary_errors(self):
        manager = self.manager()
        self.template(manager)
        first, second = manager.clone(), manager.clone()
        self.events.clear()

        def fail_drop(sql):
            self.events.append(("ddl", sql))
            if sql == f"DROP DATABASE {second.url.database}":
                raise RuntimeError("private-cause")

        self.connection.exec_driver_sql.side_effect = fail_drop
        errors = manager.close()
        self.assertEqual(len(errors), 1)
        self.assert_safe(errors[0], "drop")
        self.assertEqual(
            [value for kind, value in self.events if kind == "ddl"],
            [f"DROP DATABASE {name}" for name in reversed(NAMES)],
        )
        self.assertEqual(self.events[-1], ("dispose", "ntubtob_portal_local"))
        calls = self.connection.exec_driver_sql.call_count
        self.assertEqual(manager.close(), errors)
        self.assertEqual(self.connection.exec_driver_sql.call_count, calls)
        with self.assertRaises(module.FreshDatabaseError):
            manager.clone()
        with self.assertRaises(module.FreshDatabaseError):
            manager.release(first)

    def test_dispose_failure_never_attempts_drop_and_does_not_mask_primary(self):
        manager = self.manager()
        primary = RuntimeError("fictional-primary")
        with self.assertRaises(module.FreshDatabaseError) as caught:
            manager.create_template(Mock(side_effect=primary))
        self.engines[-1].dispose.side_effect = RuntimeError("private-cause")
        errors = manager.close()
        self.assert_safe(caught.exception, "initialize")
        self.assert_safe(errors[0], "dispose")
        self.connection.execute.assert_not_called()
        self.assertEqual(self.connection.exec_driver_sql.call_count, 1)

    def test_joined_race_connections_drain_only_after_owned_dbapi_close(self):
        manager = self.manager()
        self.template(manager)
        engine = manager.clone()
        started = datetime(2035, 1, 1, tzinfo=timezone.utc)
        backends = [self.backend(engine, pid, started)[0] for pid in (101, 102, 103)]
        self.session_rows(
            [(True, pid, started) for pid in (101, 102, 103)],
            [(True, 102, started)],
            [(True, None, None)],
        )
        self.events.clear()
        with (
            patch.object(module, "monotonic", create=True, side_effect=(0, 1, 2)),
            patch.object(module, "sleep", create=True) as sleep,
        ):
            manager.release(engine)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            self.events,
            [
                ("dispose", NAMES[1]),
                ("check", NAMES[1]),
                ("check", NAMES[1]),
                ("check", NAMES[1]),
                ("ddl", f"DROP DATABASE {NAMES[1]}"),
            ],
        )
        for dbapi in backends:
            dbapi.close.assert_called_once_with()
            dbapi.rollback.assert_called_once_with()
            cursor = dbapi.cursor.return_value.__enter__.return_value
            self.assertIn("backend_start", cursor.execute.call_args.args[0])
            self.assertIn("pg_backend_pid()", cursor.execute.call_args.args[0])
            dbapi.cursor.return_value.__exit__.assert_called_once()

    def test_foreign_or_reused_pid_refuses_immediately_without_drop_or_sleep(self):
        started = datetime(2035, 1, 1, tzinfo=timezone.utc)
        for pid, observed_start in (
            (999, started),
            (101, started + timedelta(seconds=1)),
        ):
            with self.subTest(pid=pid):
                with patch.object(module, "uuid4", return_value=UUID("4" * 32)):
                    manager = self.manager()
                    manager.create_template(Mock())
                engine = self.engines[-1]
                self.backend(engine, 101, started)
                self.session_rows([(True, pid, observed_start)])
                before = self.connection.exec_driver_sql.call_count
                with patch.object(module, "sleep", create=True) as sleep:
                    with self.assertRaises(module.FreshDatabaseError) as caught:
                        manager.release(engine)
                self.assert_safe(caught.exception, "other_sessions")
                sleep.assert_not_called()
                self.assertEqual(self.connection.exec_driver_sql.call_count, before)
                self.assertEqual(manager.close(), (caught.exception,))

    def test_owned_close_timeout_keeps_fixed_cause_and_never_retries_drop(self):
        manager = self.manager()
        engine = self.template(manager)
        started = datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.backend(engine, 101, started)
        self.session_rows([(True, 101, started)])
        before = self.connection.exec_driver_sql.call_count
        with (
            patch.object(module, "monotonic", create=True, side_effect=(0, 5)),
            patch.object(module, "sleep", create=True) as sleep,
        ):
            with self.assertRaises(module.FreshDatabaseError) as caught:
                manager.release(engine)
        self.assert_safe(caught.exception, "owned_close_timeout")
        sleep.assert_not_called()
        self.assertEqual(self.connection.exec_driver_sql.call_count, before)
        self.assertEqual(manager.close(), (caught.exception,))

    def test_checked_out_or_unknown_pool_state_never_disposes_or_queries(self):
        for value in (1, -1, True, None):
            with self.subTest(value=value):
                with patch.object(module, "uuid4", return_value=UUID("4" * 32)):
                    manager = self.manager()
                    engine = self.template(manager)
                engine.dispose.reset_mock()
                engine.pool.checkedout.return_value = value
                self.connection.execute.reset_mock()
                with self.assertRaises(module.FreshDatabaseError) as caught:
                    manager.release(engine)
                self.assert_safe(caught.exception, "connections_checked_out")
                engine.dispose.assert_not_called()
                self.connection.execute.assert_not_called()

    def test_caller_dispose_before_release_preserves_exact_close_identity(self):
        manager = self.manager()
        engine = self.template(manager)
        dbapi, _ = self.backend(engine, 101, NOW)
        engine.dispose()
        self.session_rows([(True, 101, NOW)], [(True, None, None)])
        with (
            patch.object(module, "monotonic", side_effect=(0, 1)),
            patch.object(module, "sleep") as sleep,
        ):
            manager.release(engine)
        sleep.assert_called_once_with(0.05)
        dbapi.close.assert_called_once_with()
        self.assertEqual(self.events[-1], ("ddl", f"DROP DATABASE {NAMES[0]}"))

    def test_drain_rechecks_owner_before_drop(self):
        manager = self.manager()
        engine = self.template(manager)
        self.backend(engine, 101, NOW)
        self.session_rows([(True, 101, NOW)], [(False, None, None)])
        before = self.connection.exec_driver_sql.call_count
        with (
            patch.object(module, "monotonic", side_effect=(0, 1)),
            patch.object(module, "sleep") as sleep,
        ):
            with self.assertRaises(module.FreshDatabaseError) as caught:
                manager.release(engine)
        self.assert_safe(caught.exception, "drop_preflight")
        sleep.assert_called_once_with(0.05)
        self.assertEqual(self.connection.exec_driver_sql.call_count, before)

    def test_backend_identity_read_failure_rolls_back_and_has_fixed_error(self):
        manager = self.manager()
        engine = self.template(manager)
        for row in ((True, NOW), (1, NOW.replace(tzinfo=None)), (1, None), None):
            dbapi = MagicMock()
            dbapi.cursor.return_value.__enter__.return_value.fetchone.return_value = row
            with self.assertRaises(module.FreshDatabaseError) as caught:
                self.listeners[(engine, "connect")](dbapi, SimpleNamespace(info={}))
            self.assert_safe(caught.exception, "connection_identity")
            dbapi.rollback.assert_called_once_with()
            dbapi.cursor.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
