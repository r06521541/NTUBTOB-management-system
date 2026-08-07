from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.portal_data_migration_readiness import render_sql
from tools.portal_data_phase_b import (
    BACKFILL_SQL_PATH,
    FIELDS,
    INVENTORY_METRICS,
    INVENTORY_SQL_PATH,
    POSTCHECK_SQL_PATH,
    PhaseBEvidenceError,
    render_rollback_rehearsal,
    validate_csv,
    validate_rows,
    verify_repository_artifacts,
    verify_read_only_sql,
)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture


DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class PhaseBArtifactStaticTests(unittest.TestCase):
    def test_repository_artifacts_are_fixed_and_valid(self):
        verify_repository_artifacts()

    def test_checksum_rejects_mutation(self):
        original = INVENTORY_SQL_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / INVENTORY_SQL_PATH.name
            path.write_text(
                original.replace("ROLLBACK;", "SELECT 1;\nROLLBACK;"), encoding="utf-8"
            )
            path.with_suffix(path.suffix + ".sha256").write_text(
                INVENTORY_SQL_PATH.with_suffix(".sql.sha256").read_text(
                    encoding="ascii"
                ),
                encoding="ascii",
            )
            with self.assertRaises(PhaseBEvidenceError):
                verify_read_only_sql(path)

    def test_validator_rejects_sensitive_reordered_and_failed_rows(self):
        base = {
            "section": "00_session",
            "metric": "transaction_read_only",
            "status": "required",
            "boolean_value": "true",
            "integer_value": "",
            "text_value": "",
        }
        rows = []
        for section, metric in sorted(INVENTORY_METRICS):
            rows.append(
                {
                    **base,
                    "section": section,
                    "metric": metric,
                    "boolean_value": (
                        "true" if metric == "transaction_read_only" else ""
                    ),
                    "integer_value": (
                        "1"
                        if metric != "transaction_read_only" and metric != "revision"
                        else ""
                    ),
                    "text_value": (
                        "0003_legacy_bigint_activity_game"
                        if metric == "revision"
                        else ""
                    ),
                    "status": "compare",
                }
            )
        rows[0]["status"] = "required"
        validate_rows(rows, "inventory")
        failed = dict(base, boolean_value="false")
        with self.assertRaises(PhaseBEvidenceError):
            validate_rows([failed], "inventory")
        sensitive = dict(
            base, boolean_value="", text_value="postgresql://fake.invalid/db"
        )
        with self.assertRaises(PhaseBEvidenceError):
            validate_rows([sensitive], "inventory")
        with self.assertRaises(PhaseBEvidenceError):
            validate_rows([dict(reversed(list(base.items())))], "inventory")

    def test_csv_header_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text(
                "metric,section,status,boolean_value,integer_value,text_value\n",
                encoding="utf-8",
            )
            with self.assertRaises(PhaseBEvidenceError):
                validate_csv(path, "inventory")


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PhaseBArtifactPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_database_url(DATABASE_URL)
        cls.engine = create_engine(DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self._reset()

    def _execute(self, sql: str) -> None:
        raw = self.engine.raw_connection()
        try:
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute(sql)
        finally:
            raw.close()

    def _reset(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        setup_legacy_fixture()
        self._execute(render_sql())

    def _counts(self):
        with self.engine.connect() as connection:
            return tuple(
                connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM ntubtob.people),"
                        "(SELECT count(*) FROM ntubtob.auth_identities),"
                        "(SELECT count(*) FROM ntubtob.person_qualifications),"
                        "(SELECT count(*) FROM ntubtob.access_audit),"
                        "(SELECT count(*) FROM ntubtob.members WHERE person_id IS NOT NULL)"
                    )
                ).one()
            )

    def _evidence_rows(self, path: Path):
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                sql = path.read_text(encoding="utf-8")
                query, suffix = sql.rsplit("ROLLBACK;", 1)
                self.assertFalse(suffix.strip())
                cursor.execute(query)
                names = [column.name for column in cursor.description]
                rows = cursor.fetchall()
                cursor.execute("ROLLBACK")
            return [
                dict(
                    zip(
                        names,
                        (
                            (
                                ""
                                if value is None
                                else (
                                    str(value).lower()
                                    if isinstance(value, bool)
                                    else str(value)
                                )
                            )
                            for value in row
                        ),
                    )
                )
                for row in rows
            ]
        finally:
            raw.close()

    def test_backfill_defaults_identity_qualification_audit_and_rerun(self):
        validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        sql = BACKFILL_SQL_PATH.read_text(encoding="utf-8")
        self._execute(sql)
        self.assertEqual(self._counts(), (2, 1, 1, 4, 2))
        self._execute(sql)
        self.assertEqual(self._counts(), (2, 1, 1, 4, 2))
        post = validate_rows(self._evidence_rows(POSTCHECK_SQL_PATH), "postcheck")
        self.assertEqual(post[("02_people", "nonbasic_person_count")], "0")
        self.assertEqual(post[("02_people", "noninactive_person_count")], "0")
        self.assertEqual(post[("03_identity", "ignored_identity_count")], "0")
        self.assertEqual(
            post[("04_qualification", "team_player_without_line_count")], "0"
        )

    def test_exact_transaction_rollback_restores_prestate(self):
        before = self._counts()
        self._execute(render_rollback_rehearsal())
        self.assertEqual(self._counts(), before)

    def test_multiple_line_accounts_share_one_qualification(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.line_users"
                    "(id,nickname,line_user_id,member_id,has_replied,ignored) "
                    "VALUES (9511,'虛構第二帳號','fake-line-linked-second',9201,false,false)"
                )
            )
        self._execute(BACKFILL_SQL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(self._counts(), (2, 2, 1, 5, 2))
        post = validate_rows(self._evidence_rows(POSTCHECK_SQL_PATH), "postcheck")
        self.assertEqual(post[("03_identity", "linked_identity_count")], "2")
        self.assertEqual(post[("04_qualification", "team_player_count")], "1")

    def test_precondition_and_identity_collision_fail_closed(self):
        sql = BACKFILL_SQL_PATH.read_text(encoding="utf-8")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.people(display_name,portal_access_level,portal_status,version,created_at,updated_at) "
                    "VALUES ('虛構額外人物','basic','inactive',1,now(),now())"
                )
            )
        with self.assertRaises(Exception):
            self._execute(sql)
        self.assertEqual(self._counts(), (1, 0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
