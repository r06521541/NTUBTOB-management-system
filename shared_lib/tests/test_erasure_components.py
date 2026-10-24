import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from shared_module.erasure_restore_binding import RestoreBindingCodec
from shared_module.portal_data.erasure_components import (
    build_erasure_components,
    build_erasure_intake_service,
)
from shared_module.portal_data.erasure_composition import TrustedErasurePlanBuilder
from shared_module.portal_data.erasure_plan_codec import ErasurePlanCodec
from sqlalchemy import create_engine


class ErasureComponentsTests(unittest.TestCase):
    def setUp(self):
        self.connect = Mock(side_effect=AssertionError("no database I/O"))
        self.engine = create_engine("postgresql+psycopg2://", creator=self.connect)
        self.addCleanup(self.engine.dispose)
        self.provider = Mock()
        self.restore = Mock()
        self.review = Mock()
        self.policy = Mock()
        self.clock = lambda: datetime(2035, 1, 1, tzinfo=timezone.utc)
        self.args = dict(
            engine=self.engine,
            receipt_key=b"R" * 32,
            proof_key=b"P" * 32,
            audience="fictional-erasure",
            proof_lifetime=timedelta(minutes=5),
            providers={"apple": (self.provider, "fictional-apple")},
            plan_builder=TrustedErasurePlanBuilder(
                review_source=self.review,
                policy_source=self.policy,
                restore_codec=RestoreBindingCodec(
                    namespace="00000000-0000-4000-8000-000000000003",
                    active_key="fake",
                    keys={"fake": b"B" * 32},
                ),
                provider_audiences={"apple": "fictional-apple"},
            ),
            active_plan_key_id="fake",
            plan_codecs={
                "fake": ErasurePlanCodec(
                    namespace="00000000-0000-4000-8000-000000000003", key=b"C" * 32
                )
            },
            prepare_provider=Mock(),
            restore_store=self.restore,
            clock=self.clock,
        )

    def test_fixed_pairs_share_engine_store_clock_and_receipt_key_without_io(self):
        bundle = build_erasure_components(**self.args)
        service = bundle.service
        for repo in (
            service.repository,
            service.restricted_repository,
            service.recovery_repository,
        ):
            self.assertIs(repo.engine, self.engine)
            self.assertIs(repo.clock, self.clock)
            self.assertEqual(repo._key, b"R" * 32)
        self.assertIs(service.repository.sealed_plan_store, bundle.plan_store)
        self.assertIs(
            service.restricted_repository.sealed_plan_store, bundle.plan_store
        )
        proofs = (
            service.proofs,
            service.cancellation_proofs,
            service.receipt_proofs,
            service.restricted_proofs,
            service.recovery_proofs,
        )
        self.assertEqual(len({proof._key for proof in proofs}), 5)
        for proof in proofs:
            self.assertIs(proof.clock, self.clock)
        self.connect.assert_not_called()
        self.provider.verify.assert_not_called()
        self.restore.put.assert_not_called()
        self.restore.read.assert_not_called()
        self.review.assert_not_called()
        self.policy.assert_not_called()

    def test_execution_only_uses_fixed_stored_plan_and_executors(self):
        bundle = build_erasure_components(**self.args)
        with patch.object(
            bundle.plan_store, "execute_stored", return_value="fixed"
        ) as execute:
            self.assertEqual(bundle.execute(job_id="fictional-job"), "fixed")
        execute.assert_called_once_with(
            self.engine,
            job_id="fictional-job",
            pending_executor=bundle.pending_executor,
            person_executor=bundle.person_executor,
        )
        with self.assertRaises(TypeError):
            bundle.execute(job_id="fictional-job", snapshot=object())

    def test_missing_or_ambiguous_configuration_fails_without_io(self):
        for changes in (
            {"receipt_key": b"P" * 32},
            {"proof_key": b"x"},
            {"providers": {}},
            {"plan_builder": Mock()},
            {"clock": None},
            {"restore_store": None},
        ):
            with self.subTest(changes=tuple(changes)):
                with self.assertRaisesRegex(ValueError, "^invalid_erasure_components$"):
                    build_erasure_components(**{**self.args, **changes})
        self.connect.assert_not_called()

    def test_intake_only_service_never_constructs_execution_or_custody_components(self):
        forbidden = (
            "ErasurePlanStore",
            "PendingIdentityFulfillment",
            "PersonFulfillment",
            "ErasureIntakeMaterializer",
            "AccountErasureRequestRepository",
            "RestrictedErasureRequestRepository",
        )
        patches = [
            patch(
                "shared_module.portal_data.erasure_components." + name,
                side_effect=AssertionError("not intake"),
            )
            for name in forbidden
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        args = {
            name: self.args[name]
            for name in (
                "engine",
                "receipt_key",
                "proof_key",
                "audience",
                "proof_lifetime",
                "providers",
                "clock",
            )
        }
        service = build_erasure_intake_service(**args)
        self.assertIs(service.repository, service.restricted_repository)
        self.assertIs(service.repository.engine, self.engine)
        self.assertEqual(service.recovery_repository._key, b"R" * 32)
        policy = service.repository.policy_source(
            requested_at=self.clock(), connection=Mock()
        )
        self.assertEqual(policy.fulfillment_due_at, self.clock() + timedelta(days=30))
        self.assertEqual(policy.receipt_expires_at, self.clock() + timedelta(days=180))
        self.assertEqual(policy.evidence_expires_at, policy.receipt_expires_at)
        self.review.assert_not_called()
        self.policy.assert_not_called()
        self.connect.assert_not_called()
        self.provider.verify.assert_not_called()

    def test_intake_only_factory_preserves_key_and_engine_validation(self):
        args = {
            name: self.args[name]
            for name in (
                "engine",
                "receipt_key",
                "proof_key",
                "audience",
                "proof_lifetime",
                "providers",
                "clock",
            )
        }
        for changes in (
            {"engine": Mock()},
            {"receipt_key": b"P" * 32},
            {"proof_key": b"short"},
            {"providers": {}},
            {"clock": None},
        ):
            with (
                self.subTest(fields=tuple(changes)),
                self.assertRaisesRegex(ValueError, "^invalid_erasure_components$"),
            ):
                build_erasure_intake_service(**{**args, **changes})
        self.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
