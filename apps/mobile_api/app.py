from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Callable
from uuid import uuid4

from flask import Flask, jsonify, request
from shared_module.attendance_reply import AttendanceReplyNotification
from shared_module.event_read import EventReadContractError, parse_event_key
from shared_module.mobile_api import (
    MAX_POSTGRESQL_BIGINT,
    AuthenticationError,
    BasicApiService,
    InvalidArgument,
    MalformedRequest,
    MobileApiError,
    MobileAuthService,
    NotFound,
    mobile_capabilities,
)


@dataclass(frozen=True)
class Dependencies:
    auth: MobileAuthService
    basic: BasicApiService
    publishing: object
    revision_check: Callable[[], bool]
    review: object | None = None
    google_auth: MobileAuthService | None = None
    identity_link: object | None = None


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

    def authenticate_review():
        if dependencies.review is None:
            raise AuthenticationError("review unavailable")
        value = request.headers.get("Authorization", "")
        if not value.startswith("Bearer ") or len(value) > 4103:
            raise AuthenticationError("Bearer token required")
        return dependencies.review.authenticate(value[7:])

    def game_id(value):
        if not value.startswith("game_"):
            raise MalformedRequest("game_id is malformed")
        try:
            parsed = int(value[5:])
        except ValueError:
            raise MalformedRequest("game_id is malformed") from None
        if parsed == 0:
            raise MalformedRequest("game_id is malformed")
        return parsed

    def event_id(value):
        try:
            return parse_event_key(value)
        except EventReadContractError:
            raise MalformedRequest("event_id is malformed") from None

    def notification_id(value):
        if not isinstance(value, str) or not 14 <= len(value) <= 32:
            raise MalformedRequest("notification_id is malformed")
        if not value.startswith("notification_"):
            raise MalformedRequest("notification_id is malformed")
        suffix = value[13:]
        if not suffix.isascii() or not suffix.isdigit() or suffix.startswith("0"):
            raise MalformedRequest("notification_id is malformed")
        try:
            parsed = int(suffix)
        except ValueError:
            raise MalformedRequest("notification_id is malformed") from None
        if parsed > MAX_POSTGRESQL_BIGINT:
            raise MalformedRequest("notification_id is malformed")
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
        return jsonify(result.__dict__), (
            202 if hasattr(result, "review_credential") else 201
        )

    @app.post("/api/v1/auth/google/exchange")
    def google_exchange():
        if dependencies.google_auth is None:
            raise MobileApiError("Google sign-in is unavailable")
        body = json_body(
            {"id_token", "login_attempt_id", "installation_id", "platform"}
        )
        result = dependencies.google_auth.exchange(
            assertion=body.get("id_token"),
            nonce=None,
            login_attempt_id=body.get("login_attempt_id"),
            installation_id=body.get("installation_id"),
            platform=body.get("platform"),
        )
        return jsonify(result.__dict__), (
            202 if hasattr(result, "review_credential") else 201
        )

    @app.get("/api/v1/auth/identities")
    def linked_identities():
        principal = authenticate()
        if dependencies.identity_link is None:
            raise MobileApiError("identity linking is unavailable")
        items = dependencies.identity_link.repository.linked_identity_labels(
            principal.person_id
        )
        return jsonify(
            {
                "items": [
                    {
                        "provider": item["provider"],
                        "label": item["label"],
                        "linked_at": item["linked_at"]
                        .astimezone(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                    for item in items
                ]
            }
        )

    def provider_auth(provider, body):
        service = (
            dependencies.google_auth if provider == "google" else dependencies.auth
        )
        nonce = body.get("nonce") if provider == "line" else None
        verified = service.verifier.verify(
            body.get("id_token"), service.audience, nonce, service.clock()
        )
        return service, verified

    @app.post("/api/v1/auth/identity-link/candidates/<provider>")
    def identity_link_candidate(provider):
        if dependencies.identity_link is None or provider not in {"line", "google"}:
            raise NotFound("identity provider not found")
        allowed = {"id_token", "login_attempt_id", "installation_id"}
        if provider == "line":
            allowed.add("nonce")
        body = json_body(allowed)
        _service, verified = provider_auth(provider, body)
        result = dependencies.identity_link.begin_candidate(
            provider=provider,
            subject=verified.subject,
            raw_assertion=body.get("id_token"),
            attempt_id=body.get("login_attempt_id"),
            binding=body.get("installation_id"),
        )
        return jsonify(result), 201

    @app.post("/api/v1/auth/identity-link/proofs/<provider>")
    def identity_link_proof(provider):
        if dependencies.identity_link is None or provider not in {"line", "google"}:
            raise NotFound("identity provider not found")
        allowed = {
            "candidate_credential",
            "id_token",
            "login_attempt_id",
            "installation_id",
        }
        if provider == "line":
            allowed.add("nonce")
        body = json_body(allowed)
        _service, verified = provider_auth(provider, body)
        result = dependencies.identity_link.issue_fresh_proof(
            candidate_credential=body.get("candidate_credential"),
            provider=provider,
            subject=verified.subject,
            attempt_id=body.get("login_attempt_id"),
            binding=body.get("installation_id"),
        )
        return jsonify(result), 201

    @app.post("/api/v1/auth/identity-link/confirm")
    def identity_link_confirm():
        if dependencies.identity_link is None:
            raise MobileApiError("identity linking is unavailable")
        body = json_body(
            {
                "candidate_credential",
                "proof_credential",
                "installation_id",
                "platform",
                "outcome",
                "confirmed",
            }
        )
        if body.get("confirmed") is not True:
            raise InvalidArgument("explicit identity-link confirmation is required")
        current_person_id = None
        if body.get("outcome") == "self_link":
            current_person_id = authenticate().person_id
        result = dependencies.identity_link.confirm_mobile(
            candidate_credential=body.get("candidate_credential"),
            proof_credential=body.get("proof_credential"),
            binding=body.get("installation_id"),
            outcome=body.get("outcome"),
            current_person_id=current_person_id,
            platform=body.get("platform"),
        )
        return jsonify(result.mobile_public())

    @app.post("/api/v1/auth/identity-link/cancel")
    def identity_link_cancel():
        json_body(set())
        return jsonify({"status": "cancelled_on_this_device"})

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
                "capabilities": list(mobile_capabilities(principal)),
            }
        )

    @app.patch("/api/v1/me")
    def update_me():
        principal = authenticate()
        body = json_body({"display_name"})
        status, result, replayed = dependencies.basic.update_profile(
            principal,
            body.get("display_name"),
            request.headers.get("Idempotency-Key", ""),
        )
        return jsonify({**result, "idempotent_replay": replayed}), status

    @app.get("/api/v1/auth/line/review")
    def pending_review():
        return jsonify(dependencies.review.status(authenticate_review()))

    @app.post("/api/v1/auth/line/review/messages")
    def pending_review_message():
        identity_id = authenticate_review()
        body = json_body({"body"})
        return jsonify(
            dependencies.review.append(
                identity_id,
                body.get("body"),
                request.headers.get("Idempotency-Key", ""),
            )
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

    @app.get("/api/v1/events")
    def events():
        raw_limit = request.args.get("limit", "20")
        try:
            limit = int(raw_limit)
        except ValueError:
            raise InvalidArgument("limit must be an integer") from None
        return jsonify(
            dependencies.basic.events_page(
                authenticate(), request.args.get("cursor"), limit
            )
        )

    @app.get("/api/v1/notifications")
    def notifications():
        raw_limit = request.args.get("limit", "20")
        try:
            limit = int(raw_limit)
        except ValueError:
            raise InvalidArgument("limit must be an integer") from None
        raw_unread = request.args.get("unread_only", "false")
        if raw_unread not in {"true", "false"}:
            raise InvalidArgument("unread_only must be true or false")
        return jsonify(
            dependencies.basic.notifications_page(
                authenticate(),
                request.args.get("cursor"),
                limit,
                raw_unread == "true",
            )
        )

    @app.get("/api/v1/notifications/unread-count")
    def notification_unread_count():
        return jsonify(
            {
                "unread_count": dependencies.basic.notification_unread_count(
                    authenticate()
                )
            }
        )

    @app.put("/api/v1/notifications/read-all")
    def mark_all_notifications_read():
        principal = authenticate()
        json_body(set())
        return jsonify(dependencies.basic.mark_all_notifications_read(principal))

    @app.get("/api/v1/notifications/<notification_key>")
    def notification(notification_key):
        return jsonify(
            dependencies.basic.notification(
                authenticate(), notification_id(notification_key)
            )
        )

    @app.put("/api/v1/notifications/<notification_key>/read")
    def mark_notification_read(notification_key):
        principal = authenticate()
        json_body(set())
        return jsonify(
            dependencies.basic.mark_notification_read(
                principal, notification_id(notification_key)
            )
        )

    @app.post("/api/v1/officer/notifications/preview")
    def preview_notification():
        draft = json_body({"type", "title", "body", "audience", "destination"})
        return jsonify(dependencies.publishing.preview(authenticate(), draft))

    @app.post("/api/v1/officer/notifications/confirm")
    def confirm_notification():
        body = json_body({"draft", "preview_revision", "typed_confirmation"})
        key = request.headers.get("Idempotency-Key", "")
        result = dependencies.publishing.confirm(
            authenticate(),
            body.get("draft"),
            preview_revision=body.get("preview_revision"),
            typed_confirmation=body.get("typed_confirmation"),
            idempotency_key=key,
        )
        return jsonify(result), 200 if result["idempotent_replay"] else 201

    @app.put("/api/v1/devices/current")
    def register_device():
        body = json_body({"installation_id", "platform", "provider", "token"})
        result = dependencies.publishing.register_device(
            authenticate(),
            installation_id=body.get("installation_id"),
            platform=body.get("platform"),
            provider=body.get("provider"),
            token=body.get("token"),
        )
        return jsonify(result)

    @app.delete("/api/v1/devices/current")
    def revoke_device():
        body = json_body({"installation_id"})
        return jsonify(
            dependencies.publishing.revoke_device(
                authenticate(), installation_id=body.get("installation_id")
            )
        )

    @app.get("/api/v1/games/<game_key>")
    def game(game_key):
        return jsonify(dependencies.basic.game(authenticate(), game_id(game_key)))

    @app.get("/api/v1/events/<event_key>")
    def event(event_key):
        return jsonify(dependencies.basic.event(authenticate(), event_id(event_key)))

    @app.get("/api/v1/games/<game_key>/attendance")
    def attendance(game_key):
        principal = authenticate()
        return jsonify(dependencies.basic.attendance_view(principal, game_id(game_key)))

    @app.get("/api/v1/games/<game_key>/attendance-report")
    def attendance_report(game_key):
        principal = authenticate()

        def bounded_integer(name, default, allowed):
            raw = request.args.get(name, str(default))
            try:
                value = int(raw)
            except ValueError:
                raise InvalidArgument(f"{name} must be an integer") from None
            if value not in allowed:
                raise InvalidArgument(f"{name} is outside the supported range")
            return value

        history_limit = bounded_integer("history_limit", 12, {5, 8, 12, 20})
        minimum_rate = bounded_integer(
            "minimum_response_rate", 60, set(range(0, 101, 10))
        )
        return jsonify(
            dependencies.basic.attendance_report(
                principal,
                game_id(game_key),
                history_limit=history_limit,
                minimum_rate=minimum_rate,
            )
        )

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
