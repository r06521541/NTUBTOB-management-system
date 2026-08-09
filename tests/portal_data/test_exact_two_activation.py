import contextlib
import io
import json
import os
import threading
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools import portal_data_production_activate_allowlisted_admins as operator
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class ExactTwoActivationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        setup_legacy_fixture()
        command.upgrade(Config("alembic.ini"), "head")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    TRUNCATE TABLE
                      ntubtob.identity_review_messages,
                      ntubtob.identity_review_threads,
                      ntubtob.access_audit,
                      ntubtob.person_qualifications,
                      ntubtob.auth_identities,
                      ntubtob.game_attendance_replies,
                      ntubtob.line_users,
                      ntubtob.members,
                      ntubtob.people
                    RESTART IDENTITY CASCADE;
                    WITH people AS (
                      INSERT INTO ntubtob.people
                        (display_name, portal_access_level, portal_status, version,
                         created_at, updated_at)
                      VALUES
                        ('Fake One', 'basic', 'inactive', 1, now(), now()),
                        ('Fake Two', 'basic', 'inactive', 1, now(), now())
                      RETURNING id, display_name
                    )
                    INSERT INTO ntubtob.members (id, name, person_id)
                    SELECT CASE display_name WHEN 'Fake One' THEN 7001 ELSE 7002 END,
                           display_name, id FROM people;
                    INSERT INTO ntubtob.line_users
                      (nickname, line_user_id, member_id, has_replied, ignored)
                    VALUES
                      ('Fake One', 'fake-line-one', 7001, false, false),
                      ('Fake Two', 'fake-line-two', 7002, false, false);
                    INSERT INTO ntubtob.auth_identities
                      (provider, provider_subject, person_id, status, created_at, updated_at)
                    SELECT 'line', CASE id WHEN 7001 THEN 'fake-line-one' ELSE 'fake-line-two' END,
                           person_id, 'linked', now(), now()
                    FROM ntubtob.members WHERE id IN (7001,7002);
                    INSERT INTO ntubtob.person_qualifications
                      (person_id, qualification, status, reason, created_at, updated_at)
                    SELECT person_id, 'team_player', 'active', 'fake qualification', now(), now()
                    FROM ntubtob.members WHERE id IN (7001,7002);
                    """
                )
            )
        self.environ = {
            operator.DATABASE_ENV: DATABASE_URL,
            operator.ALLOWLIST_ENV: "7001,7002",
            operator.EXECUTION_ENV: operator.EXECUTION_ACKNOWLEDGEMENT,
        }

    def _counts(self):
        with self.engine.connect() as connection:
            return tuple(
                connection.execute(
                    text(
                        """
                        SELECT
                          count(*) FILTER (WHERE portal_status='inactive'),
                          count(*) FILTER (WHERE portal_status='active'),
                          sum(version),
                          (SELECT count(*) FROM ntubtob.access_audit),
                          (SELECT count(*) FROM ntubtob.auth_identities),
                          (SELECT count(*) FROM ntubtob.members),
                          (SELECT count(*) FROM ntubtob.line_users),
                          (SELECT count(*) FROM ntubtob.person_qualifications),
                          (SELECT count(*) FROM ntubtob.game_attendance_replies)
                        FROM ntubtob.people
                        """
                    )
                ).one()
            )

    def test_success_and_safe_retry_have_exact_deltas(self):
        before = self._counts()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator.run("execute", environ=self.environ)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["activation_delta"], 2)
        self.assertEqual(payload["audit_delta"], 2)
        after = self._counts()
        self.assertEqual(before, (2, 0, 2, 0, 2, 2, 2, 2, 0))
        self.assertEqual(after, (0, 2, 4, 2, 2, 2, 2, 2, 0))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator.run("execute", environ=self.environ)
        retry = json.loads(output.getvalue())
        self.assertTrue(retry["retry_verified"])
        self.assertEqual(retry["audit_delta"], 0)
        self.assertEqual(self._counts(), after)
        with self.engine.connect() as connection:
            audits = connection.execute(
                text(
                    """
                    SELECT actor_person_id, auth_identity_id, before_state, after_state,
                           reason, request_id
                    FROM ntubtob.access_audit ORDER BY target_person_id
                    """
                )
            ).all()
        self.assertEqual(len(audits), 2)
        self.assertNotEqual(audits[0].request_id, audits[1].request_id)
        for audit in audits:
            self.assertIsNone(audit.actor_person_id)
            self.assertIsNone(audit.auth_identity_id)
            self.assertEqual(audit.before_state, {"status": "inactive"})
            self.assertEqual(audit.after_state, {"status": "active"})
            self.assertEqual(audit.reason, operator.REASON)
            self.assertRegex(audit.request_id, r"^task086-two-[0-9a-f-]{36}$")

    def test_relationship_drift_rejects_without_mutation(self):
        with self.engine.begin() as connection:
            other = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, version,
                       created_at, updated_at)
                    VALUES ('Wrong Person','basic','active',1,now(),now()) RETURNING id
                    """
                )
            )
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:other WHERE provider_subject='fake-line-two'"
                ),
                {"other": other},
            )
        before = self._counts()
        with self.assertRaises(operator.ExactTwoActivationError):
            operator.run("execute", environ=self.environ)
        self.assertEqual(self._counts(), before)

    def test_partial_failure_rolls_back_both_people_and_audits(self):
        before = self._counts()
        with self.assertRaises(operator.ExactTwoActivationError):
            operator.run("execute", environ=self.environ, fail_after_first=True)
        self.assertEqual(self._counts(), before)

    def test_unsafe_write_logging_stops_before_mutation(self):
        before = self._counts()
        with patch.object(
            operator, "_write_logging_safe", return_value=False
        ), self.assertRaises(operator.ExactTwoActivationError):
            operator.run("execute", environ=self.environ)
        self.assertEqual(self._counts(), before)

    def test_partial_completed_audit_is_not_accepted_as_retry(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_status='active', version=version+1"
                )
            )
            person_id = connection.scalar(
                text("SELECT person_id FROM ntubtob.members WHERE id=7001")
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.access_audit
                      (action, actor_person_id, target_person_id, auth_identity_id,
                       before_state, after_state, reason, request_id, created_at)
                    VALUES ('status_changed', NULL, :person_id, NULL,
                            CAST(:before AS json), CAST(:after AS json), :reason,
                            'task086-two-fake-partial', now())
                    """
                ),
                {
                    "person_id": person_id,
                    "before": '{"status":"inactive"}',
                    "after": '{"status":"active"}',
                    "reason": operator.REASON,
                },
            )
        before = self._counts()
        with self.assertRaises(operator.ExactTwoActivationError):
            operator.run("execute", environ=self.environ)
        self.assertEqual(self._counts(), before)

    def test_concurrent_execution_has_one_apply_and_one_safe_retry(self):
        outcomes = []
        errors = []
        outcome_lock = threading.Lock()

        def capture(**values):
            with outcome_lock:
                outcomes.append(values)

        def execute():
            try:
                operator.run("execute", environ=self.environ)
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=execute) for _ in range(2)]
        with patch.object(operator, "_emit", side_effect=capture):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)
        self.assertFalse(errors)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(
            sorted(row["status"] for row in outcomes), ["applied", "verified"]
        )
        self.assertEqual(self._counts(), (0, 2, 4, 2, 2, 2, 2, 2, 0))


if __name__ == "__main__":
    unittest.main()
