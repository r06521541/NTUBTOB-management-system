import unittest
from datetime import datetime, timezone

from shared_lib.shared_module.event_read import (
    EventReadContractError,
    parse_event_key,
    project_public_event,
)


class EventReadContractTest(unittest.TestCase):
    def test_event_key_is_canonical_positive_bigint(self):
        self.assertEqual(parse_event_key("event_1"), 1)
        self.assertEqual(
            parse_event_key("event_9223372036854775807"),
            9_223_372_036_854_775_807,
        )
        for value in (
            None,
            True,
            "event_",
            "event_0",
            "event_01",
            "event_-1",
            "event_１２",
            "activity_1",
            "event_9223372036854775808",
        ):
            with self.subTest(value=value):
                with self.assertRaises(EventReadContractError):
                    parse_event_key(value)

    def test_public_projection_contains_only_bounded_read_fields(self):
        projected = project_public_event(
            {
                "id": 9,
                "title": "Fictional trip",
                "type": "trip",
                "status": "published",
                "start_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "end_at": None,
                "invitees": "private sentinel",
                "activities": (
                    {
                        "id": 91,
                        "title": "Meet",
                        "type": "gathering",
                        "position": 1,
                        "start_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                        "end_at": None,
                        "linked_game_id": 23,
                        "manager": "private sentinel",
                    },
                ),
            }
        )

        self.assertEqual(
            set(projected),
            {"id", "title", "type", "status", "start_at", "end_at", "activities"},
        )
        self.assertEqual(projected["id"], "event_9")
        self.assertEqual(projected["activities"][0]["id"], "activity_91")
        self.assertEqual(projected["activities"][0]["linked_game_id"], "game_23")
        self.assertNotIn("private sentinel", repr(projected))

    def test_malformed_stored_shapes_fail_as_contract_errors(self):
        for value in (
            None,
            {},
            {"type": "trip", "status": "published", "activities": "not-a-list"},
            {
                "id": 1,
                "title": "Trip",
                "type": "trip",
                "status": "published",
                "start_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "end_at": None,
                "activities": (None,),
            },
        ):
            with self.subTest(value=value):
                with self.assertRaises(EventReadContractError):
                    project_public_event(value)


if __name__ == "__main__":
    unittest.main()
