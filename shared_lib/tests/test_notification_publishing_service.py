import unittest
from datetime import datetime, timezone

from shared_module.mobile_api import (
    IdempotencyConflict,
    InvalidArgument,
    MobilePrincipal,
    PermissionDenied,
)
from shared_module.mobile_notifications import (
    NotificationPublishingService,
    RejectingDeliveryAdapter,
)


NOW = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
OFFICER = MobilePrincipal("session", 23, 7, "officer", "Officer", 1)
BASIC = MobilePrincipal("basic-session", 24, 8, "basic", "Basic", 1)


class FakePublishingRepository:
    def __init__(self):
        self.recipients = [31, 29]
        self.commits = []
        self.registrations = []
        self.replays = {}

    def replay_notification_publish(self, **values):
        return self.replays.get((values["session_id"], values["key_hash"], values["request_hash"]))

    def expand_notification_recipients(self, audience, now):
        return list(self.recipients)

    def notification_game_exists(self, game_id):
        return game_id in {44, -9_223_372_036_854_775_808}

    def commit_notification_publish(self, **values):
        self.commits.append(values)
        return {
            "notification_id": 81,
            "recipient_count": len(values["recipient_ids"]),
            "deliveries": [
                {"channel": "in_app", "status": "succeeded", "retryable": False},
                {"channel": "push", "status": "pending", "retryable": True},
            ],
            "idempotent_replay": False,
        }

    def register_fake_device(self, **values):
        self.registrations.append(values)
        return {"registration_id": 5, "status": "active"}

    def revoke_fake_device(self, **values):
        self.registrations.append(values)
        return True


def draft():
    return {
        "type": "officer_team_broadcast",
        "title": "本週集合提醒",
        "body": "請於週六上午八點前抵達球場。",
        "audience": {"type": "team"},
        "destination": {"type": "notification"},
    }


class NotificationPublishingServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = FakePublishingRepository()
        self.service = NotificationPublishingService(
            self.repository, clock=lambda: NOW
        )

    def test_preview_is_server_expanded_bounded_and_deterministic(self):
        preview = self.service.preview(OFFICER, draft())
        self.assertEqual(preview["recipient_count"], 2)
        self.assertEqual(preview["confirmation_text"], "PUBLISH 2")
        self.assertEqual(len(preview["revision"]), 64)
        self.assertNotIn("recipient_ids", preview)

        self.repository.recipients.reverse()
        self.assertEqual(self.service.preview(OFFICER, draft()), preview)

    def test_confirm_revalidates_revision_and_commits_one_atomic_command(self):
        preview = self.service.preview(OFFICER, draft())
        result = self.service.confirm(
            OFFICER,
            draft(),
            preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"],
            idempotency_key="publish-command-0001",
        )
        self.assertEqual(result["notification_id"], "notification_81")
        self.assertEqual(result["deliveries"][1]["status"], "pending")
        committed = self.repository.commits[0]
        self.assertEqual(committed["recipient_ids"], (29, 31))
        self.assertEqual(committed["actor_person_id"], OFFICER.person_id)
        self.assertNotIn("provider", committed)

    def test_exact_idempotent_replay_skips_recipient_drift(self):
        preview = self.service.preview(OFFICER, draft())
        first = self.service.confirm(
            OFFICER, draft(), preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"], idempotency_key="publish-command-0001",
        )
        committed = self.repository.commits[0]
        self.repository.replays[(
            OFFICER.session_id, committed["key_hash"], committed["request_hash"]
        )] = {"notification_id": 81, "recipient_count": 2, "deliveries": [], "idempotent_replay": True}
        self.repository.recipients = []
        replay = self.service.confirm(
            OFFICER, draft(), preview_revision=preview["revision"],
            typed_confirmation=preview["confirmation_text"], idempotency_key="publish-command-0001",
        )
        self.assertEqual(
            replay,
            {
                "notification_id": "notification_81",
                "recipient_count": 2,
                "deliveries": [],
                "idempotent_replay": True,
            },
        )
        self.assertEqual(len(self.repository.commits), 1)

    def test_basic_stale_preview_and_wrong_confirmation_fail_before_commit(self):
        preview = self.service.preview(OFFICER, draft())
        attempts = (
            lambda: self.service.preview(BASIC, draft()),
            lambda: self.service.confirm(
                OFFICER,
                draft(),
                preview_revision="0" * 64,
                typed_confirmation=preview["confirmation_text"],
                idempotency_key="publish-command-0001",
            ),
            lambda: self.service.confirm(
                OFFICER,
                draft(),
                preview_revision=preview["revision"],
                typed_confirmation="PUBLISH",
                idempotency_key="publish-command-0001",
            ),
        )
        for attempt in attempts:
            with self.assertRaises((PermissionDenied, IdempotencyConflict, InvalidArgument)):
                attempt()
        self.assertEqual(self.repository.commits, [])

    def test_personal_game_and_team_types_are_not_interchangeable(self):
        invalid = draft()
        invalid["type"] = "officer_personal"
        with self.assertRaises(InvalidArgument):
            self.service.preview(OFFICER, invalid)

    def test_selected_people_are_bounded_unique_and_server_previewed(self):
        selected = {
            "type": "officer_personal",
            "title": "回覆提醒",
            "body": "請回覆。",
            "audience": {"type": "individual", "person_ids": ["person_31", "person_29"]},
            "destination": {"type": "notification"},
        }
        preview = self.service.preview(OFFICER, selected)
        self.assertEqual(preview["recipient_count"], 2)
        self.assertEqual(preview["draft"]["audience"]["person_ids"], (29, 31))
        for ids in ([], ["person_31", "person_31"], ["person_1"] * 101):
            invalid = {**selected, "audience": {"type": "individual", "person_ids": ids}}
            with self.assertRaises(InvalidArgument):
                self.service.preview(OFFICER, invalid)

    def test_game_identifiers_are_canonical_signed_bigints(self):
        minimum = draft()
        minimum["type"] = "officer_game_broadcast"
        minimum["audience"] = {
            "type": "game",
            "game_id": "game_-9223372036854775808",
        }
        minimum["destination"] = {
            "type": "game",
            "game_id": "game_-9223372036854775808",
        }
        self.assertEqual(self.service.preview(OFFICER, minimum)["recipient_count"], 2)
        for malformed in (
            "game_01",
            "game_-9223372036854775809",
            "game_9223372036854775808",
        ):
            invalid = {
                **minimum,
                "audience": {"type": "game", "game_id": malformed},
                "destination": {"type": "game", "game_id": malformed},
            }
            with self.assertRaises(InvalidArgument):
                self.service.preview(OFFICER, invalid)

    def test_device_lifecycle_accepts_only_explicit_fake_provider_tokens(self):
        active = self.service.register_device(
            OFFICER,
            installation_id="fictional-installation-001",
            platform="android",
            provider="fake",
            token="fake-device-token-obvious-test-only-0001",
        )
        self.assertEqual(active, {"registration_id": "device_5", "status": "active"})
        self.assertNotIn("token", self.repository.registrations[0])
        self.assertEqual(self.repository.registrations[0]["session_id"], "session")
        self.assertNotEqual(
            self.repository.registrations[0]["installation_id_hash"],
            "fictional-installation-001",
        )
        revoked = self.service.revoke_device(
            OFFICER, installation_id="fictional-installation-001"
        )
        self.assertEqual(revoked, {"status": "revoked", "changed": True})
        self.assertEqual(self.repository.registrations[1]["session_id"], "session")
        with self.assertRaises(InvalidArgument):
            self.service.register_device(
                OFFICER,
                installation_id="fictional-installation-001",
                platform="android",
                provider="fcm",
                token="real-looking-token",
            )

    def test_rejecting_adapter_returns_bounded_retryable_failure(self):
        result = RejectingDeliveryAdapter().deliver({"private": "payload"})
        self.assertEqual(
            result,
            {
                "status": "failed",
                "error_code": "provider_not_configured",
                "retryable": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
