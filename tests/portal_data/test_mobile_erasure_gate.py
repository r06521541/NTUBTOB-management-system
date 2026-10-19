"""Actual opt-in mobile gate against an explicitly isolated fictional database."""

import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import (
    AccountUnavailable,
    HmacAccessTokenCodec,
    IdentityPending,
)
from shared_module.portal_data import mobile_repository as module
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data.test_mobile_api_foundation import FakeCipher


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL required")
class MobileErasureGatePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ledger.ErasureLedgerPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.connection = self.fixture.connection
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET provider='google', "
                "person_id=:person,status='linked' WHERE id=:identity"
            ),
            {"person": self.fixture.person, "identity": self.fixture.identity},
        )
        self.subject = self.connection.scalar(
            text("SELECT provider_subject FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.fixture.identity},
        )
        self.repo = module.MobileRepository(self.engine, erasure_checks_enabled=True)
        # Isolate lifecycle preflight (unchanged here); actual mobile SQL and guard
        # use the real transaction. This is not full runtime composition evidence.
        self.repo.lifecycle = MagicMock()
        self.resolved = SimpleNamespace(
            identity=SimpleNamespace(id=self.fixture.identity),
            person=SimpleNamespace(
                id=self.fixture.person,
                access_level="basic",
                display_name="Fictional ledger person",
            ),
        )
        self.repo.lifecycle.resolve_principal.return_value = self.resolved
        self.repo.lifecycle.resolve_principal_by_ids.return_value = self.resolved
        self.session_patch = patch.object(
            module,
            "Session",
            side_effect=lambda *_: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        )
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    def tearDown(self):
        self.fixture.tearDown()

    def exchange(self, suffix="a"):
        return self.repo.exchange(
            provider="google",
            subject=self.subject,
            assertion_hash=suffix * 64,
            login_attempt_hash=suffix * 64,
            installation_id_hash="c" * 64,
            platform="ios",
            refresh_hash=suffix * 64,
            now=ledger.NOW,
        )

    def verify_job(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        return job

    def test_requested_allows_exchange_but_verified_denies_new_and_existing_access(
        self,
    ):
        job = self.fixture.job()
        principal = self.exchange()
        self.assertIsNotNone(
            self.repo.principal(
                principal.session_id,
                principal.person_id,
                principal.identity_id,
                principal.access_epoch,
                ledger.NOW,
            )
        )
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with self.assertRaises(AccountUnavailable):
            self.exchange("b")
        with self.assertRaises(AccountUnavailable):
            self.repo.principal(
                principal.session_id,
                principal.person_id,
                principal.identity_id,
                principal.access_epoch,
                ledger.NOW,
            )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.mobile_sessions WHERE person_id=:id"
                ),
                {"id": self.fixture.person},
            ),
            1,
        )

    def test_verified_blocks_refresh_and_saved_successor_but_logout_still_revokes(self):
        principal = self.exchange()
        values = dict(
            refresh_hash="a" * 64,
            attempt_id_hash="e" * 64,
            request_hash="f" * 64,
            installation_id_hash="c" * 64,
            successor_hash="1" * 64,
            successor="fictional-successor",
            cipher=FakeCipher(),
            token_codec=HmacAccessTokenCodec(b"x" * 32),
            now=ledger.NOW + timedelta(seconds=1),
        )
        self.assertFalse(self.repo.rotate(**values)[1])
        self.assertTrue(self.repo.rotate(**values)[1])
        self.verify_job()
        with self.assertRaises(AccountUnavailable):
            self.repo.rotate(**values)
        with self.assertRaises(AccountUnavailable):
            self.repo.rotate(
                **{**values, "refresh_hash": "1" * 64, "attempt_id_hash": "2" * 64}
            )
        self.repo.logout(principal.session_id, ledger.NOW + timedelta(seconds=2))
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.mobile_sessions WHERE id=:id"),
                {"id": principal.session_id},
            ),
            "revoked",
        )

    def test_other_person_job_does_not_block(self):
        job = self.fixture.job(person_id=self.fixture.other_person)
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        self.assertEqual(self.exchange().person_id, self.fixture.person)

    def test_verified_blocks_existing_provider_candidates(self):
        self.verify_job()
        for provider in ("google", "apple"):
            with self.subTest(provider=provider):
                self.connection.execute(
                    text(
                        "UPDATE ntubtob.auth_identities SET provider=:provider WHERE id=:id"
                    ),
                    {"provider": provider, "id": self.fixture.identity},
                )
                with self.assertRaises(AccountUnavailable):
                    getattr(self.repo, f"ensure_{provider}_link_candidate")(
                        self.subject, "fictional-erasure-candidate", ledger.NOW
                    )

    def test_notification_expansion_filters_verified_and_publish_actor_denied(self):
        audience = {"type": "individual", "person_id": self.fixture.person}
        job = self.fixture.job()
        self.assertEqual(
            self.repo.expand_notification_recipients(audience, ledger.NOW),
            (self.fixture.person,),
        )
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        self.assertEqual(
            self.repo.expand_notification_recipients(audience, ledger.NOW), ()
        )
        self.assertEqual(
            self.repo.expand_notification_recipients(
                {"type": "individual", "person_id": self.fixture.other_person},
                ledger.NOW,
            ),
            (self.fixture.other_person,),
        )
        with self.assertRaises(AccountUnavailable):
            self.repo.commit_notification_publish(actor_person_id=self.fixture.person)
        self.repo.erasure_checks_enabled = False
        self.assertEqual(
            self.repo.expand_notification_recipients(audience, ledger.NOW),
            (self.fixture.person,),
        )

    def test_verified_blocks_completed_idempotent_replay_without_callback(self):
        principal = self.exchange()
        mutation = MagicMock(return_value=(200, {"fictional": True}))
        values = dict(
            session_id=principal.session_id,
            person_id=self.fixture.person,
            method="POST",
            route="/fictional-erasure-replay",
            key_hash="7" * 64,
            request_hash="8" * 64,
            now=ledger.NOW,
            mutation=mutation,
        )
        self.assertFalse(self.repo.idempotent(**values)[2])
        self.assertTrue(self.repo.idempotent(**values)[2])
        mutation.assert_called_once_with()
        self.verify_job()
        with self.assertRaises(AccountUnavailable):
            self.repo.idempotent(**values)
        mutation.assert_called_once_with()

    def test_verified_blocks_notification_reads_writes_and_device_registration(self):
        self.verify_job()
        person = self.fixture.person
        for name, args, kwargs in (
            ("notification_page", (person, ledger.NOW, None, 10, False), {}),
            ("notification_detail", (person, 1, ledger.NOW), {}),
            ("notification_unread_count", (person, ledger.NOW), {}),
            ("mark_notification_read", (person, 1, ledger.NOW), {}),
            ("mark_all_notifications_read", (person, ledger.NOW), {}),
            ("register_fake_device", (), {"person_id": person}),
        ):
            with self.subTest(entry=name):
                with self.assertRaises(AccountUnavailable):
                    getattr(self.repo, name)(*args, **kwargs)

    def test_verified_pending_blocks_late_apple_credential_completion(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET provider='apple',person_id=NULL,status='pending' WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        )
        job = self.fixture.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.fixture.identity,
        )
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with self.assertRaises(AccountUnavailable):
            self.repo.complete_apple_code_for_pending(identity_id=self.fixture.identity)

    def test_pending_identity_job_blocks_before_pending_response(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=NULL,status='pending' WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        )
        job = self.fixture.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.fixture.identity,
        )
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        self.repo.lifecycle.resolve_principal.return_value = None
        with self.assertRaises(AccountUnavailable):
            self.exchange()

    def test_pending_identity_without_verified_job_still_returns_pending(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=NULL,status='pending' WHERE id=:id"
            ),
            {"id": self.fixture.identity},
        )
        self.repo.lifecycle.resolve_principal.return_value = None
        self.fixture.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.fixture.identity,
        )
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.repo.erasure_checks_enabled = enabled
                with self.assertRaises(IdentityPending):
                    self.exchange()
