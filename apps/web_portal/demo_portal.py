"""Development-only, session-backed Web Portal product demo."""

import os
from functools import wraps

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from demo_data import get_demo_games, get_demo_member


demo_portal = Blueprint("demo_portal", __name__, url_prefix="/demo")
VALID_REPLIES = {"attending", "declined", "tentative"}


def is_demo_mode_enabled(environ=None):
    """Require both explicit gates; all other combinations fail closed."""
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
        if not session.get("demo_authenticated"):
            return redirect(url_for("demo_portal.login"))
        return view(*args, **kwargs)

    return wrapped


def games_with_session_replies():
    replies = session.get("demo_replies", {})
    games = get_demo_games()
    for game in games:
        game["status"] = replies.get(game["id"], game["status"])
    return games


@demo_portal.get("/")
def entry():
    if session.get("demo_authenticated"):
        return redirect(url_for("demo_portal.dashboard"))
    return redirect(url_for("demo_portal.login"))


@demo_portal.get("/login")
def login():
    return render_template("demo/login.html", public_page=True)


@demo_portal.post("/login")
def start_demo():
    session.clear()
    session["demo_authenticated"] = True
    session["demo_member"] = get_demo_member()
    session["demo_replies"] = {}
    return redirect(url_for("demo_portal.dashboard"))


@demo_portal.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("demo_portal.login"))


@demo_portal.get("/dashboard")
@demo_login_required
def dashboard():
    games = games_with_session_replies()
    unanswered_count = sum(game["status"] == "pending" for game in games)
    return render_template(
        "demo/dashboard.html",
        member=session["demo_member"],
        next_game=games[0],
        games=games[:3],
        unanswered_count=unanswered_count,
    )


@demo_portal.get("/games")
@demo_login_required
def games():
    return render_template("demo/games.html", games=games_with_session_replies())


@demo_portal.get("/games/<game_id>")
@demo_login_required
def game_detail(game_id):
    game = next(
        (item for item in games_with_session_replies() if item["id"] == game_id),
        None,
    )
    if game is None:
        abort(404)
    return render_template("demo/game_detail.html", game=game)


@demo_portal.post("/games/<game_id>/reply")
@demo_login_required
def reply(game_id):
    valid_game_ids = {game["id"] for game in get_demo_games()}
    status = request.form.get("status")
    if game_id not in valid_game_ids or status not in VALID_REPLIES:
        abort(400)
    replies = dict(session.get("demo_replies", {}))
    replies[game_id] = status
    session["demo_replies"] = replies
    return redirect(url_for("demo_portal.game_detail", game_id=game_id))


@demo_portal.get("/profile")
@demo_login_required
def profile():
    return render_template("demo/profile.html", member=session["demo_member"])


@demo_portal.get("/pending")
def pending():
    return render_template("demo/pending.html", public_page=True)
