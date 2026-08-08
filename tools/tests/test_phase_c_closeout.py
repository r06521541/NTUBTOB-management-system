import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools import phase_c_closeout as closeout


DATABASE = {
    "schema_revision": "0004_phase_c_identity_lifecycle",
    "statement_logging_safe": True,
    "people_count": 3,
    "member_count": 3,
    "identity_count": 3,
    "reliable_linked_line_count": 2,
    "admin_principal_count": 1,
    "identity_drift_count": 0,
    "member_person_drift_count": 0,
    "duplicate_person_link_count": 0,
    "qualification_drift_count": 0,
    "missing_identity_count": 0,
    "wrong_person_link_count": 0,
    "identity_without_reliable_link_count": 0,
    "orphan_member_link_count": 0,
    "team_player_missing_count": 0,
    "team_player_extra_count": 0,
    "team_player_revoked_mismatch_count": 0,
    "active_team_player_count": 2,
    "game_attendance_reply_count": 4,
    "audit_count": 1,
    "duplicate_request_id_count": 0,
    "safe_ignore_candidate_count": 1,
    "safe_unignore_candidate_count": 0,
    "mutation_ignored_action_count": 0,
    "mutation_other_action_count": 0,
    "recovery_unignored_action_count": 0,
    "recovery_other_action_count": 0,
    "bounded_same_target_count": 0,
}
RUNTIME = {
    "revisions": {
        "web_portal": "web-portal-00001-abc",
        "line_webhook": "line-webhook-handler-00001-abc",
        "notify_cron": "notify-cronjob-service-00001-abc",
    },
    "traffic": {"web_portal": 100, "line_webhook": 100, "notify_cron": 100},
    "iam": {"web_portal": "public", "line_webhook": "public", "notify_cron": "private"},
    "phase_c": {"web_portal": True, "line_webhook": True, "notify_cron": True},
    "freeze": {"web_portal": False, "line_webhook": False, "notify_cron": False},
    "maintenance": False,
}


class CloseoutEvidenceTests(unittest.TestCase):
    def inventory_rows(self, **overrides):
        values = {
            ("00_session", "transaction_read_only"): (
                "required",
                "boolean_value",
                "true",
            ),
            ("00_session", "statement_logging_safe"): (
                "required",
                "boolean_value",
                "true",
            ),
            ("01_schema", "revision"): (
                "required",
                "text_value",
                "0004_phase_c_identity_lifecycle",
            ),
            ("02_identity", "people_count"): ("required", "integer_value", "3"),
            ("02_identity", "member_count"): ("required", "integer_value", "3"),
            ("02_identity", "identity_count"): ("required", "integer_value", "3"),
            ("02_identity", "reliable_linked_line_count"): (
                "required",
                "integer_value",
                "2",
            ),
            ("02_identity", "active_linked_allowlisted_admin_count"): (
                "required",
                "integer_value",
                "1",
            ),
            ("02_identity", "safe_ignore_candidate_count"): (
                "classification",
                "integer_value",
                "1",
            ),
            ("02_identity", "safe_unignore_candidate_count"): (
                "classification",
                "integer_value",
                "0",
            ),
            ("02_identity", "identity_drift_count"): ("required", "integer_value", "0"),
            ("02_identity", "member_person_drift_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("02_identity", "duplicate_person_link_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("02_identity", "missing_identity_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("02_identity", "wrong_person_link_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("02_identity", "identity_without_reliable_link_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("02_identity", "orphan_member_link_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("03_audit", "access_audit_count"): ("required", "integer_value", "10"),
            ("03_audit", "duplicate_request_id_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("03_audit", "mutation_ignored_action_count"): (
                "bounded",
                "integer_value",
                "0",
            ),
            ("03_audit", "mutation_other_action_count"): (
                "bounded",
                "integer_value",
                "0",
            ),
            ("03_audit", "recovery_unignored_action_count"): (
                "bounded",
                "integer_value",
                "0",
            ),
            ("03_audit", "recovery_other_action_count"): (
                "bounded",
                "integer_value",
                "0",
            ),
            ("03_audit", "bounded_same_target_count"): (
                "bounded",
                "integer_value",
                "0",
            ),
            ("04_qualification", "active_team_player_count"): (
                "required",
                "integer_value",
                "2",
            ),
            ("04_qualification", "qualification_drift_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("04_qualification", "team_player_missing_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("04_qualification", "team_player_extra_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("04_qualification", "team_player_revoked_mismatch_count"): (
                "required",
                "integer_value",
                "0",
            ),
            ("05_attendance", "game_attendance_reply_count"): (
                "required",
                "integer_value",
                "4",
            ),
        }
        values.update(overrides)
        rows = []
        for (section, metric), (status, field, value) in values.items():
            row = dict.fromkeys(closeout.CSV_FIELDS, "")
            row.update(section=section, metric=metric, status=status)
            row[field] = value
            rows.append(row)
        return rows

    def test_csv_ingestion_and_bounded_audit_sequence_fail_closed(self):
        database = closeout.ingest_inventory_rows(self.inventory_rows())
        before = {"database": database, "runtime": RUNTIME}
        action = {
            "database": {
                **database,
                "audit_count": 11,
                "mutation_ignored_action_count": 1,
                "safe_ignore_candidate_count": 0,
                "safe_unignore_candidate_count": 1,
            },
            "runtime": RUNTIME,
        }
        retry = {"database": dict(action["database"]), "runtime": RUNTIME}
        recovery = {
            "database": {
                **database,
                "audit_count": 12,
                "mutation_ignored_action_count": 1,
                "recovery_unignored_action_count": 1,
                "bounded_same_target_count": 1,
            },
            "runtime": RUNTIME,
        }
        post = {"database": dict(recovery["database"]), "runtime": RUNTIME}
        closeout.compare_sequence(before, action, retry, recovery, post)
        with self.assertRaises(closeout.CloseoutEvidenceError):
            closeout.compare_sequence(before, before, retry, recovery, post)

    def test_sequence_requires_exact_candidate_deltas_and_same_target(self):
        before = {"database": DATABASE, "runtime": RUNTIME}
        action_database = {
            **DATABASE,
            "audit_count": 2,
            "safe_ignore_candidate_count": 0,
            "safe_unignore_candidate_count": 1,
            "mutation_ignored_action_count": 1,
        }
        action = {"database": action_database, "runtime": RUNTIME}
        recovery_database = {
            **DATABASE,
            "audit_count": 3,
            "mutation_ignored_action_count": 1,
            "recovery_unignored_action_count": 1,
            "bounded_same_target_count": 1,
        }
        recovery = {"database": recovery_database, "runtime": RUNTIME}
        closeout.compare_sequence(before, action, action, recovery, recovery)
        cases = (
            {**action_database, "safe_ignore_candidate_count": 1},
            {**action_database, "safe_unignore_candidate_count": 2},
            {**recovery_database, "bounded_same_target_count": 0},
        )
        for drift in cases:
            with (
                self.subTest(drift=drift),
                self.assertRaises(closeout.CloseoutEvidenceError),
            ):
                if "bounded_same_target_count" in drift and drift["audit_count"] == 3:
                    bad_recovery = {"database": drift, "runtime": RUNTIME}
                    closeout.compare_sequence(
                        before, action, action, bad_recovery, bad_recovery
                    )
                else:
                    bad_action = {"database": drift, "runtime": RUNTIME}
                    closeout.compare_sequence(
                        before, bad_action, bad_action, recovery, recovery
                    )

    def test_sequence_rejects_runtime_revision_or_aggregate_drift(self):
        before = {"database": DATABASE, "runtime": RUNTIME}
        action_database = {
            **DATABASE,
            "audit_count": 2,
            "safe_ignore_candidate_count": 0,
            "safe_unignore_candidate_count": 1,
            "mutation_ignored_action_count": 1,
        }
        action = {"database": action_database, "runtime": RUNTIME}
        recovery_database = {
            **DATABASE,
            "audit_count": 3,
            "mutation_ignored_action_count": 1,
            "recovery_unignored_action_count": 1,
            "bounded_same_target_count": 1,
        }
        recovery = {"database": recovery_database, "runtime": RUNTIME}
        changed_revision = {
            **RUNTIME,
            "revisions": {**RUNTIME["revisions"], "web_portal": "web-portal-00002-xyz"},
        }
        cases = [{"database": action_database, "runtime": changed_revision}]
        cases.extend(
            {
                "database": {**action_database, field: value + 1},
                "runtime": RUNTIME,
            }
            for field, value in (
                ("people_count", DATABASE["people_count"]),
                ("member_count", DATABASE["member_count"]),
                ("identity_count", DATABASE["identity_count"]),
                (
                    "reliable_linked_line_count",
                    DATABASE["reliable_linked_line_count"],
                ),
                ("active_team_player_count", DATABASE["active_team_player_count"]),
                (
                    "game_attendance_reply_count",
                    DATABASE["game_attendance_reply_count"],
                ),
            )
        )
        for bad_action in cases:
            with (
                self.subTest(action=bad_action),
                self.assertRaises(closeout.CloseoutEvidenceError),
            ):
                closeout.compare_sequence(
                    before, bad_action, action, recovery, recovery
                )

    def test_complete_sql_row_contract_rejects_every_shape_drift(self):
        rows = self.inventory_rows()
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=closeout.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        closeout.ingest_inventory_rows(closeout.parse_inventory_csv(stream.getvalue()))
        cases = (
            rows[:-1],
            [*rows, dict(rows[0])],
            [*rows, {**rows[0], "metric": "unknown"}],
            [{**rows[0], "status": "risk"}, *rows[1:]],
            [{**rows[0], "boolean_value": "", "integer_value": "1"}, *rows[1:]],
            [{**rows[2], "integer_value": "bad"}, *rows[:2], *rows[3:]],
        )
        for case in cases:
            with (
                self.subTest(rows=len(case)),
                self.assertRaises(closeout.CloseoutEvidenceError),
            ):
                closeout.ingest_inventory_rows(case)

    def test_inventory_artifact_is_checksummed_and_read_only(self):
        attributes = (closeout.ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn(
            "docs/operations/sql/TASK-084-phase-c-closeout-inventory.sql text eol=lf",
            attributes,
        )
        self.assertIn(
            "docs/operations/sql/TASK-084-phase-c-closeout-inventory.sql.sha256 text eol=lf",
            attributes,
        )
        closeout.verify_inventory_artifact()
        sql = closeout.INVENTORY_SQL_PATH.read_text(encoding="utf-8")
        self.assertIn("ntubtob.game_attendance_replies", sql)
        self.assertNotIn("line_notify_tokens", sql)
        with tempfile.TemporaryDirectory() as directory:
            crlf_path = Path(directory) / closeout.INVENTORY_SQL_PATH.name
            crlf_path.write_bytes(
                closeout.INVENTORY_SQL_PATH.read_bytes()
                .replace(b"\r\n", b"\n")
                .replace(b"\n", b"\r\n")
            )
            crlf_path.with_suffix(crlf_path.suffix + ".sha256").write_text(
                closeout.INVENTORY_SQL_PATH.with_suffix(".sql.sha256").read_text(
                    encoding="ascii"
                ),
                encoding="ascii",
            )
            closeout.verify_inventory_artifact(crlf_path)

            path = Path(directory) / closeout.INVENTORY_SQL_PATH.name
            path.write_bytes(
                closeout.INVENTORY_SQL_PATH.read_bytes() + b"\nUPDATE fake\n"
            )
            path.with_suffix(path.suffix + ".sha256").write_text(
                closeout.INVENTORY_SQL_PATH.with_suffix(".sql.sha256").read_text(
                    encoding="ascii"
                ),
                encoding="ascii",
            )
            with self.assertRaises(closeout.CloseoutEvidenceError):
                closeout.verify_inventory_artifact(path)

    def test_manifest_accepts_redacted_safe_evidence(self):
        manifest = closeout.build_manifest(DATABASE, RUNTIME)
        self.assertEqual(
            json.loads(closeout.render_manifest(manifest))["schema"],
            "phase-c-closeout-v1",
        )

    def test_database_and_runtime_drift_fail_closed(self):
        cases = (
            ({**DATABASE, "admin_principal_count": 0}, RUNTIME),
            ({**DATABASE, "statement_logging_safe": False}, RUNTIME),
            ({**DATABASE, "duplicate_request_id_count": 1}, RUNTIME),
            ({**DATABASE, "missing_identity_count": 1}, RUNTIME),
            ({**DATABASE, "duplicate_person_link_count": 1}, RUNTIME),
            (DATABASE, {**RUNTIME, "traffic": {**RUNTIME["traffic"], "web_portal": 0}}),
            (
                DATABASE,
                {**RUNTIME, "freeze": {**RUNTIME["freeze"], "notify_cron": True}},
            ),
        )
        for database, runtime in cases:
            with self.subTest(database=database, runtime=runtime):
                with self.assertRaises(closeout.CloseoutEvidenceError):
                    closeout.build_manifest(database, runtime)

    def test_manifest_rejects_identifier_or_sensitive_extra_content(self):
        manifest = closeout.build_manifest(DATABASE, RUNTIME)
        with self.assertRaises(closeout.CloseoutEvidenceError):
            closeout.render_manifest({**manifest, "candidate_id": "forbidden"})
