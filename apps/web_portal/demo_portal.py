"""Development-only, session-backed Web Portal product demo."""

import os
import secrets
from functools import wraps

from flask import Blueprint, Response, abort, redirect, render_template, request, session, url_for

from demo_data import (
    get_demo_announcements,
    get_demo_games,
    get_demo_member,
    get_demo_tasks,
)


demo_portal = Blueprint("demo_portal", __name__, url_prefix="/demo")
VALID_REPLIES = {"attending", "declined", "tentative"}
VALID_ARRIVALS = {"on_time", "late", "early_leave"}
VALID_POSITIONS = {"pitcher", "catcher", "infield", "outfield", "flexible"}
VALID_FILTERS = {"all", "pending", "attending", "tentative", "declined"}
MAX_NOTE_LENGTH = 80


def is_demo_mode_enabled(environ=None):
    values = os.environ if environ is None else environ
    return values.get("WEB_PORTAL_ENV") == "development" and values.get("WEB_PORTAL_DEMO_MODE") == "true"


@demo_portal.before_request
def require_demo_mode():
    if not is_demo_mode_enabled():
        abort(404)


def demo_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("demo_authenticated"):
            return redirect(url_for("demo_portal.login"))
        return view(*args, **kwargs)

    return wrapped


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
        game["staffing_level"] = "ready" if coverage["total"] >= 9 and coverage["catchers"] else "short"
    return games


def find_game(game_id):
    return next((game for game in games_with_session_replies() if game["id"] == game_id), None)


def demo_state():
    state = session.get("demo_operations")
    if not isinstance(state, dict):
        state = {"claimed_gear": [], "ride": None, "completed_checks": []}
        session["demo_operations"] = state
    return state


def ics_escape(value):
    return str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def build_game_ics(game):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//NTUBTOB//Team Portal Demo//ZH-TW",
        "CALSCALE:GREGORIAN", "BEGIN:VEVENT", f"UID:{ics_escape(game['id'])}@demo.ntubtob.invalid",
        f"DTSTART;TZID=Asia/Taipei:{game['starts_at']}", f"DTEND;TZID=Asia/Taipei:{game['ends_at']}",
        f"SUMMARY:{ics_escape('NTUBTOB vs ' + game['opponent'])}", f"LOCATION:{ics_escape(game['location'])}",
        f"DESCRIPTION:{ics_escape(game['team_note'])}", "END:VEVENT", "END:VCALENDAR", "",
    ]
    return "\r\n".join(lines)


@demo_portal.get("/")
def entry():
    return redirect(url_for("demo_portal.dashboard" if session.get("demo_authenticated") else "demo_portal.login"))


@demo_portal.get("/login")
def login():
    return render_template("demo/login.html", public_page=True)


@demo_portal.post("/login")
def start_demo():
    session.clear()
    session.update(demo_authenticated=True, demo_member=get_demo_member(), demo_replies={})
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
    games = games_with_session_replies()
    unanswered_count = sum(game["status"] == "pending" for game in games)
    return render_template("demo/dashboard.html", member=session["demo_member"], next_game=games[0], games=games[:3], unanswered_count=unanswered_count, announcements=get_demo_announcements(), csrf_token=get_or_create_demo_csrf_token())


@demo_portal.get("/games")
@demo_login_required
def games():
    selected = request.args.get("status", "all")
    if selected not in VALID_FILTERS:
        abort(400)
    all_games = games_with_session_replies()
    filtered = all_games if selected == "all" else [game for game in all_games if game["status"] == selected]
    return render_template("demo/games.html", games=filtered, selected_filter=selected)


@demo_portal.get("/games/<game_id>")
@demo_login_required
def game_detail(game_id):
    game = find_game(game_id)
    if game is None:
        abort(404)
    return render_template("demo/game_detail.html", game=game, csrf_token=get_or_create_demo_csrf_token())


@demo_portal.post("/games/<game_id>/reply")
@demo_login_required
def reply(game_id):
    require_demo_csrf()
    if find_game(game_id) is None:
        abort(400)
    status = request.form.get("status", "")
    arrival = request.form.get("arrival", "on_time")
    position = request.form.get("position", "flexible")
    note = request.form.get("note", "").strip()
    if status not in VALID_REPLIES or arrival not in VALID_ARRIVALS or position not in VALID_POSITIONS or len(note) > MAX_NOTE_LENGTH:
        abort(400)
    replies = dict(session.get("demo_replies", {}))
    replies[game_id] = {"status": status, "arrival": arrival, "position": position, "note": note}
    session["demo_replies"] = replies
    return redirect(url_for("demo_portal.game_detail", game_id=game_id))


@demo_portal.get("/games/<game_id>/calendar.ics")
@demo_login_required
def game_calendar(game_id):
    game = find_game(game_id)
    if game is None:
        abort(404)
    return Response(build_game_ics(game), content_type="text/calendar; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{game_id}.ics"'})


@demo_portal.get("/game-day/<game_id>")
@demo_login_required
def game_day(game_id):
    game = find_game(game_id)
    if game is None:
        abort(404)
    return render_template("demo/game_day.html", game=game, tasks=get_demo_tasks(), state=demo_state(), csrf_token=get_or_create_demo_csrf_token())


@demo_portal.post("/game-day/<game_id>/operations")
@demo_login_required
def update_operations(game_id):
    require_demo_csrf()
    if find_game(game_id) is None:
        abort(400)
    action, item_id = request.form.get("action", ""), request.form.get("item_id", "")
    tasks, state = get_demo_tasks(), dict(demo_state())
    if action == "ride" and item_id in {item["id"] for item in tasks["rides"]}:
        state["ride"] = None if state.get("ride") == item_id else item_id
    elif action == "gear" and item_id in {item["id"] for item in tasks["gear"]}:
        claimed = set(state.get("claimed_gear", [])); claimed.symmetric_difference_update({item_id}); state["claimed_gear"] = sorted(claimed)
    elif action == "check" and item_id in {str(index) for index, _ in enumerate(find_game(game_id)["checklist"])}:
        checks = set(state.get("completed_checks", [])); key = f"{game_id}:{item_id}"; checks.symmetric_difference_update({key}); state["completed_checks"] = sorted(checks)
    else:
        abort(400)
    session["demo_operations"] = state
    return redirect(url_for("demo_portal.game_day", game_id=game_id))


@demo_portal.get("/profile")
@demo_login_required
def profile():
    games = games_with_session_replies()
    return render_template("demo/profile.html", member=session["demo_member"], games=games, csrf_token=get_or_create_demo_csrf_token())


@demo_portal.get("/officer")
@demo_login_required
def officer():
    games = games_with_session_replies()
    return render_template("demo/officer.html", games=games, announcements=get_demo_announcements())


@demo_portal.post("/reset")
@demo_login_required
def reset_demo():
    require_demo_csrf()
    member = session["demo_member"]
    session.clear()
    session.update(demo_authenticated=True, demo_member=member, demo_replies={})
    get_or_create_demo_csrf_token(); demo_state()
    return redirect(url_for("demo_portal.dashboard"))


@demo_portal.get("/pending")
def pending():
    return render_template("demo/pending.html", public_page=True)
