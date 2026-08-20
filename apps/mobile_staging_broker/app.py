"""HTTP boundary for the private staging broker."""

from __future__ import annotations

import json
from collections.abc import Callable

from flask import Flask, jsonify, request

from .broker import Broker, BrokerFailure

MAX_REQUEST_BYTES = 256


def _reject_constant(_value):
    raise ValueError("non-finite JSON is not accepted")


def _exact_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def create_app(runtime_factory: Callable[[], Broker]) -> Flask:
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        response = jsonify(status="ok", service="mobile-staging-broker")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/operations")
    def operation():
        length = request.content_length
        if (
            request.mimetype != "application/json"
            or length is None
            or length < 2
            or length > MAX_REQUEST_BYTES
        ):
            return _failure("REQUEST_INVALID", 400)
        try:
            payload = json.loads(
                request.get_data(cache=False, as_text=False).decode("utf-8"),
                object_pairs_hook=_exact_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, ValueError, json.JSONDecodeError):
            return _failure("REQUEST_INVALID", 400)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"operation", "operation_id"}
            or not isinstance(payload.get("operation"), str)
            or not isinstance(payload.get("operation_id"), str)
        ):
            return _failure("REQUEST_INVALID", 400)
        try:
            result = runtime_factory().execute(
                payload["operation"], payload["operation_id"]
            )
        except BrokerFailure as error:
            return _failure(error.reason_code, error.status_code)
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


def _failure(reason_code: str, status_code: int):
    response = jsonify(
        classification="FAILED",
        lifecycle_state="unchanged",
        operation="none",
        operation_id="none",
        reason_code=reason_code,
        target_state="none",
    )
    response.headers["Cache-Control"] = "no-store"
    return response, status_code
