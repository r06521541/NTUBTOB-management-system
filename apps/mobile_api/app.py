from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from flask import Flask, jsonify, request
from shared_module.attendance_reply import AttendanceReplyNotification
from shared_module.mobile_api import (
    AuthenticationError,
    BasicApiService,
    InvalidArgument,
    MalformedRequest,
    MobileApiError,
    MobileAuthService,
)


@dataclass(frozen=True)
class Dependencies:
    auth: MobileAuthService
    basic: BasicApiService
    revision_check: Callable[[], bool]


def create_app(dependencies: Dependencies) -> Flask:
    app = Flask(__name__)

    @app.before_request
    def require_revision():
        if request.path != "/health":
            try:
                ready = dependencies.revision_check()
            except Exception:
                ready = False
            if not ready:
                raise MobileApiError("required database revision is unavailable")

    @app.errorhandler(MobileApiError)
    def mobile_error(error):
        return (
            jsonify(
                {
                    "error": {
                        "code": error.code,
                        "message": str(error),
                        "request_id": request_id(),
                        "retryable": error.status in {429, 503},
                        "retry_after_seconds": None,
                        "field_errors": [],
                    }
                }
            ),
            error.status,
        )

    @app.errorhandler(404)
    def missing_route(_error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "resource_not_found",
                        "message": "resource not found",
                        "request_id": request_id(),
                        "retryable": False,
                        "retry_after_seconds": None,
                        "field_errors": [],
                    }
                }
            ),
            404,
        )

    @app.errorhandler(Exception)
    def unexpected_error(_error):
        app.logger.error("mobile_api_unexpected_error")
        return (
            jsonify(
                {
                    "error": {
                        "code": "server_error",
                        "message": "unexpected server error",
                        "request_id": request_id(),
                        "retryable": False,
                        "retry_after_seconds": None,
                        "field_errors": [],
                    }
                }
            ),
            500,
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    def request_id():
        value = request.headers.get("X-Request-ID", "")
        if value and len(value) <= 100 and value.isascii() and value.isprintable():
            return value
        return str(uuid4())

    def json_body(allowed):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise MalformedRequest("JSON object required")
        if set(body) - set(allowed):
            raise InvalidArgument("unknown JSON field")
        return body

    def authenticate():
        value = request.headers.get("Authorization", "")
        if not value.startswith("Bearer ") or len(value) > 4103:
            raise AuthenticationError("Bearer token required")
        return dependencies.auth.authenticate(value[7:])

    def game_id(value):
        if not value.startswith("game_"):
            raise MalformedRequest("game_id is malformed")
        try:
            parsed = int(value[5:])
        except ValueError:
            raise MalformedRequest("game_id is malformed") from None
        if parsed <= 0:
            raise MalformedRequest("game_id is malformed")
        return parsed

    @app.post("/api/v1/auth/line/exchange")
    def exchange():
        body = json_body(
            {"id_token", "nonce", "login_attempt_id", "installation_id", "platform"}
        )
        result = dependencies.auth.exchange(
            assertion=body.get("id_token"),
            nonce=body.get("nonce"),
            login_attempt_id=body.get("login_attempt_id"),
            installation_id=body.get("installation_id"),
            platform=body.get("platform"),
        )
        return jsonify(result.__dict__), 201

    @app.post("/api/v1/auth/refresh")
    def refresh():
        body = json_body({"refresh_token", "installation_id"})
        result = dependencies.auth.refresh(
            refresh_token=body.get("refresh_token"),
            refresh_attempt_id=request.headers.get("Refresh-Attempt-ID", ""),
            installation_id=body.get("installation_id"),
        )
        return jsonify(result.__dict__)

    @app.post("/api/v1/auth/logout")
    def logout():
        principal = authenticate()
        dependencies.auth.repository.logout(
            principal.session_id, dependencies.auth.clock()
        )
        return "", 204

    @app.get("/api/v1/me")
    def me():
        principal = authenticate()
        return jsonify(
            {
                "id": f"person_{principal.person_id}",
                "display_name": principal.display_name,
                "access_level": principal.access_level,
                "capabilities": ["games:read", "attendance:reply:self"],
            }
        )

    @app.get("/api/v1/games")
    def games():
        raw_limit = request.args.get("limit", "20")
        try:
            limit = int(raw_limit)
        except ValueError:
            raise InvalidArgument("limit must be an integer") from None
        return jsonify(
            dependencies.basic.games_page(
                authenticate(), request.args.get("cursor"), limit
            )
        )

    @app.get("/api/v1/games/<game_key>")
    def game(game_key):
        return jsonify(dependencies.basic.game(authenticate(), game_id(game_key)))

    @app.get("/api/v1/games/<game_key>/attendance")
    def attendance(game_key):
        principal = authenticate()
        return jsonify(dependencies.basic.attendance_view(principal, game_id(game_key)))

    @app.put("/api/v1/games/<game_key>/attendance-reply")
    def put_attendance(game_key):
        principal, body = authenticate(), json_body({"reply"})
        parsed_game_id = game_id(game_key)
        key = request.headers.get("Idempotency-Key", "")
        if not 16 <= len(key) <= 200:
            raise InvalidArgument("Idempotency-Key required")
        game_data = dependencies.basic.game(principal, parsed_game_id)
        notification = AttendanceReplyNotification(
            f"{game_data['home_team']} vs {game_data['away_team']}",
            principal.display_name,
            str(body.get("reply")),
        )
        status, response, replayed = dependencies.basic.attendance_reply(
            principal, parsed_game_id, body.get("reply"), key, notification
        )
        result = dict(response)
        result["idempotent_replay"] = replayed
        return jsonify(result), status

    return app
