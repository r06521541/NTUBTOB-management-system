"""Explicit erasure assembly; intake is separate from internal fulfillment.

Construction performs no I/O. Trusted callers must independently establish all
caller guards/readiness, authorized review, key custody, retention and provider /
restore ports before enabling fulfillment. The intake-only factory needs no
review/execution ports. Neither factory changes flags, first-login policy, public
routes, scheduler, permissions or schema acceptance.
"""

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from ..erasure_cancellation_proof import CancellationProofService
from ..erasure_proof import ErasureProofService
from ..erasure_receipt_proof import ReceiptVerificationProofService
from ..erasure_recovery_proof import ErasureReceiptRecoveryProofService
from ..erasure_restricted_proof import ErasureRestrictedProofService
from .erasure_composition import ErasurePlanPolicy, TrustedErasurePlanBuilder
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


def _validate_configuration(engine, receipt_key, proof_key, providers, clock):
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
        or not callable(clock)
    ):
        raise ValueError()


def _proof_services(proof_key, audience, proof_lifetime, providers, clock):
    options = dict(
        audience=audience,
        lifetime=proof_lifetime,
        providers=dict(providers),
        clock=clock,
    )
    return dict(
        proof_service=ErasureProofService(proof_key, **options),
        cancellation_proofs=CancellationProofService(proof_key, **options),
        receipt_proofs=ReceiptVerificationProofService(proof_key, **options),
        restricted_proofs=ErasureRestrictedProofService(proof_key, **options),
        recovery_proofs=ErasureReceiptRecoveryProofService(proof_key, **options),
    )


def _service(
    repository, restricted_repository, proofs, engine, receipt_key, audience, clock
):
    recovery_repository = ReceiptRecoveryRepository(
        engine,
        receipt_key,
        verifier=proofs["recovery_proofs"],
        audience=audience,
        clock=clock,
    )
    return AccountErasureService(
        repository,
        restricted_repository=restricted_repository,
        recovery_repository=recovery_repository,
        **proofs,
    )


def _initial_policy(*, requested_at, **_):
    return ErasurePlanPolicy.initial_request(requested_at)


def build_erasure_intake_service(
    *, engine, receipt_key, proof_key, audience, proof_lifetime, providers, clock
):
    """Intake/receipt/fresh-proof only: no review, plan custody or execution ports.

    Runtime opt-in and configuration validation belong to the caller. Initial
    policy is the approved request-time factory, never request-time human review.
    Materialization and fulfillment require a separately authorized composition.
    """
    try:
        _validate_configuration(engine, receipt_key, proof_key, providers, clock)
        proofs = _proof_services(proof_key, audience, proof_lifetime, providers, clock)
        repository = ErasureIntakeRepository(
            engine,
            receipt_key,
            policy_source=_initial_policy,
            verifier=proofs["restricted_proofs"],
            audience=audience,
            clock=clock,
        )
        return _service(
            repository, repository, proofs, engine, receipt_key, audience, clock
        )
    except Exception:
        raise ValueError("invalid_erasure_components") from None


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
        _validate_configuration(engine, receipt_key, proof_key, providers, clock)
        if (
            type(plan_builder) is not TrustedErasurePlanBuilder
            or type(intake_enabled) is not bool
        ):
            raise ValueError()
        proofs = _proof_services(proof_key, audience, proof_lifetime, providers, clock)
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
            verifier=proofs["restricted_proofs"],
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
                verifier=proofs["restricted_proofs"],
                audience=audience,
                clock=clock,
            )
            materializer = ErasureIntakeMaterializer(
                engine, plan_builder, store, clock=clock
            )
        service = _service(
            repository,
            restricted_repository,
            proofs,
            engine,
            receipt_key,
            audience,
            clock,
        )
        pending = PendingIdentityFulfillment(
            engine, prepare_provider, restore_store, clock=clock
        )
        person = PersonFulfillment(engine, prepare_provider, restore_store, clock=clock)
        return ErasureComponents(service, store, pending, person, materializer)
    except Exception:
        raise ValueError("invalid_erasure_components") from None
