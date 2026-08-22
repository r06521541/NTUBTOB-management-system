import unittest
from unittest.mock import Mock, patch

from apps.mobile_api.revision_readiness import (
    ACCEPTED_REVISIONS,
    EXPECTED_REVISION,
    database_revision_is_current,
)


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class RevisionReadinessTest(unittest.TestCase):
    def test_expected_revision_is_ready_without_logging(self):
        engine, logger = Mock(), Mock()
        connection = Mock()
        connection.scalar.return_value = EXPECTED_REVISION
        engine.connect.return_value = _ConnectionContext(connection)

        self.assertTrue(database_revision_is_current(engine, logger))
        logger.error.assert_not_called()

    def test_broker_journal_revision_is_ready_without_logging(self):
        engine, logger = Mock(), Mock()
        connection = Mock()
        connection.scalar.return_value = "0006_staging_broker_operation_journal"
        engine.connect.return_value = _ConnectionContext(connection)

        self.assertTrue(database_revision_is_current(engine, logger))
        logger.error.assert_not_called()

    def test_mobile_notification_revision_is_ready_without_logging(self):
        engine, logger = Mock(), Mock()
        connection = Mock()
        connection.scalar.return_value = "0007_mobile_notifications"
        engine.connect.return_value = _ConnectionContext(connection)

        self.assertTrue(database_revision_is_current(engine, logger))
        logger.error.assert_not_called()

    def test_accepted_revisions_are_exactly_the_three_mobile_revisions(self):
        self.assertEqual(
            ACCEPTED_REVISIONS,
            (
                "0005_mobile_auth_api_foundation",
                "0006_staging_broker_operation_journal",
                "0007_mobile_notifications",
            ),
        )

    def test_empty_unknown_and_malformed_revisions_fail_closed_without_value_in_log(
        self,
    ):
        for observed in ("", "0008_future_revision", None, 6, ["secret-value"]):
            with self.subTest(observed_type=type(observed).__name__):
                engine, logger = Mock(), Mock()
                connection = Mock()
                connection.scalar.return_value = observed
                engine.connect.return_value = _ConnectionContext(connection)

                self.assertFalse(database_revision_is_current(engine, logger))
                logger.error.assert_called_once_with(
                    "mobile_api_revision_check_mismatch"
                )
                self.assertNotIn("secret-value", repr(logger.error.call_args))

    def test_revision_mismatch_fails_closed_without_value_in_log(self):
        engine, logger = Mock(), Mock()
        connection = Mock()
        connection.scalar.return_value = "sensitive-unexpected-value"
        engine.connect.return_value = _ConnectionContext(connection)

        self.assertFalse(database_revision_is_current(engine, logger))
        logger.error.assert_called_once_with("mobile_api_revision_check_mismatch")

    def test_driver_error_logs_only_exception_type(self):
        engine, logger = Mock(), Mock()
        engine.url.host, engine.url.port = "private-host", 5432
        error = RuntimeError(
            "password authentication failed secret-host secret-password"
        )
        error.pgcode = "28P01"
        engine.connect.side_effect = error

        with patch("apps.mobile_api.revision_readiness.socket.getaddrinfo"), patch(
            "apps.mobile_api.revision_readiness.socket.create_connection"
        ) as create_connection:
            create_connection.return_value = Mock()
            self.assertFalse(database_revision_is_current(engine, logger))
        logger.error.assert_called_once_with(
            "mobile_api_revision_check_failed category=%s sqlstate=%s network=%s",
            "authentication",
            "28P01",
            "tcp_ok",
        )
        rendered = repr(logger.error.call_args)
        self.assertNotIn("secret-host", rendered)
        self.assertNotIn("secret-password", rendered)

    def test_unknown_error_does_not_emit_unbounded_sqlstate(self):
        engine, logger = Mock(), Mock()
        engine.url.host, engine.url.port = "private-host", 5432
        error = RuntimeError("private driver detail")
        error.pgcode = "private-unbounded-value"
        engine.connect.side_effect = error

        with patch(
            "apps.mobile_api.revision_readiness.socket.getaddrinfo",
            side_effect=OSError("private DNS detail"),
        ):
            self.assertFalse(database_revision_is_current(engine, logger))
        logger.error.assert_called_once_with(
            "mobile_api_revision_check_failed category=%s sqlstate=%s network=%s",
            "operational",
            "none",
            "dns_failed",
        )
        self.assertNotIn("private driver detail", repr(logger.error.call_args))


if __name__ == "__main__":
    unittest.main()
