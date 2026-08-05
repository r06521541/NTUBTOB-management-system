from urllib.parse import urlsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


OAUTH_STATE_SALT = "line-login-oauth-state-v1"
OAUTH_STATE_MAX_AGE_SECONDS = 600
LINE_HTTP_TIMEOUT_SECONDS = 10


class InvalidOAuthState(ValueError):
    """Raised when an OAuth state cannot be trusted."""


def safe_return_path(candidate, fallback):
    """Return a local absolute path, rejecting external or ambiguous targets."""
    if not isinstance(candidate, str) or not candidate.startswith("/"):
        return fallback
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith("//"):
        return fallback
    return candidate


def create_oauth_state(secret_key, return_path, nonce):
    serializer = URLSafeTimedSerializer(secret_key, salt=OAUTH_STATE_SALT)
    return serializer.dumps({"next": return_path, "nonce": nonce})


def load_oauth_state(secret_key, state, fallback, max_age=OAUTH_STATE_MAX_AGE_SECONDS):
    if not secret_key or not state:
        raise InvalidOAuthState("OAuth state is missing")
    serializer = URLSafeTimedSerializer(secret_key, salt=OAUTH_STATE_SALT)
    try:
        payload = serializer.loads(state, max_age=max_age)
    except (BadSignature, SignatureExpired) as exc:
        raise InvalidOAuthState("OAuth state is invalid or expired") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("nonce"), str):
        raise InvalidOAuthState("OAuth state payload is invalid")
    return safe_return_path(payload.get("next"), fallback)
