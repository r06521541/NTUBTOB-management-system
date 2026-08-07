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
    FIELDS,
    INVENTORY_SCHEMA,
    INVENTORY_SQL_PATH,
    POSTCHECK_SCHEMA,
    POSTCHECK_SQL_PATH,
    PhaseBEvidenceError,
    compare_evidence,
    render_backfill,
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
    @staticmethod
    def _valid_rows(schema):
        exact_values = {
            ("01_phase_a", "revision"): "0003_legacy_bigint_activity_game",
            ("01_phase_a", "portal_table_count"): "13",
            ("01_phase_a", "portal_rls_enabled_count"): "13",
            ("01_phase_a", "append_only_trigger_count"): "2",
        }
        rows = []
        for key, spec in schema.items():
            value = exact_values.get(key)
            if value is None:
                value = "true" if spec.field == "boolean_value" else "0"
            row = dict.fromkeys(FIELDS, "")
            row.update(section=key[0], metric=key[1], status=spec.status)
            row[spec.field] = value
            rows.append(row)
        return rows

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

    def test_metric_schema_fixes_status_field_and_gate_for_every_metric(self):
        for kind, schema in (
            ("inventory", INVENTORY_SCHEMA),
            ("postcheck", POSTCHECK_SCHEMA),
        ):
            rows = self._valid_rows(schema)
            validate_rows(rows, kind)
            for index, (key, spec) in enumerate(schema.items()):
                with self.subTest(kind=kind, key=key, failure="status"):
                    mutated = [dict(row) for row in rows]
                    mutated[index]["status"] = "unexpected"
                    with self.assertRaises(PhaseBEvidenceError):
                        validate_rows(mutated, kind)
                with self.subTest(kind=kind, key=key, failure="field"):
                    mutated = [dict(row) for row in rows]
                    mutated[index][spec.field] = ""
                    wrong_field = next(
                        field for field in FIELDS[3:] if field != spec.field
                    )
                    mutated[index][wrong_field] = "0"
                    with self.assertRaises(PhaseBEvidenceError):
                        validate_rows(mutated, kind)
                with self.subTest(kind=kind, key=key, failure="gate"):
                    mutated = [dict(row) for row in rows]
                    current = mutated[index][spec.field]
                    if spec.field == "boolean_value":
                        bad = "false"
                    elif spec.field == "text_value":
                        bad = "unexpected"
                    elif current == "0":
                        bad = "1" if spec.status != "compare" else "-1"
                    else:
                        bad = str(int(current) + 1)
                    mutated[index][spec.field] = bad
                    with self.assertRaises(PhaseBEvidenceError):
                        validate_rows(mutated, kind)

    def test_validator_rejects_missing_duplicate_unknown_and_reordered_rows(self):
        rows = self._valid_rows(INVENTORY_SCHEMA)
        for mutated in (
            rows[:-1],
            [*rows, dict(rows[0])],
            [dict(row) for row in rows],
        ):
            if len(mutated) == len(rows):
                mutated[0]["metric"] = "unknown"
            with self.assertRaises(PhaseBEvidenceError):
                validate_rows(mutated, "inventory")
        reordered = [dict(reversed(list(row.items()))) for row in rows]
        with self.assertRaises(PhaseBEvidenceError):
            validate_rows(reordered, "inventory")

    def test_csv_header_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text(
                "metric,section,status,boolean_value,integer_value,text_value\n",
                encoding="utf-8",
            )
            with self.assertRaises(PhaseBEvidenceError):
                validate_csv(path, "inventory")

    def test_public_renderer_rejects_unvalidated_mapping_bypasses(self):
        rows = self._valid_rows(INVENTORY_SCHEMA)
        valid = validate_rows(rows, "inventory")
        render_backfill(valid)
        cases = []
        partial = dict(valid)
        partial.pop(next(iter(partial)))
        cases.append(partial)
        wrong_revision = dict(valid)
        wrong_revision[("01_phase_a", "revision")] = "WRONG"
        cases.append(wrong_revision)
        nonzero_gate = dict(valid)
        nonzero_gate[("02_precondition", "people_count")] = "999"
        cases.append(nonzero_gate)
        unknown = dict(valid)
        unknown[("99_unknown", "unexpected")] = "0"
        cases.append(unknown)
        for mapping in cases:
            with self.subTest(keys=len(mapping)), self.assertRaises(
                PhaseBEvidenceError
            ):
                render_backfill(mapping)


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
        inventory = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        sql = render_backfill(inventory)
        self._execute(sql)
        self.assertEqual(self._counts(), (2, 1, 1, 4, 2))
        self._execute(sql)
        self.assertEqual(self._counts(), (2, 1, 1, 4, 2))
        post = validate_rows(self._evidence_rows(POSTCHECK_SQL_PATH), "postcheck")
        compare_evidence(inventory, post)
        self.assertEqual(post[("02_people", "nonbasic_person_count")], "0")
        self.assertEqual(post[("02_people", "noninactive_person_count")], "0")
        self.assertEqual(post[("03_identity", "ignored_identity_count")], "0")
        self.assertEqual(
            post[("04_qualification", "team_player_without_line_count")], "0"
        )

    def test_exact_transaction_rollback_restores_prestate(self):
        before = self._counts()
        inventory = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        self._execute(render_rollback_rehearsal(inventory))
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
        inventory = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        self._execute(render_backfill(inventory))
        self.assertEqual(self._counts(), (2, 2, 1, 5, 2))
        post = validate_rows(self._evidence_rows(POSTCHECK_SQL_PATH), "postcheck")
        self.assertEqual(post[("03_identity", "linked_identity_count")], "2")
        self.assertEqual(post[("04_qualification", "team_player_count")], "1")

    def test_precondition_and_identity_collision_fail_closed(self):
        inventory = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        sql = render_backfill(inventory)
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

    def test_execution_time_legacy_count_drift_fails_before_writes(self):
        inventory = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        sql = render_backfill(inventory)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.line_users"
                    "(id,nickname,line_user_id,member_id,has_replied,ignored) "
                    "VALUES (9512,'虛構盤點後帳號','fake-after-inventory',NULL,false,false)"
                )
            )
        with self.assertRaises(Exception):
            self._execute(sql)
        self.assertEqual(self._counts(), (0, 0, 0, 0, 0))

    def test_execution_time_forced_rls_and_trigger_drift_fail_before_writes(self):
        mutations = (
            "ALTER TABLE ntubtob.people FORCE ROW LEVEL SECURITY",
            "DROP TRIGGER access_audit_append_only ON ntubtob.access_audit",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                inventory = validate_rows(
                    self._evidence_rows(INVENTORY_SQL_PATH), "inventory"
                )
                sql = render_backfill(inventory)
                with self.engine.begin() as connection:
                    connection.execute(text(mutation))
                with self.assertRaises(Exception):
                    self._execute(sql)
                self.assertEqual(self._counts(), (0, 0, 0, 0, 0))
                self._reset()

    def test_postcheck_rejects_unexpected_and_inconsistent_audit(self):
        inventory = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH), "inventory")
        self._execute(render_backfill(inventory))
        mutations = (
            "INSERT INTO ntubtob.access_audit(action,reason,request_id,created_at) "
            "VALUES ('status_changed','虛構額外稽核','other-request',now())",
            "INSERT INTO ntubtob.access_audit(action,reason,request_id,created_at) "
            "VALUES ('member_backfilled','虛構不一致稽核','task065-member-999999',now())",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.engine.begin() as connection:
                    connection.execute(text(mutation))
                with self.assertRaises(PhaseBEvidenceError):
                    validate_rows(self._evidence_rows(POSTCHECK_SQL_PATH), "postcheck")
                self._reset()
                inventory = validate_rows(
                    self._evidence_rows(INVENTORY_SQL_PATH), "inventory"
                )
                self._execute(render_backfill(inventory))


if __name__ == "__main__":
    unittest.main()
