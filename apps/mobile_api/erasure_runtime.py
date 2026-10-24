"""Explicit intake-only runtime composition; no fulfillment or external I/O.

Construction validates configuration and creates local adapters only. Provider
verification runs later, outside database transactions, on explicit proof routes.
This opt-in is not standalone rollout approval or a complete erasure deployment.
"""

import base64
import hmac
import os
from datetime import timedelta

from shared_module.mobile_api import utc_now
from shared_module.portal_data.erasure_components import build_erasure_intake_service
from shared_module.provider_verifiers import (
    AppleIdTokenVerifier,
    GoogleIdTokenVerifier,
    LineIdTokenVerifier,
)

if __package__:
    from .revision_readiness import apple_lifecycle_configuration_is_valid
else:
    from revision_readiness import apple_lifecycle_configuration_is_valid

INTAKE_ENV = "MOBILE_API_ERASURE_INTAKE_ENABLED"
PROOF_AUDIENCE = "ntubtob-mobile-account-erasure"


def _reject():
    raise RuntimeError("invalid erasure intake configuration") from None


def erasure_intake_enabled(environment=None):
    """Missing/false is off; do not inspect any other setting on this path."""
    environment = os.environ if environment is None else environment
    value = environment.get(INTAKE_ENV)
    if value is None or (type(value) is str and value == "false"):
        return False
    if type(value) is str and value == "true":
        return True
    _reject()


def _audience(value):
    if (
        type(value) is not str
        or not 1 <= len(value) <= 255
        or value != value.strip()
        or not value.isascii()
        or not value.isprintable()
    ):
        _reject()
    return value


def _key(value):
    if type(value) is not str or not 44 <= len(value) <= 4096:
        _reject()
    raw = base64.b64decode(value, altchars=b"-_", validate=True)
    if len(raw) < 32 or base64.urlsafe_b64encode(raw).decode("ascii") != value:
        _reject()
    return raw


def build_runtime_erasure_service(
    *, engine, checks_enabled, environment=None, clock=utc_now
):
    """Called only after explicit opt-in; never reuse ordinary login as proof."""
    try:
        if checks_enabled is not True:
            _reject()
        environment = os.environ if environment is None else environment
        line_audience = _audience(environment.get("MOBILE_API_AUDIENCE"))
        google_audience = _audience(
            environment.get("MOBILE_API_ERASURE_GOOGLE_AUDIENCE")
        )
        google_allowlist = tuple(
            _audience(value.strip())
            for value in environment.get("MOBILE_API_GOOGLE_AUDIENCES", "").split(",")
            if value.strip()
        )
        if google_audience not in google_allowlist:
            _reject()
        apple_values = {
            "audience": environment.get("MOBILE_API_APPLE_AUDIENCE", ""),
            "client_secret": environment.get("MOBILE_API_APPLE_CLIENT_SECRET", ""),
            "credential_key": environment.get(
                "MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY", ""
            ),
            "notification_audience": environment.get(
                "MOBILE_API_APPLE_NOTIFICATION_AUDIENCE", ""
            ),
        }
        refresh_key = environment.get("MOBILE_REFRESH_REPLAY_KEY", "")
        if not apple_lifecycle_configuration_is_valid(apple_values, refresh_key):
            _reject()
        apple_audience = _audience(apple_values["audience"])
        _audience(apple_values["notification_audience"])
        # Match the existing Apple exchange adapter before constructing services.
        client_secret = apple_values["client_secret"]
        if (
            len(client_secret) > 8192
            or not client_secret.isascii()
            or not client_secret.isprintable()
        ):
            _reject()
        receipt_key = _key(environment.get("MOBILE_API_ERASURE_RECEIPT_KEY"))
        proof_key = _key(environment.get("MOBILE_API_ERASURE_PROOF_KEY"))
        login_key = _key(environment.get("MOBILE_ACCESS_SIGNING_KEY"))
        refresh_key = _key(refresh_key)
        provider_key = _key(apple_values["credential_key"])
        if len(refresh_key) != 32 or len(provider_key) != 32:
            _reject()
        if hmac.compare_digest(receipt_key, proof_key) or any(
            hmac.compare_digest(new, existing)
            for new in (receipt_key, proof_key)
            for existing in (login_key, refresh_key, provider_key)
        ):
            _reject()
        providers = {
            "line": (LineIdTokenVerifier(), line_audience),
            # Ordinary Google login supports multiple audiences and no nonce.
            # Fresh erasure proof instead binds one explicit audience and nonce.
            "google": (
                GoogleIdTokenVerifier(audiences=(google_audience,)),
                google_audience,
            ),
            "apple": (AppleIdTokenVerifier(), apple_audience),
        }
        return build_erasure_intake_service(
            engine=engine,
            receipt_key=receipt_key,
            proof_key=proof_key,
            audience=PROOF_AUDIENCE,
            proof_lifetime=timedelta(minutes=5),
            providers=providers,
            clock=clock,
        )
    except Exception:
        _reject()
