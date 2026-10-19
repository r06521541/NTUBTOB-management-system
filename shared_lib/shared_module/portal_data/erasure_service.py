"""Optional linked-account request/challenge/verification composition.

No normal bootstrap enables this service. Provider verification occurs before the
mutation transaction; the coordinator repeats proof and generation validation.
Optional restricted requests create only intents after fresh provider proof;
full access blocking and deletion fulfillment remain enablement prerequisites.
"""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..erasure_cancellation_proof import CancellationProofRejected
from ..erasure_restricted_proof import RestrictedErasureProofRejected
from ..mobile_api import (
    AuthenticationError,
    InvalidArgument,
    MobileApiError,
    MobilePrincipal,
)
from .erasure_cancellation import (
    ErasureCancellationCoordinator,
    ErasureCancellationRejected,
    ErasureCancellationUnavailable,
    load_cancellation_context,
)
from .erasure_context import (
    ErasureContextRejected,
    ErasureContextUnavailable,
    load_erasure_verification_context,
)
from .erasure_receipt import (
    ErasureReceiptRejected,
    ErasureReceiptUnavailable,
    load_erasure_receipt,
)
from .erasure_receipt_recovery import (
    ReceiptRecoveryRejected,
    ReceiptRecoveryUnavailable,
    RecoveredErasureReceipt,
)
from .erasure_receipt_verification import (
    ReceiptErasureVerificationCoordinator,
    load_receipt_verification_context,
)
from .erasure_request import ErasureRequestRejected, ErasureRequestUnavailable
from .erasure_verification import (
    ErasureVerificationCoordinator,
    ErasureVerificationRejected,
    ErasureVerificationUnavailable,
)


class AccountErasureUnavailable(MobileApiError):
    retryable = False

    def __init__(self):
        super().__init__("account erasure service unavailable; reconcile before retry")


class AccountErasureService:
    def __init__(
        self,
        repository,
        proof_service,
        *,
        cancellation_proofs=None,
        restricted_proofs=None,
        restricted_repository=None,
        receipt_proofs=None,
        recovery_proofs=None,
        recovery_repository=None,
    ):
        if (restricted_proofs is None) != (restricted_repository is None):
            raise ValueError(
                "restricted erasure dependencies must be configured together"
            )
        if (recovery_proofs is None) != (recovery_repository is None):
            raise ValueError(
                "receipt recovery dependencies must be configured together"
            )
        self.repository, self.proofs = repository, proof_service
        self.recovery_proofs = recovery_proofs
        self.recovery_repository = recovery_repository
        self.receipt_proofs = receipt_proofs
        self.receipt_coordinator = (
            None
            if receipt_proofs is None
            else ReceiptErasureVerificationCoordinator(receipt_proofs)
        )
        self.restricted_proofs = restricted_proofs
        self.restricted_repository = restricted_repository
        self.cancellation_proofs = cancellation_proofs
        self.cancellation_coordinator = (
            None
            if cancellation_proofs is None
            else ErasureCancellationCoordinator(
                verifier=cancellation_proofs,
                audience=cancellation_proofs.audience,
                max_proof_age=cancellation_proofs.lifetime,
                clock=cancellation_proofs.clock,
            )
        )
        self.coordinator = ErasureVerificationCoordinator(
            verifier=proof_service,
            audience=proof_service.audience,
            max_proof_age=proof_service.lifetime,
            clock=proof_service.clock,
        )

    def recovery_challenge(self, provider):
        """Default-off dedicated recovery challenge; no account/receipt lookup."""
        if self.recovery_proofs is None or self.recovery_repository is None:
            raise AccountErasureUnavailable()
        try:
            return self.recovery_proofs.begin(provider)
        except RestrictedErasureProofRejected:
            raise AuthenticationError("account erasure recovery rejected") from None
        except Exception:
            raise AccountErasureUnavailable() from None

    def recover_receipt(self, challenge_credential, provider_assertion, confirmed):
        """Recover an existing receipt, never request/verify/cancel or extend it."""
        if confirmed is not True:
            raise InvalidArgument("explicit confirmation required")
        if self.recovery_proofs is None or self.recovery_repository is None:
            raise AccountErasureUnavailable()
        try:
            # No service Session: provider I/O finishes before the read-only
            # repository opens its transaction and repeats proof/scope checks.
            assertion = self.recovery_proofs.authenticate(
                challenge_credential, provider_assertion
            )
            receipt = self.recovery_repository.recover(assertion)
            if type(receipt) is not RecoveredErasureReceipt or receipt.status not in {
                "requested",
                "verified",
                "processing",
                "needs_attention",
            }:
                raise ReceiptRecoveryUnavailable("recovery_result_unavailable")
            return {
                "id": receipt.job_id,
                "status": receipt.status,
                "receipt_secret": receipt.receipt_secret,
                "requested_at": receipt.requested_at.isoformat(),
                "updated_at": receipt.updated_at.isoformat(),
                "receipt_expires_at": receipt.receipt_expires_at.isoformat(),
            }
        except (RestrictedErasureProofRejected, ReceiptRecoveryRejected):
            # Missing, detached, stale, expired and incorrect credentials share
            # one public error; never expose target existence or provider data.
            raise AuthenticationError("account erasure recovery rejected") from None
        except Exception:
            raise AccountErasureUnavailable() from None

    def restricted_challenge(self, provider):
        if self.restricted_proofs is None or self.restricted_repository is None:
            raise AccountErasureUnavailable()
        try:
            return self.restricted_proofs.begin(provider)
        except RestrictedErasureProofRejected:
            raise AuthenticationError("account erasure request rejected") from None

    def request_restricted(self, challenge_credential, provider_assertion, confirmed):
        if confirmed is not True:
            raise InvalidArgument("explicit confirmation required")
        if self.restricted_proofs is None or self.restricted_repository is None:
            raise AccountErasureUnavailable()
        try:
            # No Session is opened here: provider I/O precedes repository mutation.
            assertion = self.restricted_proofs.authenticate(
                challenge_credential, provider_assertion
            )
            receipt = self.restricted_repository.request_restricted(assertion)
        except (RestrictedErasureProofRejected, ErasureRequestRejected):
            raise AuthenticationError("account erasure request rejected") from None
        except ErasureRequestUnavailable:
            raise AccountErasureUnavailable() from None
        return {
            "id": receipt.job_id,
            "status": "requested",
            "receipt_secret": receipt.receipt_secret,
            "requested_at": receipt.requested_at.isoformat(),
        }

    def receipt_challenge(self, job_id, receipt_secret, provider):
        if self.receipt_proofs is None:
            raise AccountErasureUnavailable()
        try:
            with Session(self.repository.engine) as session, session.begin():
                context = load_receipt_verification_context(
                    session,
                    job_id=job_id,
                    receipt_secret=receipt_secret,
                    clock=self.receipt_proofs.clock,
                )
            return self.receipt_proofs.begin(context, provider)
        except (
            CancellationProofRejected,
            ErasureCancellationRejected,
            ErasureVerificationRejected,
        ):
            raise AuthenticationError("account erasure verification rejected") from None
        except (SQLAlchemyError, ErasureCancellationUnavailable):
            raise AccountErasureUnavailable() from None

    def verify_receipt(self, challenge_credential, provider_assertion, confirmed):
        if confirmed is not True:
            raise InvalidArgument("explicit confirmation required")
        if self.receipt_proofs is None or self.receipt_coordinator is None:
            raise AccountErasureUnavailable()
        try:
            # Provider proof completes before opening a database transaction.
            assertion = self.receipt_proofs.authenticate(
                challenge_credential, provider_assertion
            )
            with Session(self.repository.engine) as session, session.begin():
                result = self.receipt_coordinator.verify(session, assertion=assertion)
            return {"id": result.job_id, "status": "verified"}
        except (
            CancellationProofRejected,
            ErasureCancellationRejected,
            ErasureVerificationRejected,
        ):
            raise AuthenticationError("account erasure verification rejected") from None
        except (
            SQLAlchemyError,
            ErasureCancellationUnavailable,
            ErasureVerificationUnavailable,
        ):
            raise AccountErasureUnavailable() from None

    def pending_challenge(self, job_id, receipt_secret):
        """A pending receipt selects its identity; it does not authorize erasure."""
        try:
            with Session(self.repository.engine) as session, session.begin():
                context = load_erasure_verification_context(
                    session,
                    job_id=job_id,
                    receipt_secret=receipt_secret,
                    clock=self.proofs.clock,
                )
            return self.proofs.begin(context)
        except (ErasureContextRejected, ErasureVerificationRejected):
            raise AuthenticationError("account erasure verification rejected") from None
        except (SQLAlchemyError, ErasureContextUnavailable):
            raise AccountErasureUnavailable() from None

    def cancellation_challenge(self, job_id, receipt_secret, provider):
        if self.cancellation_proofs is None:
            raise AccountErasureUnavailable()
        try:
            with Session(self.repository.engine) as session, session.begin():
                context = load_cancellation_context(
                    session,
                    job_id=job_id,
                    receipt_secret=receipt_secret,
                    clock=self.cancellation_proofs.clock,
                )
            return self.cancellation_proofs.begin(context, provider)
        except (CancellationProofRejected, ErasureCancellationRejected):
            raise AuthenticationError("account erasure cancellation rejected") from None
        except (SQLAlchemyError, ErasureCancellationUnavailable):
            raise AccountErasureUnavailable() from None

    def cancel(self, challenge_credential, provider_assertion, confirmed):
        if confirmed is not True:
            raise InvalidArgument("explicit confirmation required")
        if self.cancellation_proofs is None or self.cancellation_coordinator is None:
            raise AccountErasureUnavailable()
        try:
            assertion = self.cancellation_proofs.authenticate(
                challenge_credential, provider_assertion
            )
            proof = self.cancellation_proofs(assertion)
            with Session(self.repository.engine) as session, session.begin():
                result = self.cancellation_coordinator.cancel(
                    session, job_id=proof.job_id, assertion=assertion
                )
            return {"id": result.job_id, "status": "cancelled"}
        except (CancellationProofRejected, ErasureCancellationRejected):
            raise AuthenticationError("account erasure cancellation rejected") from None
        except (SQLAlchemyError, ErasureCancellationUnavailable):
            raise AccountErasureUnavailable() from None

    def request(self, principal: MobilePrincipal, confirmed: object) -> dict:
        if confirmed is not True:
            raise InvalidArgument("explicit confirmation required")
        try:
            receipt = self.repository.request(principal)
        except ErasureRequestRejected:
            raise AuthenticationError("account erasure request rejected") from None
        except ErasureRequestUnavailable:
            raise AccountErasureUnavailable() from None
        return {
            "id": receipt.job_id,
            "status": "requested",
            "receipt_secret": receipt.receipt_secret,
            "requested_at": receipt.requested_at.isoformat(),
        }

    def status(self, job_id: str, receipt_secret: str) -> dict:
        try:
            with Session(self.repository.engine) as session, session.begin():
                receipt = load_erasure_receipt(
                    session,
                    job_id=job_id,
                    receipt_secret=receipt_secret,
                    clock=self.proofs.clock,
                )
            return {
                "id": receipt.job_id,
                "status": receipt.status,
                "requested_at": receipt.requested_at.isoformat(),
                "updated_at": receipt.updated_at.isoformat(),
            }
        except ErasureReceiptRejected:
            raise AuthenticationError("account erasure receipt unavailable") from None
        except (SQLAlchemyError, ErasureReceiptUnavailable):
            raise AccountErasureUnavailable() from None

    def challenge(
        self, principal: MobilePrincipal, job_id: str, receipt_secret: str
    ) -> dict:
        if type(principal) is not MobilePrincipal:
            raise AuthenticationError("account erasure verification rejected")
        try:
            with Session(self.repository.engine) as session, session.begin():
                context = load_erasure_verification_context(
                    session,
                    job_id=job_id,
                    receipt_secret=receipt_secret,
                    identity_id=principal.identity_id,
                    clock=self.proofs.clock,
                )
                if context.person_id != principal.person_id:
                    raise AuthenticationError("account erasure verification rejected")
            return self.proofs.begin(context)
        except (ErasureContextRejected, ErasureVerificationRejected):
            raise AuthenticationError("account erasure verification rejected") from None
        except (SQLAlchemyError, ErasureContextUnavailable):
            raise AccountErasureUnavailable() from None

    def verify(self, challenge_credential: str, provider_assertion: str) -> dict:
        try:
            # Potential provider network I/O MUST finish before opening this Session.
            assertion = self.proofs.authenticate(
                challenge_credential, provider_assertion
            )
            proof = self.proofs(assertion)
            with Session(self.repository.engine) as session, session.begin():
                result = self.coordinator.verify(
                    session, job_id=proof.job_id, assertion=assertion
                )
            return {"id": result.job_id, "status": "verified"}
        except ErasureVerificationRejected:
            raise AuthenticationError("account erasure verification rejected") from None
        except (SQLAlchemyError, ErasureVerificationUnavailable):
            # This includes a lost commit response. No automatic mutation retry.
            raise AccountErasureUnavailable() from None
