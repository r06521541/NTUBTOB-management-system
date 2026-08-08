import json
import tempfile
import unittest
from pathlib import Path

from tools import phase_c_closeout as closeout


DATABASE = {
    "schema_revision": "0004_phase_c_identity_lifecycle",
    "admin_principal_count": 1,
    "identity_drift_count": 0,
    "member_person_drift_count": 0,
    "qualification_drift_count": 0,
    "audit_count": 1,
    "duplicate_request_id_count": 0,
    "safe_candidate_count": 0,
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
    def test_inventory_artifact_is_checksummed_and_read_only(self):
        closeout.verify_inventory_artifact()
        with tempfile.TemporaryDirectory() as directory:
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
            ({**DATABASE, "duplicate_request_id_count": 1}, RUNTIME),
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
