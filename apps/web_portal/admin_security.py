from __future__ import annotations

import os
import secrets
import time
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from role_policy import (
    MANAGE_MEMBERS,
    VIEW_MEMBER_PORTAL,
    has_capability,
    resolve_production_principal,
)

ADMIN_MEMBER_IDS_ENV = "WEB_PORTAL_ADMIN_MEMBER_IDS"
CSRF_SESSION_KEY = "member_matching_csrf_token"
LOGOUT_CSRF_SESSION_KEY = "logout_csrf_token"
ADMIN_REAUTH_SESSION_KEY = "admin_reauthenticated_at"
ADMIN_REAUTH_MAX_AGE_SECONDS = 300
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
            g.portal_principal = principal
            return view(*args, **kwargs)

        return protected_view

    return decorator


def get_current_principal():
    """Resolve the current production principal without persisting its role."""
    cached = getattr(g, "portal_principal", None)
    if cached is not None:
        return cached
    if _phase_c_principal_loader is not None:
        principal = _phase_c_principal_loader(session)
        # False means Phase C is deliberately disabled. Once enabled, a None
        # result is fail-closed and must not fall back to legacy authorization.
        if principal is not False:
            if principal is not None:
                g.portal_principal = principal
            return principal
    try:
        from shared_module.portal_data.runtime import admin_authority_mode
    except ImportError:
        return None
    mode = admin_authority_mode()
    if mode != "legacy_allowlist":
        # Authentication can remain valid, but no administrator source is
        # selected.  Resolve only the basic principal so admin fails with 403.
        return resolve_production_principal(session, frozenset())
    allowlist = parse_admin_member_ids(os.environ.get(ADMIN_MEMBER_IDS_ENV))
    principal = resolve_production_principal(session, allowlist)
    if principal is not None:
        g.portal_principal = principal
    return principal


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


def mark_fresh_admin_reauthentication(now: int | None = None):
    value = int(time.time()) if now is None else now
    if type(value) is not int or value <= 0:
        raise ValueError("invalid reauthentication time")
    session[ADMIN_REAUTH_SESSION_KEY] = value


def require_fresh_admin_reauthentication(now: int | None = None):
    current = int(time.time()) if now is None else now
    authenticated_at = session.get(ADMIN_REAUTH_SESSION_KEY)
    if (
        type(current) is not int
        or type(authenticated_at) is not int
        or authenticated_at <= 0
        or current < authenticated_at
        or current - authenticated_at > ADMIN_REAUTH_MAX_AGE_SECONDS
    ):
        abort(403)


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
