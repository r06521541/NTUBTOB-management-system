"""Default-unused receipt/fresh-provider verification for any owned identity.

Provider calls happen before this adapter. No login session, identity, Person or
mapping is created. The existing coordinator remains the only verification writer.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..erasure_receipt_proof import (
    FreshReceiptVerificationProof,
    ReceiptVerificationContext,
    ReceiptVerificationProofService,
)
from .erasure_cancellation import _connection, load_cancellation_context
from .erasure_intake_routing import receipt_table
from .erasure_verification import (
    ERASURE_VERIFICATION_PURPOSE,
    ErasureVerificationCoordinator,
    ErasureVerificationRejected,
    ErasureVerificationUnavailable,
    FreshErasureProof,
)


def load_receipt_verification_context(session, *, job_id, receipt_secret, clock):
    # Reuse the receipt/target generation/expiry reader, not cancellation authority.
    context = load_cancellation_context(
        session, job_id=job_id, receipt_secret=receipt_secret, clock=clock
    )
    if (
        session.connection().scalar(
            text(
                f"SELECT status FROM ntubtob.{receipt_table(session.connection(), job_id)} WHERE id=:id"
            ),
            {"id": job_id},
        )
        != "requested"
    ):
        raise ErasureVerificationRejected("requested_job_required")
    return ReceiptVerificationContext(
        context.job_id,
        context.target_kind,
        context.target_generation,
        context.requested_at,
    )


class ReceiptErasureVerificationCoordinator:
    def __init__(self, proofs):
        if type(proofs) is not ReceiptVerificationProofService:
            raise ErasureVerificationUnavailable("invalid_configuration")
        self.proofs = proofs

    def verify(self, session, *, assertion):
        try:
            connection = _connection(session)
            # Local decrypt after canonical locks; never provider I/O here.
            proof = self.proofs(assertion)
            if type(proof) is not FreshReceiptVerificationProof:
                raise ErasureVerificationRejected("invalid_receipt_proof")
            identity = (
                connection.execute(
                    text(
                        "SELECT id,person_id,account_generation FROM ntubtob.auth_identities "
                        "WHERE provider=:provider AND provider_subject=:subject FOR UPDATE"
                    ),
                    {"provider": proof.provider, "subject": proof.provider_subject},
                )
                .mappings()
                .one_or_none()
            )
            if identity is None:
                raise ErasureVerificationRejected("identity_scope_changed")
            bound = FreshErasureProof(
                job_id=proof.job_id,
                purpose=ERASURE_VERIFICATION_PURPOSE,
                audience=proof.audience,
                identity_id=identity["id"],
                provider=proof.provider,
                provider_subject=proof.provider_subject,
                identity_generation=str(identity["account_generation"]),
                target_kind=proof.target_kind,
                person_id=identity["person_id"],
                target_generation=proof.target_generation,
                authenticated_at=proof.authenticated_at,
                expires_at=proof.expires_at,
            )
            coordinator = ErasureVerificationCoordinator(
                verifier=lambda _: bound,
                audience=self.proofs.audience,
                max_proof_age=self.proofs.lifetime,
                clock=self.proofs.clock,
            )
            return coordinator.verify(session, job_id=proof.job_id, assertion=assertion)
        except SQLAlchemyError:
            raise ErasureVerificationUnavailable(
                "receipt_verification_unavailable"
            ) from None
