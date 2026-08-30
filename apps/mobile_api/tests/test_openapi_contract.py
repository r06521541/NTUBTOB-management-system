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
                "/auth/google/exchange",
                "/auth/identities",
                "/auth/identity-link/candidates/{provider}",
                "/auth/identity-link/proofs/{provider}",
                "/auth/identity-link/confirm",
                "/auth/identity-link/cancel",
                "/auth/line/review",
                "/auth/line/review/messages",
                "/auth/refresh",
                "/auth/logout",
                "/me",
                "/games",
                "/games/{game_id}",
                "/events",
                "/events/{event_id}",
                "/events/{event_id}/attendance-reply",
                "/events/{event_id}/activities/{activity_id}/attendance-reply",
                "/games/{game_id}/attendance",
                "/games/{game_id}/attendance-report",
                "/games/{game_id}/attendance-reply",
                "/notifications",
                "/notifications/unread-count",
                "/notifications/{notification_id}",
                "/notifications/{notification_id}/read",
                "/notifications/read-all",
                "/officer/notifications/preview",
                "/officer/notifications/confirm",
                "/devices/current",
            },
        )

    def test_pending_review_and_profile_contracts_are_bounded(self):
        paths = self.contract["paths"]
        self.assertIn("202", paths["/auth/line/exchange"]["post"]["responses"])
        self.assertIn("202", paths["/auth/google/exchange"]["post"]["responses"])
        self.assertEqual(
            set(
                paths["/auth/google/exchange"]["post"]["requestBody"]["content"][
                    "application/json"
                ]["schema"]
            ),
            {"$ref"},
        )
        envelope = self.contract["components"]["schemas"]["PendingReviewEnvelope"]
        self.assertNotIn("access_token", envelope["properties"])
        self.assertNotIn("refresh_token", envelope["properties"])
        self.assertEqual(envelope["properties"]["expires_in"]["const"], 600)
        self.assertEqual(set(paths["/auth/line/review"]), {"get"})
        self.assertEqual(set(paths["/auth/line/review/messages"]), {"post"})
        self.assertIn("patch", paths["/me"])

    def test_identity_link_contract_is_cross_provider_redacted_and_bounded(self):
        text = CONTRACT.read_text(encoding="utf-8")
        paths = self.contract["paths"]
        self.assertEqual(
            self.contract["components"]["parameters"]["IdentityProvider"]["schema"][
                "enum"
            ],
            ["line", "google"],
        )
        self.assertIn(
            "300 seconds", paths["/auth/identity-link/cancel"]["post"]["description"]
        )
        identity_list = json.dumps(paths["/auth/identities"], sort_keys=True)
        for private in ("provider_subject", "identity_id", "email", "avatar", "token"):
            self.assertNotIn(private, identity_list)
        self.assertIn("without a second session", text)

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
        person = schemas["AttendanceReportPerson"]
        self.assertNotIn("member_number", person["required"])
        self.assertEqual(
            person["properties"]["member_number"]["type"], ["integer", "null"]
        )
        self.assertEqual(person["properties"]["member_number"]["minimum"], 0)
        self.assertEqual(person["properties"]["member_number"]["maximum"], 999)
        self.assertNotIn("member_id", json.dumps(person, sort_keys=True))

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
        self.assertIn("notifications:publish", person_capabilities)
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

    def test_publishing_device_and_deep_link_contracts_are_inert_and_typed(self):
        schemas = self.contract["components"]["schemas"]
        self.assertEqual(
            schemas["DeviceRegistrationRequest"]["properties"]["provider"]["const"],
            "fake",
        )
        publishing = json.dumps(
            {
                key: self.contract["paths"][key]
                for key in (
                    "/officer/notifications/preview",
                    "/officer/notifications/confirm",
                    "/devices/current",
                )
            },
            sort_keys=True,
        ).lower()
        devices_current = self.contract["paths"]["/devices/current"]
        for method in ("put", "delete"):
            self.assertEqual(
                devices_current[method]["responses"]["409"],
                {"$ref": "#/components/responses/Conflict"},
            )
        for required in (
            "notifications:publish",
            "preview is not authorization",
            "one transaction",
            "no real provider",
            "fake provider token",
        ):
            self.assertIn(required, publishing)
        destination = json.dumps(schemas["NotificationDestination"], sort_keys=True)
        self.assertNotIn("url", destination.lower())
        self.assertIn("safely fall back", destination.lower())
        game_destination = next(
            item
            for item in schemas["NotificationDestination"]["oneOf"]
            if item["properties"]["type"].get("const") == "game"
        )
        self.assertEqual(game_destination["properties"]["game_id"]["maxLength"], 25)
        game_audience = next(
            item
            for item in schemas["NotificationAudience"]["oneOf"]
            if item["properties"]["type"].get("const") == "game"
        )
        draft_game_destination = next(
            item
            for item in schemas["NotificationDraft"]["properties"]["destination"][
                "oneOf"
            ]
            if item["properties"]["type"].get("const") == "game"
        )
        self.assertEqual(game_audience["properties"]["game_id"]["maxLength"], 25)
        self.assertEqual(
            draft_game_destination["properties"]["game_id"]["maxLength"], 25
        )

    def test_event_contract_is_snapshot_scoped_and_privacy_bounded(self):
        schemas = self.contract["components"]["schemas"]
        capabilities = schemas["Person"]["properties"]["capabilities"]["items"]["enum"]
        self.assertIn("events:read", capabilities)
        event = schemas["Event"]
        self.assertEqual(
            set(event["properties"]),
            {
                "id",
                "title",
                "type",
                "status",
                "start_at",
                "end_at",
                "attendance",
                "activities",
            },
        )
        self.assertEqual(
            event["properties"]["status"]["enum"], ["published", "cancelled"]
        )
        event_parameter = self.contract["components"]["parameters"]["EventId"]
        event_id_contracts = (
            (
                event_parameter["schema"],
                event_parameter["description"],
                "^event_[1-9][0-9]*$",
                25,
            ),
            (
                event["properties"]["id"],
                event["properties"]["id"]["description"],
                "^event_[1-9][0-9]*$",
                25,
            ),
            (
                schemas["EventActivity"]["properties"]["id"],
                schemas["EventActivity"]["properties"]["id"]["description"],
                "^activity_[1-9][0-9]*$",
                28,
            ),
        )
        for identifier, description, pattern, max_length in event_id_contracts:
            with self.subTest(description=description):
                self.assertEqual(identifier["pattern"], pattern)
                self.assertEqual(identifier["maxLength"], max_length)
                self.assertIn("1..9223372036854775807", description)
                self.assertIn("leading zero", description)
                self.assertIn("overflow", description)
        linked_game = schemas["EventActivity"]["properties"]["linked_game_id"]
        self.assertEqual(linked_game["pattern"], "^game_-?[1-9][0-9]*$")
        self.assertEqual(linked_game["maxLength"], 25)
        self.assertIn("nonzero signed 64-bit", linked_game["description"])
        serialized = json.dumps(
            {
                "paths": {
                    key: value
                    for key, value in self.contract["paths"].items()
                    if key.startswith("/events")
                },
                "event": event,
                "activity": schemas["EventActivity"],
            },
            sort_keys=True,
        )
        self.assertIn("immutable invitee snapshot", serialized)
        response_properties = set(event["properties"]) | set(
            schemas["EventActivity"]["properties"]
        )
        for private in (
            "provider_subject",
            "invitees",
            "eligibility",
            "manager",
            "audit",
            "reason",
        ):
            self.assertNotIn(private, response_properties)
        self.assertEqual(
            schemas["EventAttendanceReply"]["enum"],
            ["attending", "not_attending", "maybe"],
        )
        self.assertIn(
            "Linked Game Activities fail closed",
            self.contract["paths"][
                "/events/{event_id}/activities/{activity_id}/attendance-reply"
            ]["put"]["description"],
        )


if __name__ == "__main__":
    unittest.main()
