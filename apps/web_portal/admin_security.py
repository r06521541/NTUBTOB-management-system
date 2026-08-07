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
LOGOUT_CSRF_SESSION_KEY = "logout_csrf_token"
_phase_c_principal_loader = None


def configure_phase_c_principal_loader(loader):
    global _phase_c_principal_loader
    _phase_c_principal_loader = loader


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
            principal = get_current_principal()
            if principal is None:
                return redirect(url_for("redirect_to_login", next=request.path))
            if not has_capability(principal, capability):
                abort(403)
            return view(*args, **kwargs)

        return protected_view

    return decorator


def get_current_principal():
    """Resolve the current production principal without persisting its role."""
    if _phase_c_principal_loader is not None:
        principal = _phase_c_principal_loader(session)
        # False means Phase C is deliberately disabled. Once enabled, a None
        # result is fail-closed and must not fall back to legacy authorization.
        if principal is not False:
            return principal
    allowlist = parse_admin_member_ids(os.environ.get(ADMIN_MEMBER_IDS_ENV))
    return resolve_production_principal(session, allowlist)


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


def get_or_create_logout_csrf_token():
    token = session.get(LOGOUT_CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[LOGOUT_CSRF_SESSION_KEY] = token
    return token


def require_valid_logout_csrf():
    expected = session.get(LOGOUT_CSRF_SESSION_KEY)
    received = request.form.get("csrf_token")
    if not isinstance(expected, str) or not expected:
        abort(400)
    if not isinstance(received, str) or not received:
        abort(400)
    if not secrets.compare_digest(expected, received):
        abort(400)
