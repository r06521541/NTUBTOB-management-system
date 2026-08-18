import unittest
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_module.mobile_api import AuthenticationError

from apps.mobile_api.line_verifier import LineJwtVerifier


class LineJwtVerifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public_key = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cls.verifier = LineJwtVerifier(public_key.decode("ascii"))

    def token(self, **overrides):
        now = datetime.now(timezone.utc)
        claims = {
            "iss": "https://access.line.me",
            "aud": "fake-native-client",
            "sub": "fake-line-subject",
            "nonce": "fake-nonce-123456",
            "exp": now + timedelta(minutes=5),
        }
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm="RS256"), now

    def test_valid_signature_audience_nonce_and_expiry(self):
        token, now = self.token()
        result = self.verifier.verify(
            token, "fake-native-client", "fake-nonce-123456", now
        )
        self.assertEqual(result.subject, "fake-line-subject")

    def test_wrong_audience_nonce_expiry_and_signature_fail_closed(self):
        cases = []
        token, now = self.token(aud="wrong")
        cases.append((token, "fake-nonce-123456", now))
        token, now = self.token()
        cases.append((token, "wrong-nonce-1234", now))
        token, now = self.token(exp=now - timedelta(seconds=1))
        cases.append((token, "fake-nonce-123456", now))
        cases.append((token + "corrupt", "fake-nonce-123456", now))
        for token, nonce, checked_at in cases:
            with self.subTest(nonce=nonce):
                with self.assertRaises(AuthenticationError):
                    self.verifier.verify(token, "fake-native-client", nonce, checked_at)


if __name__ == "__main__":
    unittest.main()
