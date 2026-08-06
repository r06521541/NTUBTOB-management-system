"""Session-only Event and Activity product prototype."""

from copy import deepcopy
from datetime import date, time

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from demo_event_data import get_league_game, get_seed_events
from demo_portal import demo_capability_required, demo_login_required, get_or_create_demo_csrf_token, is_demo_mode_enabled, require_demo_csrf
from role_policy import MANAGE_EVENTS


demo_events = Blueprint("demo_events", __name__, url_prefix="/demo")
EVENT_TYPES = {"game_day", "practice", "meal", "trip", "meeting", "other"}
ACTIVITY_TYPES = {"game", "meal", "transport", "lodging", "gathering", "free_time", "other"}
EVENT_STATUSES = {"draft", "published", "cancelled"}
EVENT_REPLIES = {"attending", "tentative", "declined"}
ACTIVITY_REPLIES = EVENT_REPLIES | {"not_applicable"}
EVENT_FILTERS = {"all"} | EVENT_TYPES
MAX_EVENTS = 5
MAX_ACTIVITIES = 12
LIMITS = {"title": 60, "location": 80, "description": 300}


@demo_events.before_request
def require_demo_mode():
    if not is_demo_mode_enabled():
        abort(404)


def officer_required(view):
    return demo_capability_required(MANAGE_EVENTS)(view)


def event_store():
    events = session.get("demo_events")
    if not isinstance(events, list):
        events = get_seed_events()
        session["demo_events"] = events
    return events


def save_events(events):
    session["demo_events"] = events


def event_replies():
    replies = session.get("demo_event_replies")
    if not isinstance(replies, dict):
        replies = {}
        session["demo_event_replies"] = replies
    return replies


def find_event(event_id, include_draft=False):
    event = next((item for item in event_store() if item["id"] == event_id), None)
    if event and (include_draft or event["status"] != "draft"):
        return event
    return None


def find_activity(event, activity_id):
    return next((item for item in event["activities"] if item["id"] == activity_id), None)


def next_id(prefix):
    counter = int(session.get("demo_event_id_counter", 100)) + 1
    session["demo_event_id_counter"] = counter
    return f"{prefix}-demo-{counter}"


def required_text(name, limit):
    value = request.form.get(name, "").strip()
    if not value or len(value) > limit:
        abort(400)
    return value


def optional_text(name, limit):
    value = request.form.get(name, "").strip()
    if len(value) > limit:
        abort(400)
    return value


def parse_event_form():
    event_type = request.form.get("type", "")
    if event_type not in EVENT_TYPES:
        abort(400)
    try:
        start_date = date.fromisoformat(request.form.get("start_date", ""))
        end_date = date.fromisoformat(request.form.get("end_date", ""))
    except ValueError:
        abort(400)
    if end_date < start_date or (end_date - start_date).days > 14:
        abort(400)
    return {"title": required_text("title", LIMITS["title"]), "type": event_type, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "location": required_text("location", LIMITS["location"]), "description": optional_text("description", LIMITS["description"])}


def parse_activity_form():
    activity_type = request.form.get("type", "")
    if activity_type not in ACTIVITY_TYPES:
        abort(400)
    activity_date = request.form.get("date", "")
    try:
        date.fromisoformat(activity_date)
    except ValueError:
        abort(400)
    start, end = request.form.get("start", ""), request.form.get("end", "")
    try:
        start_time = time.fromisoformat(start)
        end_time = time.fromisoformat(end)
    except ValueError:
        abort(400)
    if start_time >= end_time:
        abort(400)
    values = {"type": activity_type, "title": required_text("title", LIMITS["title"]), "date": activity_date, "start": start, "end": end, "location": required_text("location", LIMITS["location"]), "description": optional_text("description", LIMITS["description"]), "source": None}
    if activity_type == "game":
        source = request.form.get("source", "manual")
        if source not in {"manual", "league_imported"}:
            abort(400)
        if source == "league_imported":
            fixture = get_league_game()
            values.update(fixture, type="game", source="league_imported", description="聯盟匯入 fixture，欄位唯讀。")
        else:
            venue = request.form.get("venue", "")
            if venue not in {"home", "away"}:
                abort(400)
            values.update(source="manual", opponent=required_text("opponent", 60), venue=venue)
    return values


def template_event(template):
    defaults = {
        "blank": ("未命名活動", "other", []),
        "friendly": ("示範友誼賽", "game_day", [{"type": "game", "title": "友誼賽", "date": "2026-09-12", "start": "09:00", "end": "11:30", "location": "示範球場", "description": "手動建立比賽。", "source": "manual", "opponent": "待確認虛構隊", "venue": "home"}]),
        "meal": ("球隊聚餐草稿", "meal", [{"type": "meal", "title": "球隊聚餐", "date": "2026-09-12", "start": "18:00", "end": "20:00", "location": "示範餐廳.invalid", "description": "虛構聚餐。", "source": None}]),
        "weekend": ("週末移地活動草稿", "trip", [{"type": "transport", "title": "集合出發", "date": "2026-09-12", "start": "08:00", "end": "09:00", "location": "示範大學正門", "description": "虛構交通。", "source": None}, {"type": "lodging", "title": "示範住宿", "date": "2026-09-12", "start": "20:00", "end": "21:00", "location": "Demo Stay.invalid", "description": "不收集個資。", "source": None}]),
    }
    if template not in defaults:
        abort(400)
    title, event_type, activities = deepcopy(defaults[template])
    for activity in activities:
        activity["id"] = next_id("activity")
    return {"id": next_id("event"), "title": title, "type": event_type, "start_date": "2026-09-12", "end_date": "2026-09-13" if template == "weekend" else "2026-09-12", "location": "待確認虛構地點", "description": "由 Demo 模板建立。", "status": "draft", "creator": "示範幹部 小林", "activities": activities}


@demo_events.get("/events")
@demo_login_required
def events_list():
    selected = request.args.get("type", "all")
    if selected not in EVENT_FILTERS:
        abort(400)
    events = [item for item in event_store() if item["status"] != "draft" and (selected == "all" or item["type"] == selected)]
    return render_template("demo/events/list.html", events=events, selected=selected, replies=event_replies())


@demo_events.get("/events/<event_id>")
@demo_login_required
def event_detail(event_id):
    event = find_event(event_id)
    if event is None:
        abort(404)
    replies = event_replies().get(event_id, {"event": None, "activities": {}})
    incomplete = [item for item in event["activities"] if item["id"] not in replies.get("activities", {})]
    return render_template("demo/events/detail.html", event=event, reply=replies, incomplete=incomplete, csrf_token=get_or_create_demo_csrf_token())


@demo_events.post("/events/<event_id>/reply")
@demo_login_required
def reply_event(event_id):
    require_demo_csrf()
    event = find_event(event_id)
    status = request.form.get("status", "")
    apply_all = request.form.get("apply_all", "false")
    if event is None or status not in EVENT_REPLIES or apply_all not in {"true", "false"}:
        abort(400)
    replies = dict(event_replies()); current = deepcopy(replies.get(event_id, {"event": None, "activities": {}})); current["event"] = status
    if apply_all == "true":
        current["activities"] = {item["id"]: status for item in event["activities"]}
    replies[event_id] = current; session["demo_event_replies"] = replies
    return redirect(url_for("demo_events.event_detail", event_id=event_id))


@demo_events.post("/events/<event_id>/activities/<activity_id>/reply")
@demo_login_required
def reply_activity(event_id, activity_id):
    require_demo_csrf()
    event = find_event(event_id)
    status = request.form.get("status", "")
    if event is None or find_activity(event, activity_id) is None or status not in ACTIVITY_REPLIES:
        abort(400)
    replies = dict(event_replies()); current = deepcopy(replies.get(event_id, {"event": None, "activities": {}})); current["activities"][activity_id] = status; replies[event_id] = current; session["demo_event_replies"] = replies
    return redirect(url_for("demo_events.event_detail", event_id=event_id))


@demo_events.get("/officer/events")
@officer_required
def officer_events():
    return render_template("demo/events/officer.html", events=event_store(), csrf_token=get_or_create_demo_csrf_token())


@demo_events.post("/officer/events/new")
@officer_required
def create_event():
    require_demo_csrf()
    events = list(event_store())
    if len(events) >= MAX_EVENTS:
        abort(400)
    events.append(template_event(request.form.get("template", ""))); save_events(events)
    return redirect(url_for("demo_events.edit_event", event_id=events[-1]["id"]))


@demo_events.get("/officer/events/<event_id>/edit")
@officer_required
def edit_event(event_id):
    event = find_event(event_id, include_draft=True)
    if event is None:
        abort(404)
    return render_template("demo/events/builder.html", event=event, league_game=get_league_game(), csrf_token=get_or_create_demo_csrf_token())


@demo_events.post("/officer/events/<event_id>/edit")
@officer_required
def update_event(event_id):
    require_demo_csrf(); event = find_event(event_id, include_draft=True)
    if event is None:
        abort(404)
    event.update(parse_event_form()); save_events(event_store())
    return redirect(url_for("demo_events.edit_event", event_id=event_id))


@demo_events.post("/officer/events/<event_id>/activities")
@officer_required
def add_activity(event_id):
    require_demo_csrf(); event = find_event(event_id, include_draft=True)
    if event is None:
        abort(404)
    if len(event["activities"]) >= MAX_ACTIVITIES:
        abort(400)
    activity = parse_activity_form(); activity["id"] = next_id("activity"); event["activities"].append(activity); save_events(event_store())
    return redirect(url_for("demo_events.edit_event", event_id=event_id))


@demo_events.post("/officer/events/<event_id>/activities/<activity_id>/edit")
@officer_required
def update_activity(event_id, activity_id):
    require_demo_csrf(); event = find_event(event_id, include_draft=True)
    activity = find_activity(event, activity_id) if event else None
    if activity is None:
        abort(404)
    if activity.get("source") == "league_imported":
        abort(400)
    values = parse_activity_form()
    if values.get("source") == "league_imported":
        abort(400)
    activity.update(values); save_events(event_store())
    return redirect(url_for("demo_events.edit_event", event_id=event_id))


@demo_events.post("/officer/events/<event_id>/activities/<activity_id>/action")
@officer_required
def activity_action(event_id, activity_id):
    require_demo_csrf(); event = find_event(event_id, include_draft=True)
    activity = find_activity(event, activity_id) if event else None
    action = request.form.get("action", "")
    if activity is None or action not in {"delete", "up", "down"}:
        abort(400)
    index = event["activities"].index(activity)
    if action == "delete":
        event["activities"].pop(index)
    elif action == "up" and index > 0:
        event["activities"][index - 1], event["activities"][index] = event["activities"][index], event["activities"][index - 1]
    elif action == "down" and index < len(event["activities"]) - 1:
        event["activities"][index + 1], event["activities"][index] = event["activities"][index], event["activities"][index + 1]
    save_events(event_store())
    return redirect(url_for("demo_events.edit_event", event_id=event_id))


@demo_events.post("/officer/events/<event_id>/status")
@officer_required
def update_status(event_id):
    require_demo_csrf(); event = find_event(event_id, include_draft=True); status = request.form.get("status", "")
    if event is None or status not in EVENT_STATUSES:
        abort(400)
    event["status"] = status; save_events(event_store())
    return redirect(url_for("demo_events.edit_event", event_id=event_id))
