"""Purpose-separated Web OAuth flow state for identity linking and recovery."""

import base64
import binascii
import hashlib
import json
import secrets
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

FLOW_KEYS = ("identity_link_oauth_state", "identity_link_oauth_sealed")
STATE_SALT = "identity-link-web-oauth-state-v1"
MAX_AGE_SECONDS = 300
MAX_STATE_LENGTH = 2048
MAX_SEALED_LENGTH = 4096
PROVIDERS = {"line", "google"}


class InvalidIdentityLinkOAuth(ValueError):
    pass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def clear_flow(session):
    for key in FLOW_KEYS:
        session.pop(key, None)


def _exact_redirect(value, allowed):
    if value not in allowed:
        raise InvalidIdentityLinkOAuth("redirect URI is not allowlisted")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.fragment:
        raise InvalidIdentityLinkOAuth("redirect URI is invalid")
    return value


def _key(secret_key):
    if not isinstance(secret_key, str) or len(secret_key.encode("utf-8")) < 32:
        raise InvalidIdentityLinkOAuth("identity-link OAuth key is unavailable")
    return hashlib.sha256(
        ("identity-link-flow-aead-v1:" + secret_key).encode()
    ).digest()


def _aad(state, payload):
    return (
        "identity-link-flow-aad-v1:"
        + payload["provider"]
        + ":"
        + payload["purpose"]
        + ":"
        + payload["flow_nonce"]
        + ":"
        + state
    ).encode()


def begin_flow(
    session, *, secret_key, provider, purpose, redirect_uri, allowed_redirects
):
    if provider not in PROVIDERS or purpose not in {"self_link", "recovery_link"}:
        raise InvalidIdentityLinkOAuth("OAuth flow is invalid")
    redirect_uri = _exact_redirect(redirect_uri, allowed_redirects)
    clear_flow(session)
    flow_nonce, oidc_nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    payload = {
        "provider": provider,
        "purpose": purpose,
        "flow_nonce": flow_nonce,
        "oidc_nonce": oidc_nonce,
        "redirect_uri": redirect_uri,
    }
    state = URLSafeTimedSerializer(secret_key, salt=STATE_SALT).dumps(payload)
    key = _key(secret_key)
    nonce = secrets.token_bytes(12)
    sealed = _b64(
        nonce
        + AESGCM(key).encrypt(
            nonce,
            json.dumps(
                {**payload, "verifier": verifier}, sort_keys=True, separators=(",", ":")
            ).encode(),
            _aad(state, payload),
        )
    )
    if len(state) > MAX_STATE_LENGTH or len(sealed) > MAX_SEALED_LENGTH:
        raise InvalidIdentityLinkOAuth("OAuth flow envelope is too large")
    session["identity_link_oauth_state"] = state
    session["identity_link_oauth_sealed"] = sealed
    return {
        "state": state,
        "nonce": oidc_nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "redirect_uri": redirect_uri,
    }


def consume_callback(
    session, *, secret_key, state, provider, redirect_uri, allowed_redirects
):
    expected_state = session.pop("identity_link_oauth_state", None)
    sealed = session.pop("identity_link_oauth_sealed", None)
    if (
        not expected_state
        or not sealed
        or not isinstance(state, str)
        or len(state) > MAX_STATE_LENGTH
        or len(sealed) > MAX_SEALED_LENGTH
        or not secrets.compare_digest(expected_state, state)
    ):
        raise InvalidIdentityLinkOAuth("OAuth state/session mismatch")
    try:
        payload = URLSafeTimedSerializer(secret_key, salt=STATE_SALT).loads(
            state, max_age=MAX_AGE_SECONDS
        )
        raw = base64.urlsafe_b64decode(sealed + "=" * (-len(sealed) % 4))
        key = _key(secret_key)
        stored = json.loads(
            AESGCM(key).decrypt(raw[:12], raw[12:], _aad(state, payload))
        )
    except (
        BadSignature,
        SignatureExpired,
        InvalidTag,
        binascii.Error,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        KeyError,
    ):
        raise InvalidIdentityLinkOAuth("OAuth flow is invalid or expired") from None
    redirect_uri = _exact_redirect(redirect_uri, allowed_redirects)
    expected = {"provider", "purpose", "flow_nonce", "oidc_nonce", "redirect_uri"}
    if set(payload) != expected or any(
        stored.get(key) != value for key, value in payload.items()
    ):
        raise InvalidIdentityLinkOAuth("OAuth flow binding mismatch")
    if payload["provider"] != provider or payload["redirect_uri"] != redirect_uri:
        raise InvalidIdentityLinkOAuth("OAuth provider/redirect mix-up")
    if (
        not isinstance(stored.get("verifier"), str)
        or not 43 <= len(stored["verifier"]) <= 128
    ):
        raise InvalidIdentityLinkOAuth("PKCE verifier is unavailable")
    return {**payload, "code_verifier": stored["verifier"]}
