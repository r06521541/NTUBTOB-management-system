from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from psycopg2 import Error as PsycopgError
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import \
    require_local_database_url
from tools.portal_data_migration_readiness import (EXPECTED_REVISIONS, HEADER,
                                                   VerificationError,
                                                   render_sql, revision_chain,
                                                   verify_artifact, verify_sql)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class MigrationReadinessStaticTests(unittest.TestCase):
    def test_revision_chain_is_single_and_exact(self):
        self.assertEqual(revision_chain(), EXPECTED_REVISIONS)

    def test_committed_artifact_is_current_and_safe(self):
        verify_artifact()

    def test_verifier_rejects_destructive_or_dml_mutations(self):
        safe = render_sql()
        for mutation in (
            "DROP TABLE ntubtob.members;",
            "DELETE FROM ntubtob.members;",
            "ALTER TABLE ntubtob.games DROP COLUMN year;",
            "CREATE TABLE ntubtob.line_users (id bigint);",
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(VerificationError):
                    verify_sql(safe.replace("COMMIT;", f"{mutation}\nCOMMIT;"))

    def test_verifier_rejects_remote_or_credential_content(self):
        safe = render_sql()
        for mutation in (
            "-- postgresql://example.invalid/database\n",
            "-- host.supabase.co\n",
            "-- password=not-a-real-password\n",
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(VerificationError):
                    verify_sql(safe.replace(HEADER, HEADER + mutation))

    def test_verifier_fails_when_revision_graph_drifts(self):
        with patch(
            "tools.portal_data_migration_readiness.revision_chain",
            return_value=EXPECTED_REVISIONS + ("unexpected",),
        ):
            with self.assertRaisesRegex(VerificationError, "revision graph"):
                verify_sql(render_sql())


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class MigrationReadinessPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_database_url(DATABASE_URL)
        cls.engine = create_engine(DATABASE_URL)
        cls.config = Config("alembic.ini")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        command.downgrade(self.config, "0001_legacy_baseline")
        setup_legacy_fixture()
        command.stamp(self.config, "0001_legacy_baseline")

    def _version(self):
        with self.engine.connect() as connection:
            return connection.scalar(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )

    def _portal_tables(self):
        with self.engine.connect() as connection:
            return set(
                connection.scalars(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'ntubtob' AND tablename IN "
                        "('people', 'auth_identities', 'person_qualifications', "
                        "'access_audit', 'events', 'activities', "
                        "'event_eligibility_rules', 'event_invitee_overrides', "
                        "'event_invitees', 'event_attendance_replies', "
                        "'activity_attendance_replies', 'event_managers', "
                        "'event_audit')"
                    )
                )
            )

    def _legacy_counts(self):
        tables = (
            "attendance_reply_types",
            "ballparks",
            "cancellations",
            "discord_webhooks",
            "game_attendance_replies",
            "games",
            "line_groups",
            "line_notify_tokens",
            "line_users",
            "members",
        )
        with self.engine.connect() as connection:
            return {
                table: connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))
                for table in tables
            }

    def _execute_offline_artifact(self, sql):
        raw = self.engine.raw_connection()
        try:
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute(sql)
        finally:
            raw.close()

    def test_mid_migration_failure_is_atomic(self):
        sql = render_sql().replace(
            "ALTER TABLE ntubtob.members ADD COLUMN person_id bigint NULL;",
            "ALTER TABLE ntubtob.members ADD COLUMN person_id bigint NULL;\n"
            "SELECT 1 / 0;",
            1,
        )
        with self.assertRaises(PsycopgError):
            self._execute_offline_artifact(sql)
        self.assertEqual(self._version(), "0001_legacy_baseline")
        self.assertEqual(self._portal_tables(), set())
        with self.engine.connect() as connection:
            person_id_exists = connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'ntubtob' AND table_name = 'members' "
                    "AND column_name = 'person_id'"
                )
            )
        self.assertEqual(person_id_exists, 0)

    def test_lock_timeout_fails_cleanly_and_retry_succeeds(self):
        locker = self.engine.connect()
        transaction = locker.begin()
        try:
            locker.execute(text("LOCK TABLE ntubtob.members IN ACCESS EXCLUSIVE MODE"))
            short_sql = render_sql().replace(
                "SET LOCAL lock_timeout = '5s';",
                "SET LOCAL lock_timeout = '250ms';",
                1,
            )
            with self.assertRaises(PsycopgError):
                self._execute_offline_artifact(short_sql)
        finally:
            transaction.rollback()
            locker.close()

        self.assertEqual(self._version(), "0001_legacy_baseline")
        self.assertEqual(self._portal_tables(), set())
        command.upgrade(self.config, "head")
        self.assertEqual(self._version(), "0003_legacy_bigint_activity_game")

    def test_upgrade_preserves_legacy_rows_and_does_not_backfill(self):
        before = self._legacy_counts()
        command.upgrade(self.config, "head")
        self.assertEqual(self._legacy_counts(), before)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.people")), 0
            )
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.auth_identities")),
                0,
            )
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.events")), 0
            )


if __name__ == "__main__":
    unittest.main()
