"""Fail-closed deployment bootstrap for the independent mobile API."""

import base64
import logging
import os

from app import Dependencies, create_app
from cryptography.fernet import Fernet, InvalidToken
from google_verifier import GoogleIdTokenVerifier
from line_verifier import LineIdTokenVerifier
from revision_readiness import database_revision_is_current
from shared_module.attendance_reply import AttendanceReplyService
from shared_module.identity_linking import IdentityLinkProofCodec, IdentityLinkService
from shared_module.mobile_api import (
    BasicApiService,
    HmacAccessTokenCodec,
    MobileApiError,
    MobileAuthService,
    PendingReviewService,
)
from shared_module.mobile_notifications import NotificationPublishingService
from shared_module.models.db import engine
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository
from shared_module.portal_data.mobile_repository import MobileRepository

logger = logging.getLogger(__name__)


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


def google_audiences() -> tuple[str, ...]:
    values = tuple(
        value.strip()
        for value in required("MOBILE_API_GOOGLE_AUDIENCES").split(",")
        if value.strip()
    )
    if not values:
        raise RuntimeError("MOBILE_API_GOOGLE_AUDIENCES is invalid")
    return values


def revision_is_current() -> bool:
    return database_revision_is_current(engine, logger)


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
google_auth = MobileAuthService(
    repository,
    GoogleIdTokenVerifier(audiences=google_audiences()),
    cipher,
    HmacAccessTokenCodec(token_key),
    audience="google-provider-verified",
    verify_audience=False,
    require_nonce=False,
)
identity_link = IdentityLinkService(
    repository,
    IdentityLinkProofCodec(token_key),
    clock=auth.clock,
    recovery_auth=auth,
)


def unavailable_notifier(_notification):
    raise RuntimeError("notification port is not configured")


data = IdentityLifecycleRepository(engine)
attendance = AttendanceReplyService(data, unavailable_notifier)
app = create_app(
    Dependencies(
        auth,
        BasicApiService(data, attendance, repository),
        NotificationPublishingService(repository),
        revision_is_current,
        PendingReviewService(data, auth.token_codec),
        google_auth,
        identity_link,
    )
)
