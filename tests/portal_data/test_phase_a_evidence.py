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
from tools.portal_data_phase_a_evidence import (
    FIELDS,
    POST_FIXTURE_PATH,
    POST_SQL_PATH,
    PRE_FIXTURE_PATH,
    PRE_SQL_PATH,
    PhaseAEvidenceError,
    compare_evidence,
    validate_csv,
    validate_rows,
    verify_repository_artifacts,
    verify_sql,
)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class PhaseAEvidenceStaticTests(unittest.TestCase):
    def setUp(self):
        with PRE_FIXTURE_PATH.open(newline="", encoding="utf-8") as stream:
            self.pre_rows = list(csv.DictReader(stream))
        with POST_FIXTURE_PATH.open(newline="", encoding="utf-8") as stream:
            self.post_rows = list(csv.DictReader(stream))

    def test_repository_artifacts_are_fixed_and_valid(self):
        verify_repository_artifacts()

    def test_sql_checksum_rejects_any_mutation(self):
        for path, kind in ((PRE_SQL_PATH, "pre"), (POST_SQL_PATH, "post")):
            original = path.read_text(encoding="utf-8")
            with tempfile.TemporaryDirectory() as directory:
                mutated = Path(directory) / path.name
                mutated.write_text(
                    original.replace("ROLLBACK;", "SELECT 1;\nROLLBACK;"),
                    encoding="utf-8",
                )
                mutated.with_suffix(mutated.suffix + ".sha256").write_text(
                    path.with_suffix(path.suffix + ".sha256").read_text(
                        encoding="ascii"
                    ),
                    encoding="ascii",
                )
                with self.subTest(path=path.name), self.assertRaises(
                    PhaseAEvidenceError
                ):
                    verify_sql(mutated, kind)

    def test_rejects_missing_duplicate_unknown_and_reordered_fields(self):
        with self.assertRaises(PhaseAEvidenceError):
            validate_rows(self.pre_rows[:-1], "pre")
        with self.assertRaises(PhaseAEvidenceError):
            validate_rows([*self.pre_rows, dict(self.pre_rows[0])], "pre")
        unknown = [dict(row) for row in self.pre_rows]
        unknown[0]["metric"] = "unexpected"
        with self.assertRaises(PhaseAEvidenceError):
            validate_rows(unknown, "pre")
        reordered = [dict(reversed(list(row.items()))) for row in self.pre_rows]
        with self.assertRaises(PhaseAEvidenceError):
            validate_rows(reordered, "pre")

    def test_rejects_bad_values_sensitive_text_and_failed_gate(self):
        for field, value in (
            ("boolean_value", "yes"),
            ("integer_value", "-1"),
            ("text_value", "postgresql://fake.invalid/db"),
        ):
            rows = [dict(row) for row in self.pre_rows]
            target = rows[0]
            for value_field in FIELDS[3:]:
                target[value_field] = ""
            target[field] = value
            with self.subTest(field=field), self.assertRaises(PhaseAEvidenceError):
                validate_rows(rows, "pre")
        failed = [dict(row) for row in self.post_rows]
        next(row for row in failed if row["metric"] == "revision_matches")[
            "boolean_value"
        ] = "false"
        with self.assertRaises(PhaseAEvidenceError):
            validate_rows(failed, "post")

    def test_rejects_legacy_aggregate_drift(self):
        pre = validate_rows(self.pre_rows, "pre")
        post_rows = [dict(row) for row in self.post_rows]
        next(row for row in post_rows if row["metric"] == "members")[
            "integer_value"
        ] = "5"
        post = validate_rows(post_rows, "post")
        with self.assertRaisesRegex(PhaseAEvidenceError, "aggregate drift"):
            compare_evidence(pre, post)

    def test_csv_header_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text(
                "metric,section,status,boolean_value,integer_value,text_value\n",
                encoding="utf-8",
            )
            with self.assertRaises(PhaseAEvidenceError):
                validate_csv(path, "pre")


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PhaseAEvidencePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_database_url(DATABASE_URL)
        cls.engine = create_engine(DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def _execute_artifact(self, sql: str) -> None:
        raw = self.engine.raw_connection()
        try:
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute(sql)
        finally:
            raw.close()

    def _rows(self, path: Path) -> list[dict[str, str]]:
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                sql = path.read_text(encoding="utf-8")
                query, rollback = sql.rsplit("ROLLBACK;", 1)
                self.assertEqual(rollback.strip(), "")
                cursor.execute(query)
                names = [column.name for column in cursor.description]
                values = cursor.fetchall()
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
                for row in values
            ]
        finally:
            raw.close()

    def _reset(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        setup_legacy_fixture()

    def test_clean_pre_migration_post_rehearsal(self):
        self._reset()
        pre = validate_rows(self._rows(PRE_SQL_PATH), "pre")
        self._execute_artifact(render_sql())
        post = validate_rows(self._rows(POST_SQL_PATH), "post")
        compare_evidence(pre, post)

    def test_postcheck_rejects_rows_rls_policy_and_legacy_drift(self):
        mutations = (
            "INSERT INTO ntubtob.people(display_name,portal_access_level,"
            "portal_status,created_at,updated_at) VALUES "
            "('Fake','basic','active',now(),now())",
            "ALTER TABLE ntubtob.people DISABLE ROW LEVEL SECURITY",
            "CREATE POLICY fake_policy ON ntubtob.people USING (true)",
            "INSERT INTO ntubtob.members(name) VALUES ('Fake')",
            "DROP INDEX ntubtob.ix_auth_identities_person",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self._reset()
                pre = validate_rows(self._rows(PRE_SQL_PATH), "pre")
                self._execute_artifact(render_sql())
                with self.engine.begin() as connection:
                    connection.execute(text(mutation))
                with self.assertRaises(PhaseAEvidenceError):
                    post = validate_rows(self._rows(POST_SQL_PATH), "post")
                    compare_evidence(pre, post)

    def test_precheck_rejects_a_partial_or_completed_migration(self):
        self._reset()
        self._execute_artifact(render_sql())
        with self.assertRaises(PhaseAEvidenceError):
            validate_rows(self._rows(PRE_SQL_PATH), "pre")


if __name__ == "__main__":
    unittest.main()
