"""Development-only, session-backed Web Portal product demo."""

import os
import secrets
from functools import wraps

from demo_data import (
    get_demo_announcements,
    get_demo_games,
    get_demo_member,
    get_demo_tasks,
)
from flask import (
    Blueprint,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from role_policy import (
    MANAGE_EVENTS,
    MANAGE_MEMBERS,
    ROLES,
    VIEW_MEMBER_PORTAL,
    has_capability,
    resolve_demo_principal,
)

demo_portal = Blueprint("demo_portal", __name__, url_prefix="/demo")
VALID_REPLIES = {"attending", "declined", "tentative"}
VALID_POSITIONS = {"pitcher", "catcher", "infield", "outfield", "flexible"}
VALID_FILTERS = {"all", "pending", "attending", "tentative", "declined"}
VALID_VIEWS = {"timeline", "month"}
VALID_VENUES = {"all", "home", "away"}
VALID_ARRIVALS = {"on_time", "late", "early_leave", "spectator"}
VALID_ETA = {"unspecified", "08:00", "08:20", "08:40", "09:00", "09:30"}
VALID_TRANSPORT = {"self", "needs_ride", "offers_ride"}
VALID_MEETING_POINTS = {"none", "demo_station", "demo_university"}
VALID_SEATS = {"0", "1", "2", "3", "4"}
VALID_NOTIFICATION_KEYS = {"game_invites", "deadline_reminders", "game_changes"}
MAX_NOTE_LENGTH = 80


def is_demo_mode_enabled(environ=None):
    values = os.environ if environ is None else environ
    return (
        values.get("WEB_PORTAL_ENV") == "development"
        and values.get("WEB_PORTAL_DEMO_MODE") == "true"
    )


@demo_portal.before_request
def require_demo_mode():
    if not is_demo_mode_enabled():
        abort(404)


def demo_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        principal = resolve_demo_principal(session)
        if not has_capability(principal, VIEW_MEMBER_PORTAL):
            return redirect(url_for("demo_portal.login"))
        return view(*args, **kwargs)

    return wrapped


def demo_capability_required(capability):
    def decorator(view):
        @demo_login_required
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not has_capability(resolve_demo_principal(session), capability):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def demo_has_capability(capability):
    return has_capability(resolve_demo_principal(session), capability)


@demo_portal.app_context_processor
def expose_demo_role_policy():
    return {
        "demo_has_capability": demo_has_capability,
        "manage_events_capability": MANAGE_EVENTS,
        "manage_members_capability": MANAGE_MEMBERS,
    }


def get_or_create_demo_csrf_token():
    token = session.get("demo_csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["demo_csrf_token"] = token
    return token


def require_demo_csrf():
    expected = session.get("demo_csrf_token")
    provided = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected, provided):
        abort(400)


def games_with_session_replies():
    replies = session.get("demo_replies", {})
    games = get_demo_games()
    for game in games:
        response = replies.get(game["id"], {})
        game["status"] = response.get("status", game["status"])
        game["my_response"] = response
        coverage = game["coverage"]
        game["staffing_level"] = (
            "ready" if coverage["total"] >= 9 and coverage["catchers"] else "short"
        )
    return games


def find_game(game_id):
    return next(
        (game for game in games_with_session_replies() if game["id"] == game_id), None
    )


def demo_state():
    state = session.get("demo_operations")
    if not isinstance(state, dict):
        state = {"games": {}}
        session["demo_operations"] = state
    return state


def game_operations(game_id):
    state = dict(demo_state())
    games = dict(state.get("games", {}))
    operations = games.get(game_id)
    if not isinstance(operations, dict):
        operations = {"transport": None, "claimed_gear": [], "completed_checks": []}
        games[game_id] = operations
        state["games"] = games
        session["demo_operations"] = state
    return operations


def notification_preferences():
    values = session.get("demo_notifications")
    if not isinstance(values, dict):
        values = {key: True for key in VALID_NOTIFICATION_KEYS}
        session["demo_notifications"] = values
    return values


def dashboard_tasks(games):
    tasks = []
    next_game = games[0]
    operations = game_operations(next_game["id"])
    if next_game["status"] == "pending":
        tasks.append({"kind": "reply", "label": "回覆下一場出席狀態"})
    if not operations.get("transport"):
        tasks.append({"kind": "transport", "label": "選擇下一場交通方式"})
    if not operations.get("claimed_gear"):
        tasks.append({"kind": "gear", "label": "查看尚待認領的裝備"})
    return tasks


def ics_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def build_game_ics(game):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NTUBTOB//Team Portal Demo//ZH-TW",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{ics_escape(game['id'])}@demo.ntubtob.invalid",
        f"DTSTART;TZID=Asia/Taipei:{game['starts_at']}",
        f"DTEND;TZID=Asia/Taipei:{game['ends_at']}",
        f"SUMMARY:{ics_escape('NTUBTOB vs ' + game['opponent'])}",
        f"LOCATION:{ics_escape(game['location'])}",
        f"DESCRIPTION:{ics_escape(game['team_note'])}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    return "\r\n".join(lines)


@demo_portal.get("/")
def entry():
    return redirect(
        url_for(
            "demo_portal.dashboard"
            if session.get("demo_authenticated")
            else "demo_portal.login"
        )
    )


@demo_portal.get("/login")
def login():
    return render_template("demo/login.html", public_page=True)


@demo_portal.post("/login")
def start_demo():
    role = request.form.get("role", "officer")
    if role not in ROLES:
        abort(400)
    member = get_demo_member()
    member["demo_role"] = role
    session.clear()
    session.update(demo_authenticated=True, demo_member=member, demo_replies={})
    get_or_create_demo_csrf_token()
    demo_state()
    return redirect(url_for("demo_portal.dashboard"))


@demo_portal.post("/logout")
def logout():
    if session.get("demo_authenticated"):
        require_demo_csrf()
    session.clear()
    return redirect(url_for("demo_portal.login"))


@demo_portal.get("/dashboard")
@demo_login_required
def dashboard():
    from demo_events import event_replies, event_store

    games = games_with_session_replies()
    unanswered_count = sum(game["status"] == "pending" for game in games)
    published_events = [
        event for event in event_store() if event["status"] == "published"
    ]
    replies = event_replies()
    event_tasks = [
        event
        for event in published_events
        if not replies.get(event["id"], {}).get("event")
    ]
    return render_template(
        "demo/dashboard.html",
        member=session["demo_member"],
        next_game=games[0],
        games=games[:3],
        unanswered_count=unanswered_count,
        announcements=get_demo_announcements(),
        tasks=dashboard_tasks(games),
        upcoming_events=published_events[:2],
        event_tasks=event_tasks,
        csrf_token=get_or_create_demo_csrf_token(),
    )


@demo_portal.get("/games")
@demo_login_required
def games():
    selected = request.args.get("status", "all")
    selected_view = request.args.get("view", "timeline")
    selected_venue = request.args.get("venue", "all")
    if (
        selected not in VALID_FILTERS
        or selected_view not in VALID_VIEWS
        or selected_venue not in VALID_VENUES
    ):
        abort(400)
    all_games = games_with_session_replies()
    filtered = (
        all_games
        if selected == "all"
        else [game for game in all_games if game["status"] == selected]
    )
    if selected_venue != "all":
        filtered = [game for game in filtered if game["venue_type"] == selected_venue]
    return render_template(
        "demo/games.html",
        games=filtered,
        selected_filter=selected,
        selected_view=selected_view,
        selected_venue=selected_venue,
    )


@demo_portal.get("/games/<game_id>")
@demo_login_required
def game_detail(game_id):
    game = find_game(game_id)
    if game is None:
        abort(404)
    return render_template(
        "demo/game_detail.html", game=game, csrf_token=get_or_create_demo_csrf_token()
    )


@demo_portal.post("/games/<game_id>/reply")
@demo_login_required
def reply(game_id):
    require_demo_csrf()
    if find_game(game_id) is None:
        abort(400)
    status = request.form.get("status", "")
    arrival = request.form.get("arrival", "on_time")
    position = request.form.get("position", "flexible")
    eta = request.form.get("eta", "unspecified")
    note = request.form.get("note", "").strip()
    if (
        status not in VALID_REPLIES
        or arrival not in VALID_ARRIVALS
        or position not in VALID_POSITIONS
        or eta not in VALID_ETA
        or len(note) > MAX_NOTE_LENGTH
    ):
        abort(400)
    replies = dict(session.get("demo_replies", {}))
    replies[game_id] = {
        "status": status,
        "arrival": arrival,
        "position": position,
        "eta": eta,
        "note": note,
    }
    session["demo_replies"] = replies
    return redirect(url_for("demo_portal.game_detail", game_id=game_id))


@demo_portal.get("/games/<game_id>/calendar.ics")
@demo_login_required
def game_calendar(game_id):
    game = find_game(game_id)
    if game is None:
        abort(404)
    return Response(
        build_game_ics(game),
        content_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{game_id}.ics"'},
    )


@demo_portal.get("/game-day/<game_id>")
@demo_login_required
def game_day(game_id):
    game = find_game(game_id)
    if game is None:
        abort(404)
    return render_template(
        "demo/game_day.html",
        game=game,
        tasks=get_demo_tasks(),
        state=game_operations(game_id),
        csrf_token=get_or_create_demo_csrf_token(),
    )


@demo_portal.post("/game-day/<game_id>/operations")
@demo_login_required
def update_operations(game_id):
    require_demo_csrf()
    if find_game(game_id) is None:
        abort(400)
    action, item_id = request.form.get("action", ""), request.form.get("item_id", "")
    tasks, state = get_demo_tasks(), dict(game_operations(game_id))
    if action == "gear" and item_id in {item["id"] for item in tasks["gear"]}:
        claimed = set(state.get("claimed_gear", []))
        claimed.symmetric_difference_update({item_id})
        state["claimed_gear"] = sorted(claimed)
    elif action == "check" and item_id in {
        str(index) for index, _ in enumerate(find_game(game_id)["checklist"])
    }:
        checks = set(state.get("completed_checks", []))
        checks.symmetric_difference_update({item_id})
        state["completed_checks"] = sorted(checks)
    else:
        abort(400)
    all_state = dict(demo_state())
    games_state = dict(all_state.get("games", {}))
    games_state[game_id] = state
    all_state["games"] = games_state
    session["demo_operations"] = all_state
    return redirect(url_for("demo_portal.game_day", game_id=game_id))


@demo_portal.post("/game-day/<game_id>/transport")
@demo_login_required
def update_transport(game_id):
    require_demo_csrf()
    if find_game(game_id) is None:
        abort(400)
    mode = request.form.get("mode", "")
    meeting_point = request.form.get("meeting_point", "none")
    seats = request.form.get("seats", "0")
    if (
        mode not in VALID_TRANSPORT
        or meeting_point not in VALID_MEETING_POINTS
        or seats not in VALID_SEATS
    ):
        abort(400)
    if mode == "self" and (meeting_point != "none" or seats != "0"):
        abort(400)
    if mode == "needs_ride" and (meeting_point == "none" or seats != "0"):
        abort(400)
    if mode == "offers_ride" and (meeting_point == "none" or seats == "0"):
        abort(400)
    state = dict(game_operations(game_id))
    state["transport"] = {
        "mode": mode,
        "meeting_point": meeting_point,
        "seats": int(seats),
    }
    all_state = dict(demo_state())
    games_state = dict(all_state.get("games", {}))
    games_state[game_id] = state
    all_state["games"] = games_state
    session["demo_operations"] = all_state
    return redirect(url_for("demo_portal.game_day", game_id=game_id))


@demo_portal.get("/profile")
@demo_login_required
def profile():
    games = games_with_session_replies()
    return render_template(
        "demo/profile.html",
        member=session["demo_member"],
        games=games,
        notifications=notification_preferences(),
        csrf_token=get_or_create_demo_csrf_token(),
    )


@demo_portal.post("/profile/notifications")
@demo_login_required
def update_notifications():
    require_demo_csrf()
    key = request.form.get("key", "")
    enabled = request.form.get("enabled", "")
    if key not in VALID_NOTIFICATION_KEYS or enabled not in {"true", "false"}:
        abort(400)
    values = dict(notification_preferences())
    values[key] = enabled == "true"
    session["demo_notifications"] = values
    return redirect(url_for("demo_portal.profile"))


@demo_portal.get("/officer")
@demo_capability_required(MANAGE_EVENTS)
def officer():
    games = games_with_session_replies()
    return render_template(
        "demo/officer.html", games=games, announcements=get_demo_announcements()
    )


@demo_portal.post("/reset")
@demo_login_required
def reset_demo():
    require_demo_csrf()
    member = session["demo_member"]
    session.clear()
    session.update(demo_authenticated=True, demo_member=member, demo_replies={})
    get_or_create_demo_csrf_token()
    demo_state()
    notification_preferences()
    return redirect(url_for("demo_portal.dashboard"))


@demo_portal.get("/pending")
def pending():
    return render_template("demo/pending.html", public_page=True)


def demo_identity_state():
    state = session.get("demo_identity_lifecycle")
    if not isinstance(state, dict):
        state = {
            "identity_status": "pending",
            "ignored": False,
            "person_status": None,
            "qualification": None,
        }
        session["demo_identity_lifecycle"] = state
    return state


@demo_portal.route("/identity-lifecycle", methods=["GET", "POST"])
@demo_capability_required(MANAGE_MEMBERS)
def identity_lifecycle():
    state = dict(demo_identity_state())
    if request.method == "POST":
        require_demo_csrf()
        action = request.form.get("action", "")
        transitions = {
            "ignore": {"identity_status": "pending", "ignored": True},
            "unignore": {"identity_status": "pending", "ignored": False},
            "reject": {"identity_status": "blocked", "ignored": True},
            "unblock": {"identity_status": "pending", "ignored": False},
            "approve_guest": {
                "identity_status": "linked",
                "ignored": False,
                "person_status": "active",
                "qualification": "guest_player (bounded)",
            },
            "revoke_guest": {"qualification": "guest_player (revoked)"},
            "disable_person": {"person_status": "disabled"},
            "activate_person": {"person_status": "active"},
        }
        change = transitions.get(action)
        if change is None:
            abort(400)
        state.update(change)
        session["demo_identity_lifecycle"] = state
        return redirect(url_for("demo_portal.identity_lifecycle"))
    return render_template(
        "demo/identity_lifecycle.html",
        state=state,
        csrf_token=get_or_create_demo_csrf_token(),
    )
