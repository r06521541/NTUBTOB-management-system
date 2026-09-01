from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from psycopg2 import Error as PsycopgError
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.portal_data_migration_readiness import (
    EXPECTED_REVISIONS,
    EXPECTED_TABLES,
    HEADER,
    VerificationError,
    render_sql,
    revision_chain,
    verify_artifact,
    verify_sql,
)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)
ROOT = Path(__file__).resolve().parents[2]


class MigrationReadinessStaticTests(unittest.TestCase):
    def test_revision_chain_is_single_and_exact(self):
        self.assertEqual(revision_chain(), EXPECTED_REVISIONS)
        self.assertEqual(
            EXPECTED_REVISIONS[-1], "0011_event_notification_guest_lifecycle"
        )

    def test_historical_suites_pin_0010_and_current_suites_own_head(self):
        historical_suites = (
            "test_mobile_api_foundation.py",
            "test_staging_broker_journal.py",
        )
        for name in historical_suites:
            with self.subTest(name=name):
                source = (ROOT / "tests" / "portal_data" / name).read_text(
                    encoding="utf-8"
                )
                setup = source.split("    def setUp(self):", 1)[1].split(
                    "\n    def ", 1
                )[0]
                self.assertIn(
                    'command.upgrade(config, "0010_apple_provider_lifecycle")',
                    setup,
                )
                self.assertNotIn('"head"', setup)

        current_suites = {
            "test_mobile_notifications.py": 'command.upgrade(config, "head")',
            "test_event_guest_lifecycle.py": 'command.upgrade(self.config, "head")',
        }
        for name, expected_upgrade in current_suites.items():
            with self.subTest(name=name):
                source = (ROOT / "tests" / "portal_data" / name).read_text(
                    encoding="utf-8"
                )
                setup = source.split("    def setUp(self):", 1)[1].split(
                    "\n    def ", 1
                )[0]
                self.assertIn(expected_upgrade, setup)
                self.assertIn("0011_event_notification_guest_lifecycle", source)

        notification_source = (
            ROOT / "tests" / "portal_data" / "test_mobile_notifications.py"
        ).read_text(encoding="utf-8")
        self.assertIn("destination_event_id", notification_source)

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

    def test_verifier_rejects_unapproved_create_statements(self):
        safe = render_sql()
        mutations = (
            "CREATE VIEW ntubtob.fake_view AS SELECT 1;",
            "CREATE INDEX fake_index ON ntubtob.members(id);",
            "CREATE FUNCTION ntubtob.fake_function() RETURNS integer "
            "LANGUAGE sql AS $$ SELECT 1 $$;",
            "CREATE TRIGGER fake_trigger BEFORE UPDATE ON ntubtob.members "
            "FOR EACH ROW EXECUTE FUNCTION ntubtob.reject_audit_mutation();",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(VerificationError):
                    verify_sql(safe.replace("COMMIT;", f"{mutation}\nCOMMIT;"))

    def test_verifier_rejects_marker_mutations(self):
        safe = render_sql()
        mutations = (
            safe.replace(
                "CREATE TABLE ntubtob.alembic_version",
                "CREATE TABLE IF NOT EXISTS ntubtob.alembic_version",
                1,
            ),
            safe.replace("'0001_legacy_baseline'", "'wrong_baseline'", 1),
            safe.replace(
                " RETURNING ntubtob.alembic_version.version_num;",
                " ON CONFLICT DO NOTHING "
                "RETURNING ntubtob.alembic_version.version_num;",
                1,
            ),
            safe.replace(
                "COMMIT;",
                "DELETE FROM ntubtob.alembic_version;\nCOMMIT;",
                1,
            ),
            safe.replace(
                "COMMIT;",
                "TRUNCATE TABLE ntubtob.alembic_version;\nCOMMIT;",
                1,
            ),
            safe.replace(
                "UPDATE ntubtob.alembic_version "
                "SET version_num='0003_legacy_bigint_activity_game'",
                "UPDATE ntubtob.alembic_version SET version_num='wrong_revision'",
                1,
            ),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[:120]):
                with self.assertRaises(VerificationError):
                    verify_sql(mutation)

    def test_verifier_rejects_rls_and_privilege_mutations(self):
        safe = render_sql()
        first_table = sorted(EXPECTED_TABLES)[0]
        exact_rls = f"ALTER TABLE ntubtob.{first_table} ENABLE ROW LEVEL SECURITY;"
        mutations = (
            safe.replace(exact_rls, "", 1),
            safe.replace(
                exact_rls,
                exact_rls
                + "\nALTER TABLE ntubtob.unexpected ENABLE ROW LEVEL SECURITY;",
                1,
            ),
            safe.replace(
                exact_rls,
                exact_rls + f"\nALTER TABLE ntubtob.{first_table} "
                "FORCE ROW LEVEL SECURITY;",
                1,
            ),
            safe.replace(
                exact_rls,
                exact_rls + f"\nCREATE POLICY fake_policy ON ntubtob.{first_table};",
                1,
            ),
            safe.replace(
                exact_rls,
                exact_rls + f"\nGRANT SELECT ON ntubtob.{first_table} TO PUBLIC;",
                1,
            ),
            safe.replace("COMMIT;", "COMMIT;\nBEGIN;\nCOMMIT;", 1),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[-160:]):
                with self.assertRaises(VerificationError):
                    verify_sql(mutation)

    def test_verifier_rejects_checksum_drift(self):
        with self.assertRaisesRegex(VerificationError, "checksum"):
            verify_sql(render_sql(), "0" * 64)

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

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self._reset_to_clean_baseline()
        setup_legacy_fixture()

    def tearDown(self):
        self._reset_to_clean_baseline()
        setup_legacy_fixture()
        self._execute_offline_artifact(render_sql())

    def _reset_to_clean_baseline(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DROP TABLE IF EXISTS
                      ntubtob.event_audit, ntubtob.event_managers,
                      ntubtob.activity_attendance_replies,
                      ntubtob.event_attendance_replies, ntubtob.event_invitees,
                      ntubtob.event_invitee_overrides,
                      ntubtob.event_eligibility_rules, ntubtob.activities,
                      ntubtob.events, ntubtob.access_audit,
                      ntubtob.person_qualifications, ntubtob.auth_identities,
                      ntubtob.people
                    CASCADE;
                    ALTER TABLE IF EXISTS ntubtob.members
                      DROP COLUMN IF EXISTS person_id CASCADE;
                    DROP FUNCTION IF EXISTS ntubtob.reject_audit_mutation() CASCADE;
                    DROP TABLE IF EXISTS ntubtob.alembic_version;
                    """
                )
            )

    def _version(self):
        with self.engine.connect() as connection:
            exists = connection.scalar(
                text("SELECT to_regclass('ntubtob.alembic_version') IS NOT NULL")
            )
            if not exists:
                return None
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
        self.assertIsNone(self._version())
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

        self.assertIsNone(self._version())
        self.assertEqual(self._portal_tables(), set())
        self._execute_offline_artifact(render_sql())
        self.assertEqual(self._version(), "0003_legacy_bigint_activity_game")

    def test_clean_artifact_creates_marker_and_fail_closed_rls(self):
        self._execute_offline_artifact(render_sql())
        self.assertEqual(self._version(), "0003_legacy_bigint_activity_game")
        self.assertEqual(self._portal_tables(), EXPECTED_TABLES)
        with self.engine.connect() as connection:
            rls = set(
                connection.scalars(
                    text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n "
                        "ON n.oid = c.relnamespace WHERE n.nspname = 'ntubtob' "
                        "AND c.relname = ANY(:tables) AND c.relrowsecurity "
                        "AND NOT c.relforcerowsecurity"
                    ),
                    {"tables": list(EXPECTED_TABLES)},
                )
            )
            policies = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'ntubtob' "
                    "AND tablename = ANY(:tables)"
                ),
                {"tables": list(EXPECTED_TABLES)},
            )
        self.assertEqual(rls, EXPECTED_TABLES)
        self.assertEqual(policies, 0)

    def test_preexisting_marker_is_rejected_without_partial_schema(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE ntubtob.alembic_version "
                    "(version_num varchar(32) PRIMARY KEY); "
                    "INSERT INTO ntubtob.alembic_version VALUES "
                    "('0001_legacy_baseline')"
                )
            )
        with self.assertRaises(PsycopgError):
            self._execute_offline_artifact(render_sql())
        self.assertEqual(self._version(), "0001_legacy_baseline")
        self.assertEqual(self._portal_tables(), set())

    def test_preexisting_portal_object_is_rejected_atomically(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE ntubtob.people (id bigint PRIMARY KEY)")
            )
        with self.assertRaises(PsycopgError):
            self._execute_offline_artifact(render_sql())
        self.assertIsNone(self._version())
        self.assertEqual(self._portal_tables(), {"people"})

    def test_upgrade_preserves_legacy_rows_and_does_not_backfill(self):
        before = self._legacy_counts()
        self._execute_offline_artifact(render_sql())
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
