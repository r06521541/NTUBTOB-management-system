import hashlib
import hmac
import os
import secrets
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode

import messages
import requests
from admin_security import (
    admin_required,
    configure_phase_c_principal_loader,
    get_current_principal,
    get_or_create_csrf_token,
    get_or_create_logout_csrf_token,
    member_required,
    parse_admin_member_ids,
    require_valid_csrf,
    require_valid_logout_csrf,
)
from demo_events import demo_events
from demo_portal import demo_portal, is_demo_mode_enabled
from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_caching import Cache
from identity_maintenance import is_identity_maintenance_enabled
from line_login import (
    LINE_HTTP_TIMEOUT_SECONDS,
    InvalidOAuthState,
    create_oauth_state,
    load_oauth_state,
    require_string_field,
    return_path_category,
    safe_return_path,
)
from performance_diagnostics import AttendanceTiming
from role_policy import MANAGE_MEMBERS, ROLE_ADMIN, ROLE_MEMBER
from role_policy import Principal as WebPrincipal
from role_policy import has_capability

from envs import login_channel_id, login_channel_secret, secret_key

DEMO_MODE_ENABLED = is_demo_mode_enabled()

if not DEMO_MODE_ENABLED:
    import shared_module.attendance_analyzer as attendance_analyzer
    from shared_module.message_templates.general_message import reply_text_mapping
    from shared_module.models.game_attendance_replies import GameAttendanceReply
    from shared_module.models.games import Game
    from shared_module.models.line_users import LineUser
    from shared_module.models.members import Member
    from shared_module.notify.discord_notify import DiscordNotifyHelper
    from shared_module.settings import local_timezone
else:
    # Keep production-only ORM and notifier imports out of the offline demo process.
    # Existing production routes are explicitly unavailable below while demo is on.
    Game = Member = LineUser = GameAttendanceReply = object
    attendance_analyzer = None
    local_timezone = timezone(timedelta(hours=8))
    reply_text_mapping = {}

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_NAME="ntubtob_web_session_v2",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_PATH="/",
    SESSION_COOKIE_SECURE=not DEMO_MODE_ENABLED,
    SESSION_COOKIE_DOMAIN=None,
)
if DEMO_MODE_ENABLED and not secret_key:
    # Non-sensitive fallback is deliberately limited to the double-gated local demo.
    app.secret_key = "development-demo-session-key-not-for-production"
else:
    app.secret_key = secret_key  # 用於保持安全的session
app.register_blueprint(demo_portal)
app.register_blueprint(demo_events)

LEGACY_SESSION_COOKIE_NAME = "session"
OAUTH_SESSION_KEYS = ("oauth_state_nonce", "next_url")
LEGACY_IDENTITY_SESSION_KEYS = ("member", "display_name")
AUTHENTICATED_IDENTITY_SESSION_KEYS = ("user_id", "member_id")
PHASE_C_SESSION_KEYS = ("person_id", "auth_identity_id", "member_id", "user_id")
ATTENDANCE_NAME_STYLES = frozenset({"formal", "display"})


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


def phase_c_repository():
    if os.environ.get("PORTAL_DATA_PHASE_C_ENABLED") != "true" or DEMO_MODE_ENABLED:
        return None
    try:
        from shared_module.portal_data.runtime import get_identity_lifecycle_repository
    except ImportError:
        return None
    return get_identity_lifecycle_repository(
        parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS")),
    )


def load_phase_c_web_principal(session_values):
    if os.environ.get("PORTAL_DATA_PHASE_C_ENABLED") != "true":
        return False
    repository = phase_c_repository()
    user_id = session_values.get("user_id")
    person_id = session_values.get("person_id")
    identity_id = session_values.get("auth_identity_id")
    if repository is None or not isinstance(user_id, str):
        return None
    principal = repository.resolve_line_principal(user_id)
    if (
        principal is None
        or principal.person.id != person_id
        or principal.identity.id != identity_id
    ):
        for key in PHASE_C_SESSION_KEYS:
            session.pop(key, None)
        return None
    allowlist = parse_admin_member_ids(os.environ.get("WEB_PORTAL_ADMIN_MEMBER_IDS"))
    role = ROLE_ADMIN if principal.person.member_id in allowlist else ROLE_MEMBER
    return WebPrincipal(role=role, member_id=principal.person.member_id)


configure_phase_c_principal_loader(load_phase_c_web_principal)

# 設定 Cache 配置
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # 使用本地內存
    "CACHE_DEFAULT_TIMEOUT": 600,  # 預設 Cache 有效期為600秒（10分鐘）
}
app.config.from_mapping(cache_config)

# 初始化 Cache
cache = Cache(app)

LINE_REDIRECT_URI = "https://web-portal-7uz453jt3a-de.a.run.app/line/callback"

LINE_AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_USER_INFO_URL = "https://api.line.me/v2/profile"


discord_notify_helper = None if DEMO_MODE_ENABLED else DiscordNotifyHelper()


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
        "game_roster",
        "clear_attendance_cache",
        "account",
        "logout",
    }
    if request.endpoint in blocked_endpoints:
        return "Not available in offline demo mode", 404
    return None


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

    # 生成隨機的 state
    return_path = safe_return_path(
        (next_values[0] if next_values else None) or session.pop("next_url", None),
        url_for("attendance"),
    )
    nonce = secrets.token_urlsafe(16)
    session["oauth_state_nonce"] = nonce
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
        return invalid_oauth_state_response(url_for("attendance"))

    session_nonce = session.pop("oauth_state_nonce", None)
    if not isinstance(session_nonce, str) or not hmac.compare_digest(
        state_nonce, session_nonce
    ):
        return invalid_oauth_state_response(next_url)

    if not code:
        return "Invalid authorization response", 400

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

    if os.environ.get("PORTAL_DATA_PHASE_C_ENABLED") == "true":
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


@app.route("/attendance")
@member_required
def attendance():
    timing = AttendanceTiming()
    name_style = requested_attendance_name_style()
    repository = phase_c_repository()
    lifecycle_principal = (
        repository.resolve_line_principal(session.get("user_id", ""))
        if repository is not None
        else None
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
    timing.finish("member_lookup")

    # 查詢未來的比賽
    upcoming_games = Game.search_for_invited()
    timing.finish("games_query")

    games_with_attendance = []
    for game in upcoming_games:
        mapping = attendance_for_game(game.id, name_style)
        games_with_attendance.append(
            {
                "id": game.id,
                "game_summary": game.generate_short_summary_for_team(),
                "attendance_mapping": mapping,
            }
        )
    timing.finish("attendance_analysis")

    now = datetime.now(local_timezone).strftime("%Y年%-m月%-d日 %H:%M:%S")
    response = render_template(
        "attendance.html",
        update_time=now,
        my_membership=member,
        games_with_attendance=games_with_attendance,
        reply_text_mapping=reply_text_mapping,
        name_style=name_style,
        can_manage_members=has_capability(get_current_principal(), MANAGE_MEMBERS),
    )
    timing.finish("render")
    timing.emit(app.logger)
    return response


@app.route("/account")
@member_required
def account():
    repository = phase_c_repository()
    lifecycle_principal = (
        repository.resolve_line_principal(session.get("user_id", ""))
        if repository is not None
        else None
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
    return render_template(
        "account.html",
        member=member,
        role_label=("系統管理者" if principal.role == ROLE_ADMIN else "一般隊員"),
        can_manage_members=can_manage_members,
        logout_csrf_token=get_or_create_logout_csrf_token(),
        profile_csrf_token=get_or_create_csrf_token(),
        profile_request_id=f"profile-{secrets.token_urlsafe(24)}",
    )


@app.route("/account/profile", methods=["POST"])
@member_required
def update_own_profile():
    require_valid_csrf()
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
        return render_template(
            "identity_admin.html",
            dashboard=repository.admin_dashboard(actor_person_id),
            csrf_token=get_or_create_csrf_token(),
            request_nonce=secrets.token_urlsafe(16),
            identity_maintenance_enabled=is_identity_maintenance_enabled(),
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
        identity_maintenance_enabled=is_identity_maintenance_enabled(),
    )


@app.route("/match-member/match", methods=["POST"])
@admin_required
def match_line_user():
    require_valid_csrf()
    if not is_identity_maintenance_enabled():
        return "Identity maintenance is temporarily unavailable", 503
    repository = phase_c_repository()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    line_user_id = request.form["line_user_id"]
    member_id = request.form["member_id"]
    identity = repository.line_identity(line_user_id)
    actor_person_id = session.get("person_id")
    request_id = request.form.get("request_id", "")
    if (
        identity is None
        or not isinstance(actor_person_id, int)
        or not request_id.startswith("identity-match-")
    ):
        abort(400)
    repository.approve_member(
        actor_person_id,
        identity.id,
        int(member_id),
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


@app.route("/identity-admin/action", methods=["POST"])
@admin_required
def identity_admin_action():
    require_valid_csrf()
    if not is_identity_maintenance_enabled():
        return "Identity maintenance is temporarily unavailable", 503
    repository = phase_c_repository()
    actor_person_id = session.get("person_id")
    if repository is None or not isinstance(actor_person_id, int):
        return "Identity service is temporarily unavailable", 503
    action = request.form.get("action", "")
    reason = request.form.get("reason", "")
    request_id = request.form.get("request_id", "")
    identity_id = request.form.get("identity_id", type=int)
    person_id = request.form.get("person_id", type=int)
    remap_member_id = None
    if action == "remap":
        remap_member_id = request.form.get("member_id", type=int)
        if (
            identity_id is None
            or remap_member_id is None
            or request.form.getlist("confirm_remap") != ["yes"]
        ):
            abort(400)
    try:
        if action == "approve_non_member" and identity_id is not None:
            qualifications = request.form.getlist("qualification")
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
                request.form.get("member_id", type=int),
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
                remap_member_id,
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
    if not is_identity_maintenance_enabled():
        return "Identity maintenance is temporarily unavailable", 503
    repository = phase_c_repository()
    if repository is None:
        return "Identity service is temporarily unavailable", 503
    identity = repository.line_identity(request.form["line_user_id"])
    actor_person_id = session.get("person_id")
    request_id = request.form.get("request_id", "")
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


key_prefix_future_games = "future_games"


@app.route("/future-games")
@cache.cached(timeout=3600, key_prefix=key_prefix_future_games)
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


@app.route("/game-roster/<int:game_id>")
@member_required
def game_roster(game_id: int):
    name_style = requested_attendance_name_style()
    game = Game.search_by_id(game_id)
    if game is None:
        abort(404)
    attendance_mapping = attendance_for_game(game.id, name_style)
    return render_template(
        "game_roster.html",
        game=game,
        players=process_replies(attendance_mapping),
        unanswered_count=len(attendance_mapping.get(5, ())),
        name_style=name_style,
        can_manage_members=has_capability(get_current_principal(), MANAGE_MEMBERS),
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
    app.run(host="0.0.0.0", port=8080)
