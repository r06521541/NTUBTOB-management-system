import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, time, timedelta, timezone
from functools import wraps
from urllib.parse import urlencode, urlsplit

import messages
import requests
from admin_security import (
    admin_required,
    capability_required,
    configure_phase_c_principal_loader,
    get_current_principal,
    get_or_create_csrf_token,
    get_or_create_logout_csrf_token,
    member_required,
    parse_admin_member_ids,
    require_valid_csrf,
    require_valid_logout_csrf,
)
from dashboard_weather import (
    DashboardWeatherError,
    fictional_dashboard_forecast,
    is_weather_window,
    load_dashboard_forecast,
)
from demo_events import demo_events
from demo_portal import demo_portal, is_demo_mode_enabled
from flask import (
    Flask,
    Response,
    abort,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_caching import Cache
from game_command_center import (
    GAME_SCOPES,
    attendance_projection,
    bounded_game_role,
    game_scope,
    insight_projection,
    load_bounded_games,
)
from identity_maintenance import (
    is_identity_maintenance_enabled,
    is_phase_c_enabled,
    is_rollout_freeze_enabled,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from line_login import (
    LINE_HTTP_TIMEOUT_SECONDS,
    InvalidOAuthState,
    create_oauth_state,
    load_oauth_state,
    require_string_field,
    return_path_category,
    safe_return_path,
)
from local_preview import (
    FICTIONAL_DEMO_FLAG,
    require_local_preview_startup,
    require_loopback_request,
)
from performance_diagnostics import AttendanceTiming
from role_policy import (
    MANAGE_EVENTS,
    MANAGE_MEMBERS,
    MANAGE_PENDING_IDENTITIES,
    MANAGE_QUALIFICATIONS,
    ROLE_ADMIN,
    ROLE_BASIC,
    ROLE_OFFICER,
)
from role_policy import Principal as WebPrincipal
from role_policy import has_capability, role_label
from sqlalchemy.exc import SQLAlchemyError
from ui_text import PORTAL_COPY

from envs import login_channel_id, login_channel_secret, secret_key

DEMO_MODE_ENABLED = is_demo_mode_enabled()
LOCAL_PREVIEW_MODE_ENABLED = require_local_preview_startup(os.environ)
FICTIONAL_DEMO_MODE_ENABLED = (
    LOCAL_PREVIEW_MODE_ENABLED and os.environ.get(FICTIONAL_DEMO_FLAG) == "true"
)
FICTIONAL_ACCESS_REASON = "TASK-099 fictional access rehearsal"
logger = logging.getLogger(__name__)

if not DEMO_MODE_ENABLED:
    import shared_module.attendance_analyzer as attendance_analyzer
    from shared_module.attendance_reply import (
        AttendanceReplyCommand,
        AttendanceReplyNotification,
        AttendanceReplyService,
    )
    from shared_module.event_read import (
        EventReadContractError,
        parse_event_key,
        project_public_event,
    )
    from shared_module.message_templates.general_message import reply_text_mapping
    from shared_module.models.ballparks import Ballpark
    from shared_module.models.game_attendance_replies import GameAttendanceReply
    from shared_module.models.games import Game
    from shared_module.models.line_users import LineUser
    from shared_module.models.members import Member
    from shared_module.notify.discord_notify import DiscordNotifyHelper
    from shared_module.settings import local_timezone
else:
    # Keep production-only ORM and notifier imports out of the offline demo process.
    # Existing production routes are explicitly unavailable below while demo is on.
    Game = Member = LineUser = GameAttendanceReply = Ballpark = object
    attendance_analyzer = None
    local_timezone = timezone(timedelta(hours=8))
    reply_text_mapping = {}

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_NAME="ntubtob_web_session_v2",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_PATH="/",
    SESSION_COOKIE_SECURE=not (DEMO_MODE_ENABLED or LOCAL_PREVIEW_MODE_ENABLED),
    SESSION_COOKIE_DOMAIN=None,
)
if LOCAL_PREVIEW_MODE_ENABLED:
    # Live UI editing must not keep serving a stale JavaScript or stylesheet.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
if DEMO_MODE_ENABLED and not secret_key:
    app.secret_key = "development-demo-session-key-not-for-production"
elif LOCAL_PREVIEW_MODE_ENABLED and not secret_key:
    # Non-sensitive fallback is deliberately limited to the localhost preview.
    app.secret_key = "development-local-session-key-not-for-production"
else:
    app.secret_key = secret_key  # 用於保持安全的session
app.register_blueprint(demo_portal)
app.register_blueprint(demo_events)


@app.context_processor
def inject_portal_copy():
    person_id = session.get("person_id")
    identity_id = session.get("auth_identity_id")
    lineup_identity_key = (
        f"person-{person_id}-identity-{identity_id}"
        if isinstance(person_id, int) and isinstance(identity_id, int)
        else ""
    )
    principal = getattr(g, "portal_principal", None)
    can_manage_people = has_capability(principal, MANAGE_MEMBERS)
    can_manage_games = getattr(principal, "role", None) in {
        ROLE_ADMIN,
        ROLE_OFFICER,
    }
    if (
        not can_manage_games
        and principal is not None
        and isinstance(session.get("user_id"), str)
    ):
        can_manage_games = _game_management_context() is not None
    lifecycle_context = getattr(g, "portal_lifecycle_context", None)
    lifecycle_person = lifecycle_context[1].person if lifecycle_context else None
    can_manage_events = bool(
        has_capability(principal, MANAGE_EVENTS)
        and lifecycle_person is not None
        and getattr(
            lifecycle_person,
            "status",
            getattr(lifecycle_person, "portal_status", None),
        )
        == "active"
    )
    return {
        "portal_copy": PORTAL_COPY,
        "lineup_identity_key": lineup_identity_key,
        "can_manage_games": can_manage_games,
        "can_manage_events": can_manage_events,
        "can_manage_people": can_manage_people,
        "portal_schedule_endpoint": (
            "game_command_center" if can_manage_games else "future_games"
        ),
        "fictional_demo_mode": FICTIONAL_DEMO_MODE_ENABLED,
    }


LEGACY_SESSION_COOKIE_NAME = "session"
OAUTH_SESSION_KEYS = (
    "oauth_state_nonce",
    "next_url",
    "oauth_browser_bootstrap_pending",
)
LEGACY_IDENTITY_SESSION_KEYS = ("member", "display_name")
AUTHENTICATED_IDENTITY_SESSION_KEYS = ("user_id", "member_id")
PHASE_C_SESSION_KEYS = ("person_id", "auth_identity_id", "member_id", "user_id")
ATTENDANCE_NAME_STYLES = frozenset({"formal", "display"})
ROLLOUT_FREEZE_RESPONSE = ("System transition is in progress; try again later", 503)


def requested_attendance_name_style():
    values = request.args.getlist("name_style")
    if not values:
        return "formal"
    if len(values) != 1 or values[0] not in ATTENDANCE_NAME_STYLES:
        abort(400)
    return values[0]


def attendance_for_game(game_id, name_style):
    if name_style == "display":
        return attendance_analyzer.get_attendance_of_game(
            game_id, use_display_name=True
        )
    return attendance_analyzer.get_attendance_of_game(game_id)


def attendance_for_games(games, name_style):
    """Return all requested Phase C attendance mappings in one repository call."""
    repository = phase_c_repository()
    if repository is None:
        return {game.id: attendance_for_game(game.id, name_style) for game in games}
    summaries = repository.attendance_summaries(
        (game.id for game in games), use_display_name=name_style == "display"
    )
    mappings = {}
    for game in games:
        mapping = {}
        summary = summaries.get(game.id)
        if summary is not None:
            for participant in summary.participants:
                mapping.setdefault(participant["reply"], []).append(participant)
        mappings[game.id] = mapping
    return mappings


def _game_calendar_date(game):
    start_datetime = game.start_datetime
    if start_datetime.tzinfo is None:
        start_datetime = start_datetime.replace(tzinfo=local_timezone)
    return start_datetime.astimezone(local_timezone).date()


def phase_c_repository():
    if not is_phase_c_enabled(demo_mode=DEMO_MODE_ENABLED):
        return None
    try:
        from shared_module.portal_data.runtime import get_identity_lifecycle_repository
    except ImportError:
        return None
    return get_identity_lifecycle_repository(
        parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS")),
        allow_persisted_admins=LOCAL_PREVIEW_MODE_ENABLED,
    )


def load_phase_c_web_principal(session_values):
    if not is_phase_c_enabled(demo_mode=DEMO_MODE_ENABLED):
        return False
    repository = phase_c_repository()
    person_id = session_values.get("person_id")
    identity_id = session_values.get("auth_identity_id")
    if repository is None:
        return None
    user_id = session_values.get("user_id")
    if isinstance(user_id, str) and user_id:
        principal = repository.resolve_line_principal(user_id)
    elif type(person_id) is int and type(identity_id) is int:
        principal = repository.resolve_principal_by_ids(identity_id, person_id)
    else:
        return None
    if (
        principal is None
        or principal.person.id != person_id
        or principal.identity.id != identity_id
    ):
        for key in PHASE_C_SESSION_KEYS:
            session.pop(key, None)
        return None
    g.portal_lifecycle_context = (repository, principal)
    allowlist = parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS"))
    if LOCAL_PREVIEW_MODE_ENABLED:
        role = {
            "admin": ROLE_ADMIN,
            "officer": ROLE_OFFICER,
            "basic": ROLE_BASIC,
        }.get(principal.person.access_level)
        if role is None:
            return None
    else:
        role = ROLE_ADMIN if principal.person.member_id in allowlist else ROLE_BASIC
    return WebPrincipal(role=role, member_id=principal.person.member_id)


configure_phase_c_principal_loader(load_phase_c_web_principal)


def register_identity_link_routes():
    names = {
        "google": (
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID",
            "WEB_IDENTITY_LINK_GOOGLE_CLIENT_SECRET",
            "WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI",
        ),
        "line": (
            "WEB_IDENTITY_LINK_LINE_CLIENT_ID",
            "WEB_IDENTITY_LINK_LINE_CLIENT_SECRET",
            "WEB_IDENTITY_LINK_LINE_REDIRECT_URI",
        ),
    }
    clients = {
        provider: {
            key: os.environ.get(name, "")
            for key, name in zip(
                ("client_id", "client_secret", "redirect_uri"), env_names
            )
        }
        for provider, env_names in names.items()
    }
    if any(not value for config in clients.values() for value in config.values()):
        return False
    repository = phase_c_repository()
    if repository is None:
        return False
    from identity_link_provider import WebIdentityProviderPort
    from identity_link_web import create_identity_link_blueprint
    from shared_module.identity_linking import (
        IdentityLinkProofCodec,
        IdentityLinkService,
    )
    from shared_module.portal_data.mobile_repository import MobileRepository
    from shared_module.provider_verifiers import (
        GoogleIdTokenVerifier,
        LineIdTokenVerifier,
    )

    data = MobileRepository(repository.engine)
    service = IdentityLinkService(
        data,
        IdentityLinkProofCodec(
            hashlib.sha256(
                ("identity-link-proof-v1:" + app.secret_key).encode()
            ).digest()
        ),
        clock=lambda: datetime.now(timezone.utc),
    )
    provider_port = WebIdentityProviderPort(
        clients=clients,
        verifiers={
            "google": GoogleIdTokenVerifier(
                audiences=(clients["google"]["client_id"],)
            ),
            "line": LineIdTokenVerifier(),
        },
    )
    app.register_blueprint(
        create_identity_link_blueprint(
            provider_port=provider_port,
            service=service,
            require_csrf=require_valid_csrf,
            allowed_redirects={config["redirect_uri"] for config in clients.values()},
            current_person_id=lambda: (
                session.get("person_id")
                if type(session.get("person_id")) is int
                else None
            ),
        )
    )
    return True


IDENTITY_LINK_ROUTES_ENABLED = register_identity_link_routes()


@app.get("/identity-recovery")
def identity_recovery():
    if not IDENTITY_LINK_ROUTES_ENABLED:
        abort(404)
    return render_template(
        "identity_recovery.html",
        csrf_token=get_or_create_csrf_token(),
        candidate_provider=session.get("identity_link_candidate_provider"),
        summary=session.get("identity_link_summary"),
    )


def _game_management_context():
    user_id = session.get("user_id")
    person_id = session.get("person_id")
    identity_id = session.get("auth_identity_id")
    cached = getattr(g, "portal_lifecycle_context", None)
    if cached is None:
        repository = phase_c_repository()
        if repository is None:
            return None
        if isinstance(user_id, str) and user_id:
            lifecycle_principal = repository.resolve_line_principal(user_id)
        elif type(person_id) is int and type(identity_id) is int:
            lifecycle_principal = repository.resolve_principal_by_ids(
                identity_id, person_id
            )
        else:
            return None
    else:
        repository, lifecycle_principal = cached
    if (
        lifecycle_principal is None
        or lifecycle_principal.person.id != person_id
        or lifecycle_principal.identity.id != identity_id
    ):
        for key in PHASE_C_SESSION_KEYS:
            session.pop(key, None)
        return None
    role = bounded_game_role(
        lifecycle_principal.person,
        parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS")),
        local_preview=LOCAL_PREVIEW_MODE_ENABLED,
    )
    if role is None:
        return None
    return repository, lifecycle_principal, role


def game_management_required(view):
    @wraps(view)
    def protected_view(*args, **kwargs):
        if (
            type(session.get("person_id")) is not int
            or type(session.get("auth_identity_id")) is not int
        ) and not (isinstance(session.get("user_id"), str) and session.get("user_id")):
            return redirect(url_for("redirect_to_login", next=request.path))
        principal = get_current_principal()
        if principal is None:
            abort(403)
        context = _game_management_context()
        if context is None:
            abort(403)
        g.game_management_context = context
        return view(*args, **kwargs)

    return protected_view


def _can_manage_games(lifecycle_principal):
    if lifecycle_principal is None:
        return False
    return (
        bounded_game_role(
            lifecycle_principal.person,
            parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS")),
            local_preview=LOCAL_PREVIEW_MODE_ENABLED,
        )
        is not None
    )


# 設定 Cache 配置
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # 使用本地內存
    "CACHE_DEFAULT_TIMEOUT": 600,  # 預設 Cache 有效期為600秒（10分鐘）
}
app.config.from_mapping(cache_config)

# 初始化 Cache
cache = Cache(app)

LINE_REDIRECT_URI = "https://web-portal-7uz453jt3a-de.a.run.app/line/callback"
_LINE_REDIRECT_PARTS = urlsplit(LINE_REDIRECT_URI)
LINE_CALLBACK_ORIGIN = f"{_LINE_REDIRECT_PARTS.scheme}://{_LINE_REDIRECT_PARTS.netloc}"

LINE_AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_USER_INFO_URL = "https://api.line.me/v2/profile"
BROWSER_BOOTSTRAP_INITIATION_SALT = "line-browser-bootstrap-initiation-v1"
BROWSER_BOOTSTRAP_INITIATION_PURPOSE = "line-browser-bootstrap"
BROWSER_BOOTSTRAP_INITIATION_MAX_AGE_SECONDS = 120
BROWSER_BOOTSTRAP_CONSUMED_SESSION_KEY = "oauth_browser_bootstrap_consumed"
BROWSER_BOOTSTRAP_CONSUMED_LIMIT = 8
LINE_LOGIN_REJECTION_CATEGORIES = frozenset(
    {
        "state_invalid_or_expired",
        "session_nonce_missing",
        "session_nonce_mismatch",
        "browser_bootstrap_invalid",
    }
)


discord_notify_helper = (
    None if DEMO_MODE_ENABLED or LOCAL_PREVIEW_MODE_ENABLED else DiscordNotifyHelper()
)


@app.before_request
def minimize_legacy_identity_session():
    """Re-sign existing sessions without legacy personal-data snapshots."""
    for key in LEGACY_IDENTITY_SESSION_KEYS:
        if key in session:
            session.pop(key)


@app.before_request
def isolate_demo_from_production_data_routes():
    if not DEMO_MODE_ENABLED:
        return None
    blocked_endpoints = {
        "line_callback",
        "query_attendance",
        "attendance",
        "index",
        "match_line_user",
        "ignore_line_user",
        "future_games",
        "member_dashboard",
        "events",
        "event_detail",
        "game_detail",
        "reply_to_game",
        "game_roster",
        "game_command_center",
        "game_command_detail",
        "game_insights",
        "lineup_lab",
        "clear_attendance_cache",
        "account",
        "logout",
    }
    if request.endpoint in blocked_endpoints:
        return "Not available in offline demo mode", 404
    return None


@app.before_request
def enforce_local_preview_boundary():
    if not LOCAL_PREVIEW_MODE_ENABLED:
        return None
    try:
        require_loopback_request(request.host)
    except RuntimeError:
        abort(404)
    if request.endpoint == "redirect_to_login":
        return redirect(url_for("local_preview_login"))
    if request.endpoint in {"line_login", "line_callback", "add_line_friend"}:
        abort(404)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        allowed = request.endpoint in {"local_preview_login", "logout"}
        if request.endpoint == "change_person_access" and FICTIONAL_DEMO_MODE_ENABLED:
            repository = phase_c_repository()
            allowed = repository is not None and repository.is_fictional_demo_fixture()
        if request.endpoint == "admin_create_member" and FICTIONAL_DEMO_MODE_ENABLED:
            repository = phase_c_repository()
            allowed = repository is not None and repository.is_fictional_demo_fixture()
        if not allowed:
            return "Local preview is read-only", 403
    return None


@app.route("/local-preview/login", methods=["GET", "POST"])
def local_preview_login():
    if not LOCAL_PREVIEW_MODE_ENABLED:
        abort(404)
    repository = phase_c_repository()
    if repository is None:
        return "Local preview identity service is unavailable", 503
    if request.method == "POST":
        require_valid_csrf()
        raw_identity_id = request.form.get("identity_id", "")
        if (
            not raw_identity_id.isascii()
            or not raw_identity_id.isdecimal()
            or int(raw_identity_id) <= 0
        ):
            abort(400)
        principal = repository.local_preview_principal(int(raw_identity_id))
        if principal is None:
            abort(404)
        for key in PHASE_C_SESSION_KEYS:
            session.pop(key, None)
        session.update(
            user_id=principal.identity.provider_subject,
            person_id=principal.person.id,
            auth_identity_id=principal.identity.id,
            member_id=principal.person.member_id,
        )
        return redirect(url_for("member_dashboard"))
    return render_template(
        "local_preview_login.html",
        identities=repository.local_preview_identities(),
        csrf_token=get_or_create_csrf_token(),
    )


@app.after_request
def expire_legacy_session_cookie(response):
    """Remove only the host-scoped legacy Flask session cookie."""
    if LEGACY_SESSION_COOKIE_NAME in request.cookies:
        response.delete_cookie(
            LEGACY_SESSION_COOKIE_NAME,
            path="/",
            secure=app.config["SESSION_COOKIE_SECURE"],
            httponly=True,
            samesite="Lax",
        )
    return response


def notify_successful_log(message: str):
    discord_notify_helper.notify_successful_log(message)


def notify_alarm_log(message: str):
    discord_notify_helper.notify_alarm_log(message)


def notify_management_message(message: str):
    discord_notify_helper.notify_management_message(message)


def notify_attendance_reply(notification):
    notify_management_message(notification.management_message())


def log_login_callback_destination(return_path):
    """Emit a bounded diagnostic without risking the successful login flow."""
    try:
        app.logger.info(
            "line_login_callback destination=%s",
            return_path_category(return_path),
        )
    except Exception:
        # Logging is operationally useful but must never block authentication.
        # Do not log this exception through the same potentially failing logger.
        pass


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/add-line-friend")
def add_line_friend():
    return render_template("add_line_friend.html")


@app.route("/redirect-to-login")
def redirect_to_login():
    next_values = request.args.getlist("next")
    if len(next_values) > 1:
        return "Invalid return path", 400

    return_path = safe_return_path(
        next_values[0] if next_values else None,
        url_for("home"),
    )
    return render_template(
        "redirect_page.html",
        normal_login_url=url_for("line_login", next=return_path),
        browser_login_url=url_for("line_login", mode="browser", next=return_path),
    )


@app.route("/line/login")
def line_login():
    modes = request.args.getlist("mode")
    if not modes:
        browser_fallback = False
    elif modes == ["browser"]:
        browser_fallback = True
    else:
        return "Invalid login mode", 400

    next_values = request.args.getlist("next")
    if len(next_values) > 1:
        return "Invalid return path", 400

    # Browser fallback must first land on the fixed callback origin so its
    # fresh nonce is committed to the same cookie jar used by the callback.
    if browser_fallback:
        return_path = safe_return_path(
            next_values[0] if next_values else None,
            url_for("attendance"),
        )
        initiation = create_browser_bootstrap_initiation(return_path)
        return redirect(
            f"{LINE_CALLBACK_ORIGIN}"
            f"{url_for('line_browser_login_bootstrap', initiation=initiation)}"
        )

    # 生成隨機的 state
    return_path = safe_return_path(
        (next_values[0] if next_values else None) or session.pop("next_url", None),
        url_for("attendance"),
    )
    nonce = secrets.token_urlsafe(16)
    session["oauth_state_nonce"] = nonce
    return line_authorization_redirect(return_path, nonce, browser_fallback=False)


def line_authorization_redirect(return_path, nonce, *, browser_fallback):
    state = create_oauth_state(
        app.secret_key,
        return_path,
        nonce,
    )
    authorization_parameters = {
        "response_type": "code",
        "client_id": login_channel_id,
        "redirect_uri": LINE_REDIRECT_URI,
        "state": state,
        "scope": "profile openid",
    }
    if browser_fallback:
        authorization_parameters["disable_auto_login"] = "true"
    login_query = urlencode(authorization_parameters)
    login_url = f"{LINE_AUTH_URL}?{login_query}"
    return redirect(login_url)


def create_browser_bootstrap_initiation(return_path):
    serializer = URLSafeTimedSerializer(
        app.secret_key,
        salt=BROWSER_BOOTSTRAP_INITIATION_SALT,
    )
    return serializer.dumps(
        {
            "purpose": BROWSER_BOOTSTRAP_INITIATION_PURPOSE,
            "next": return_path,
            "nonce": secrets.token_urlsafe(16),
        }
    )


def load_browser_bootstrap_initiation(value):
    if not isinstance(value, str) or not value:
        return None
    serializer = URLSafeTimedSerializer(
        app.secret_key,
        salt=BROWSER_BOOTSTRAP_INITIATION_SALT,
    )
    try:
        payload = serializer.loads(
            value,
            max_age=BROWSER_BOOTSTRAP_INITIATION_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or set(payload) != {"purpose", "next", "nonce"}:
        return None
    return_path = payload.get("next")
    initiation_nonce = payload.get("nonce")
    if (
        payload.get("purpose") != BROWSER_BOOTSTRAP_INITIATION_PURPOSE
        or not isinstance(return_path, str)
        or safe_return_path(return_path, "") != return_path
        or not isinstance(initiation_nonce, str)
        or not initiation_nonce
    ):
        return None
    return return_path


def reject_browser_login_bootstrap(*, clear_transaction=True):
    if clear_transaction:
        for key in OAUTH_SESSION_KEYS:
            session.pop(key, None)
    log_line_login_rejection("browser_bootstrap_invalid")
    return "Login transaction unavailable", 400


def log_line_login_rejection(category):
    if category not in LINE_LOGIN_REJECTION_CATEGORIES:
        return
    try:
        logger.warning("line_login_rejected category=%s", category)
    except Exception:
        pass


def is_canonical_line_callback_origin():
    return request.host == _LINE_REDIRECT_PARTS.netloc


@app.get("/line/login/browser/bootstrap")
def line_browser_login_bootstrap():
    initiation_values = request.args.getlist("initiation")
    if (
        not is_canonical_line_callback_origin()
        or len(request.args) != 1
        or len(initiation_values) != 1
    ):
        return reject_browser_login_bootstrap(clear_transaction=False)
    initiation = initiation_values[0]
    return_path = load_browser_bootstrap_initiation(initiation)
    if return_path is None:
        return reject_browser_login_bootstrap(clear_transaction=False)

    consumed = session.get(BROWSER_BOOTSTRAP_CONSUMED_SESSION_KEY, [])
    if not isinstance(consumed, list) or any(
        not isinstance(item, str) or len(item) != 64 for item in consumed
    ):
        return reject_browser_login_bootstrap(clear_transaction=False)
    initiation_digest = hashlib.sha256(initiation.encode("utf-8")).hexdigest()
    if initiation_digest in consumed:
        return reject_browser_login_bootstrap(clear_transaction=False)
    consumed = consumed[-(BROWSER_BOOTSTRAP_CONSUMED_LIMIT - 1) :] + [initiation_digest]

    session.clear()
    session[BROWSER_BOOTSTRAP_CONSUMED_SESSION_KEY] = consumed
    session["oauth_state_nonce"] = secrets.token_urlsafe(16)
    session["next_url"] = return_path
    session["oauth_browser_bootstrap_pending"] = True
    return redirect(f"{LINE_CALLBACK_ORIGIN}{url_for('line_browser_login_authorize')}")


@app.get("/line/login/browser/authorize")
def line_browser_login_authorize():
    nonce = session.get("oauth_state_nonce")
    return_path = session.get("next_url")
    if (
        not is_canonical_line_callback_origin()
        or request.args
        or session.get("oauth_browser_bootstrap_pending") is not True
        or not isinstance(nonce, str)
        or not nonce
        or not isinstance(return_path, str)
        or safe_return_path(return_path, "") != return_path
    ):
        return reject_browser_login_bootstrap()

    session.pop("oauth_browser_bootstrap_pending", None)
    session.pop("next_url", None)
    return line_authorization_redirect(return_path, nonce, browser_fallback=True)


@app.route("/line/callback")
def line_callback():
    code = request.args.get("code")
    state = request.args.get("state")

    # 驗證 state 是否符合
    try:
        next_url, state_nonce = load_oauth_state(
            app.secret_key,
            state,
            url_for("attendance"),
        )
    except InvalidOAuthState:
        log_line_login_rejection("state_invalid_or_expired")
        return invalid_oauth_state_response(url_for("attendance"))

    session_nonce = session.pop("oauth_state_nonce", None)
    if not isinstance(session_nonce, str):
        log_line_login_rejection("session_nonce_missing")
        return invalid_oauth_state_response(next_url)
    if not hmac.compare_digest(state_nonce, session_nonce):
        log_line_login_rejection("session_nonce_mismatch")
        return invalid_oauth_state_response(next_url)

    if not code:
        return "Invalid authorization response", 400

    if is_phase_c_enabled(demo_mode=DEMO_MODE_ENABLED) and is_rollout_freeze_enabled(
        demo_mode=DEMO_MODE_ENABLED
    ):
        return ROLLOUT_FREEZE_RESPONSE

    # 使用授權碼獲取access token
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": LINE_REDIRECT_URI,
        "client_id": login_channel_id,
        "client_secret": login_channel_secret,
    }
    try:
        token_response = requests.post(
            LINE_TOKEN_URL,
            data=data,
            timeout=LINE_HTTP_TIMEOUT_SECONDS,
        )
        token_response.raise_for_status()
        access_token = require_string_field(token_response.json(), "access_token")

        # 使用access token獲取使用者資訊
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_response = requests.get(
            LINE_USER_INFO_URL,
            headers=headers,
            timeout=LINE_HTTP_TIMEOUT_SECONDS,
        )
        profile_response.raise_for_status()
        user_info_res = profile_response.json()
        user_id = require_string_field(user_info_res, "userId")
        display_name = (
            require_string_field(user_info_res, "displayName", allow_empty=True)
            or "LINE 使用者"
        )
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return "LINE Login is temporarily unavailable", 502

    repository = phase_c_repository()
    if repository is not None:
        request_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
        try:
            pending = repository.ensure_pending_line_identity(
                user_id,
                display_name,
                f"phase-c-pending-{request_key}",
            )
            principal = repository.resolve_line_principal(user_id)
        except Exception:
            return "Identity service is temporarily unavailable", 503
        if pending.created:
            try:
                notify_management_message("Portal 有新的身分核可申請")
            except Exception:
                pass
        if principal is not None:
            session.update(
                user_id=user_id,
                person_id=principal.person.id,
                auth_identity_id=principal.identity.id,
            )
            if principal.person.member_id is not None:
                session["member_id"] = principal.person.member_id
            else:
                session.pop("member_id", None)
            session.pop("pending_identity_id", None)
            log_login_callback_destination(next_url)
            return redirect(next_url)
        session["pending_identity_id"] = pending.identity.id
        if pending.identity.status == "pending":
            return render_template(
                "identity_review.html",
                messages=repository.review_messages(pending.identity.id),
                csrf_token=get_or_create_csrf_token(),
                request_id=f"review-{secrets.token_urlsafe(24)}",
                read_only=False,
            )
        return render_template("not_authenticated.html"), 403

    if is_phase_c_enabled(demo_mode=DEMO_MODE_ENABLED):
        return "Identity service is temporarily unavailable", 503

    # Legacy read boundary remains available only while Phase C is disabled.
    is_authenticated = False
    user = LineUser.search_by_id(user_id)
    if user:
        member = Member.search_by_id(user.member_id)
        if member:
            is_authenticated = True

            # 儲存使用者資訊於session中
            session["user_id"] = user_id
            session["member_id"] = member.id

    if is_authenticated:
        log_login_callback_destination(next_url)
        return redirect(next_url)
    else:
        # 直接切換至未獲授權頁面
        return render_template("not_authenticated.html")


def invalid_oauth_state_response(return_path):
    """Discard only stale OAuth state while preserving authenticated identity."""
    for key in OAUTH_SESSION_KEYS:
        session.pop(key, None)
    login_options_url = url_for(
        "redirect_to_login",
        next=safe_return_path(return_path, url_for("attendance")),
    )
    return (
        render_template("line_login_error.html", login_options_url=login_options_url),
        400,
    )


@app.route("/identity-review", methods=["GET", "POST"])
def identity_review():
    repository = phase_c_repository()
    identity_id = session.get("pending_identity_id")
    if repository is None or not isinstance(identity_id, int):
        return render_template("not_authenticated.html"), 403
    if request.method == "POST":
        require_valid_csrf()
        if is_rollout_freeze_enabled(demo_mode=DEMO_MODE_ENABLED):
            return ROLLOUT_FREEZE_RESPONSE
        request_id = request.form.get("request_id", "")
        if not request_id.startswith("review-") or len(request_id) > 100:
            abort(400)
        try:
            repository.post_review_message(
                identity_id,
                request.form.get("message", ""),
                request_id,
            )
        except Exception:
            return "Unable to send identity review message", 409
        try:
            notify_management_message("Portal 有新的身分核可訊息")
        except Exception:
            pass
        return redirect(url_for("identity_review"))
    return render_template(
        "identity_review.html",
        messages=repository.review_messages(identity_id),
        csrf_token=get_or_create_csrf_token(),
        request_id=f"review-{secrets.token_urlsafe(24)}",
        read_only=repository.identity_status_for_id(identity_id) != "pending",
    )


@app.route("/query-attendance")
def query_attendance():
    if "user_id" not in session:
        return redirect(url_for("redirect_to_login", next=request.url))
    return redirect(url_for("attendance"))


def current_portal_member():
    """Load the current Member/Person projection without trusting the session copy."""
    cached = getattr(g, "portal_lifecycle_context", None)
    if cached is not None:
        _, lifecycle_principal = cached
        return lifecycle_principal.person, lifecycle_principal
    repository = phase_c_repository()
    lifecycle_principal = (
        repository.resolve_principal_by_ids(
            session.get("auth_identity_id"), session.get("person_id")
        )
        if repository is not None
        and type(session.get("auth_identity_id")) is int
        and type(session.get("person_id")) is int
        else None
    )
    member = (
        lifecycle_principal.person
        if lifecycle_principal is not None
        else Member.search_by_id(session.get("member_id"))
    )
    return member, lifecycle_principal


def latest_member_replies(member_id):
    if not isinstance(member_id, int) or isinstance(member_id, bool):
        return {}
    replies = {}
    for reply in GameAttendanceReply.search_by_member_id(member_id):
        current = replies.get(reply.game_id)
        if current is None or (
            reply.updated_at,
            reply.id,
        ) > (current.updated_at, current.id):
            replies[reply.game_id] = reply
    return replies


EVENT_TYPE_LABELS = {
    "game": "賽事",
    "meal": "聚餐",
    "trip": "旅程",
    "practice": "練習",
    "social": "聚會",
    "other": "其他活動",
}
ACTIVITY_TYPE_LABELS = {
    "game": "賽事",
    "meal": "用餐",
    "transport": "交通",
    "lodging": "住宿",
    "gathering": "集合",
    "other": "其他行程",
}
EVENT_ELIGIBILITY_LABELS = {
    "team_player": "正式球員",
    "guest_player": "客座球員",
    "affiliate": "校友／親友",
    "staff": "隊務人員",
}


def _parse_management_key(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix):
        abort(404)
    candidate = "event_" + value[len(prefix) :]
    try:
        return parse_event_key(candidate)
    except EventReadContractError:
        abort(404)


def _parse_event_datetime(name, *, required=True):
    value = request.form.get(name, "").strip()
    if not value and not required:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        abort(400)
    if parsed.tzinfo is not None:
        abort(400)
    return parsed.replace(tzinfo=local_timezone)


def _event_management_context():
    if not _has_narrow_event_management_authority():
        abort(403)
    context = _event_read_context()
    if context is None:
        abort(503)
    repository, principal = context
    if (
        getattr(
            principal.person,
            "status",
            getattr(principal.person, "portal_status", None),
        )
        != "active"
    ):
        abort(403)
    return repository, principal


def _event_management_service():
    repository, _ = _event_management_context()
    from shared_module.portal_data.repository import PostgresTeamPortalRepository
    from shared_module.portal_data.services import PortalDataService

    return PortalDataService(
        PostgresTeamPortalRepository(
            repository.engine,
            parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS")),
            allow_persisted_event_managers=True,
        )
    )


def _has_narrow_event_management_authority():
    principal = get_current_principal()
    if has_capability(principal, MANAGE_EVENTS):
        return True
    lifecycle_context = getattr(g, "portal_lifecycle_context", None)
    if lifecycle_context is None:
        return False
    lifecycle_principal = lifecycle_context[1]
    person = lifecycle_principal.person
    return (
        getattr(person, "status", getattr(person, "portal_status", None)) == "active"
        and getattr(person, "access_level", None) == "officer"
    )


def event_manager_required(view):
    @wraps(view)
    def protected_view(*args, **kwargs):
        if get_current_principal() is None:
            return redirect(url_for("redirect_to_login", next=request.path))
        if not _has_narrow_event_management_authority():
            abort(403)
        return view(*args, **kwargs)

    return protected_view


def _event_management_projection(event):
    projected = dict(event)
    projected["start_local"] = event["start_at"].astimezone(local_timezone)
    projected["end_local"] = (
        event["end_at"].astimezone(local_timezone) if event["end_at"] else None
    )
    projected["type_label"] = EVENT_TYPE_LABELS[event["event_type"]]
    projected["activities"] = tuple(
        {
            **activity,
            "type_label": ACTIVITY_TYPE_LABELS[activity["activity_type"]],
            "start_local": activity["start_at"].astimezone(local_timezone),
            "end_local": (
                activity["end_at"].astimezone(local_timezone)
                if activity["end_at"]
                else None
            ),
        }
        for activity in event["activities"]
    )
    return projected


def _event_write_failure(error):
    from shared_module.portal_data.domain import (
        AuthorizationError as PortalAuthorizationError,
    )
    from shared_module.portal_data.domain import ConflictError as PortalConflictError
    from shared_module.portal_data.domain import (
        ValidationError as PortalValidationError,
    )

    if isinstance(error, PortalAuthorizationError):
        abort(403)
    if isinstance(error, PortalValidationError):
        abort(400)
    if isinstance(error, PortalConflictError):
        abort(409)
    raise error


def _local_event_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(local_timezone)


def _web_event_projection(event):
    public = project_public_event(event)
    public["type_label"] = EVENT_TYPE_LABELS[public["type"]]
    public["participation_category_label"] = EVENT_ELIGIBILITY_LABELS.get(
        public["participation_category"], "其他"
    )
    public["start_datetime"] = _local_event_time(public["start_at"])
    public["end_datetime"] = (
        _local_event_time(public["end_at"]) if public["end_at"] else None
    )
    for activity in public["activities"]:
        activity["type_label"] = ACTIVITY_TYPE_LABELS[activity["type"]]
        activity["start_datetime"] = _local_event_time(activity["start_at"])
        activity["end_datetime"] = (
            _local_event_time(activity["end_at"]) if activity["end_at"] else None
        )
        linked_game_id = activity["linked_game_id"]
        activity["linked_game_route_id"] = (
            int(linked_game_id[5:])
            if isinstance(linked_game_id, str)
            and linked_game_id.startswith("game_")
            and linked_game_id[5:].isascii()
            and linked_game_id[5:].isdecimal()
            and int(linked_game_id[5:]) > 0
            else None
        )
    return public


def _event_read_context():
    cached = getattr(g, "portal_lifecycle_context", None)
    if cached is None:
        return None
    repository, lifecycle_principal = cached
    if lifecycle_principal.person.id != session.get(
        "person_id"
    ) or lifecycle_principal.identity.id != session.get("auth_identity_id"):
        return None
    return repository, lifecycle_principal


def _event_template_context(lifecycle_principal):
    return {
        "can_manage_members": has_capability(get_current_principal(), MANAGE_MEMBERS),
        "can_manage_games": _can_manage_games(lifecycle_principal),
    }


@app.get("/events")
@member_required
def events():
    context = _event_read_context()
    if context is None:
        return render_template("event_unavailable.html"), 503
    repository, lifecycle_principal = context
    try:
        projected_events = tuple(
            _web_event_projection(event)
            for event in repository.scoped_events(lifecycle_principal.person.id)
        )
    except Exception:
        logger.warning("Event data is unavailable")
        return (
            render_template(
                "event_unavailable.html",
                **_event_template_context(lifecycle_principal),
            ),
            503,
        )
    return render_template(
        "events.html",
        events=projected_events,
        **_event_template_context(lifecycle_principal),
    )


@app.get("/events/<event_key>")
@member_required
def event_detail(event_key):
    try:
        event_id = parse_event_key(event_key)
    except EventReadContractError:
        abort(404)
    context = _event_read_context()
    if context is None:
        return render_template("event_unavailable.html"), 503
    repository, lifecycle_principal = context
    try:
        event = repository.scoped_event(lifecycle_principal.person.id, event_id)
    except Exception:
        logger.warning("Event data is unavailable")
        return (
            render_template(
                "event_unavailable.html",
                **_event_template_context(lifecycle_principal),
            ),
            503,
        )
    if event is None:
        abort(404)
    try:
        projected_event = _web_event_projection(event)
    except EventReadContractError:
        logger.warning("Event data is unavailable")
        return (
            render_template(
                "event_unavailable.html",
                **_event_template_context(lifecycle_principal),
            ),
            503,
        )
    game_replies = latest_member_replies(session.get("member_id"))
    for activity in projected_event["activities"]:
        game_id = activity["linked_game_route_id"]
        activity["game_reply"] = (
            game_replies.get(game_id) if game_id is not None else None
        )
    return render_template(
        "event_detail.html",
        event=projected_event,
        csrf_token=get_or_create_csrf_token(),
        reply_text_mapping=reply_text_mapping,
        **_event_template_context(lifecycle_principal),
    )


def _event_attendance_failure(error):
    from shared_module.portal_data.domain import (
        AuthorizationError as PortalAuthorizationError,
    )
    from shared_module.portal_data.domain import ConflictError as PortalConflictError
    from shared_module.portal_data.domain import (
        ValidationError as PortalValidationError,
    )

    if isinstance(error, PortalAuthorizationError):
        abort(403)
    if isinstance(error, PortalValidationError):
        abort(400)
    if isinstance(error, PortalConflictError):
        abort(409)
    raise error


@app.post("/events/<event_key>/attendance")
@member_required
def reply_to_event_attendance(event_key):
    require_valid_csrf()
    try:
        event_id = parse_event_key(event_key)
    except EventReadContractError:
        abort(404)
    reply = request.form.get("reply", "")
    if reply not in {"attending", "not_attending", "maybe"}:
        abort(400)
    apply_all_value = request.form.get("apply_all")
    if apply_all_value not in {None, "true"}:
        abort(400)
    apply_all = apply_all_value == "true"
    context = _event_read_context()
    if context is None:
        abort(503)
    repository, principal = context
    try:
        repository.reply_to_event_attendance(
            principal.person.id, event_id, reply, apply_all
        )
    except Exception as error:
        _event_attendance_failure(error)
    return redirect(url_for("event_detail", event_key=event_key))


@app.post("/events/<event_key>/activities/<activity_key>/attendance")
@member_required
def reply_to_activity_attendance(event_key, activity_key):
    require_valid_csrf()
    try:
        event_id = parse_event_key(event_key)
        activity_id = _parse_management_key(activity_key, "activity_")
    except EventReadContractError:
        abort(404)
    reply = request.form.get("reply", "")
    if reply not in {"attending", "not_attending", "maybe"}:
        abort(400)
    context = _event_read_context()
    if context is None:
        abort(503)
    repository, principal = context
    try:
        repository.reply_to_activity_attendance(
            principal.person.id, event_id, activity_id, reply
        )
    except Exception as error:
        _event_attendance_failure(error)
    return redirect(url_for("event_detail", event_key=event_key))


@app.get("/manage/events")
@event_manager_required
def manage_events():
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        managed = tuple(
            _event_management_projection(event)
            for event in service.managed_events(principal.person.id)
        )
    except Exception as error:
        return _event_write_failure(error)
    return render_template(
        "event_management.html",
        events=managed,
        csrf_token=get_or_create_csrf_token(),
        event_types=EVENT_TYPE_LABELS,
        eligibility_labels=EVENT_ELIGIBILITY_LABELS,
    )


@app.post("/manage/events/new")
@event_manager_required
def create_managed_event():
    require_valid_csrf()
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        event_id = service.create_event(
            principal.person.id,
            request.form.get("title", ""),
            request.form.get("event_type", ""),
            _parse_event_datetime("start_at"),
            request.form.getlist("eligibility"),
            _parse_event_datetime("end_at", required=False),
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=f"event_{event_id}"))


def _managed_event_page(event_id):
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        event = _event_management_projection(
            service.managed_event(principal.person.id, event_id)
        )
        preview = service.eligibility_preview(principal.person.id, event_id)
    except Exception as error:
        return _event_write_failure(error)
    notification_preview = None
    if event["status"] != "draft":
        try:
            notification_preview = service.preview_event_notification(
                principal.person.id, event_id
            )
        except Exception:
            notification_preview = None
    return render_template(
        "event_management_edit.html",
        event=event,
        preview=preview,
        notification_preview=notification_preview,
        csrf_token=get_or_create_csrf_token(),
        new_request_id=lambda: secrets.token_urlsafe(24),
        event_types=EVENT_TYPE_LABELS,
        activity_types=ACTIVITY_TYPE_LABELS,
        eligibility_labels=EVENT_ELIGIBILITY_LABELS,
    )


@app.get("/manage/events/<event_key>")
@event_manager_required
def edit_managed_event(event_key):
    return _managed_event_page(_parse_management_key(event_key, "event_"))


@app.post("/manage/events/<event_key>")
@event_manager_required
def update_managed_event(event_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    _, principal = _event_management_context()
    try:
        expected_version = int(request.form.get("version", ""))
    except ValueError:
        abort(400)
    service = _event_management_service()
    try:
        service.update_event(
            principal.person.id,
            event_id,
            request.form.get("title", ""),
            request.form.get("event_type", ""),
            _parse_event_datetime("start_at"),
            _parse_event_datetime("end_at", required=False),
            request.form.getlist("eligibility"),
            expected_version,
            request.form.get("request_id", ""),
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/activities")
@event_manager_required
def add_managed_activity(event_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        service.add_activity(
            principal.person.id,
            event_id,
            request.form.get("title", ""),
            request.form.get("activity_type", ""),
            _parse_event_datetime("start_at"),
            _parse_event_datetime("end_at", required=False),
            request.form.get("request_id") or None,
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/activities/<activity_key>")
@event_manager_required
def update_managed_activity(event_key, activity_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    activity_id = _parse_management_key(activity_key, "activity_")
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        service.update_activity(
            principal.person.id,
            event_id,
            activity_id,
            request.form.get("title", ""),
            request.form.get("activity_type", ""),
            _parse_event_datetime("start_at"),
            _parse_event_datetime("end_at", required=False),
            request.form.get("request_id", ""),
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/activities/<activity_key>/action")
@event_manager_required
def managed_activity_action(event_key, activity_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    activity_id = _parse_management_key(activity_key, "activity_")
    _, principal = _event_management_context()
    service = _event_management_service()
    action = request.form.get("action", "")
    try:
        if action == "delete":
            service.delete_activity(
                principal.person.id,
                event_id,
                activity_id,
                request_id=request.form.get("request_id") or None,
            )
        elif action in {"up", "down"}:
            service.move_activity(
                principal.person.id,
                event_id,
                activity_id,
                action,
                request_id=request.form.get("request_id") or None,
            )
        else:
            abort(400)
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/overrides")
@event_manager_required
def set_managed_event_override(event_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    person_id = _parse_management_key(request.form.get("person_key"), "person_")
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        service.set_invitee_override(
            principal.person.id,
            event_id,
            person_id,
            request.form.get("action", ""),
            request.form.get("participation_category", ""),
            request.form.get("reason", ""),
            request.form.get("request_id", ""),
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/publish")
@event_manager_required
def publish_managed_event(event_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        service.publish_event(
            principal.person.id, event_id, request.form.get("request_id", "")
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/cancel")
@event_manager_required
def cancel_managed_event(event_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        service.cancel_event(
            principal.person.id, event_id, request.form.get("request_id", "")
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.post("/manage/events/<event_key>/notification")
@event_manager_required
def confirm_managed_event_notification(event_key):
    require_valid_csrf()
    event_id = _parse_management_key(event_key, "event_")
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        service.confirm_event_notification(
            principal.person.id,
            event_id,
            notification_type=request.form.get("notification_type", ""),
            preview_revision=request.form.get("preview_revision", ""),
            typed_confirmation=request.form.get("typed_confirmation", ""),
            request_id=request.form.get("request_id", ""),
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("edit_managed_event", event_key=event_key))


@app.get("/manage/guests")
@event_manager_required
def manage_guests():
    state = request.args.get("state", "active")
    if state not in {"scheduled", "active", "expired", "revoked"}:
        abort(400)
    _, principal = _event_management_context()
    service = _event_management_service()
    try:
        guests = tuple(
            {
                **guest,
                "valid_from_local": guest["valid_from"].astimezone(local_timezone),
                "valid_until_local": guest["valid_until"].astimezone(local_timezone),
            }
            for guest in service.managed_guests(principal.person.id, state)
        )
        candidates = service.guest_candidates(principal.person.id)
    except Exception as error:
        return _event_write_failure(error)
    return render_template(
        "guest_management.html",
        guests=guests,
        candidates=candidates,
        selected_state=state,
        csrf_token=get_or_create_csrf_token(),
        new_request_id=lambda: secrets.token_urlsafe(24),
    )


@app.post("/manage/guests/<person_key>")
@event_manager_required
def mutate_managed_guest(person_key):
    require_valid_csrf()
    person_id = _parse_management_key(person_key, "person_")
    _, principal = _event_management_context()
    action = request.form.get("action", "")
    try:
        expected_version = int(request.form.get("expected_version", ""))
    except ValueError:
        abort(400)
    service = _event_management_service()
    try:
        service.mutate_guest_qualification(
            principal.person.id,
            person_id,
            action,
            expected_version=expected_version,
            reason=request.form.get("reason", ""),
            request_id=request.form.get("request_id", ""),
            valid_from=(
                _optional_form_datetime("valid_from") if action == "grant" else None
            ),
            valid_until=(
                _optional_form_datetime("valid_until")
                if action in {"grant", "extend"}
                else None
            ),
        )
    except Exception as error:
        return _event_write_failure(error)
    return redirect(url_for("manage_guests"))


@app.route("/dashboard")
@member_required
def member_dashboard():
    member, lifecycle_principal = current_portal_member()
    if member is None:
        for key in AUTHENTICATED_IDENTITY_SESSION_KEYS:
            session.pop(key, None)
        return render_template("not_authenticated.html"), 403

    games = Game.search_for_invited()
    replies = latest_member_replies(session.get("member_id"))
    game_cards = [
        {
            "game": game,
            "reply": replies.get(game.id).reply if game.id in replies else None,
        }
        for game in games
    ]
    unanswered_count = sum(item["reply"] is None for item in game_cards)
    weather = None
    weather_pending = False
    next_game_day = ()
    later_games = game_cards
    if game_cards:
        first_game_date = _game_calendar_date(game_cards[0]["game"])
        next_game_day = tuple(
            item
            for item in game_cards
            if _game_calendar_date(item["game"]) == first_game_date
        )
        later_games = tuple(
            item
            for item in game_cards
            if _game_calendar_date(item["game"]) != first_game_date
        )
    next_game = next_game_day[0] if next_game_day else None
    if next_game and FICTIONAL_DEMO_MODE_ENABLED:
        weather = fictional_dashboard_forecast()
    elif next_game and is_weather_window(
        next_game["game"], datetime.now(local_timezone), local_timezone
    ):
        weather_pending = True
    return render_template(
        "dashboard.html",
        member=member,
        next_game=next_game,
        weather=weather,
        weather_pending=weather_pending,
        same_day_games=next_game_day[1:],
        games=later_games[:3],
        unanswered_count=unanswered_count,
        reply_text_mapping=reply_text_mapping,
        csrf_token=get_or_create_csrf_token(),
        can_manage_members=has_capability(get_current_principal(), MANAGE_MEMBERS),
        can_manage_games=_can_manage_games(lifecycle_principal),
    )


@app.get("/dashboard/weather/<int:game_id>")
@member_required
def dashboard_weather(game_id):
    games = Game.search_for_invited()
    game = next((item for item in games if item.id == game_id), None)
    now = datetime.now(local_timezone)
    if game is None or not is_weather_window(game, now, local_timezone):
        return "", 204
    weather = None
    try:
        ballpark = Ballpark.search_by_name(game.location)
        if ballpark is None:
            raise DashboardWeatherError("Weather location configuration is unavailable")
        weather = load_dashboard_forecast(game, ballpark, local_timezone)
    except DashboardWeatherError:
        logger.warning("Dashboard weather data is unavailable")
    if weather is None:
        return "", 204
    return render_template("_dashboard_weather.html", weather=weather)


@app.route("/attendance")
@member_required
def attendance():
    timing = AttendanceTiming()
    name_style = requested_attendance_name_style()
    member, lifecycle_principal = current_portal_member()
    if member is None:
        for key in AUTHENTICATED_IDENTITY_SESSION_KEYS:
            session.pop(key, None)
        return render_template("not_authenticated.html"), 403
    timing.finish("member_lookup")

    # 查詢未來的比賽
    try:
        upcoming_games = Game.search_for_invited()
    except SQLAlchemyError:
        upcoming_games = ()
        load_error = True
    else:
        load_error = False
    timing.finish("games_query")

    try:
        attendance_by_game = attendance_for_games(upcoming_games, name_style)
    except SQLAlchemyError:
        attendance_by_game = {}
        load_error = True
    games_with_attendance = []
    for game in upcoming_games:
        mapping = attendance_by_game.get(game.id)
        if mapping is None:
            load_error = True
            continue
        games_with_attendance.append(
            {
                "id": game.id,
                "game_sign": game.get_game_sign(),
                "game_date": game.get_formatted_date(),
                "game_time": game.get_formatted_start_time_with_colon(),
                "home_team": game.home_team,
                "away_team": game.away_team,
                "location": game.location,
                "attendance_mapping": mapping,
            }
        )
    timing.finish("attendance_analysis")

    now = datetime.now(local_timezone).strftime("%Y年%m月%d日 %H:%M:%S")
    response = render_template(
        "attendance.html",
        update_time=now,
        my_membership=member,
        games_with_attendance=games_with_attendance,
        reply_text_mapping=reply_text_mapping,
        name_style=name_style,
        my_replies=latest_member_replies(session.get("member_id")),
        load_error=load_error,
        can_manage_members=has_capability(get_current_principal(), MANAGE_MEMBERS),
        can_manage_games=_can_manage_games(lifecycle_principal),
    )
    timing.finish("render")
    timing.emit(app.logger)
    return response


@app.route("/games/<int:game_id>")
@member_required
def game_detail(game_id):
    game = Game.search_by_id(game_id)
    if game is None:
        abort(404)
    member, lifecycle_principal = current_portal_member()
    if member is None:
        return render_template("not_authenticated.html"), 403
    name_style = requested_attendance_name_style()
    return render_template(
        "game_detail.html",
        game=game,
        my_reply=latest_member_replies(session.get("member_id")).get(game_id),
        attendance_mapping=attendance_for_game(game.id, name_style),
        reply_text_mapping=reply_text_mapping,
        name_style=name_style,
        csrf_token=get_or_create_csrf_token(),
        can_manage_members=has_capability(get_current_principal(), MANAGE_MEMBERS),
        can_manage_games=_can_manage_games(lifecycle_principal),
    )


@app.route("/games/<int:game_id>/attendance", methods=["POST"])
@member_required
def reply_to_game(game_id):
    require_valid_csrf()
    reply = request.form.get("reply", type=int)
    if reply not in {1, 2, 3, 4, 5}:
        abort(400)
    game = Game.search_by_id(game_id)
    repository = phase_c_repository()
    person_id = session.get("person_id")
    if game is None:
        abort(404)
    if repository is None or not isinstance(person_id, int):
        return "Identity service is temporarily unavailable", 503
    return_event_key = request.form.get("return_event", "")
    if return_event_key:
        try:
            return_event_id = parse_event_key(return_event_key)
        except EventReadContractError:
            abort(400)
        event = repository.scoped_event(person_id, return_event_id)
        if event is None or not any(
            activity.get("linked_game_id") == game_id
            for activity in event.get("activities", ())
        ):
            abort(400)
    cached = getattr(g, "portal_lifecycle_context", None)
    lifecycle_principal = cached[1] if cached is not None else None
    member = (
        lifecycle_principal.person
        if lifecycle_principal is not None
        else Member.search_by_id(session.get("member_id"))
    )
    if member is None:
        return "Identity service is temporarily unavailable", 503
    person_name = (
        lifecycle_principal.person.preferred_name()
        if lifecycle_principal is not None
        else member.name
    )
    try:
        AttendanceReplyService(
            repository,
            notify_attendance_reply,
            logger=app.logger,
        ).reply(
            AttendanceReplyCommand(
                person_id=person_id,
                game_id=game_id,
                reply=reply,
                game_start=game.start_datetime,
                notification=AttendanceReplyNotification(
                    game_summary=game.generate_short_summary_for_team(),
                    person_name=person_name,
                    reply_label=reply_text_mapping[reply],
                ),
            )
        )
    except Exception:
        return "Attendance reply could not be saved", 409
    if return_event_key:
        return redirect(url_for("event_detail", event_key=return_event_key))
    return redirect(url_for("game_detail", game_id=game_id))


@app.route("/account")
@member_required
def account():
    repository = phase_c_repository()
    cached = getattr(g, "portal_lifecycle_context", None)
    lifecycle_principal = cached[1] if cached is not None else None
    if lifecycle_principal is None and repository is not None:
        user_id = session.get("user_id")
        person_id = session.get("person_id")
        identity_id = session.get("auth_identity_id")
        if isinstance(user_id, str) and user_id:
            lifecycle_principal = repository.resolve_line_principal(user_id)
        elif type(person_id) is int and type(identity_id) is int:
            lifecycle_principal = repository.resolve_principal_by_ids(
                identity_id, person_id
            )
    member = (
        lifecycle_principal.person
        if lifecycle_principal is not None
        else Member.search_by_id(session.get("member_id"))
    )
    if member is None:
        for key in AUTHENTICATED_IDENTITY_SESSION_KEYS:
            session.pop(key, None)
        return render_template("not_authenticated.html"), 403

    principal = get_current_principal()
    can_manage_members = has_capability(principal, MANAGE_MEMBERS)
    linked_methods = ()
    if lifecycle_principal is not None:
        from shared_module.portal_data.mobile_repository import MobileRepository

        linked_methods = MobileRepository(repository.engine).linked_identity_labels(
            lifecycle_principal.person.id
        )
    linked_providers = {item["provider"] for item in linked_methods}
    return render_template(
        "account.html",
        member=member,
        role_label=role_label(principal),
        can_manage_members=can_manage_members,
        logout_csrf_token=get_or_create_logout_csrf_token(),
        profile_csrf_token=get_or_create_csrf_token(),
        profile_request_id=f"profile-{secrets.token_urlsafe(24)}",
        can_manage_games=_can_manage_games(lifecycle_principal),
        linked_methods=linked_methods,
        available_link_providers=(
            tuple(
                provider
                for provider in ("google", "line")
                if provider not in linked_providers
            )
            if IDENTITY_LINK_ROUTES_ENABLED
            else ()
        ),
        link_candidate_provider=session.get("identity_link_candidate_provider"),
        link_summary=session.get("identity_link_summary"),
    )


@app.route("/account/profile", methods=["POST"])
@member_required
def update_own_profile():
    require_valid_csrf()
    if is_rollout_freeze_enabled(demo_mode=DEMO_MODE_ENABLED):
        return ROLLOUT_FREEZE_RESPONSE
    repository = phase_c_repository()
    person_id = session.get("person_id")
    request_id = request.form.get("request_id", "")
    if repository is None or not isinstance(person_id, int):
        return "Identity service is temporarily unavailable", 503
    if not request_id.startswith("profile-"):
        abort(400)
    try:
        repository.update_profile(
            person_id,
            person_id,
            request.form.get("display_name", ""),
            request_id,
        )
    except Exception:
        return "Profile could not be updated", 409
    return redirect(url_for("account"))


@app.route("/logout", methods=["POST"])
@member_required
def logout():
    require_valid_logout_csrf()
    session.clear()
    return redirect(url_for("redirect_to_login", next=url_for("account")))


@app.route("/match-member")
@admin_required
def index():
    repository = phase_c_repository()
    actor_person_id = session.get("person_id")
    if repository is not None and isinstance(actor_person_id, int):
        dashboard = _fictional_identity_dashboard(
            repository.admin_dashboard(actor_person_id)
        )
        return render_template(
            "identity_admin.html",
            dashboard=dashboard,
            eligible_member_targets=_eligible_member_targets(dashboard["people"]),
            csrf_token=get_or_create_csrf_token(),
            request_nonce=secrets.token_urlsafe(16),
            identity_maintenance_enabled=is_identity_maintenance_enabled(
                demo_mode=DEMO_MODE_ENABLED
            ),
            current_identity_id=session.get("auth_identity_id"),
        )
    line_users = LineUser.search_all_unknowns()
    members = Member.search_all()
    members.insert(0, None)
    return render_template(
        "match_member.html",
        line_users=line_users,
        members=members,
        csrf_token=get_or_create_csrf_token(),
        identity_maintenance_enabled=is_identity_maintenance_enabled(
            demo_mode=DEMO_MODE_ENABLED
        ),
    )


def _admin_repository_or_unavailable():
    repository = phase_c_repository()
    actor_person_id = session.get("person_id")
    if repository is None or not isinstance(actor_person_id, int):
        return None, None
    return repository, actor_person_id


def _fictional_identity_dashboard(dashboard):
    if not FICTIONAL_DEMO_MODE_ENABLED:
        return dashboard
    now = datetime.now(local_timezone)
    sample_identity = {
        "identity_id": -7100,
        "nickname": "虛構待核可申請者",
        "identity_status": "pending",
        "ignored": False,
        "person_id": None,
        "person_name": None,
        "person_status": None,
        "member_id": None,
        "qualifications": (),
        "review_status": "open",
        "last_activity_at": now - timedelta(hours=2),
        "stale": False,
        "fictional_sample": True,
    }
    sample_audit = (
        {
            "action": "identity_pending",
            "actor_person_id": None,
            "target_person_id": None,
            "auth_identity_id": -7100,
            "reason": "Fictional demo：收到新的 LINE 身分核可申請",
            "created_at": now - timedelta(hours=2),
            "fictional_sample": True,
        },
        {
            "action": "review_message_sent",
            "actor_person_id": 7101,
            "target_person_id": None,
            "auth_identity_id": -7100,
            "reason": "Fictional demo：管理員回覆申請者",
            "created_at": now - timedelta(hours=1),
            "fictional_sample": True,
        },
    )
    return {
        **dashboard,
        "identities": (sample_identity, *dashboard["identities"]),
        "audit": (*sample_audit, *dashboard["audit"]),
    }


def _eligible_member_targets(people):
    return tuple(
        {
            "person_id": person.get("person_id"),
            "member_id": person["member_id"],
            "display_name": person.get("display_name"),
            "formal_name": person.get("formal_name"),
            "status": person["status"],
        }
        for person in people
        if type(person.get("member_id")) is int
        and person["member_id"] > 0
        and person.get("status") in {"active", "inactive"}
    )


def _is_portal_data_domain_error(error):
    return error.__class__.__module__.startswith(
        "shared_module.portal_data"
    ) and error.__class__.__name__ in {
        "AuthorizationError",
        "ConflictError",
        "ValidationError",
    }


@app.route("/manage/people")
@admin_required
def admin_people():
    repository, actor_person_id = _admin_repository_or_unavailable()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    people = repository.person_directory(actor_person_id)
    query = request.args.get("q", "").strip()
    show_inactive = request.args.get("show_inactive") == "1"
    page = request.args.get("page", default=1, type=int)
    if page < 1:
        abort(400)
    if not show_inactive:
        people = tuple(
            person
            for person in people
            if person.get("portal_status", person.get("status")) == "active"
        )
    if query:
        people = tuple(
            person
            for person in people
            if query.casefold()
            in " ".join(
                str(person.get(key) or "")
                for key in ("display_name", "formal_name", "member_id")
            ).casefold()
        )
    page_size = 25
    total_pages = max(1, (len(people) + page_size - 1) // page_size)
    if page > total_pages:
        abort(404)
    start = (page - 1) * page_size
    return render_template(
        "person_list.html",
        people=people[start : start + page_size],
        available_members=(),
        query=query,
        show_inactive=show_inactive,
        page=page,
        total_pages=total_pages,
        request_nonce=secrets.token_urlsafe(16),
        csrf_token=get_or_create_csrf_token(),
        identity_maintenance_enabled=is_identity_maintenance_enabled(
            demo_mode=DEMO_MODE_ENABLED
        ),
    )


@app.route("/manage/people/<int:person_id>")
@admin_required
def admin_person_detail(person_id):
    repository, actor_person_id = _admin_repository_or_unavailable()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    person = next(
        (
            item
            for item in repository.admin_dashboard(actor_person_id)["people"]
            if item["person_id"] == person_id
        ),
        None,
    )
    if person is None:
        abort(404)
    tab = request.args.get("tab", "profile")
    if tab not in {"profile", "member", "qualifications", "attendance"}:
        abort(400)
    try:
        insight = (
            repository.person_attendance_insight(person_id)
            if tab == "attendance"
            else None
        )
    except SQLAlchemyError:
        return "Player insight is temporarily unavailable", 503
    return render_template(
        "person_detail.html",
        person=person,
        active_tab=tab,
        insight=insight,
        reply_text_mapping=reply_text_mapping,
        csrf_token=get_or_create_csrf_token(),
        request_nonce=secrets.token_urlsafe(16),
        identity_maintenance_enabled=is_identity_maintenance_enabled(
            demo_mode=DEMO_MODE_ENABLED
        ),
        can_change_access=(
            not LOCAL_PREVIEW_MODE_ENABLED or FICTIONAL_DEMO_MODE_ENABLED
        ),
        fictional_access_reason=(
            FICTIONAL_ACCESS_REASON if FICTIONAL_DEMO_MODE_ENABLED else None
        ),
    )


@app.post("/manage/people/<int:person_id>/access")
@admin_required
def change_person_access(person_id):
    require_valid_csrf()
    repository, actor_person_id = _admin_repository_or_unavailable()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    access_level = {
        "promote_officer": "officer",
        "demote_basic": "basic",
    }.get(request.form.get("action", ""))
    if access_level is None:
        abort(400)
    request_id = _required_request_id("person-access-")
    if FICTIONAL_DEMO_MODE_ENABLED and (
        request_id != f"person-access-{person_id}-{access_level}"
        or request.form.get("reason") != FICTIONAL_ACCESS_REASON
    ):
        abort(400)
    try:
        repository.change_access(
            actor_person_id,
            person_id,
            access_level,
            request.form.get("reason", ""),
            request_id,
        )
    except Exception as error:
        if _is_portal_data_domain_error(error):
            return "Access could not be changed", 409
        raise
    return redirect(url_for("admin_person_detail", person_id=person_id))


@app.route("/manage/pending-identities")
@capability_required(MANAGE_PENDING_IDENTITIES)
def admin_pending_identities():
    repository, actor_person_id = _admin_repository_or_unavailable()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    dashboard = _fictional_identity_dashboard(
        repository.admin_dashboard(actor_person_id)
    )
    pending_identities = tuple(
        item
        for item in dashboard["identities"]
        if item["identity_status"] == "pending" or item["review_status"] == "open"
    )
    return render_template(
        "identity_admin.html",
        dashboard={
            "identities": pending_identities,
            "people": dashboard["people"],
            "audit": dashboard["audit"] if FICTIONAL_DEMO_MODE_ENABLED else (),
        },
        eligible_member_targets=_eligible_member_targets(dashboard["people"]),
        csrf_token=get_or_create_csrf_token(),
        request_nonce=secrets.token_urlsafe(16),
        identity_maintenance_enabled=is_identity_maintenance_enabled(
            demo_mode=DEMO_MODE_ENABLED
        ),
        current_identity_id=session.get("auth_identity_id"),
        pending_only=True,
    )


@app.get("/local-preview/identity-review")
def local_preview_identity_review():
    require_loopback_request(request.host)
    if not FICTIONAL_DEMO_MODE_ENABLED:
        abort(404)
    sample_time = datetime.now(local_timezone)
    sample_messages = (
        {
            "sender_role": "applicant",
            "body": "您好，我是今年加入球隊的學長，想申請隊員帳號。",
            "created_at": sample_time - timedelta(hours=2),
        },
        {
            "sender_role": "admin",
            "body": "收到，請再告訴我畢業系級，確認後會協助完成配對。",
            "created_at": sample_time - timedelta(hours=1),
        },
    )
    return render_template(
        "identity_review.html",
        messages=sample_messages,
        csrf_token="local-preview-read-only",
        request_id="local-preview-read-only",
        read_only=True,
        fictional_preview=True,
    )


@app.route("/manage/people/<int:person_id>/qualifications", methods=["GET", "POST"])
@capability_required(MANAGE_QUALIFICATIONS)
def manage_person_qualifications(person_id):
    require_valid_csrf() if request.method == "POST" else None
    repository, actor_person_id = _admin_repository_or_unavailable()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    dashboard = repository.admin_dashboard(actor_person_id)
    person = next(
        (item for item in dashboard["people"] if item["person_id"] == person_id),
        None,
    )
    if person is None:
        abort(404)
    if request.method == "POST":
        qualification = request.form.get("qualification", "")
        request_id = _required_request_id("qualification-")
        reason = request.form.get("reason", "").strip()
        if qualification not in {"affiliate", "staff"}:
            abort(400)
        if not 3 <= len(reason) <= 300:
            abort(400)
        action = request.form.get("action", "")
        try:
            if action == "grant":
                repository.grant_qualification(
                    actor_person_id,
                    person_id,
                    qualification,
                    reason,
                    request_id,
                    valid_from=_optional_form_datetime("valid_from"),
                    valid_until=_optional_form_datetime("valid_until"),
                )
            elif action == "revoke":
                repository.revoke_qualification(
                    actor_person_id, person_id, qualification, reason, request_id
                )
            else:
                abort(400)
        except (ValueError, TypeError):
            abort(400)
        return redirect(url_for("manage_person_qualifications", person_id=person_id))
    return render_template(
        "qualifications.html",
        person=person,
        qualifications=person.get("qualifications", ()),
        csrf_token=get_or_create_csrf_token(),
        request_nonce=secrets.token_urlsafe(16),
        identity_maintenance_enabled=is_identity_maintenance_enabled(
            demo_mode=DEMO_MODE_ENABLED
        ),
    )


def _optional_form_int(name):
    value = request.form.get(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        abort(400)


@app.route("/manage/people/new", methods=["GET", "POST"])
@admin_required
def admin_create_member():
    repository, actor_person_id = _admin_repository_or_unavailable()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    mutation_enabled = FICTIONAL_DEMO_MODE_ENABLED or is_identity_maintenance_enabled(
        demo_mode=DEMO_MODE_ENABLED
    )
    if request.method == "POST":
        require_valid_csrf()
        if not mutation_enabled:
            return "Identity maintenance is temporarily unavailable", 503
        formal_name = request.form.get("name", "")
        request_id = _required_request_id("member-create-")
        try:
            person = repository.create_member(
                actor_person_id,
                formal_name,
                formal_name,
                request.form.get("reason", ""),
                request_id,
                enroll_year=_optional_form_int("enroll_year"),
                major=request.form.get("major"),
                number=_optional_form_int("number"),
                positions=request.form.get("positions"),
            )
        except Exception as error:
            if _is_portal_data_domain_error(error):
                return "Member could not be created", 409
            raise
        return redirect(url_for("admin_person_detail", person_id=person.id))
    return render_template(
        "member_create.html",
        csrf_token=get_or_create_csrf_token(),
        request_id=f"member-create-{secrets.token_urlsafe(24)}",
        mutation_enabled=mutation_enabled,
    )


@app.route("/match-member/match", methods=["POST"])
@admin_required
def match_line_user():
    require_valid_csrf()
    if is_rollout_freeze_enabled(demo_mode=DEMO_MODE_ENABLED):
        return ROLLOUT_FREEZE_RESPONSE
    if not is_identity_maintenance_enabled(demo_mode=DEMO_MODE_ENABLED):
        return "Identity maintenance is temporarily unavailable", 503
    repository = phase_c_repository()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    line_user_id = _required_form_text("line_user_id")
    member_id = _required_positive_form_int("member_id")
    request_id = _required_request_id("identity-match-")
    identity = repository.line_identity(line_user_id)
    actor_person_id = session.get("person_id")
    if (
        identity is None
        or not isinstance(actor_person_id, int)
        or not request_id.startswith("identity-match-")
    ):
        abort(400)
    repository.approve_member(
        actor_person_id,
        identity.id,
        member_id,
        request.form.get("reason", ""),
        request_id,
    )
    try:
        notify_management_message("Portal 身分核可已完成")
    except Exception:
        pass

    return redirect(url_for("index"))


def _optional_form_datetime(name):
    value = request.form.get(name, "").strip()
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone)
    return parsed


def _required_positive_form_int(name):
    value = request.form.get(name)
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        abort(400)
    parsed = int(value)
    if parsed <= 0:
        abort(400)
    return parsed


def _required_form_text(name):
    value = request.form.get(name)
    if (
        not isinstance(value, str)
        or not value.strip()
        or not value.isascii()
        or len(value) > 255
    ):
        abort(400)
    return value


def _required_request_id(prefix):
    value = request.form.get("request_id")
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or not value.isascii()
        or not 1 <= len(value) <= 120
    ):
        abort(400)
    return value


@app.route("/identity-admin/action", methods=["POST"])
@admin_required
def identity_admin_action():
    require_valid_csrf()
    if is_rollout_freeze_enabled(demo_mode=DEMO_MODE_ENABLED):
        return ROLLOUT_FREEZE_RESPONSE
    if not is_identity_maintenance_enabled(demo_mode=DEMO_MODE_ENABLED):
        return "Identity maintenance is temporarily unavailable", 503
    repository = phase_c_repository()
    actor_person_id = session.get("person_id")
    if repository is None or not isinstance(actor_person_id, int):
        return "Identity service is temporarily unavailable", 503
    action = request.form.get("action", "")
    reason = request.form.get("reason", "")
    request_id = request.form.get("request_id", "")
    if (
        action in {"grant_qualification", "revoke_qualification"}
        and request.form.get("qualification", "") == "guest_player"
    ):
        abort(400)
    if action == "create_member" and "guest_player" in request.form.getlist(
        "qualification"
    ):
        abort(400)
    if action == "create_member":
        request_id = _required_request_id("member-create-")
    identity_id = request.form.get("identity_id", type=int)
    person_id = request.form.get("person_id", type=int)
    target_member_id = None
    if action in {"approve_member", "remap"}:
        target_member_id = _required_positive_form_int("member_id")
        eligible_member_ids = {
            item["member_id"]
            for item in _eligible_member_targets(
                repository.admin_dashboard(actor_person_id)["people"]
            )
        }
        if target_member_id not in eligible_member_ids:
            abort(400)
    if action == "remap":
        if identity_id is None or request.form.getlist("confirm_remap") != ["yes"]:
            abort(400)
    try:
        if action == "approve_non_member" and identity_id is not None:
            qualifications = request.form.getlist("qualification")
            if "guest_player" in qualifications:
                abort(400)
            repository.approve_non_member(
                actor_person_id,
                identity_id,
                request.form.get("display_name", ""),
                reason,
                request_id,
                formal_name=request.form.get("formal_name") or None,
                qualifications=qualifications,
                guest_valid_from=_optional_form_datetime("guest_valid_from"),
                guest_valid_until=_optional_form_datetime("guest_valid_until"),
            )
        elif action == "approve_member" and identity_id is not None:
            repository.approve_member(
                actor_person_id,
                identity_id,
                target_member_id,
                reason,
                request_id,
            )
        elif action in {"ignore", "unignore"} and identity_id is not None:
            repository.set_ignored(
                actor_person_id,
                identity_id,
                action == "ignore",
                reason,
                request_id,
            )
        elif (
            action
            in {
                "reject",
                "unblock",
                "unblock_linked",
                "disable_identity",
                "enable_identity",
            }
            and identity_id is not None
        ):
            status = {
                "reject": "blocked",
                "unblock": "pending",
                "unblock_linked": "linked",
                "disable_identity": "disabled",
                "enable_identity": "linked",
            }[action]
            repository.set_identity_status(
                actor_person_id,
                identity_id,
                status,
                reason,
                request_id,
                current_identity_id=session.get("auth_identity_id"),
            )
        elif action == "unlink" and identity_id is not None:
            repository.unlink_identity(
                actor_person_id,
                identity_id,
                reason,
                request_id,
                current_identity_id=session.get("auth_identity_id"),
            )
        elif action == "remap" and identity_id is not None:
            repository.remap_member_identity(
                actor_person_id,
                identity_id,
                target_member_id,
                reason,
                request_id,
                current_identity_id=session.get("auth_identity_id"),
            )
        elif action == "person_status" and person_id is not None:
            repository.change_person_status(
                actor_person_id,
                person_id,
                request.form.get("status", ""),
                reason,
                request_id,
            )
        elif action == "profile" and person_id is not None:
            repository.update_profile(
                actor_person_id,
                person_id,
                request.form.get("display_name", ""),
                request_id,
                reason=reason,
                formal_name=request.form.get("formal_name") or None,
                admin_note=request.form.get("admin_note") or None,
                admin_edit=True,
            )
        elif action == "grant_qualification" and person_id is not None:
            repository.grant_qualification(
                actor_person_id,
                person_id,
                request.form.get("qualification", ""),
                reason,
                request_id,
                valid_from=_optional_form_datetime("valid_from"),
                valid_until=_optional_form_datetime("valid_until"),
            )
        elif action == "revoke_qualification" and person_id is not None:
            repository.revoke_qualification(
                actor_person_id,
                person_id,
                request.form.get("qualification", ""),
                reason,
                request_id,
            )
        elif action == "review_message" and identity_id is not None:
            repository.post_review_message(
                identity_id,
                request.form.get("message", ""),
                request_id,
                actor_person_id=actor_person_id,
            )
        elif action == "create_member":
            repository.create_member_person(
                actor_person_id,
                _required_positive_form_int("member_id"),
                request.form.get("display_name", ""),
                reason,
                request_id,
                qualifications=request.form.getlist("qualification"),
            )
        else:
            abort(400)
    except (TypeError, ValueError):
        abort(400)
    except Exception:
        return "Identity action could not be applied", 409
    try:
        notify_management_message("Portal identity action completed")
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/match-member/ignore", methods=["POST"])
@admin_required
def ignore_line_user():
    require_valid_csrf()
    if is_rollout_freeze_enabled(demo_mode=DEMO_MODE_ENABLED):
        return ROLLOUT_FREEZE_RESPONSE
    if not is_identity_maintenance_enabled(demo_mode=DEMO_MODE_ENABLED):
        return "Identity maintenance is temporarily unavailable", 503
    repository = phase_c_repository()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    line_user_id = _required_form_text("line_user_id")
    request_id = _required_request_id("identity-ignore-")
    identity = repository.line_identity(line_user_id)
    actor_person_id = session.get("person_id")
    if (
        identity is None
        or not isinstance(actor_person_id, int)
        or not request_id.startswith("identity-ignore-")
    ):
        abort(400)
    repository.set_ignored(
        actor_person_id,
        identity.id,
        True,
        request.form.get("reason", ""),
        request_id,
    )

    return redirect(url_for("index"))


@app.route("/future-games")
@member_required
def future_games():
    now = datetime.now(local_timezone)
    today_begin = datetime.combine(now, time.min, tzinfo=local_timezone)
    _30_days_later = today_begin + timedelta(days=31)
    all_games = Game.search_between(today_begin, _30_days_later)
    this_week_games, this_month_games = Game.get_games_in_this_week_and_month(all_games)

    has_offseason = False
    for game in this_week_games:
        if game.season == 3:
            has_offseason = True

    for game in this_month_games:
        if game.season == 3:
            has_offseason = True

    return render_template(
        "future_games.html",
        this_week_games=this_week_games,
        this_month_games=this_month_games,
        has_offseason=has_offseason,
    )


@app.get("/manage")
@game_management_required
def management_hub():
    return render_template(
        "management_hub.html",
        can_manage_games=True,
        can_manage_events=has_capability(get_current_principal(), MANAGE_EVENTS),
        can_manage_people=has_capability(get_current_principal(), MANAGE_MEMBERS),
    )


@app.route("/game-roster/<int:game_id>")
@member_required
def game_roster(game_id: int):
    return redirect(
        url_for(
            "lineup_lab",
            game_id=game_id,
            name_style=request.args.get("name_style"),
        )
    )


def _command_game_rows(repository, games, name_style):
    rows = []
    for game in games:
        try:
            snapshot = attendance_projection(
                repository.attendance_summary(
                    game.id,
                    use_display_name=name_style == "display",
                )
            )
        except Exception:
            snapshot = None
        rows.append({"game": game, "attendance": snapshot})
    return tuple(rows)


def _bounded_game(game_id, now):
    return next(
        (game for game in load_bounded_games(Game, now) if game.id == game_id),
        None,
    )


@app.get("/manage/games")
@game_management_required
def game_command_center():
    scopes = request.args.getlist("scope")
    scope = scopes[0] if scopes else "future"
    if len(scopes) > 1 or scope not in GAME_SCOPES:
        abort(400)
    name_style = requested_attendance_name_style()
    repository, _, role = g.game_management_context
    now = datetime.now(local_timezone)
    try:
        games = tuple(
            game
            for game in load_bounded_games(Game, now)
            if game_scope(game, now) == scope
        )
        rows = _command_game_rows(repository, games, name_style)
    except Exception:
        return (
            render_template(
                "game_command_center.html",
                rows=(),
                scope=scope,
                name_style=name_style,
                role=role,
                data_time=now,
                load_error=True,
                can_manage_games=True,
            ),
            503,
        )
    return render_template(
        "game_command_center.html",
        rows=rows,
        scope=scope,
        name_style=name_style,
        role=role,
        data_time=now,
        load_error=False,
        can_manage_games=True,
    )


@app.get("/manage/games/<int:game_id>")
@game_management_required
def game_command_detail(game_id):
    name_style = requested_attendance_name_style()
    repository, _, role = g.game_management_context
    now = datetime.now(local_timezone)
    try:
        game = _bounded_game(game_id, now)
    except Exception:
        return "Game information is temporarily unavailable", 503
    if game is None:
        abort(404)
    try:
        snapshot = attendance_projection(
            repository.attendance_summary(
                game.id,
                use_display_name=name_style == "display",
            )
        )
    except Exception:
        snapshot = None
    return render_template(
        "game_command_detail.html",
        game=game,
        snapshot=snapshot,
        name_style=name_style,
        role=role,
        data_time=now,
        can_manage_games=True,
        reply_text_mapping=reply_text_mapping,
    )


@app.get("/people/<int:person_id>/game-insights")
@game_management_required
def person_game_insight(person_id):
    repository, _, role = g.game_management_context
    try:
        insight = repository.person_attendance_insight(person_id)
    except SQLAlchemyError:
        return "Player insight is temporarily unavailable", 503
    if insight is None:
        abort(404)
    return render_template(
        "person_game_insight.html",
        insight=insight,
        role=role,
        reply_text_mapping=reply_text_mapping,
        can_manage_games=True,
    )


@app.get("/games/<int:game_id>/attendance-report")
@game_management_required
def game_attendance_report(game_id):
    repository, _, role = g.game_management_context
    history_limit = request.args.get("history", default=12, type=int)
    minimum_rate = request.args.get("rate", default=0, type=int)
    if history_limit not in {5, 8, 12, 20} or minimum_rate not in {
        0,
        *range(10, 101, 10),
    }:
        abort(400)
    try:
        report = repository.game_attendance_report(
            game_id,
            history_limit=history_limit,
            minimum_rate=minimum_rate,
        )
    except SQLAlchemyError:
        return "Attendance report is temporarily unavailable", 503
    if report is None:
        abort(404)
    return render_template(
        "game_attendance_report.html",
        report=report,
        role=role,
        reply_text_mapping=reply_text_mapping,
        can_manage_games=True,
    )


@app.get("/manage/game-insights")
@game_management_required
def game_insights():
    name_style = requested_attendance_name_style()
    repository, _, role = g.game_management_context
    now = datetime.now(local_timezone)
    try:
        games = load_bounded_games(Game, now)
        rows = _command_game_rows(repository, games, name_style)
    except Exception:
        return "Game insights are temporarily unavailable", 503
    snapshots = {
        row["game"].id: row["attendance"]
        for row in rows
        if row["attendance"] is not None
    }
    return render_template(
        "game_insights.html",
        insight=insight_projection(games, snapshots, now),
        name_style=name_style,
        role=role,
        data_time=now,
        incomplete_count=len(games) - len(snapshots),
        can_manage_games=True,
    )


@app.get("/games/<int:game_id>/lineup-lab")
@member_required
def lineup_lab(game_id):
    name_style = requested_attendance_name_style()
    repository = phase_c_repository()
    lifecycle_principal = (
        repository.resolve_line_principal(session.get("user_id", ""))
        if repository is not None
        else None
    )
    if (
        lifecycle_principal is None
        or lifecycle_principal.person.id != session.get("person_id")
        or lifecycle_principal.identity.id != session.get("auth_identity_id")
    ):
        abort(403)
    now = datetime.now(local_timezone)
    try:
        game = _bounded_game(game_id, now)
    except Exception:
        return "Game lineup information is temporarily unavailable", 503
    if game is None:
        abort(404)
    if game.cancellation_time is not None:
        return "Cancelled games cannot start a new lineup draft", 409
    try:
        snapshot = attendance_projection(
            repository.attendance_summary(
                game.id,
                use_display_name=name_style == "display",
            )
        )
    except Exception:
        return "Game lineup information is temporarily unavailable", 503
    return render_template(
        "lineup_lab.html",
        game=game,
        candidates=snapshot["candidates"],
        name_style=name_style,
        role=lifecycle_principal.person.access_level,
        actor_person_id=lifecycle_principal.person.id,
        data_time=now,
        can_manage_games=_can_manage_games(lifecycle_principal),
    )


@app.get("/manage/games/<int:game_id>/lineup-lab")
@game_management_required
def managed_lineup_lab_redirect(game_id):
    return redirect(
        url_for(
            "lineup_lab",
            game_id=game_id,
            name_style=request.args.get("name_style"),
        )
    )


def process_replies(attendance_mapping: dict[int, list[Member]]) -> list[str]:
    names = []

    for reply, members in attendance_mapping.items():
        for member in members:
            name = member.name

            if reply == 1:
                names.append(name)
            elif reply == 3:
                names.append(f"{name}（晚到）")
            elif reply == 4:
                names.append(f"{name}（早走）")

    return names


if __name__ == "__main__":
    app.run(
        host=(
            os.environ.get("WEB_PORTAL_BIND_HOST", "127.0.0.1")
            if LOCAL_PREVIEW_MODE_ENABLED
            else "0.0.0.0"
        ),
        port=8080,
    )
