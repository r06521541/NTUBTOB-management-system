import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from itsdangerous import TimestampSigner

WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))

from line_login import (  # noqa: E402
    InvalidOAuthState,
    create_oauth_state,
    load_oauth_state,
    return_path_category,
    safe_return_path,
)


class OAuthStateTest(unittest.TestCase):
    def setUp(self):
        self.secret = "fake-test-signing-key"

    def test_signed_state_round_trip_preserves_internal_return_path(self):
        state = create_oauth_state(self.secret, "/attendance?game=7", "fake-nonce")
        self.assertEqual(
            load_oauth_state(self.secret, state, "/attendance"),
            ("/attendance?game=7", "fake-nonce"),
        )

    def test_tampered_missing_and_malformed_states_fail_closed(self):
        valid = create_oauth_state(self.secret, "/attendance", "fake-nonce")
        cases = (None, "", f"{valid}tampered", TimestampSigner(self.secret).sign(b"bad"))
        for state in cases:
            with self.subTest(state=state):
                with self.assertRaises(InvalidOAuthState):
                    load_oauth_state(self.secret, state, "/attendance")

    def test_expired_state_fails_closed(self):
        state = create_oauth_state(self.secret, "/attendance", "fake-nonce")
        with patch("itsdangerous.timed.time.time", return_value=2_000_000_000):
            with self.assertRaises(InvalidOAuthState):
                load_oauth_state(self.secret, state, "/attendance", max_age=1)

    def test_return_path_rejects_external_and_ambiguous_targets(self):
        fallback = "/attendance"
        for candidate in (
            None,
            "",
            "https://attacker.example/path",
            "//attacker.example/path",
            "/\\attacker.example/path",
            "/%5c%5cattacker.example/path",
            "/%2fattacker.example/path",
            "/%252fattacker.example/path",
            "/path\x00suffix",
            "/path%0asuffix",
            "relative/path",
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual(safe_return_path(candidate, fallback), fallback)

        self.assertEqual(safe_return_path("/future-games?q=1", fallback), "/future-games?q=1")

    def test_return_path_category_uses_only_fixed_allowlisted_labels(self):
        cases = {
            "/attendance?sentinel-query=secret": "attendance",
            "/account": "account",
            "/game-roster/23?sentinel-query=secret": "roster",
            "/games/23/lineup-lab?sentinel-query=secret": "roster",
            "/game-roster/0": "default",
            "/future-games": "default",
            "https://sentinel.example/private": "default",
            None: "default",
        }
        for return_path, expected in cases.items():
            with self.subTest(return_path=return_path):
                self.assertEqual(return_path_category(return_path), expected)


if __name__ == "__main__":
    unittest.main()
