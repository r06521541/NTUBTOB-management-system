import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from shared_module.account_deletion import (
    AccountDeletionRequest,
    AccountDeletionService,
)
from shared_module.mobile_api import InvalidArgument, MobilePrincipal


class AccountDeletionServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.service = AccountDeletionService(self.repository)
        self.principal = MobilePrincipal("fake-session", 1, 2, "basic", "Fake", 1)
        self.key = "11111111-2222-4333-8444-555555555555"
        self.record = AccountDeletionRequest(
            "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            datetime(2035, 1, 1, tzinfo=timezone.utc),
        )

    def test_status_is_absent_or_a_bounded_request_never_completed(self):
        self.repository.status.return_value = None
        self.assertEqual(self.service.status(self.principal), {"request": None})
        self.repository.status.return_value = self.record
        self.assertEqual(
            self.service.status(self.principal),
            {
                "request": {
                    "id": self.record.id,
                    "status": "requested",
                    "requested_at": "2035-01-01T00:00:00Z",
                }
            },
        )

    def test_confirmed_constant_command_does_not_persist_the_key(self):
        self.repository.request.return_value = self.record
        result = self.service.request(self.principal, True, self.key)
        self.repository.request.assert_called_once_with(self.principal)
        self.assertEqual(result["request"]["status"], "requested")

    def test_confirmation_requires_exact_boolean_true(self):
        for confirmation in (False, None, 1, "true", [], {}):
            with self.subTest(confirmation=confirmation):
                with self.assertRaises(InvalidArgument):
                    self.service.request(self.principal, confirmation, self.key)
        self.repository.request.assert_not_called()

    def test_key_requires_canonical_uuid(self):
        for key in (
            None,
            "",
            "fake",
            "1" * 32,
            " " + self.key,
            self.key + " ",
            "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
            "{" + self.key + "}",
        ):
            with self.subTest(key=key), self.assertRaises(InvalidArgument):
                self.service.request(self.principal, True, key)
        self.repository.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
