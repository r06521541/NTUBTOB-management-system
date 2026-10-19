"""Execution-lock lifecycle probes with fictional request keys only."""

import unittest
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import IdempotencyConflict
from shared_module.portal_data.mobile_repository import MobileRepository


class IdempotencyExecutionLockTests(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock()
        self.connection = self.engine.connect.return_value.__enter__.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.scalar.return_value = True
        self.repo = MobileRepository(self.engine)
        self.values = dict(
            session_id="fake", method="PUT", route="/fake", key_hash="fake"
        )

    def test_success_detaches_and_exception_closes_owner_without_retry(self):
        with self.assertRaisesRegex(RuntimeError, "fictional"):
            with self.repo._idempotency_execution_lock(self.values):
                self.connection.detach.assert_called_once()
                raise RuntimeError("fictional")
        self.engine.connect.assert_called_once()
        self.engine.connect.return_value.__exit__.assert_called_once()
        self.connection.begin.return_value.__exit__.assert_called_once()

    def test_body_hash_does_not_change_serialization_key(self):
        keys = []
        for body in ("first", "different"):
            with self.repo._idempotency_execution_lock(
                {**self.values, "request_hash": body}
            ):
                keys.append(self.connection.scalar.call_args.args[1])
        self.assertEqual(keys[0], keys[1])

    def test_autocommit_or_unknown_rejected_before_probe(self):
        for value in (True, None):
            self.connection.connection.dbapi_connection.autocommit = value
            with self.assertRaises(IdempotencyConflict):
                with self.repo._idempotency_execution_lock(self.values):
                    self.fail("entered callback")
        self.connection.scalar.assert_not_called()

    def test_unknown_probe_and_transport_error_do_not_retry(self):
        self.connection.scalar.return_value = None
        with self.assertRaises(IdempotencyConflict):
            with self.repo._idempotency_execution_lock(self.values):
                self.fail("entered callback")
        self.connection.detach.assert_not_called()
        self.connection.scalar.side_effect = RuntimeError("fictional transport")
        with self.assertRaises(RuntimeError):
            with self.repo._idempotency_execution_lock(self.values):
                self.fail("entered callback")
        self.assertEqual(self.engine.connect.call_count, 2)

    def test_busy_timeout_closes_checkout_without_callback_or_detach(self):
        self.connection.scalar.return_value = False
        with patch(
            "shared_module.portal_data.mobile_repository.time.monotonic",
            side_effect=[0, 11],
        ):
            with self.assertRaisesRegex(IdempotencyConflict, "still running"):
                with self.repo._idempotency_execution_lock(self.values):
                    self.fail("entered callback")
        self.connection.detach.assert_not_called()
        self.engine.connect.return_value.__exit__.assert_called_once()

    def test_busy_sleep_happens_after_checkout_closed(self):
        self.connection.scalar.side_effect = [False, True]

        def sleep(_delay):
            self.engine.connect.return_value.__exit__.assert_called_once()
            self.connection.begin.return_value.__exit__.assert_called_once()

        with patch(
            "shared_module.portal_data.mobile_repository.time.sleep", side_effect=sleep
        ):
            with self.repo._idempotency_execution_lock(self.values):
                pass
        self.assertEqual(self.engine.connect.call_count, 2)
