"""Default-unused receipt recovery proof, distinct from request/verify/cancel.

The existing restricted-proof framing generates the random nonce and validates
the provider assertion outside DB transactions. Its server-generated attempt UUID
is only envelope entropy here: it creates no durable request/attempt or job binding.
No fake job context, target generation claim, session or identity is created.
Only the separately locked repository can resolve a live target and original job.

The final callable only decrypts locally. Proofs may replay within their original
short window; they are not single-use and cannot recover a deleted target's lost
receipt. No API/native/runtime composition enables this codec. Boundary failures
use the existing fixed RestrictedErasureProofRejected, without private diagnostics.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from .erasure_restricted_proof import ErasureRestrictedProofService

RECEIPT_RECOVERY_PURPOSE = "account_erasure_receipt_recovery"


@dataclass(frozen=True, repr=False)
class FreshReceiptRecoveryProof:
    """Trusted local verifier output, never client-deserialized authorization.

    No generation is claimed at challenge time. The repository resolves the current
    identity only after proof, then checks its timestamps and exact locked job scope.
    issued_at always refers to the original server challenge, not authentication.
    """

    provider: str
    provider_subject: str
    issued_at: datetime
    authenticated_at: datetime
    expires_at: datetime
    purpose: str
    audience: str


class ErasureReceiptRecoveryProofService(ErasureRestrictedProofService):
    """Internal fixed-purpose variant; old purpose/key/AAD/DTO remain unchanged."""

    _purpose = RECEIPT_RECOVERY_PURPOSE
    _key_domain = b"account-erasure-receipt-recovery-aead-v1"
    _aad_prefix = "account-erasure-receipt-recovery:"

    def _proof_factory(self, payload, *, issued, authenticated, expiry):
        return FreshReceiptRecoveryProof(
            provider=payload["provider"],
            provider_subject=payload["provider_subject"],
            issued_at=issued,
            authenticated_at=authenticated,
            expires_at=expiry,
            purpose=payload["purpose"],
            audience=payload["audience"],
        )

    def __call__(self, verified_credential: str) -> FreshReceiptRecoveryProof:
        return cast(FreshReceiptRecoveryProof, super().__call__(verified_credential))
