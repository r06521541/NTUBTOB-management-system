import unittest
from unittest.mock import Mock

from apps.mobile_api.revision_readiness import (
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

    def test_revision_mismatch_fails_closed_without_value_in_log(self):
        engine, logger = Mock(), Mock()
        connection = Mock()
        connection.scalar.return_value = "sensitive-unexpected-value"
        engine.connect.return_value = _ConnectionContext(connection)

        self.assertFalse(database_revision_is_current(engine, logger))
        logger.error.assert_called_once_with("mobile_api_revision_check_mismatch")

    def test_driver_error_logs_only_exception_type(self):
        engine, logger = Mock(), Mock()
        engine.connect.side_effect = RuntimeError("secret-host secret-password")

        self.assertFalse(database_revision_is_current(engine, logger))
        logger.error.assert_called_once_with(
            "mobile_api_revision_check_failed error_type=%s",
            "RuntimeError",
        )
        rendered = repr(logger.error.call_args)
        self.assertNotIn("secret-host", rendered)
        self.assertNotIn("secret-password", rendered)


if __name__ == "__main__":
    unittest.main()
