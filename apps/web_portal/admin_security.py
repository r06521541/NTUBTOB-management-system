import os
import secrets
from functools import wraps

from flask import abort, redirect, request, session, url_for

from role_policy import (
    MANAGE_MEMBERS,
    VIEW_MEMBER_PORTAL,
    has_capability,
    resolve_production_principal,
)


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


def capability_required(capability):
    def decorator(view):
        @wraps(view)
        def protected_view(*args, **kwargs):
            allowlist = parse_admin_member_ids(
                os.environ.get(ADMIN_MEMBER_IDS_ENV)
            )
            principal = resolve_production_principal(session, allowlist)
            if principal is None:
                return redirect(url_for("redirect_to_login", next=request.path))
            if not has_capability(principal, capability):
                abort(403)
            return view(*args, **kwargs)

        return protected_view

    return decorator


def admin_required(view):
    return capability_required(MANAGE_MEMBERS)(view)


def member_required(view):
    """Require a session created for a matched LINE user and Member."""

    return capability_required(VIEW_MEMBER_PORTAL)(view)


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
