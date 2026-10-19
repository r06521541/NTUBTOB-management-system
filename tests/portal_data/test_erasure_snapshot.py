import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, create_mock_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from shared_lib.shared_module.account_erasure_scope import ErasureScopeRejected
from shared_lib.shared_module.portal_data.erasure_snapshot import (
    legacy_attendance_snapshot,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import (
    AuthIdentityRecord,
    LegacyGameAttendanceReplyRecord,
    LegacyLineUserRecord,
    LegacyMemberRecord,
)


class ErasureSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.in_transaction.return_value = True
        self.session.connection.return_value.get_isolation_level.return_value = (
            "REPEATABLE READ"
        )
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False

    def rows(self, *groups):
        self.connection.execute.side_effect = [
            SimpleNamespace(all=lambda rows=rows: rows) for rows in groups
        ]

    def test_legacy_only_reply_found_and_only_key_columns_selected(self):
        self.rows([(20, 10)], [(30, 20, None)], [(40, None, None, 30)], [], [])
        result = legacy_attendance_snapshot(self.session, 10)
        self.assertEqual(result.reply_ids, (40,))
        self.assertEqual(result.line_user_ids, (30,))
        for call in self.connection.execute.call_args_list:
            statement = call.args[0]
            self.assertTrue(statement.is_select)
            for column in statement.selected_columns:
                self.assertNotIn(
                    column.name, {"nickname", "line_user_id", "provider_subject"}
                )
        self.session.commit.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.add.assert_not_called()
        self.session.execute.assert_not_called()
        self.assertEqual(self.connection.execute.call_count, 5)

    def test_foreign_member_referenced_by_candidate_is_resolved_and_rejected(self):
        self.rows([(20, 10)], [], [(40, 10, 21, None)], [], [(21, 11)])
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, 10)
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_foreign_user_chain_is_loaded_and_rejected(self):
        self.rows([(20, 10)], [], [(40, 10, None, 31)], [(31, 21, None)], [(21, 11)])
        with self.assertRaises(ErasureScopeRejected):
            legacy_attendance_snapshot(self.session, 10)

    def test_direct_auth_link_finds_reply_without_member(self):
        self.rows([], [(30, None, 10)], [(40, None, None, 30)], [], [])
        result = legacy_attendance_snapshot(self.session, 10)
        self.assertEqual(result.member_ids, ())
        self.assertEqual(result.line_user_ids, (30,))
        self.assertEqual(result.reply_ids, (40,))
        self.assertEqual(self.connection.execute.call_count, 5)

    def test_direct_and_legacy_conflict_is_rejected_without_reply(self):
        self.rows([], [(30, 21, 10)], [], [], [(21, 11)])
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, 10)
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_referenced_foreign_direct_owner_is_loaded_and_rejected(self):
        self.rows([], [], [(40, 10, None, 31)], [(31, None, 11)], [])
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, 10)
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_subject_is_only_used_in_exact_line_join_not_returned(self):
        self.rows([], [], [], [], [])
        legacy_attendance_snapshot(self.session, 10)
        for index in (1, 3):
            statement = self.connection.execute.call_args_list[index].args[0]
            sql = str(statement)
            self.assertIn("LEFT OUTER JOIN ntubtob.auth_identities", sql)
            self.assertIn(
                "auth_identities.provider_subject = ntubtob.line_users.line_user_id",
                sql,
            )
            self.assertIn("auth_identities.provider =", sql)
            self.assertIn("line", statement.compile().params.values())
            self.assertEqual(
                [column.name for column in statement.selected_columns],
                ["id", "member_id", "person_id"],
            )
            self.assertNotIn("lower(", sql)
            self.assertNotIn("LIKE", sql)
            self.assertNotIn("auth_identities.status", sql)

    def test_missing_person_member_mapping_still_checks_direct_replies(self):
        self.rows([], [], [(40, 10, None, None)], [], [])
        self.assertEqual(legacy_attendance_snapshot(self.session, 10).reply_ids, (40,))

    def test_requires_explicit_consistent_transaction_before_queries(self):
        for isolation in ("READ COMMITTED", "AUTOCOMMIT"):
            self.session.connection.return_value.get_isolation_level.return_value = (
                isolation
            )
            with self.assertRaises(ErasureScopeRejected):
                legacy_attendance_snapshot(self.session, 10)
        self.session.in_transaction.return_value = False
        with self.assertRaises(ErasureScopeRejected):
            legacy_attendance_snapshot(self.session, 10)
        self.session.execute.assert_not_called()
        self.connection.execute.assert_not_called()

    def test_repeatable_read_with_autocommit_or_unknown_driver_state_is_rejected(self):
        for autocommit in (True, None, "false"):
            self.connection.connection.dbapi_connection.autocommit = autocommit
            with (
                self.subTest(autocommit=autocommit),
                self.assertRaises(ErasureScopeRejected),
            ):
                legacy_attendance_snapshot(self.session, 10)
        self.connection.execute.assert_not_called()

    def test_bad_person_id_rejected_before_connection(self):
        with self.assertRaises(ErasureScopeRejected):
            legacy_attendance_snapshot(self.session, True)
        self.session.connection.assert_not_called()

    def test_database_failure_is_safe_and_does_not_retry(self):
        self.connection.execute.side_effect = OperationalError(
            "private SQL", {}, Exception("private DB URL")
        )
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, 10)
        self.assertEqual(error.exception.reason, "SNAPSHOT_READ_FAILED")
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(self.connection.execute.call_count, 1)


DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class ErasureSnapshotPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            require_local_database_url(DATABASE_URL), isolation_level="REPEATABLE READ"
        )
        with cls.engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0013_account_deletion_requests")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection)
        self.session.begin()
        self.person_ids = []
        self.member_ids = []
        self.user_ids = []
        for index in range(2):
            person_id = self.connection.scalar(
                text(
                    "INSERT INTO ntubtob.people (display_name, portal_access_level, portal_status, version, created_at, updated_at) "
                    "VALUES ('Fictional scope fixture', 'basic', 'active', 1, now(), now()) RETURNING id"
                )
            )
            member_id = self.connection.scalar(
                text(
                    "INSERT INTO ntubtob.members (name, person_id) VALUES ('Fictional scope fixture', :person) RETURNING id"
                ),
                {"person": person_id},
            )
            user_id = self.connection.scalar(
                text(
                    "INSERT INTO ntubtob.line_users (nickname, line_user_id, member_id, has_replied, ignored) "
                    "VALUES ('Fictional scope fixture', :subject, :member, false, false) RETURNING id"
                ),
                {"member": member_id, "subject": "fictional-scope-user-" + str(index)},
            )
            self.person_ids.append(person_id)
            self.member_ids.append(member_id)
            self.user_ids.append(user_id)
        self.game_id = self.connection.scalar(
            text("INSERT INTO ntubtob.games DEFAULT VALUES RETURNING id")
        )
        self.reply_type = self.connection.scalar(
            text("SELECT id FROM ntubtob.attendance_reply_types ORDER BY id LIMIT 1")
        )

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def add_reply(self, person, member, user):
        return self.connection.scalar(
            text(
                "INSERT INTO ntubtob.game_attendance_replies (game_id, person_id, member_id, user_id, reply) "
                "VALUES (:game, :person, :member, :user, :reply) RETURNING id"
            ),
            {
                "game": self.game_id,
                "person": person,
                "member": member,
                "user": user,
                "reply": self.reply_type,
            },
        )

    def add_identity(self, person, subject, *, provider="line", status="linked"):
        return self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider, provider_subject, person_id, status, created_at, updated_at) "
                "VALUES (:provider, :subject, :person, :status, now(), now()) RETURNING id"
            ),
            {
                "provider": provider,
                "subject": subject,
                "person": person,
                "status": status,
            },
        )

    def test_direct_line_identity_without_member_finds_legacy_user_and_reply(self):
        self.connection.execute(
            text("UPDATE ntubtob.line_users SET member_id=NULL WHERE id=:id"),
            {"id": self.user_ids[0]},
        )
        self.connection.execute(
            text("DELETE FROM ntubtob.members WHERE id=:id"),
            {"id": self.member_ids[0]},
        )
        self.add_identity(self.person_ids[0], "fictional-scope-user-0")
        selected = self.add_reply(None, None, self.user_ids[0])
        result = legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(result.member_ids, ())
        self.assertEqual(result.line_user_ids, (self.user_ids[0],))
        self.assertEqual(result.reply_ids, (selected,))
        self.assertIsNone(
            self.connection.scalar(
                text("SELECT member_id FROM ntubtob.line_users WHERE id=:id"),
                {"id": self.user_ids[0]},
            )
        )

    def test_direct_owner_conflicting_with_member_is_rejected_without_reply(self):
        self.add_identity(self.person_ids[0], "fictional-scope-user-1")
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_member_owner_conflicting_with_direct_owner_is_rejected_without_reply(self):
        self.add_identity(self.person_ids[1], "fictional-scope-user-0")
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_same_subject_other_provider_or_case_does_not_prove_line_ownership(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.line_users SET member_id=NULL WHERE id IN (:first, :second)"
            ),
            {"first": self.user_ids[0], "second": self.user_ids[1]},
        )
        self.add_identity(
            self.person_ids[0], "fictional-scope-user-0", provider="apple"
        )
        self.add_identity(self.person_ids[0], "FICTIONAL-SCOPE-USER-1")
        result = legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(result.line_user_ids, ())

    def test_bound_disabled_identity_is_still_owned_but_pending_is_not_person_scope(
        self,
    ):
        self.connection.execute(
            text(
                "UPDATE ntubtob.line_users SET member_id=NULL WHERE id IN (:first, :second)"
            ),
            {"first": self.user_ids[0], "second": self.user_ids[1]},
        )
        self.add_identity(
            self.person_ids[0], "fictional-scope-user-0", status="disabled"
        )
        self.add_identity(None, "fictional-scope-user-1", status="pending")
        result = legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(result.line_user_ids, (self.user_ids[0],))

    def test_referenced_foreign_direct_identity_conflicts_with_reply_person(self):
        self.connection.execute(
            text("UPDATE ntubtob.line_users SET member_id=NULL WHERE id=:id"),
            {"id": self.user_ids[1]},
        )
        self.add_identity(self.person_ids[1], "fictional-scope-user-1")
        self.add_reply(self.person_ids[0], None, self.user_ids[1])
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_two_players_same_game_legacy_only_reply_is_found_without_mutation(self):
        selected = self.add_reply(None, None, self.user_ids[0])
        other = self.add_reply(self.person_ids[1], self.member_ids[1], self.user_ids[1])
        result = legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(result.reply_ids, (selected,))
        self.assertNotIn(other, result.reply_ids)
        count = self.connection.scalar(
            text(
                "SELECT count(*) FROM ntubtob.game_attendance_replies WHERE game_id=:game"
            ),
            {"game": self.game_id},
        )
        self.assertEqual(count, 2)

    def test_real_foreign_key_valid_but_cross_person_tuple_is_rejected(self):
        self.add_reply(self.person_ids[0], self.member_ids[1], self.user_ids[1])
        with self.assertRaises(ErasureScopeRejected) as error:
            legacy_attendance_snapshot(self.session, self.person_ids[0])
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_driver_autocommit_with_repeatable_read_is_not_a_snapshot(self):
        # A separate read-only test connection; no fixture writes use autocommit.
        with self.engine.connect() as connection:
            driver = connection.connection.dbapi_connection
            driver.set_session(isolation_level="REPEATABLE READ", autocommit=True)
            try:
                self.assertEqual(connection.get_isolation_level(), "REPEATABLE READ")
                with Session(bind=connection) as session, session.begin():
                    with self.assertRaises(ErasureScopeRejected) as error:
                        legacy_attendance_snapshot(session, self.person_ids[0])
                self.assertEqual(error.exception.reason, "SNAPSHOT_AUTOCOMMIT_REJECTED")
            finally:
                driver.autocommit = False

    def test_other_mapper_binds_cannot_route_snapshot_away_from_checked_connection(
        self,
    ):
        selected = self.add_reply(None, None, self.user_ids[0])
        other_engine = create_mock_engine(
            "postgresql://", lambda *args, **kwargs: self.fail("wrong bind used")
        )
        with (
            Session(
                bind=self.connection,
                binds={
                    model: other_engine
                    for model in (
                        AuthIdentityRecord,
                        LegacyMemberRecord,
                        LegacyLineUserRecord,
                        LegacyGameAttendanceReplyRecord,
                    )
                },
            ) as session,
            session.begin(),
        ):
            self.assertEqual(
                legacy_attendance_snapshot(session, self.person_ids[0]).reply_ids,
                (selected,),
            )
