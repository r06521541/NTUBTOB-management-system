import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_lib.shared_module.portal_data.models import (
    AppleProviderCodeExchangeRecord,
    AppleProviderCredentialRecord,
    AppleProviderNotificationRecord,
)
from tests.portal_data import _apple_lifecycle_test_harness as cleanup_harness
from tests.portal_data._apple_lifecycle_test_harness import (
    remove_retained_apple_evidence_from_isolated_test_database,
)

ROOT = Path(__file__).resolve().parents[2]


class AppleProviderLifecycleMigrationContractTests(unittest.TestCase):
    def test_revision_is_additive_and_downgrade_retains_security_evidence(self):
        migration = (
            ROOT / "migrations/versions/0010_apple_provider_lifecycle.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'down_revision: Union[str, None] = "0009_event_management_writes"',
            migration,
        )
        for table in (
            "apple_provider_code_exchanges",
            "apple_provider_credentials",
            "apple_provider_notifications",
        ):
            self.assertIn(f"CREATE TABLE ntubtob.{table}", migration)
        downgrade = migration.split("def downgrade() -> None:", 1)[1]
        self.assertNotIn("DROP TABLE", downgrade)
        self.assertNotIn("DELETE FROM", downgrade)
        upgrade = migration.split("def downgrade() -> None:", 1)[0]
        self.assertNotIn("IF NOT EXISTS", upgrade)

    def test_retained_evidence_cleanup_is_confined_to_test_harness(self):
        harness = (
            ROOT / "tests/portal_data/_apple_lifecycle_test_harness.py"
        ).read_text(encoding="utf-8")
        self.assertIn("DROP TABLE IF EXISTS", harness)
        self.assertIn('current == "0010_apple_provider_lifecycle"', harness)
        self.assertIn("PRE_0010_CLEANUP_REVISIONS", harness)
        self.assertIn("LOCAL_DATABASE_NAME", harness)
        self.assertIn("LOCAL_HOSTS", harness)
        for table in (
            "apple_provider_code_exchanges",
            "apple_provider_credentials",
            "apple_provider_notifications",
        ):
            self.assertIn(f"ntubtob.{table}", harness)

    def test_retained_evidence_cleanup_rejects_nonlocal_database(self):
        engine = SimpleNamespace(
            url=SimpleNamespace(
                drivername="postgresql",
                host="database.example.invalid",
                database="production",
            )
        )
        with self.assertRaisesRegex(RuntimeError, "isolated test database"):
            remove_retained_apple_evidence_from_isolated_test_database(engine)

    def test_retained_evidence_cleanup_rejects_unproven_revision_without_ddl(self):
        for revisions in (
            (),
            ("0004_phase_c_identity_lifecycle", "branch_revision"),
            ("unknown_revision",),
            ("0011_future_revision",),
        ):
            with self.subTest(revisions=revisions):
                engine = MagicMock()
                engine.url = SimpleNamespace(
                    drivername="postgresql",
                    host="localhost",
                    database=cleanup_harness.LOCAL_DATABASE_NAME,
                )
                engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = (
                    revisions
                )
                inspector = MagicMock()
                inspector.has_table.return_value = True
                with patch.object(cleanup_harness, "inspect", return_value=inspector):
                    with self.assertRaisesRegex(RuntimeError, "exact known revision"):
                        remove_retained_apple_evidence_from_isolated_test_database(
                            engine
                        )
                engine.begin.assert_not_called()

    def test_retained_evidence_cleanup_treats_fresh_schema_as_noop(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        inspector = MagicMock()
        inspector.has_table.return_value = False
        with patch.object(cleanup_harness, "inspect", return_value=inspector):
            remove_retained_apple_evidence_from_isolated_test_database(engine)
        engine.connect.assert_not_called()
        engine.begin.assert_not_called()

    def test_retained_evidence_cleanup_allows_exact_test_revision_only(self):
        engine = MagicMock()
        engine.url = SimpleNamespace(
            drivername="postgresql",
            host="localhost",
            database=cleanup_harness.LOCAL_DATABASE_NAME,
        )
        engine.connect.return_value.__enter__.return_value.scalars.return_value.all.return_value = [
            "0004_phase_c_identity_lifecycle"
        ]
        inspector = MagicMock()
        inspector.has_table.return_value = True
        with patch.object(cleanup_harness, "inspect", return_value=inspector):
            remove_retained_apple_evidence_from_isolated_test_database(engine)
        engine.begin.assert_called_once_with()
        engine.begin.return_value.__enter__.return_value.execute.assert_called_once()

    def test_models_keep_plaintext_provider_tokens_out_of_schema(self):
        tables = (
            AppleProviderCodeExchangeRecord.__table__,
            AppleProviderCredentialRecord.__table__,
            AppleProviderNotificationRecord.__table__,
        )
        columns = {column.name for table in tables for column in table.columns}
        self.assertIn("encrypted_refresh_token", columns)
        self.assertIn("refresh_token_hash", columns)
        self.assertIn("code_hash", columns)
        for forbidden in (
            "authorization_code",
            "refresh_token",
            "client_secret",
            "provider_payload",
            "email",
            "provider_subject",
        ):
            self.assertNotIn(forbidden, columns)


if __name__ == "__main__":
    unittest.main()
