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
from tools import portal_data_production_activate_linked_players as operator
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class LinkedPlayerActivationPostgresTests(unittest.TestCase):
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
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, version,
                       created_at, updated_at)
                    SELECT 'Fake ' || value, 'basic',
                           CASE WHEN value <= 2 THEN 'active' ELSE 'inactive' END,
                           1, now(), now()
                    FROM generate_series(1,6) AS value;
                    INSERT INTO ntubtob.members (id, name, person_id)
                    SELECT 7000 + row_number() OVER (ORDER BY id), display_name, id
                    FROM ntubtob.people;
                    INSERT INTO ntubtob.line_users
                      (nickname, line_user_id, member_id, has_replied, ignored)
                    SELECT name, 'fake-line-' || id, id, false, false
                    FROM ntubtob.members;
                    INSERT INTO ntubtob.auth_identities
                      (provider, provider_subject, person_id, status, created_at, updated_at)
                    SELECT 'line', 'fake-line-' || id, person_id, 'linked', now(), now()
                    FROM ntubtob.members;
                    INSERT INTO ntubtob.person_qualifications
                      (person_id, qualification, status, reason, created_at, updated_at)
                    SELECT person_id, 'team_player', 'active', 'fake qualification', now(), now()
                    FROM ntubtob.members;
                    """
                )
            )
        self.environ = {
            operator.boundary.DATABASE_ENV: DATABASE_URL,
            operator.boundary.ALLOWLIST_ENV: "7001,7002",
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

    def test_discovery_proves_dynamic_cohort_and_controls(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator.run("discovery", environ=self.environ)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["eligible_cohort_count"], 4)
        self.assertEqual(payload["active_control_count"], 2)
        self.assertEqual(payload["drift_count"], 0)
        self.assertEqual(payload["status"], "ready")

    def test_success_and_exact_retry_preserve_non_person_aggregates(self):
        before = self._counts()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator.run("execute", environ=self.environ, approved_cohort_count=4)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["activation_delta"], 4)
        self.assertEqual(payload["audit_delta"], 4)
        after = self._counts()
        self.assertEqual(before, (4, 2, 6, 0, 6, 6, 6, 6, 0))
        self.assertEqual(after, (0, 6, 10, 4, 6, 6, 6, 6, 0))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            operator.run("execute", environ=self.environ, approved_cohort_count=4)
        retry = json.loads(output.getvalue())
        self.assertTrue(retry["retry_verified"])
        self.assertEqual(retry["audit_delta"], 0)
        self.assertEqual(self._counts(), after)

    def test_missing_or_wrong_approved_count_stops_before_mutation(self):
        before = self._counts()
        for approved_count in (None, 3, 5, 0, True):
            with (
                self.subTest(approved_count=approved_count),
                self.assertRaises(operator.LinkedPlayerActivationError),
            ):
                operator.run(
                    "execute",
                    environ=self.environ,
                    approved_cohort_count=approved_count,
                )
            self.assertEqual(self._counts(), before)

    def test_relationship_drift_rejects_without_repair(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=NULL, status='disabled' WHERE provider_subject='fake-line-7006'"
                )
            )
        before = self._counts()
        with self.assertRaises(operator.LinkedPlayerActivationError):
            operator.run("execute", environ=self.environ, approved_cohort_count=4)
        self.assertEqual(self._counts(), before)

    def test_partial_completion_audit_rejects_without_repair(self):
        with self.engine.begin() as connection:
            person_id = connection.scalar(
                text("SELECT person_id FROM ntubtob.members WHERE id=7003")
            )
            connection.execute(
                text(
                    """
                    UPDATE ntubtob.people
                    SET portal_status='active', version=version+1, updated_at=now()
                    WHERE id=:person_id;
                    INSERT INTO ntubtob.access_audit
                      (action, actor_person_id, target_person_id, auth_identity_id,
                       before_state, after_state, reason, request_id, created_at)
                    VALUES
                      ('status_changed', NULL, :person_id, NULL,
                       '{"status":"inactive"}'::jsonb,
                       '{"status":"active"}'::jsonb,
                       :reason, 'task087-linked-fake-partial', now())
                    """
                ),
                {"person_id": person_id, "reason": operator.REASON},
            )
        before = self._counts()
        with self.assertRaises(operator.LinkedPlayerActivationError):
            operator.run("execute", environ=self.environ, approved_cohort_count=4)
        self.assertEqual(self._counts(), before)

    def test_partial_failure_and_unsafe_logging_roll_back_all(self):
        before = self._counts()
        with self.assertRaises(operator.LinkedPlayerActivationError):
            operator.run(
                "execute",
                environ=self.environ,
                approved_cohort_count=4,
                fail_after=2,
            )
        self.assertEqual(self._counts(), before)
        with (
            patch.object(operator.boundary, "_write_logging_safe", return_value=False),
            self.assertRaises(operator.LinkedPlayerActivationError),
        ):
            operator.run("execute", environ=self.environ, approved_cohort_count=4)
        self.assertEqual(self._counts(), before)

    def test_concurrency_has_one_apply_and_one_verified_retry(self):
        outcomes = []
        errors = []
        lock = threading.Lock()

        def capture(**values):
            with lock:
                outcomes.append(values)

        def execute():
            try:
                operator.run("execute", environ=self.environ, approved_cohort_count=4)
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
        self.assertEqual(self._counts(), (0, 6, 10, 4, 6, 6, 6, 6, 0))


if __name__ == "__main__":
    unittest.main()
