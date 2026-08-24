"""Compatibility export for the canonical shared Google verifier."""

from shared_module.provider_verifiers import (
    GOOGLE_ISSUERS,
    GoogleIdTokenVerifier,
    verify_with_google_auth,
)

__all__ = ["GOOGLE_ISSUERS", "GoogleIdTokenVerifier", "verify_with_google_auth"]
