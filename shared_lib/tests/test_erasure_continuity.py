"""Fictional immutable receipt/evidence extensions; no provider or database I/O."""

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.engine import Connection

NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
JOB = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"


class ContinuityDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module(
            "shared_module.portal_data.erasure_continuity"
        )
        self.root = dict(
            id=JOB,
            target_kind="person",
            expected_generation=GEN,
            requested_at=NOW,
            receipt_secret_hash="a" * 64,
            receipt_expires_at=NOW + timedelta(days=180),
            evidence_expires_at=NOW + timedelta(days=180),
        )
        self.connection = MagicMock(spec=Connection)
        self.connection.in_transaction.return_value = True
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.connection = SimpleNamespace(
            dbapi_connection=SimpleNamespace(autocommit=False)
        )
        self.connection.scalar.return_value = False
        self.connection.execute.return_value.mappings.return_value.all.return_value = []

    def resolve(self, revision="0021_erasure_continuity"):
        return self.module.effective_deadlines(
            self.connection, self.root, revisions=(revision,)
        )

    def test_legacy_never_queries_unavailable_extension_table(self):
        deadlines = self.resolve("0020_erasure_intake")
        self.assertEqual(deadlines.receipt_until, self.root["receipt_expires_at"])
        self.assertEqual(deadlines.evidence_until, self.root["evidence_expires_at"])
        self.connection.execute.assert_not_called()

    def test_exact_chain_extends_without_rewriting_originals(self):
        original = self.root.copy()
        event = dict(
            request_id=JOB,
            target_kind="person",
            expected_generation=GEN,
            original_requested_at=NOW,
            original_receipt_hash="a" * 64,
            sequence=1,
            previous_receipt_until=self.root["receipt_expires_at"],
            previous_evidence_until=self.root["evidence_expires_at"],
            receipt_until=NOW + timedelta(days=210),
            evidence_until=NOW + timedelta(days=240),
            occurred_at=NOW + timedelta(days=179),
        )
        self.connection.execute.return_value.mappings.return_value.all.return_value = [
            event
        ]
        deadlines = self.resolve()
        self.assertEqual(deadlines.receipt_until, NOW + timedelta(days=210))
        self.assertEqual(deadlines.evidence_until, NOW + timedelta(days=240))
        self.assertEqual(self.root, original)
        for field, invalid in (
            ("sequence", 2),
            ("expected_generation", JOB),
            ("original_receipt_hash", "b" * 64),
            ("occurred_at", NOW + timedelta(days=180)),
            ("evidence_until", NOW + timedelta(days=200)),
        ):
            with self.subTest(field=field):
                self.connection.execute.return_value.mappings.return_value.all.return_value = [
                    {**event, field: invalid}
                ]
                with self.assertRaises(self.module.ContinuityUnavailable):
                    self.resolve()

    def test_unknown_revision_and_filtered_or_autocommit_connection_reject(self):
        with self.assertRaises(self.module.ContinuityUnavailable):
            self.resolve("0022_unknown")
        self.connection.scalar.return_value = True
        with self.assertRaises(self.module.ContinuityUnavailable):
            self.resolve()
        self.connection.scalar.return_value = False
        self.connection.connection.dbapi_connection.autocommit = True
        with self.assertRaises(self.module.ContinuityUnavailable):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
