"""Explicit, default-unused erasure assembly; not a runtime enablement switch.

Construction performs no I/O. Trusted callers must independently establish all
caller guards/readiness, authorized review, key custody, retention and provider /
restore ports before enabling anything. This factory does not change bootstrap,
first-login policy, public routes, scheduler, permissions or schema acceptance.
"""

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from ..erasure_cancellation_proof import CancellationProofService
from ..erasure_proof import ErasureProofService
from ..erasure_receipt_proof import ReceiptVerificationProofService
from ..erasure_recovery_proof import ErasureReceiptRecoveryProofService
from ..erasure_restricted_proof import ErasureRestrictedProofService
from .erasure_composition import TrustedErasurePlanBuilder
from .erasure_fulfillment import PendingIdentityFulfillment
from .erasure_intake import ErasureIntakeMaterializer, ErasureIntakeRepository
from .erasure_person_fulfillment import PersonFulfillment
from .erasure_plan_store import ErasurePlanStore
from .erasure_receipt_recovery import ReceiptRecoveryRepository
from .erasure_request import AccountErasureRequestRepository
from .erasure_restricted_request import RestrictedErasureRequestRepository
from .erasure_service import AccountErasureService


@dataclass(frozen=True, repr=False)
class ErasureComponents:
    service: AccountErasureService
    plan_store: ErasurePlanStore
    pending_executor: PendingIdentityFulfillment
    person_executor: PersonFulfillment
    intake_materializer: ErasureIntakeMaterializer | None = None

    def materialize(self, *, job_id, identity_id):
        """Internal authorized review operation, never a public receipt mutation."""
        if self.intake_materializer is None:
            raise ValueError("intake_not_enabled")
        return self.intake_materializer.materialize(
            job_id=job_id, identity_id=identity_id
        )

    def execute(self, *, job_id):
        """Internal authorized-job dispatch; never expose as a public job-id API."""
        return self.plan_store.execute_stored(
            self.service.repository.engine,
            job_id=job_id,
            pending_executor=self.pending_executor,
            person_executor=self.person_executor,
        )


def build_erasure_components(
    *,
    engine,
    receipt_key,
    proof_key,
    audience,
    proof_lifetime,
    providers,
    plan_builder,
    active_plan_key_id,
    plan_codecs,
    prepare_provider,
    restore_store,
    clock,
    intake_enabled=False,
):
    """All inputs explicit. Purpose-specific proof services keep existing domains."""
    try:
        if (
            not isinstance(engine, Engine)
            or engine.dialect.name != "postgresql"
            or type(receipt_key) is not bytes
            or len(receipt_key) < 32
            or type(proof_key) is not bytes
            or len(proof_key) < 32
            or receipt_key == proof_key
            or type(providers) is not dict
            or not providers
            or type(plan_builder) is not TrustedErasurePlanBuilder
            or not callable(clock)
            or type(intake_enabled) is not bool
        ):
            raise ValueError()
        options = dict(
            audience=audience,
            lifetime=proof_lifetime,
            providers=dict(providers),
            clock=clock,
        )
        verification = ErasureProofService(proof_key, **options)
        cancellation = CancellationProofService(proof_key, **options)
        receipt = ReceiptVerificationProofService(proof_key, **options)
        restricted = ErasureRestrictedProofService(proof_key, **options)
        recovery = ErasureReceiptRecoveryProofService(proof_key, **options)
        store = ErasurePlanStore(
            active_key_id=active_plan_key_id, codecs=plan_codecs, clock=clock
        )
        repository = AccountErasureRequestRepository(
            engine, receipt_key, plan_builder, clock, sealed_plan_store=store
        )
        restricted_repository = RestrictedErasureRequestRepository(
            engine,
            receipt_key,
            plan_builder,
            verifier=restricted,
            audience=audience,
            clock=clock,
            sealed_plan_store=store,
        )
        materializer = None
        if intake_enabled:
            repository = restricted_repository = ErasureIntakeRepository(
                engine,
                receipt_key,
                policy_source=plan_builder.intake_policy,
                verifier=restricted,
                audience=audience,
                clock=clock,
            )
            materializer = ErasureIntakeMaterializer(
                engine, plan_builder, store, clock=clock
            )
        recovery_repository = ReceiptRecoveryRepository(
            engine, receipt_key, verifier=recovery, audience=audience, clock=clock
        )
        service = AccountErasureService(
            repository,
            verification,
            cancellation_proofs=cancellation,
            restricted_proofs=restricted,
            restricted_repository=restricted_repository,
            receipt_proofs=receipt,
            recovery_proofs=recovery,
            recovery_repository=recovery_repository,
        )
        pending = PendingIdentityFulfillment(
            engine, prepare_provider, restore_store, clock=clock
        )
        person = PersonFulfillment(engine, prepare_provider, restore_store, clock=clock)
        return ErasureComponents(service, store, pending, person, materializer)
    except Exception:
        raise ValueError("invalid_erasure_components") from None
