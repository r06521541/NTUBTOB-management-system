import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class EventManagementWebContractTests(unittest.TestCase):
    def test_confirmation_script_fails_closed_until_full_dialog_is_ready(self):
        script = (ROOT / "apps/web_portal/static/event_management.js").read_text(
            encoding="utf-8"
        )
        templates = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "apps/web_portal/templates/event_management.html",
                "apps/web_portal/templates/event_management_edit.html",
            )
        )

        self.assertIn("if (!dialog || forms.length === 0) return", script)
        self.assertIn("if (!message || !cancel || !confirm) return", script)
        self.assertLess(
            script.index('confirm.addEventListener("click"'),
            script.index("button.disabled = false"),
        )
        self.assertNotIn("window.confirm", script)
        self.assertIn("requestSubmit(submission.submitter)", script)
        self.assertNotRegex(templates, r'<button[^>]+type="submit"(?![^>]+disabled)')

    def test_management_templates_state_snapshot_and_notification_boundaries(self):
        edit = (
            ROOT / "apps/web_portal/templates/event_management_edit.html"
        ).read_text(encoding="utf-8")

        self.assertIn("發布時固定邀請快照", edit)
        self.assertIn("不會發送通知", edit)
        self.assertIn("快照已發布", edit)
        self.assertIn("資格池預覽", edit)
        self.assertIn("candidate.display_name", edit)
        self.assertIn("candidate.person_id", edit)
        self.assertNotIn("provider_subject", edit)
        self.assertNotIn("contact", edit.lower())
        self.assertNotIn("notify", edit.lower())


if __name__ == "__main__":
    unittest.main()
