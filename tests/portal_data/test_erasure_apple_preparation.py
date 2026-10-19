"""Real isolated PostgreSQL coordinator with fictional cipher and HTTP only."""

import hashlib
import unittest
from unittest.mock import Mock

from sqlalchemy import text

from shared_lib.shared_module.apple_token_revocation import AppleTokenRevoker
from shared_lib.shared_module.portal_data.erasure_apple_preparation import (
    AppleErasurePreparation,
)
from tests.portal_data import test_erasure_fulfillment as fixture
from tests.portal_data import test_erasure_ledger as ledger

TOKEN = b"fictional-refresh-token"


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL not configured")
class ApplePreparationPostgresTests(unittest.TestCase):
    cleanup_fixture = fixture.PendingFulfillmentPostgresTests.cleanup_fixture
    scalar = fixture.PendingFulfillmentPostgresTests.scalar
    execute = fixture.PendingFulfillmentPostgresTests.execute

    def setUp(self):
        fixture.PendingFulfillmentPostgresTests.setUp(self)
        self.cipher = Mock()
        self.cipher.open.return_value = TOKEN
        self.http_status = 200
        self.preparer = AppleErasurePreparation(
            provider_cipher=self.cipher,
            client_id="fictional-app",
            client_secret="fictional-client-secret",
            revoker=AppleTokenRevoker(transport=self.transport),
        )

    def seed(self, connection, identity):
        fixture.PendingFulfillmentPostgresTests.seed(self, connection, identity)
        connection.execute(
            text(
                "UPDATE ntubtob.apple_provider_credentials SET refresh_token_hash=:hash "
                "WHERE auth_identity_id=:id"
            ),
            {"hash": hashlib.sha256(TOKEN).hexdigest(), "id": identity},
        )

    def prepare_provider(self, connection, job, item):
        return self.preparer(connection, job, item)

    def transport(self, url, body, timeout):
        self.calls += 1
        self.assertEqual(url, "https://appleid.apple.com/auth/revoke")
        self.assertEqual(timeout, 5.0)
        # A separate connection sees the committed fence before dispatch.
        self.assertIsNotNone(
            self.scalar(
                "SELECT irreversible_started_at FROM ntubtob.account_erasure_jobs "
                "WHERE id=:id",
                id=self.job_id,
            )
        )
        return self.http_status, b""

    def assert_retained_provider_and_cleaned_local(self):
        for table in ("apple_provider_credentials", "auth_identities"):
            column = "id" if table == "auth_identities" else "auth_identity_id"
            self.assertEqual(
                self.scalar(
                    f"SELECT count(*) FROM ntubtob.{table} WHERE {column}=:id",
                    id=self.fixture.identity,
                ),
                1,
            )
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.ids["identity_review_messages"][0],
            ),
            0,
        )

    def test_exact_credential_success_after_committed_fence(self):
        result = self.execute()
        self.assertEqual(result.classification, "confirmed", result)
        self.assertEqual(self.calls, 1)
        self.cipher.open.assert_called_once_with(b"fake")
        for identity, count in (
            (self.fixture.identity, 0),
            (self.fixture.other_identity, 1),
        ):
            self.assertEqual(
                self.scalar(
                    "SELECT count(*) FROM ntubtob.auth_identities WHERE id=:id",
                    id=identity,
                ),
                count,
            )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id",
                id=self.job_id,
            ),
            "online_completed",
        )

    def test_present_unreadable_credential_is_not_missing_or_completed(self):
        self.cipher.open.side_effect = ValueError("fictional-cipher-failure")
        result = self.execute()
        self.assertEqual(result.classification, "needs_attention", result)
        self.assertEqual(self.calls, 0)
        self.assert_retained_provider_and_cleaned_local()

    def test_uncertain_dispatch_never_retries(self):
        self.http_status = 500
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assert_retained_provider_and_cleaned_local()
        self.assertEqual(self.execute().classification, "needs_attention")
        self.assertEqual(self.calls, 1)
        self.cipher.open.assert_called_once_with(b"fake")

    def test_credential_drift_rejects_before_decrypt_or_dispatch(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.apple_provider_credentials "
                    "SET encrypted_refresh_token=decode('626164','hex') "
                    "WHERE auth_identity_id=:id"
                ),
                {"id": self.fixture.identity},
            )
        self.assertEqual(self.execute().classification, "not_applied")
        self.cipher.open.assert_not_called()
        self.assertEqual(self.calls, 0)
        self.assertEqual(
            self.scalar(
                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id",
                id=self.ids["identity_review_messages"][0],
            ),
            1,
        )
