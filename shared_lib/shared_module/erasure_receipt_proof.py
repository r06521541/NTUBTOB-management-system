"""Receipt-bound verification proof, distinct from intent/cancellation/login.

Subject resolution deliberately follows provider proof inside the later locked DB
transaction. A receipt never selects an arbitrary identity or grants business access.
No runtime composition enables this codec. Provider verification runs outside DB.
"""

from dataclasses import dataclass
from datetime import datetime

from .erasure_cancellation_proof import CancellationProofService

RECEIPT_VERIFICATION_PURPOSE = "account_erasure_receipt_verification"


@dataclass(frozen=True, repr=False)
class ReceiptVerificationContext:
    job_id: str
    target_kind: str
    target_generation: str
    requested_at: datetime


@dataclass(frozen=True, repr=False)
class FreshReceiptVerificationProof:
    job_id: str
    target_kind: str
    target_generation: str
    provider: str
    provider_subject: str
    issued_at: datetime
    authenticated_at: datetime
    expires_at: datetime
    purpose: str
    audience: str


class ReceiptVerificationProofService(CancellationProofService):
    """Typed codec variant with independent derived key and authenticated domain.

    Invalid envelopes use the shared fixed CancellationProofRejected exception;
    service composition must translate it without echoing private payloads.
    """

    _domain = "account-erasure-receipt-verification"
    _purpose = RECEIPT_VERIFICATION_PURPOSE
    _context_type = ReceiptVerificationContext
    _proof_type = FreshReceiptVerificationProof
