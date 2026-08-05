from flask import Blueprint, jsonify


def create_health_blueprint() -> Blueprint:
    blueprint = Blueprint("health", __name__)

    @blueprint.get("/healthz")
    def healthz():
        response = jsonify(
            status="ok",
            service="game-broadcast-service",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return blueprint
