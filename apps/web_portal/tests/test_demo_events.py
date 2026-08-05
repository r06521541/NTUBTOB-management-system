import importlib
import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))


class DemoEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {"WEB_PORTAL_ENV": "development", "WEB_PORTAL_DEMO_MODE": "true"}, clear=False)
        cls.environment.start()
        cls.app_module = importlib.import_module("app")
        cls.app = cls.app_module.app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def setUp(self):
        self.client = self.app.test_client()
        self.client.post("/demo/login")

    def csrf(self):
        with self.client.session_transaction() as values:
            return values["demo_csrf_token"]

    def event_form(self, **changes):
        values = {"title": "測試活動", "type": "trip", "start_date": "2026-09-10", "end_date": "2026-09-12", "location": "虛構地點", "description": "離線測試"}
        values.update(changes)
        return values

    def activity_form(self, **changes):
        values = {"type": "meal", "source": "manual", "title": "示範行程", "date": "2026-09-10", "start": "10:00", "end": "11:00", "location": "虛構地點", "description": "測試", "opponent": "虛構對手", "venue": "home"}
        values.update(changes)
        return values

    def create(self, template="blank"):
        response = self.client.post("/demo/officer/events/new", data={"csrf_token": self.csrf(), "template": template})
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"].split("/")[-2]

    def test_new_routes_require_gate_and_login(self):
        anonymous = self.app.test_client()
        for path in ("/demo/events", "/demo/events/event-demo-trip", "/demo/officer/events"):
            self.assertEqual(anonymous.get(path).status_code, 302)
        with patch.dict(os.environ, {"WEB_PORTAL_DEMO_MODE": "false"}, clear=False):
            self.assertEqual(self.client.get("/demo/events").status_code, 404)
            self.assertEqual(self.client.get("/demo/officer/events").status_code, 404)

    def test_non_officer_builder_get_and_post_are_forbidden_without_mutation(self):
        self.client.get("/demo/officer/events")
        with self.client.session_transaction() as values:
            member = dict(values["demo_member"])
            member["demo_role"] = "member"
            values["demo_member"] = member
            before = deepcopy(values["demo_events"])
        self.assertEqual(self.client.get("/demo/officer/events").status_code, 403)
        self.assertEqual(self.client.post("/demo/officer/events/new", data={"csrf_token": self.csrf(), "template": "meal"}).status_code, 403)
        with self.client.session_transaction() as values:
            self.assertEqual(values["demo_events"], before)

    def test_templates_and_blank_create_server_ids(self):
        for template in ("friendly", "meal", "weekend", "blank"):
            with self.subTest(template=template):
                self.client.post("/demo/reset", data={"csrf_token": self.csrf()})
                event_id = self.create(template)
                self.assertTrue(event_id.startswith("event-demo-"))
                with self.client.session_transaction() as values:
                    event = next(item for item in values["demo_events"] if item["id"] == event_id)
                    self.assertEqual(event["status"], "draft")
                    self.assertTrue(all(item["id"].startswith("activity-demo-") for item in event["activities"]))
        self.assertEqual(self.client.post("/demo/officer/events/new", data={"csrf_token": self.csrf(), "template": "unknown"}).status_code, 400)

    def test_event_validation_and_html_is_escaped(self):
        event_id = self.create()
        endpoint = f"/demo/officer/events/{event_id}/edit"
        token = self.csrf()
        response = self.client.post(endpoint, data={"csrf_token": token, **self.event_form(title="<script>alert(1)</script>")})
        self.assertEqual(response.status_code, 302)
        page = self.client.get(endpoint)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page.data)
        self.assertNotIn(b"<script>alert(1)</script>", page.data)
        for changes in ({"type": "festival"}, {"title": "x" * 61}, {"start_date": "bad"}, {"end_date": "2026-09-01"}, {"end_date": "2026-10-10"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(endpoint, data={"csrf_token": token, **self.event_form(**changes)}).status_code, 400)

    def test_activity_crud_sorting_and_cross_event_guard(self):
        first, second = self.create("blank"), self.create("blank")
        token = self.csrf()
        add = f"/demo/officer/events/{first}/activities"
        self.client.post(add, data={"csrf_token": token, **self.activity_form(title="第一項")})
        self.client.post(add, data={"csrf_token": token, **self.activity_form(title="第二項", start="11:00", end="12:00")})
        with self.client.session_transaction() as values:
            event = next(item for item in values["demo_events"] if item["id"] == first)
            first_id, second_id = event["activities"][0]["id"], event["activities"][1]["id"]
        action = f"/demo/officer/events/{first}/activities/{second_id}/action"
        self.assertEqual(self.client.post(action, data={"csrf_token": token, "action": "up"}).status_code, 302)
        edit = f"/demo/officer/events/{first}/activities/{second_id}/edit"
        self.assertEqual(self.client.post(edit, data={"csrf_token": token, **self.activity_form(title="已編輯")}).status_code, 302)
        cross = f"/demo/officer/events/{second}/activities/{first_id}/action"
        self.assertIn(self.client.post(cross, data={"csrf_token": token, "action": "delete"}).status_code, (400, 404))
        self.assertEqual(self.client.post(action, data={"csrf_token": token, "action": "delete"}).status_code, 302)
        for changes in ({"type": "unknown"}, {"title": "x" * 61}, {"date": "bad"}, {"start": "aa:bb"}, {"start": "12:00", "end": "11:00"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(add, data={"csrf_token": token, **self.activity_form(**changes)}).status_code, 400)

    def test_limits_fail_without_destroying_state(self):
        self.create("blank"); self.create("blank")
        with self.client.session_transaction() as values:
            before = deepcopy(values["demo_events"])
        self.assertEqual(self.client.post("/demo/officer/events/new", data={"csrf_token": self.csrf(), "template": "blank"}).status_code, 400)
        with self.client.session_transaction() as values:
            self.assertEqual(values["demo_events"], before)
            events = deepcopy(values["demo_events"])
            target = events[0]
            target["activities"] = [{"id": f"activity-demo-limit-{index}"} for index in range(12)]
            target_id = target["id"]
            values["demo_events"] = events
        self.assertEqual(self.client.post(f"/demo/officer/events/{target_id}/activities", data={"csrf_token": self.csrf(), **self.activity_form()}).status_code, 400)

    def test_imported_fixture_is_read_only_and_ignores_payload(self):
        event_id = self.create("blank")
        token = self.csrf()
        payload = self.activity_form(type="game", source="league_imported", title="惡意覆寫", opponent="覆寫對手", date="2026-01-01")
        self.assertEqual(self.client.post(f"/demo/officer/events/{event_id}/activities", data={"csrf_token": token, **payload}).status_code, 302)
        with self.client.session_transaction() as values:
            event = next(item for item in values["demo_events"] if item["id"] == event_id)
            activity = event["activities"][0]
            self.assertEqual(activity["league_id"], "DEMO-LEAGUE-2026-0815")
            self.assertEqual(activity["opponent"], "星河虛構隊")
            activity_id = activity["id"]
        self.assertEqual(self.client.post(f"/demo/officer/events/{event_id}/activities/{activity_id}/edit", data={"csrf_token": token, **self.activity_form(type="game")}).status_code, 400)

    def test_draft_publish_cancel_and_csrf(self):
        event_id = self.create("meal")
        self.assertEqual(self.client.get(f"/demo/events/{event_id}").status_code, 404)
        endpoint = f"/demo/officer/events/{event_id}/status"
        self.assertEqual(self.client.post(endpoint, data={"csrf_token": "bad", "status": "published"}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={"csrf_token": self.csrf(), "status": "published"}).status_code, 302)
        self.assertEqual(self.client.get(f"/demo/events/{event_id}").status_code, 200)
        self.assertEqual(self.client.post(endpoint, data={"csrf_token": self.csrf(), "status": "cancelled"}).status_code, 302)
        self.assertIn("此活動已取消".encode(), self.client.get(f"/demo/events/{event_id}").data)
        self.assertEqual(self.client.post(endpoint, data={"csrf_token": self.csrf(), "status": "invalid"}).status_code, 400)

    def test_two_level_attendance_apply_all_override_and_isolation(self):
        token = self.csrf()
        event_id = "event-demo-trip"
        self.client.post(f"/demo/events/{event_id}/reply", data={"csrf_token": token, "status": "attending", "apply_all": "true"})
        with self.client.session_transaction() as values:
            replies = values["demo_event_replies"][event_id]
            activity_id = next(iter(replies["activities"]))
            self.assertTrue(all(value == "attending" for value in replies["activities"].values()))
        self.client.post(f"/demo/events/{event_id}/activities/{activity_id}/reply", data={"csrf_token": token, "status": "not_applicable"})
        with self.client.session_transaction() as values:
            self.assertEqual(values["demo_event_replies"][event_id]["activities"][activity_id], "not_applicable")
            self.assertNotIn("event-demo-meal", values["demo_event_replies"])
        cross = self.client.post(f"/demo/events/event-demo-meal/activities/{activity_id}/reply", data={"csrf_token": token, "status": "attending"})
        self.assertEqual(cross.status_code, 400)
        dashboard = self.client.get("/demo/dashboard")
        self.assertIn("1 個活動待回覆".encode(), dashboard.data)

    def test_complete_builder_publish_member_flow_and_no_external_calls(self):
        event_id = self.create("weekend")
        token = self.csrf()
        add_url = f"/demo/officer/events/{event_id}/activities"
        for index in range(3):
            data = self.activity_form(type="game", title=f"第 {index + 1} 場", opponent=f"虛構隊 {index + 1}", start=f"{9 + index:02d}:00", end=f"{10 + index:02d}:00")
            self.assertEqual(self.client.post(add_url, data={"csrf_token": token, **data}).status_code, 302)
        self.client.post(f"/demo/officer/events/{event_id}/status", data={"csrf_token": token, "status": "published"})
        forbidden_model = MagicMock()
        with patch.object(self.app_module, "Game", forbidden_model), patch.object(self.app_module, "Member", forbidden_model), patch.object(self.app_module.requests, "get", side_effect=AssertionError), patch.object(self.app_module.requests, "post", side_effect=AssertionError):
            listing = self.client.get("/demo/events?type=trip")
            detail = self.client.get(f"/demo/events/{event_id}")
        self.assertIn("週末移地活動草稿".encode(), listing.data)
        self.assertGreaterEqual(detail.data.count(b"activity-card"), 5)
        self.client.post(f"/demo/events/{event_id}/reply", data={"csrf_token": token, "status": "attending", "apply_all": "true"})
        forbidden_model.assert_not_called()

    def test_invalid_filters_ids_and_actions_fail_closed(self):
        self.assertEqual(self.client.get("/demo/events?type=unknown").status_code, 400)
        self.assertEqual(self.client.get("/demo/events/event-demo-draft").status_code, 404)
        self.assertEqual(self.client.get("/demo/events/unknown").status_code, 404)
        before = deepcopy(self.client.get("/demo/events").data)
        self.assertEqual(self.client.post("/demo/events/event-demo-trip/reply", data={"csrf_token": self.csrf(), "status": "maybe", "apply_all": "false"}).status_code, 400)
        self.assertEqual(self.client.get("/demo/events").data, before)


if __name__ == "__main__":
    unittest.main()
