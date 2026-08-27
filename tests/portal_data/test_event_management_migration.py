import unittest
from pathlib import Path

from shared_lib.shared_module.portal_data.models import EventAuditRecord

ROOT = Path(__file__).resolve().parents[2]


class EventManagementMigrationContractTests(unittest.TestCase):
    def test_revision_is_additive_and_retains_audit_evidence_on_downgrade(self):
        migration = (
            ROOT / "migrations/versions/0009_event_management_writes.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'down_revision: Union[str, None] = "0008_mobile_notification_delivery"',
            migration,
        )
        self.assertIn("'edited'", migration)
        self.assertIn("'cancelled'", migration)
        downgrade = migration.split("def downgrade() -> None:", 1)[1]
        self.assertNotIn("DROP TABLE", downgrade)
        self.assertNotIn("DELETE FROM", downgrade)

    def test_model_accepts_only_explicit_event_audit_actions(self):
        constraints = " ".join(
            str(constraint.sqltext)
            for constraint in EventAuditRecord.__table__.constraints
            if getattr(constraint, "name", None) == "ck_event_audit_action"
        )
        for action in ("published", "edited", "cancelled"):
            self.assertIn(action, constraints)
        self.assertNotIn("notification", constraints)


if __name__ == "__main__":
    unittest.main()
