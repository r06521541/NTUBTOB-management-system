import unittest
from base64 import urlsafe_b64encode
from unittest.mock import Mock, patch

from apps.mobile_api.revision_readiness import (
    ACCEPTED_REVISIONS,
    EXPECTED_REVISION,
    apple_lifecycle_configuration_is_valid,
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
    def test_apple_provider_credential_key_must_be_distinct_from_refresh_key(self):
        refresh_key = urlsafe_b64encode(b"r" * 32).decode("ascii")
        provider_key = urlsafe_b64encode(b"p" * 32).decode("ascii")
        values = {
            "audience": "fictional.ios.client",
            "client_secret": "fictional-runtime-client-secret",
            "credential_key": provider_key,
            "notification_audience": "fictional.notification.audience",
        }

        self.assertTrue(apple_lifecycle_configuration_is_valid(values, refresh_key))
        self.assertFalse(
            apple_lifecycle_configuration_is_valid(
                {**values, "credential_key": refresh_key}, refresh_key
            )
        )

    def test_expected_revision_is_ready_without_logging(self):
        engine, logger = Mock(), Mock()
        connection = Mock()
        connection.scalar.return_value = EXPECTED_REVISION
        engine.connect.return_value = _ConnectionContext(connection)

        self.assertTrue(database_revision_is_current(engine, logger))
        logger.error.assert_not_called()

    def test_accepted_revision_is_exactly_the_delivery_contract(self):
        self.assertEqual(
            ACCEPTED_REVISIONS,
            (
                "0008_mobile_notification_delivery",
                "0009_event_management_writes",
                "0010_apple_provider_lifecycle",
            ),
        )

    def test_each_rollout_compatible_revision_is_ready(self):
        for revision in ACCEPTED_REVISIONS:
            engine, logger = Mock(), Mock()
            connection = Mock()
            connection.scalar.return_value = revision
            engine.connect.return_value = _ConnectionContext(connection)

            with self.subTest(revision=revision):
                self.assertTrue(database_revision_is_current(engine, logger))
                logger.error.assert_not_called()

    def test_empty_unknown_and_malformed_revisions_fail_closed_without_value_in_log(
        self,
    ):
        for observed in ("", "0010_future_revision", None, 6, ["secret-value"]):
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
