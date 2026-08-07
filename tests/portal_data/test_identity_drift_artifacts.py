from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import \
    require_local_database_url
from tools.portal_data_identity_drift import (FIELDS, INVENTORY_SCHEMA,
                                              INVENTORY_SQL_PATH,
                                              IdentityDriftEvidenceError,
                                              validate_rows, verify_artifact)
from tools.portal_data_migration_readiness import render_sql
from tools.portal_data_phase_b import \
    INVENTORY_SQL_PATH as PHASE_B_INVENTORY_PATH
from tools.portal_data_phase_b import render_backfill
from tools.portal_data_phase_b import validate_rows as validate_phase_b_rows
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


def _valid_rows(pending: str = "0", ignored: str = "0"):
    exact = {
        ("01_phase_a", "revision"): "0003_legacy_bigint_activity_game",
        ("01_phase_a", "portal_table_count"): "13",
        ("01_phase_a", "portal_rls_enabled_count"): "13",
        ("01_phase_a", "portal_rls_forced_count"): "0",
        ("01_phase_a", "append_only_trigger_count"): "2",
        ("03_identity", "pending_candidate_count"): pending,
        ("03_identity", "ignored_candidate_count"): ignored,
    }
    rows = []
    for key in sorted(INVENTORY_SCHEMA):
        spec = INVENTORY_SCHEMA[key]
        row = dict.fromkeys(FIELDS, "")
        row.update(section=key[0], metric=key[1], status="required")
        row[spec.field] = exact.get(
            key, "true" if spec.field == "boolean_value" else "0"
        )
        rows.append(row)
    return rows


class IdentityDriftArtifactStaticTests(unittest.TestCase):
    def test_repository_artifact_is_checksummed_and_read_only(self):
        verify_artifact()

    def test_checksum_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / INVENTORY_SQL_PATH.name
            path.write_bytes(INVENTORY_SQL_PATH.read_bytes() + b"\n-- changed\n")
            path.with_suffix(".sql.sha256").write_text(
                INVENTORY_SQL_PATH.with_suffix(".sql.sha256").read_text(
                    encoding="ascii"
                ),
                encoding="ascii",
            )
            with self.assertRaises(IdentityDriftEvidenceError):
                verify_artifact(path)

    def test_pending_and_ignored_counts_are_informational(self):
        evidence = validate_rows(_valid_rows(pending="2", ignored="3"))
        self.assertEqual(evidence[("03_identity", "pending_candidate_count")], "2")
        self.assertEqual(evidence[("03_identity", "ignored_candidate_count")], "3")

    def test_validator_rejects_contract_and_unsafe_drift(self):
        rows = _valid_rows()
        cases = []
        cases.append(rows[:-1])
        cases.append([*rows, dict(rows[0])])
        cases.append([*rows, {**rows[0], "metric": "unexpected"}])
        cases.append([*rows[1:], rows[0]])
        cases.append([{**rows[0], "integer_value": "0"}, *rows[1:]])
        unsafe = [dict(row) for row in rows]
        index = next(
            i for i, row in enumerate(unsafe) if row["metric"] == "missing_identity_count"
        )
        unsafe[index]["integer_value"] = "1"
        cases.append(unsafe)
        sensitive = [dict(row) for row in rows]
        sensitive[1]["text_value"] = "token-value"
        cases.append(sensitive)
        for case in cases:
            with self.subTest(rows=len(case)), self.assertRaises(
                IdentityDriftEvidenceError
            ):
                validate_rows(case)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class IdentityDriftArtifactPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_database_url(DATABASE_URL)
        cls.engine = create_engine(DATABASE_URL)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def _execute(self, sql: str) -> None:
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute(sql)
            raw.commit()
        finally:
            raw.close()

    def _evidence_rows(self, path: Path):
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                query, suffix = path.read_text(encoding="utf-8").rsplit("ROLLBACK;", 1)
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
                            ""
                            if value is None
                            else str(value).lower()
                            if isinstance(value, bool)
                            else str(value)
                            for value in row
                        ),
                    )
                )
                for row in rows
            ]
        finally:
            raw.close()

    def _reset(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        setup_legacy_fixture()
        self._execute(render_sql())
        phase_b = validate_phase_b_rows(
            self._evidence_rows(PHASE_B_INVENTORY_PATH), "inventory"
        )
        self._execute(render_backfill(phase_b))

    def test_consistent_state_allows_pending_and_ignored_candidates(self):
        self._reset()
        evidence = validate_rows(self._evidence_rows(INVENTORY_SQL_PATH))
        self.assertEqual(evidence[("03_identity", "pending_candidate_count")], "1")
        self.assertEqual(evidence[("03_identity", "ignored_candidate_count")], "1")

    def test_each_cross_model_drift_fails_closed(self):
        mutations = {
            "missing identity": "UPDATE ntubtob.auth_identities SET status='disabled'",
            "wrong person": "UPDATE ntubtob.auth_identities SET person_id=(SELECT person_id FROM ntubtob.members WHERE id=9202)",
            "identity without reliable link": "UPDATE ntubtob.auth_identities SET provider_subject='fake-line-pending'",
            "team player missing": "UPDATE ntubtob.person_qualifications SET status='revoked'",
            "team player extra": "INSERT INTO ntubtob.person_qualifications (person_id,qualification,status,reason,created_at,updated_at) SELECT person_id,'team_player','active','local drift fixture',now(),now() FROM ntubtob.members WHERE id=9202",
            "duplicate subject": "ALTER TABLE ntubtob.auth_identities DROP CONSTRAINT uq_auth_provider_subject; INSERT INTO ntubtob.auth_identities (provider,provider_subject,person_id,status,created_at,updated_at) SELECT provider,provider_subject,person_id,status,now(),now() FROM ntubtob.auth_identities LIMIT 1",
            "orphan member": "ALTER TABLE ntubtob.line_users DROP CONSTRAINT ntubtob_line_users_member_id_fkey; UPDATE ntubtob.line_users SET member_id=999999 WHERE id=9502",
            "unexpected audit": "INSERT INTO ntubtob.access_audit (action,reason,request_id,created_at) VALUES ('status_changed','local drift fixture','task068-unexpected',now())",
            "inconsistent audit": "INSERT INTO ntubtob.access_audit (action,target_person_id,reason,request_id,created_at) SELECT 'identity_linked',person_id,'local drift fixture','task065-inconsistent',now() FROM ntubtob.members WHERE id=9202",
        }
        for name, mutation in mutations.items():
            with self.subTest(drift=name):
                self._reset()
                self._execute(mutation)
                with self.assertRaises(IdentityDriftEvidenceError):
                    validate_rows(self._evidence_rows(INVENTORY_SQL_PATH))

    def test_forced_rls_and_exact_audit_relationship_drift_fail_closed(self):
        audit_trigger = (
            "ALTER TABLE ntubtob.access_audit DISABLE TRIGGER "
            "access_audit_append_only; "
        )
        mutations = {
            "forced RLS": (
                "ALTER TABLE ntubtob.people FORCE ROW LEVEL SECURITY",
                ("01_phase_a", "portal_rls_forced_count"),
            ),
            "task065-prefixed unexpected action": (
                "INSERT INTO ntubtob.access_audit "
                "(action,reason,request_id,created_at) VALUES "
                "('status_changed','local drift fixture','task065-status-1',now())",
                ("05_audit", "unexpected_audit_count"),
            ),
            "malformed deterministic request ID": (
                audit_trigger
                + "UPDATE ntubtob.access_audit SET request_id='task065-member-999999' "
                "WHERE action='member_backfilled' AND request_id='task065-member-9201'; "
                "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER access_audit_append_only",
                ("05_audit", "inconsistent_audit_count"),
            ),
            "wrong before state": (
                audit_trigger
                + "UPDATE ntubtob.access_audit SET before_state='{}'::json "
                "WHERE action='member_backfilled' AND request_id='task065-member-9201'; "
                "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER access_audit_append_only",
                ("05_audit", "inconsistent_audit_count"),
            ),
            "wrong after state": (
                audit_trigger
                + "UPDATE ntubtob.access_audit SET after_state='{}'::json "
                "WHERE action='identity_linked'; "
                "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER access_audit_append_only",
                ("05_audit", "inconsistent_audit_count"),
            ),
            "wrong actor relationship": (
                audit_trigger
                + "UPDATE ntubtob.access_audit SET actor_person_id=target_person_id "
                "WHERE action='qualification_granted'; "
                "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER access_audit_append_only",
                ("05_audit", "inconsistent_audit_count"),
            ),
            "wrong auth relationship": (
                audit_trigger
                + "UPDATE ntubtob.access_audit SET auth_identity_id="
                "(SELECT id FROM ntubtob.auth_identities LIMIT 1) "
                "WHERE action='member_backfilled' AND request_id='task065-member-9201'; "
                "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER access_audit_append_only",
                ("05_audit", "inconsistent_audit_count"),
            ),
            "wrong target relationship": (
                audit_trigger
                + "UPDATE ntubtob.access_audit SET target_person_id="
                "(SELECT person_id FROM ntubtob.members WHERE id=9202) "
                "WHERE action='identity_linked'; "
                "ALTER TABLE ntubtob.access_audit ENABLE TRIGGER access_audit_append_only",
                ("05_audit", "inconsistent_audit_count"),
            ),
        }
        for name, (mutation, expected_metric) in mutations.items():
            with self.subTest(drift=name):
                self._reset()
                self._execute(mutation)
                rows = self._evidence_rows(INVENTORY_SQL_PATH)
                matching = [
                    row
                    for row in rows
                    if (row["section"], row["metric"]) == expected_metric
                ]
                self.assertEqual(len(matching), 1)
                self.assertNotEqual(matching[0]["integer_value"], "0")
                with self.assertRaises(IdentityDriftEvidenceError):
                    validate_rows(rows)


if __name__ == "__main__":
    unittest.main()
