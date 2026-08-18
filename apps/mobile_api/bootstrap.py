"""Fail-closed deployment bootstrap for the independent mobile API."""

import base64
import os

from app import Dependencies, create_app
from cryptography.fernet import Fernet, InvalidToken
from line_verifier import LineIdTokenVerifier
from shared_module.attendance_reply import AttendanceReplyService
from shared_module.mobile_api import (
    BasicApiService,
    HmacAccessTokenCodec,
    MobileApiError,
    MobileAuthService,
)
from shared_module.models.db import engine
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository
from shared_module.portal_data.mobile_repository import MobileRepository
from sqlalchemy import text


class RuntimeCipher:
    def __init__(self, key: str):
        if not key:
            raise RuntimeError("MOBILE_REFRESH_REPLAY_KEY is required")
        try:
            self._cipher = Fernet(key.encode("ascii"))
        except (TypeError, ValueError):
            raise RuntimeError("MOBILE_REFRESH_REPLAY_KEY is invalid") from None

    def seal(self, value: bytes) -> bytes:
        return self._cipher.encrypt(value)

    def open(self, value: bytes) -> bytes:
        try:
            return self._cipher.decrypt(value)
        except InvalidToken:
            raise MobileApiError("refresh replay payload is unavailable") from None


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def revision_is_current() -> bool:
    try:
        with engine.connect() as connection:
            return (
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                )
                == "0005_mobile_auth_api_foundation"
            )
    except Exception:
        return False


repository = MobileRepository(engine)
cipher = RuntimeCipher(required("MOBILE_REFRESH_REPLAY_KEY"))
token_key = base64.urlsafe_b64decode(required("MOBILE_ACCESS_SIGNING_KEY"))
auth = MobileAuthService(
    repository,
    LineIdTokenVerifier(),
    cipher,
    HmacAccessTokenCodec(token_key),
    audience=required("MOBILE_API_AUDIENCE"),
)


def unavailable_notifier(_notification):
    raise RuntimeError("notification port is not configured")


data = IdentityLifecycleRepository(engine)
attendance = AttendanceReplyService(data, unavailable_notifier)
app = create_app(
    Dependencies(
        auth, BasicApiService(data, attendance, repository), revision_is_current
    )
)
