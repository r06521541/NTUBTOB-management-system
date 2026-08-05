import os
import secrets
from functools import wraps

from flask import abort, redirect, request, session, url_for


ADMIN_MEMBER_IDS_ENV = "WEB_PORTAL_ADMIN_MEMBER_IDS"
CSRF_SESSION_KEY = "member_matching_csrf_token"


def parse_admin_member_ids(value):
    """Return a complete, valid allowlist or fail closed with an empty set."""
    if value is None or not value.strip():
        return frozenset()

    raw_ids = value.split(",")
    if any(not raw_id.strip() for raw_id in raw_ids):
        return frozenset()

    member_ids = []
    for raw_id in raw_ids:
        candidate = raw_id.strip()
        if not candidate.isascii() or not candidate.isdecimal():
            return frozenset()
        member_id = int(candidate)
        if member_id <= 0:
            return frozenset()
        member_ids.append(member_id)

    if len(member_ids) != len(set(member_ids)):
        return frozenset()
    return frozenset(member_ids)


def admin_required(view):
    @wraps(view)
    def protected_view(*args, **kwargs):
        if "user_id" not in session or "member_id" not in session:
            return redirect(url_for("redirect_to_login", next=request.path))

        allowlist = parse_admin_member_ids(os.environ.get(ADMIN_MEMBER_IDS_ENV))
        member_id = session.get("member_id")
        if not isinstance(member_id, int) or isinstance(member_id, bool):
            abort(403)
        if member_id not in allowlist:
            abort(403)
        return view(*args, **kwargs)

    return protected_view


def get_or_create_csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def require_valid_csrf():
    expected = session.get(CSRF_SESSION_KEY)
    received = request.form.get("csrf_token")
    if not isinstance(expected, str) or not expected:
        abort(400)
    if not isinstance(received, str) or not received:
        abort(400)
    if not secrets.compare_digest(expected, received):
        abort(400)
