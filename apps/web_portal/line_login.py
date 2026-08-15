import re
from urllib.parse import urlsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

OAUTH_STATE_SALT = "line-login-oauth-state-v1"
OAUTH_STATE_MAX_AGE_SECONDS = 600
LINE_HTTP_TIMEOUT_SECONDS = 10
AMBIGUOUS_ESCAPE_PATTERN = re.compile(
    r"%(?:0[0-9a-f]|1[0-9a-f]|25|2f|5c|7f)", re.I
)


class InvalidOAuthState(ValueError):
    """Raised when an OAuth state cannot be trusted."""


def safe_return_path(candidate, fallback):
    """Return a local absolute path, rejecting external or ambiguous targets."""
    if not isinstance(candidate, str) or not candidate.startswith("/"):
        return fallback
    parsed = urlsplit(candidate)
    if (
        parsed.scheme
        or parsed.netloc
        or candidate.startswith("//")
        or "\\" in candidate
        or any(
            ord(character) < 32 or ord(character) == 127 for character in candidate
        )
        or AMBIGUOUS_ESCAPE_PATTERN.search(candidate)
    ):
        return fallback
    return candidate


def return_path_category(return_path):
    """Map a trusted return path to a fixed, non-sensitive log category."""
    parsed_path = urlsplit(return_path).path if isinstance(return_path, str) else ""
    if parsed_path == "/attendance":
        return "attendance"
    if parsed_path == "/account":
        return "account"
    if re.fullmatch(r"/game-roster/[1-9][0-9]*", parsed_path) or re.fullmatch(
        r"/games/[1-9][0-9]*/lineup-lab", parsed_path
    ):
        return "roster"
    return "default"


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
    return safe_return_path(payload.get("next"), fallback), payload["nonce"]


def require_string_field(payload, field, allow_empty=False):
    if not isinstance(payload, dict):
        raise ValueError("Invalid response payload")
    value = payload.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError("Invalid response payload")
    return value
