import json
import unittest
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "openapi.json"


class OpenApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_canonical_routes_match_runtime_surface(self):
        self.assertEqual(
            set(self.contract["paths"]),
            {
                "/auth/line/exchange",
                "/auth/refresh",
                "/auth/logout",
                "/me",
                "/games",
                "/games/{game_id}",
                "/games/{game_id}/attendance",
                "/games/{game_id}/attendance-report",
                "/games/{game_id}/attendance-reply",
                "/notifications",
                "/notifications/unread-count",
                "/notifications/{notification_id}",
                "/notifications/{notification_id}/read",
                "/notifications/read-all",
            },
        )

    def test_public_reply_enum_and_error_codes_are_exact(self):
        schemas = self.contract["components"]["schemas"]
        self.assertEqual(
            schemas["AttendanceReply"]["enum"],
            [
                "attending",
                "not_attending",
                "arriving_late",
                "leaving_early",
                "undecided",
            ],
        )
        codes = schemas["Error"]["properties"]["error"]["properties"]["code"]["enum"]
        for required in (
            "identity_pending",
            "account_unavailable",
            "unauthenticated",
            "forbidden",
            "resource_not_found",
            "idempotency_conflict",
            "validation_failed",
            "rate_limited",
            "service_unavailable",
        ):
            self.assertIn(required, codes)

    def test_transport_bounds_privacy_and_reconcile_semantics_are_explicit(self):
        text = CONTRACT.read_text(encoding="utf-8")
        for required in (
            "Refresh-Attempt-ID",
            "Idempotency-Key",
            "Authorization header only",
            "exact replay grace 300 seconds",
            "terminal result retention 86400 seconds",
            "no unreplied roster",
            "reconcile with GET attendance",
            "expected_version is intentionally absent",
            "redacted from logs",
        ):
            self.assertIn(required, text)

    def test_officer_report_contract_is_bounded_and_low_sensitive(self):
        schemas = self.contract["components"]["schemas"]
        self.assertEqual(
            schemas["Person"]["properties"]["access_level"]["enum"],
            ["basic", "officer", "admin"],
        )
        self.assertIn(
            "attendance:report:read",
            schemas["Person"]["properties"]["capabilities"]["items"]["enum"],
        )
        report = schemas["AttendanceReport"]
        self.assertEqual(
            set(report["properties"]),
            {
                "game_id",
                "generated_at",
                "observation",
                "attending",
                "not_attending",
                "not_yet_replied",
            },
        )
        serialized = json.dumps(report, sort_keys=True)
        for private in ("provider_subject", "admin_note", "audit", "contact"):
            self.assertNotIn(private, serialized)

    def test_deployment_unit_is_static_python310_and_excludes_private_env(self):
        root = CONTRACT.parent
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        bootstrap = (root / "bootstrap.py").read_text(encoding="utf-8")
        env_example = (root / ".env_example.yaml").read_text(encoding="utf-8")
        ignored = (root / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.10-slim", dockerfile)
        self.assertIn("bootstrap:app", dockerfile)
        self.assertNotIn("PyJWT", requirements)
        self.assertIn("LineIdTokenVerifier()", bootstrap)
        self.assertNotIn("MOBILE_LINE_PUBLIC_KEY", bootstrap + env_example)
        self.assertIn("cryptography==43.0.3", requirements)
        self.assertIn(".env.yaml", ignored)
        self.assertNotIn("gcloud", dockerfile + (root / "cloudbuild.yaml").read_text())

    def test_notification_contract_freezes_visibility_cursor_and_idempotent_reads(self):
        schemas = self.contract["components"]["schemas"]
        self.assertEqual(
            schemas["NotificationType"]["enum"],
            [
                "game_reminder",
                "attendance_reminder",
                "game_change",
                "officer_personal",
                "officer_game_broadcast",
                "officer_team_broadcast",
                "admin_system_announcement",
            ],
        )
        self.assertEqual(
            schemas["Notification"]["properties"]["body"]["maxLength"], 500
        )
        notification_id = self.contract["components"]["parameters"]["NotificationId"][
            "schema"
        ]
        self.assertEqual(notification_id["maxLength"], 32)
        self.assertEqual(schemas["Notification"]["properties"]["id"]["maxLength"], 32)
        self.assertIn(
            "exactly created_at plus 90 days",
            schemas["Notification"]["properties"]["visible_until"][
                "description"
            ].lower(),
        )
        person_capabilities = schemas["Person"]["properties"]["capabilities"]["items"][
            "enum"
        ]
        self.assertIn("notifications:read", person_capabilities)
        encoded = json.dumps(
            {
                key: self.contract["paths"][key]
                for key in self.contract["paths"]
                if key.startswith("/notifications")
            },
            sort_keys=True,
        )
        for required in (
            "90 days",
            "created_at and notification_id descending",
            "server-derived Person principal",
            "idempotent",
            "unread",
        ):
            self.assertIn(required.lower(), encoded.lower())


if __name__ == "__main__":
    unittest.main()
