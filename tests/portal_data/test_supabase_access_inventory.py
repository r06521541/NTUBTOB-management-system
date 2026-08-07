from __future__ import annotations

import csv
import io
import unittest
from pathlib import Path

from tools.supabase_access_inventory import (
    FIELDS,
    FIXTURE_PATH,
    SQL_PATH,
    InventoryValidationError,
    validate_csv,
    validate_rows,
    verify_sql,
)


class SupabaseAccessInventorySqlTests(unittest.TestCase):
    def setUp(self):
        self.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_committed_query_is_safe(self):
        verify_sql(self.sql)

    def test_rejects_transaction_boundary_mutations(self):
        for mutated in (
            self.sql.replace("BEGIN TRANSACTION READ ONLY;", "BEGIN;", 1),
            self.sql.replace("ROLLBACK;", "COMMIT;", 1),
            self.sql.replace("ROLLBACK;", "", 1),
        ):
            with self.subTest(mutated=mutated[-30:]):
                with self.assertRaises(InventoryValidationError):
                    verify_sql(mutated)

    def test_rejects_mutation_and_role_operations(self):
        for statement in (
            "INSERT INTO ntubtob.members (name) VALUES ('Fake');",
            "UPDATE ntubtob.members SET name = 'Fake';",
            "DELETE FROM ntubtob.members;",
            "MERGE INTO ntubtob.members USING source ON true WHEN MATCHED THEN DELETE;",
            "COPY ntubtob.members TO STDOUT;",
            "TRUNCATE ntubtob.members;",
            "CREATE TABLE ntubtob.unsafe (id integer);",
            "ALTER TABLE ntubtob.members ADD COLUMN unsafe text;",
            "DROP TABLE ntubtob.members;",
            "GRANT SELECT ON ntubtob.members TO public;",
            "REVOKE SELECT ON ntubtob.members FROM public;",
            "SET ROLE postgres;",
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(InventoryValidationError):
                    verify_sql(self.sql.replace("ROLLBACK;", statement + "\nROLLBACK;"))

    def test_rejects_application_rows_unknown_catalogs_and_helpers(self):
        for statement in (
            "SELECT * FROM ntubtob.members;",
            "SELECT * FROM information_schema.tables;",
            "SELECT pg_read_file('/fake');",
            "SELECT lo_export(1, '/fake');",
            "SELECT * FROM dblink('fake', 'select 1') AS x(value integer);",
            "SELECT net.http_get(url := 'https://example.invalid');",
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(InventoryValidationError):
                    verify_sql(self.sql.replace("ROLLBACK;", statement + "\nROLLBACK;"))

    def test_rejects_raw_identity_output_and_contract_drift(self):
        raw_output = self.sql.replace(
            "SELECT section, metric, status, boolean_value, integer_value, text_value",
            "SELECT section, metric, status, boolean_value, integer_value, text_value, current_user",
            1,
        )
        with self.assertRaises(InventoryValidationError):
            verify_sql(raw_output)
        with self.assertRaises(InventoryValidationError):
            verify_sql(
                self.sql.replace(
                    "text_value\nFROM inventory", "text_value, details\nFROM inventory"
                )
            )

        for identity_expression in (
            "r.rolname::text",
            "policyname",
            "qual::text",
            "with_check::text",
            "grantee::text",
            "tableowner",
        ):
            with self.subTest(identity_expression=identity_expression):
                with self.assertRaises(InventoryValidationError):
                    verify_sql(
                        self.sql.replace(
                            "text_value\nFROM inventory",
                            f"{identity_expression}\nFROM inventory",
                            1,
                        )
                    )

    def test_rejects_missing_or_unknown_result_metric(self):
        with self.assertRaises(InventoryValidationError):
            verify_sql(
                self.sql.replace(
                    "'00_session', 'server_major'",
                    "'00_session', 'unexpected_metric'",
                    1,
                )
            )


class SupabaseAccessInventoryResultTests(unittest.TestCase):
    def setUp(self):
        with FIXTURE_PATH.open(newline="", encoding="utf-8") as stream:
            self.rows = list(csv.DictReader(stream))

    def test_fake_fixture_matches_contract(self):
        self.assertEqual(len(validate_csv(FIXTURE_PATH)), 33)

    def test_rejects_unknown_extra_or_missing_fields(self):
        extra = dict(self.rows[0])
        extra["role_name"] = "fake_role"
        with self.assertRaises(InventoryValidationError):
            validate_rows([extra, *self.rows[1:]])
        missing = [row for row in self.rows if row["metric"] != "policy_count"]
        with self.assertRaises(InventoryValidationError):
            validate_rows(missing)
        unknown = [dict(row) for row in self.rows]
        unknown[0]["section"] = "99_unknown"
        with self.assertRaises(InventoryValidationError):
            validate_rows(unknown)

    def test_rejects_duplicate_invalid_or_multi_value_rows(self):
        duplicated = [*self.rows, dict(self.rows[0])]
        with self.assertRaises(InventoryValidationError):
            validate_rows(duplicated)
        invalid = [dict(row) for row in self.rows]
        invalid[0]["boolean_value"] = "yes"
        with self.assertRaises(InventoryValidationError):
            validate_rows(invalid)
        multi = [dict(row) for row in self.rows]
        multi[0]["integer_value"] = "1"
        with self.assertRaises(InventoryValidationError):
            validate_rows(multi)

    def test_rejects_sensitive_values(self):
        samples = (
            "actual_role_name",
            "person@example.com",
            "https://project.example",
            "postgresql://user:pass@host/db",
            "USING (member_id = 1)",
            "secret",
        )
        for sample in samples:
            rows = [dict(row) for row in self.rows]
            target = next(row for row in rows if row["text_value"])
            target["text_value"] = sample
            with self.subTest(sample=sample):
                with self.assertRaises(InventoryValidationError):
                    validate_rows(rows)

    def test_csv_header_order_is_exact(self):
        data = io.StringIO()
        writer = csv.DictWriter(data, fieldnames=(*FIELDS, "extra"))
        writer.writeheader()
        temporary = Path("tests/fixtures/task052_invalid_header.csv")
        try:
            temporary.write_text(data.getvalue(), encoding="utf-8")
            with self.assertRaises(InventoryValidationError):
                validate_csv(temporary)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
