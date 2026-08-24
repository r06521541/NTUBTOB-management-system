"""Production OAuth-code adapter; provider ID tokens use shared verifiers."""

from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

AUTH_URLS = {
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
    "line": "https://access.line.me/oauth2/v2.1/authorize",
}
TOKEN_URLS = {
    "google": "https://oauth2.googleapis.com/token",
    "line": "https://api.line.me/oauth2/v2.1/token",
}


class ProviderConfigurationError(RuntimeError):
    pass


class WebIdentityProviderPort:
    def __init__(self, *, clients, verifiers, transport=requests.post, timeout=10):
        if set(clients) != {"google", "line"} or set(verifiers) != {"google", "line"}:
            raise ProviderConfigurationError(
                "identity-link providers are not configured"
            )
        for provider, config in clients.items():
            if set(config) != {"client_id", "client_secret", "redirect_uri"} or any(
                not isinstance(value, str) or not value for value in config.values()
            ):
                raise ProviderConfigurationError(
                    "identity-link provider is not configured"
                )
            if not config["redirect_uri"].startswith("https://"):
                raise ProviderConfigurationError("identity-link redirect is invalid")
        if not 0 < timeout <= 10:
            raise ProviderConfigurationError("identity-link timeout is invalid")
        self.clients, self.verifiers = clients, verifiers
        self.transport, self.timeout = transport, timeout

    def redirect_uri(self, provider):
        try:
            return self.clients[provider]["redirect_uri"]
        except KeyError:
            raise ProviderConfigurationError("unknown identity provider") from None

    def authorization_url(self, **values):
        provider = values["provider"]
        params = {
            "response_type": "code",
            "client_id": self.clients[provider]["client_id"],
            "redirect_uri": values["redirect_uri"],
            "state": values["state"],
            "nonce": values["nonce"],
            "code_challenge": values["code_challenge"],
            "code_challenge_method": "S256",
            "scope": "openid",
        }
        return AUTH_URLS[provider] + "?" + urlencode(params)

    def exchange_code(self, **values):
        provider, config = values["provider"], self.clients[values["provider"]]
        try:
            response = self.transport(
                TOKEN_URLS[provider],
                data={
                    "grant_type": "authorization_code",
                    "code": values["code"],
                    "redirect_uri": values["redirect_uri"],
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code_verifier": values["code_verifier"],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("id_token")
            if not isinstance(token, str) or not token or len(token) > 4096:
                raise ValueError
            return token
        except (requests.RequestException, ValueError, TypeError, KeyError):
            raise RuntimeError("identity provider exchange unavailable") from None

    def verify_id_token(self, **values):
        config = self.clients[values["provider"]]
        return self.verifiers[values["provider"]].verify(
            values["id_token"],
            config["client_id"],
            values["nonce"],
            datetime.now(timezone.utc),
        )
