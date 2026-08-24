import unittest
import requests
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
from identity_link_provider import ProviderConfigurationError, WebIdentityProviderPort

CLIENTS = {
    provider: {
        "client_id": provider + "-client",
        "client_secret": "fake-secret",
        "redirect_uri": f"https://portal.example/callback/{provider}",
    }
    for provider in ("google", "line")
}


class ProviderPortTest(unittest.TestCase):
    def test_empty_configuration_fails_closed(self):
        with self.assertRaises(ProviderConfigurationError):
            WebIdentityProviderPort(clients={}, verifiers={})

    def test_authorization_is_code_s256_nonce_and_exact_redirect(self):
        port = WebIdentityProviderPort(
            clients=CLIENTS, verifiers={"google": Mock(), "line": Mock()}
        )
        url = port.authorization_url(
            provider="google",
            state="state",
            nonce="nonce",
            redirect_uri=CLIENTS["google"]["redirect_uri"],
            code_challenge="challenge",
        )
        values = parse_qs(urlsplit(url).query)
        self.assertEqual(values["response_type"], ["code"])
        self.assertEqual(values["code_challenge_method"], ["S256"])
        self.assertEqual(values["nonce"], ["nonce"])

    def test_exchange_returns_only_id_token_and_errors_are_redacted(self):
        response = Mock()
        response.json.return_value = {
            "id_token": "raw-id-token",
            "access_token": "ignore",
        }
        port = WebIdentityProviderPort(
            clients=CLIENTS,
            verifiers={"google": Mock(), "line": Mock()},
            transport=Mock(return_value=response),
        )
        self.assertEqual(
            port.exchange_code(
                provider="google",
                code="code",
                redirect_uri=CLIENTS["google"]["redirect_uri"],
                code_verifier="verifier",
            ),
            "raw-id-token",
        )
        response.raise_for_status.side_effect = requests.RequestException(
            "raw-id-token"
        )
        with self.assertRaises(RuntimeError) as raised:
            port.exchange_code(
                provider="google",
                code="code",
                redirect_uri=CLIENTS["google"]["redirect_uri"],
                code_verifier="verifier",
            )
        self.assertNotIn("raw-id-token", str(raised.exception))
