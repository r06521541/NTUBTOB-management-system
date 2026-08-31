"""Compatibility export for the canonical shared Apple verifier."""

from shared_module.provider_verifiers import APPLE_ISSUER
from shared_module.provider_verifiers import APPLE_JWKS_URL as JWKS_URL
from shared_module.provider_verifiers import (
    AppleIdTokenVerifier,
    AppleJwkCache,
    AppleVerificationUnavailable,
)
from shared_module.provider_verifiers import (
    apple_jwks_urlopen_transport as urlopen_transport,
)

__all__ = [
    "APPLE_ISSUER",
    "JWKS_URL",
    "AppleIdTokenVerifier",
    "AppleJwkCache",
    "AppleVerificationUnavailable",
    "urlopen_transport",
]
