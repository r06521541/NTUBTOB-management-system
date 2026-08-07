from __future__ import annotations

import os
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class LegacyFixtureRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_database_url(DATABASE_URL)
        cls.engine = create_engine(DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_exact_fixture_and_migration_chain_are_reproducible(self):
        config = Config("alembic.ini")
        command.downgrade(config, "0001_legacy_baseline")
        setup_legacy_fixture()
        command.stamp(config, "0001_legacy_baseline")
        command.upgrade(config, "head")
        command.downgrade(config, "0001_legacy_baseline")
        setup_legacy_fixture()
        command.upgrade(config, "head")
        command.check(config)

        with self.engine.connect() as connection:
            names = connection.scalars(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'ntubtob' ORDER BY tablename"
                )
            ).all()
            self.assertTrue(
                {
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
                }.issubset(names)
            )
            bigint_identity_count = connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'ntubtob' AND column_name = 'id' "
                    "AND data_type = 'bigint' AND is_identity = 'YES' "
                    "AND table_name IN ('attendance_reply_types', 'ballparks', "
                    "'cancellations', 'discord_webhooks', 'game_attendance_replies', "
                    "'games', 'line_groups', 'line_notify_tokens', 'line_users', 'members')"
                )
            )
            self.assertEqual(bigint_identity_count, 10)
            foreign_keys = set(
                connection.execute(
                    text(
                        "SELECT kcu.table_name, kcu.column_name, "
                        "ccu.table_name, ccu.column_name "
                        "FROM information_schema.table_constraints tc "
                        "JOIN information_schema.key_column_usage kcu "
                        "ON tc.constraint_name = kcu.constraint_name "
                        "AND tc.table_schema = kcu.table_schema "
                        "JOIN information_schema.constraint_column_usage ccu "
                        "ON ccu.constraint_name = tc.constraint_name "
                        "AND ccu.table_schema = tc.table_schema "
                        "WHERE tc.constraint_type = 'FOREIGN KEY' "
                        "AND tc.table_schema = 'ntubtob' "
                        "AND tc.table_name IN ('cancellations', "
                        "'game_attendance_replies', 'line_users')"
                    )
                ).all()
            )
            self.assertEqual(
                foreign_keys,
                {
                    ("cancellations", "game_id", "games", "id"),
                    ("game_attendance_replies", "game_id", "games", "id"),
                    ("game_attendance_replies", "member_id", "members", "id"),
                    ("game_attendance_replies", "reply", "attendance_reply_types", "id"),
                    ("game_attendance_replies", "user_id", "line_users", "id"),
                    ("line_users", "member_id", "members", "id"),
                },
            )
            rls_count = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace WHERE n.nspname = 'ntubtob' "
                    "AND c.relrowsecurity AND c.relname IN ('attendance_reply_types', "
                    "'ballparks', 'cancellations', 'discord_webhooks', "
                    "'game_attendance_replies', 'games', 'line_groups', "
                    "'line_notify_tokens', 'line_users', 'members')"
                )
            )
            self.assertEqual(rls_count, 10)
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.cancellations")),
                0,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema = 'ntubtob' AND table_name = 'activities' "
                        "AND column_name = 'game_id'"
                    )
                ),
                "bigint",
            )


if __name__ == "__main__":
    unittest.main()
