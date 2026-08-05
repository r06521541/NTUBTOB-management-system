from collections.abc import Callable

from linebot.v3.exceptions import InvalidSignatureError


class WebhookDispatchError(RuntimeError):
    """Report an unexpected dispatch failure without exposing request data."""


def handle_webhook_request(request, dispatch: Callable[[str, str], None]):
    """Validate the webhook boundary before dispatching LINE events."""
    signature = request.headers.get("X-Line-Signature", "").strip()
    if not signature:
        return "Bad Request", 400

    body = request.get_data(as_text=True)
    try:
        dispatch(body, signature)
    except InvalidSignatureError:
        return "Bad Request", 400
    except Exception:
        raise WebhookDispatchError("Webhook dispatch failed") from None

    return "OK", 200
