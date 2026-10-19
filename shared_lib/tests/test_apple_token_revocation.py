import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

from shared_module.apple_token_revocation import (
    AppleRevocationUnknown,
    AppleTokenRevoker,
)


class AppleTokenRevokerTests(unittest.TestCase):
    def test_http_error_is_closed_without_reading_private_body(self):
        body = MagicMock()
        error = HTTPError(
            "https://appleid.apple.com/auth/revoke", 400, "fake", {}, body
        )
        opener = MagicMock()
        opener.open.side_effect = error
        with patch(
            "shared_module.apple_token_revocation.build_opener", return_value=opener
        ):
            self.assertEqual(
                AppleTokenRevoker().revoke(
                    client_id="fake.app",
                    client_secret="fake-secret",
                    token="fake-token",
                ),
                "manual_action_needed",
            )
        body.read.assert_not_called()
        body.close.assert_called_once_with()
        opener.open.assert_called_once()

    def test_native_transport_is_bounded_and_disables_redirects(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b""
        with patch(
            "shared_module.apple_token_revocation.build_opener", return_value=opener
        ) as factory:
            self.assertEqual(
                AppleTokenRevoker().revoke(
                    client_id="fake.app",
                    client_secret="fake-secret",
                    token="fake-token",
                ),
                "succeeded",
            )
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://appleid.apple.com/auth/revoke")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 5.0})
        response.read.assert_called_once_with(1)
        self.assertIsNone(
            factory.call_args.args[0].redirect_request(
                request, None, 302, "redirect", {}, "https://example.invalid"
            )
        )

    def test_fixed_endpoint_form_and_empty_success(self):
        calls = []

        def transport(url, body, timeout):
            calls.append((url, parse_qs(body.decode("ascii")), timeout))
            return 200, b""

        revoker = AppleTokenRevoker(transport=transport)
        self.assertEqual(
            revoker.revoke(
                client_id="fictional.app",
                client_secret="fake-secret",
                token="fake&token",
            ),
            "succeeded",
        )
        self.assertEqual(
            calls,
            [
                (
                    "https://appleid.apple.com/auth/revoke",
                    {
                        "client_id": ["fictional.app"],
                        "client_secret": ["fake-secret"],
                        "token": ["fake&token"],
                        "token_type_hint": ["refresh_token"],
                    },
                    5.0,
                )
            ],
        )

    def test_uncertain_response_never_retries_or_echoes_body(self):
        for response in (
            (200, b"private"),
            (500, b"private"),
            (429, b"private"),
            (302, b"private"),
            (204, b""),
            (True, b""),
        ):
            with self.subTest(response=response):
                calls = []

                def transport(*args):
                    calls.append(1)
                    return response

                with self.assertRaisesRegex(
                    AppleRevocationUnknown, "^apple_revocation_unknown$"
                ):
                    AppleTokenRevoker(transport=transport).revoke(
                        client_id="fake.app",
                        client_secret="fake-secret",
                        token="fake-token",
                    )
                self.assertEqual(calls, [1])

    def test_rejection_is_manual_not_success(self):
        for status in (400, 401, 403):
            self.assertEqual(
                AppleTokenRevoker(transport=lambda *args: (status, b"private")).revoke(
                    client_id="fake.app",
                    client_secret="fake-secret",
                    token="fake-token",
                ),
                "manual_action_needed",
            )

    def test_private_transport_exception_is_suppressed(self):
        def transport(*args):
            raise RuntimeError("private fake credential")

        with self.assertRaises(AppleRevocationUnknown) as caught:
            AppleTokenRevoker(transport=transport).revoke(
                client_id="fake.app", client_secret="fake-secret", token="fake-token"
            )
        self.assertEqual(str(caught.exception), "apple_revocation_unknown")
        self.assertTrue(caught.exception.__suppress_context__)

    def test_bad_input_performs_no_io(self):
        def transport(*args):
            self.fail("must not dispatch")

        for token in (None, "", "a\nsecret", "a" * 65537):
            with self.assertRaisesRegex(ValueError, "^invalid_revocation_input$"):
                AppleTokenRevoker(transport=transport).revoke(
                    client_id="fake.app", client_secret="fake-secret", token=token
                )


if __name__ == "__main__":
    unittest.main()
