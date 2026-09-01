from __future__ import annotations

import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

SHARED_LIB_ROOT = Path(__file__).resolve().parents[2] / "shared_lib"
if str(SHARED_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_LIB_ROOT))

from alembic import command
from alembic.config import Config
from shared_module.identity_linking import (
    IdentityLinkConflict,
    IdentityLinkProofCodec,
    IdentityLinkService,
)
from shared_module.mobile_api import Conflict, HmacAccessTokenCodec
from shared_module.portal_data.domain import ConflictError
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository
from shared_module.portal_data.mobile_repository import MobileRepository
from shared_module.portal_data.models import PortalDataBase
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)
NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


class FakeCipher:
    def seal(self, value):
        return b"fake:" + value[::-1]

    def open(self, value):
        return value.removeprefix(b"fake:")[::-1]


class CapturingAccessTokenCodec:
    def __init__(self):
        self.principal = None

    def issue(self, principal, _now):
        self.principal = principal
        return "obvious-fake-access", 900


@unittest.skipUnless(DATABASE_URL, "portal-data PostgreSQL URL is required")
class MobileApiFoundationIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        setup_legacy_fixture()
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", DATABASE_URL)
        command.upgrade(config, "0010_apple_provider_lifecycle")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE ntubtob.mobile_auth_exchanges, "
                    "ntubtob.mobile_idempotency_records, "
                    "ntubtob.mobile_refresh_attempts, "
                    "ntubtob.mobile_refresh_tokens, ntubtob.mobile_sessions "
                    "RESTART IDENTITY CASCADE"
                )
            )
            person_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people "
                    "(display_name, portal_access_level, portal_status, version, created_at, updated_at) "
                    "VALUES ('Mobile Test', 'basic', 'active', 1, :now, :now) RETURNING id"
                ),
                {"now": NOW},
            )
            identity_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('line', :subject, :person, 'linked', :now, :now) RETURNING id"
                ),
                {
                    "subject": f"mobile-{self.id()}",
                    "person": person_id,
                    "now": NOW,
                },
            )
            admin_member_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.members (name, person_id) "
                    "VALUES ('Mobile Test Admin', :person) RETURNING id"
                ),
                {"person": person_id},
            )
        self.person_id, self.identity_id = person_id, identity_id
        self.admin_member_id = admin_member_id
        self.repository = MobileRepository(self.engine)
        self.admin_lifecycle = IdentityLifecycleRepository(
            self.engine, admin_member_ids=(admin_member_id,)
        )

    def _google_candidate_proofs(self, suffix="one"):
        candidate_id = self.repository.ensure_google_link_candidate(
            f"google-candidate-{suffix}-{self.id()}",
            f"pending-{suffix}",
            NOW,
        )["identity_id"]
        codec = IdentityLinkProofCodec(b"l" * 32)
        candidate = codec.verify_candidate(
            codec.issue_candidate(
                identity_id=candidate_id,
                provider="google",
                identity_updated_at=NOW,
                assertion_hash=("a" if suffix == "one" else "e") * 64,
                attempt_hash=("b" if suffix == "one" else "f") * 64,
                binding_hash="c" * 64,
                jti=f"candidate-{suffix}-123456",
                now=NOW,
            ),
            NOW,
        )
        proof = codec.verify_fresh_proof(
            codec.issue_fresh_proof(
                identity_id=self.identity_id,
                person_id=self.person_id,
                provider="line",
                identity_updated_at=NOW,
                candidate_jti=candidate.jti,
                attempt_hash="d" * 64,
                binding_hash="c" * 64,
                jti=f"proof-{suffix}-123456789",
                now=NOW,
            ),
            NOW,
        )
        return codec, candidate, proof, candidate_id

    def _confirm_recovery(self, codec, candidate, proof, **overrides):
        token_codec = overrides.pop("token_codec", HmacAccessTokenCodec(b"x" * 32))
        values = dict(
            codec=codec,
            candidate=candidate,
            proof=proof,
            now=NOW + timedelta(seconds=1),
            outcome="recovery_link",
            current_person_id=None,
            recovery={
                "refresh": "obvious-fake-refresh",
                "refresh_hash": "1" * 64,
                "installation_id_hash": "2" * 64,
                "platform": "android",
                "token_codec": token_codec,
            },
            session_mode="mobile",
        )
        values.update(overrides)
        return self.repository.confirm_identity_link(**values)

    def test_recovery_confirm_and_lost_response_replay_have_exact_counts(self):
        codec, candidate, proof, _candidate_id = self._google_candidate_proofs()
        token_codec = CapturingAccessTokenCodec()
        first = self._confirm_recovery(codec, candidate, proof, token_codec=token_codec)
        replay = self._confirm_recovery(
            codec, candidate, proof, now=NOW + timedelta(seconds=2)
        )
        self.assertEqual(first.status, "linked")
        self.assertIsNotNone(first.mobile_session)
        self.assertIsNotNone(token_codec.principal)
        self.assertEqual(token_codec.principal.access_level, "basic")
        self.assertEqual(replay.status, "already_linked")
        self.assertIsNone(replay.mobile_session)
        with self.engine.connect() as connection:
            counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM ntubtob.mobile_sessions), "
                    "(SELECT count(*) FROM ntubtob.mobile_refresh_tokens), "
                    "(SELECT count(*) FROM ntubtob.mobile_auth_exchanges), "
                    "(SELECT count(*) FROM ntubtob.access_audit WHERE action='identity_linked')"
                )
            ).one()
        self.assertEqual(tuple(counts), (1, 1, 1, 1))

    def test_service_recovery_accepts_fictional_negative_identity_ids(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.people "
                    "(id, display_name, portal_access_level, portal_status, version, "
                    "created_at, updated_at) VALUES "
                    "(-112001, 'Fictional Tester', 'basic', 'active', 1, :now, :now)"
                ),
                {"now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(id, provider, provider_subject, person_id, status, created_at, "
                    "updated_at) VALUES "
                    "(-112001, 'line', 'fake-fictional-line-subject', -112001, "
                    "'linked', :now, :now)"
                ),
                {"now": NOW},
            )
        service = IdentityLinkService(
            self.repository,
            IdentityLinkProofCodec(b"k" * 32),
            clock=lambda: NOW,
            recovery_auth=SimpleNamespace(
                token_factory=lambda: "fake-refresh-token-for-recovery-proof",
                token_codec=HmacAccessTokenCodec(b"a" * 32),
            ),
        )
        candidate = service.begin_candidate(
            provider="google",
            subject="fake-google-recovery-subject",
            raw_assertion="fake-google-assertion",
            attempt_id="fake-google-attempt",
            binding="fake-installation-binding",
        )
        proof = service.issue_fresh_proof(
            candidate_credential=candidate["candidate_credential"],
            provider="line",
            subject="fake-fictional-line-subject",
            attempt_id="fake-line-proof-attempt",
            binding="fake-installation-binding",
        )
        result = service.confirm_mobile(
            candidate_credential=candidate["candidate_credential"],
            proof_credential=proof["proof_credential"],
            binding="fake-installation-binding",
            outcome="recovery_link",
            platform="android",
        )
        self.assertEqual(result.status, "linked")
        self.assertIsNotNone(result.mobile_session)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT person_id, status FROM ntubtob.auth_identities "
                        "WHERE provider='google' AND "
                        "provider_subject='fake-google-recovery-subject'"
                    )
                ).one(),
                (-112001, "linked"),
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.mobile_sessions "
                        "WHERE person_id=-112001 AND auth_identity_id=-112001 "
                        "AND status='active'"
                    )
                ),
                1,
            )

    def test_recovery_session_insert_failure_rolls_back_link_and_audit(self):
        codec, candidate, proof, candidate_id = self._google_candidate_proofs(
            "rollback"
        )
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="6" * 64,
            login_attempt_hash="9" * 64,
            installation_id_hash="8" * 64,
            platform="ios",
            refresh_hash="7" * 64,
            now=NOW,
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ntubtob.mobile_auth_exchanges "
                    "(provider, assertion_hash, login_attempt_hash, session_id, expires_at, created_at) "
                    "VALUES ('google', :assertion, :attempt, :session, :expires, :now)"
                ),
                {
                    "assertion": candidate.assertion_hash,
                    "attempt": "5" * 64,
                    "session": principal.session_id,
                    "expires": NOW + timedelta(minutes=10),
                    "now": NOW,
                },
            )
        with self.assertRaises(IntegrityError):
            self._confirm_recovery(codec, candidate, proof)
        with self.engine.connect() as connection:
            state = connection.execute(
                text(
                    "SELECT status, person_id FROM ntubtob.auth_identities WHERE id=:id"
                ),
                {"id": candidate_id},
            ).one()
            linked_audits = connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.access_audit "
                    "WHERE auth_identity_id=:id AND action='identity_linked'"
                ),
                {"id": candidate_id},
            )
            sessions = connection.scalar(
                text("SELECT count(*) FROM ntubtob.mobile_sessions")
            )
        self.assertEqual(tuple(state), ("pending", None))
        self.assertEqual(linked_audits, 0)
        self.assertEqual(sessions, 1)
        self.assertIsNotNone(principal.session_id)

    def test_two_concurrent_same_person_confirms_serialize_without_duplicate_effects(
        self,
    ):
        codec, candidate, proof, _candidate_id = self._google_candidate_proofs("race")
        barrier = threading.Barrier(2)

        def confirm(index):
            barrier.wait()
            return MobileRepository(self.engine).confirm_identity_link(
                codec=codec,
                candidate=candidate,
                proof=proof,
                now=NOW + timedelta(seconds=index + 1),
                outcome="recovery_link",
                current_person_id=None,
                recovery={
                    "refresh": f"obvious-fake-refresh-{index}",
                    "refresh_hash": str(index + 3) * 64,
                    "installation_id_hash": "2" * 64,
                    "platform": "android",
                    "token_codec": HmacAccessTokenCodec(b"x" * 32),
                },
                session_mode="mobile",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(confirm, index) for index in (0, 1)]
            try:
                results = [future.result(timeout=10) for future in futures]
            finally:
                for future in futures:
                    future.cancel()
        self.assertEqual(
            sorted(result.status for result in results),
            ["already_linked", "linked"],
        )
        self.assertEqual(
            sum(result.mobile_session is not None for result in results), 1
        )
        with self.engine.connect() as connection:
            counts = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM ntubtob.mobile_sessions), "
                    "(SELECT count(*) FROM ntubtob.access_audit WHERE action='identity_linked')"
                )
            ).one()
        self.assertEqual(tuple(counts), (1, 1))

    def test_line_link_then_domain_unlink_rejects_old_candidate_ticket(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"
                ),
                {"id": self.person_id},
            )
            google_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('google', :subject, :person, 'linked', :now, :now) RETURNING id"
                ),
                {"subject": f"proof-{self.id()}", "person": self.person_id, "now": NOW},
            )
        snapshot = self.repository.ensure_line_link_candidate(
            f"line-candidate-{self.id()}", "Candidate", "pending-line-unlink", NOW
        )
        codec = IdentityLinkProofCodec(b"l" * 32)
        candidate = codec.verify_candidate(
            codec.issue_candidate(
                identity_id=snapshot["identity_id"],
                provider="line",
                identity_updated_at=snapshot["updated_at"],
                assertion_hash="a" * 64,
                attempt_hash="b" * 64,
                binding_hash="c" * 64,
                jti="candidate-unlink-123456",
                now=NOW,
            ),
            NOW,
        )
        proof = codec.verify_fresh_proof(
            codec.issue_fresh_proof(
                identity_id=google_id,
                person_id=self.person_id,
                provider="google",
                identity_updated_at=NOW,
                candidate_jti=candidate.jti,
                attempt_hash="d" * 64,
                binding_hash="c" * 64,
                jti="proof-unlink-123456",
                now=NOW,
            ),
            NOW,
        )
        self.repository.confirm_identity_link(
            codec=codec,
            candidate=candidate,
            proof=proof,
            now=NOW + timedelta(seconds=1),
            outcome="self_link",
            current_person_id=self.person_id,
            recovery=None,
            session_mode="web",
        )
        self.admin_lifecycle.unlink_identity(
            self.person_id,
            snapshot["identity_id"],
            "test unlink",
            "unlink-old-ticket",
            current_identity_id=google_id,
        )
        with self.assertRaises(IdentityLinkConflict):
            self.repository.confirm_identity_link(
                codec=codec,
                candidate=candidate,
                proof=proof,
                now=NOW + timedelta(seconds=2),
                outcome="self_link",
                current_person_id=self.person_id,
                recovery=None,
                session_mode="web",
            )

    def test_cross_person_concurrent_confirms_never_remap_candidate(self):
        codec, candidate, first_proof, candidate_id = self._google_candidate_proofs(
            "cross"
        )
        with self.engine.begin() as connection:
            second_person = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people (display_name, portal_access_level, portal_status, version, created_at, updated_at) "
                    "VALUES ('Second Person', 'basic', 'active', 1, :now, :now) RETURNING id"
                ),
                {"now": NOW},
            )
            second_identity = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities (provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('line', :subject, :person, 'linked', :now, :now) RETURNING id"
                ),
                {"subject": f"second-{self.id()}", "person": second_person, "now": NOW},
            )
        second_proof = codec.verify_fresh_proof(
            codec.issue_fresh_proof(
                identity_id=second_identity,
                person_id=second_person,
                provider="line",
                identity_updated_at=NOW,
                candidate_jti=candidate.jti,
                attempt_hash="e" * 64,
                binding_hash="c" * 64,
                jti="proof-cross-second-123456",
                now=NOW,
            ),
            NOW,
        )
        barrier = threading.Barrier(2)

        def confirm(index, proof):
            barrier.wait()
            try:
                return MobileRepository(self.engine).confirm_identity_link(
                    codec=codec,
                    candidate=candidate,
                    proof=proof,
                    now=NOW + timedelta(seconds=index + 1),
                    outcome="recovery_link",
                    current_person_id=None,
                    session_mode="mobile",
                    recovery={
                        "refresh": f"refresh-{index}",
                        "refresh_hash": str(index + 3) * 64,
                        "installation_id_hash": "2" * 64,
                        "platform": "android",
                        "token_codec": HmacAccessTokenCodec(b"x" * 32),
                    },
                )
            except IdentityLinkConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(confirm, 0, first_proof),
                executor.submit(confirm, 1, second_proof),
            ]
            try:
                results = [future.result(timeout=10) for future in futures]
            finally:
                for future in futures:
                    future.cancel()
        self.assertEqual(sum(result is None for result in results), 1)
        self.assertEqual(
            sum(result is not None and result.status == "linked" for result in results),
            1,
        )
        with self.engine.connect() as connection:
            person = connection.scalar(
                text("SELECT person_id FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": candidate_id},
            )
            counts = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM ntubtob.mobile_sessions), "
                    "(SELECT count(*) FROM ntubtob.access_audit WHERE action='identity_linked' AND auth_identity_id=:id)"
                ),
                {"id": candidate_id},
            ).one()
        self.assertIn(person, {self.person_id, second_person})
        self.assertEqual(tuple(counts), (1, 1))

    def test_concurrent_ignore_and_confirm_serialize_to_one_safe_terminal_state(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"
                ),
                {"id": self.person_id},
            )
            google_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities (provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('google', :subject, :person, 'linked', :now, :now) RETURNING id"
                ),
                {
                    "subject": f"ignore-proof-{self.id()}",
                    "person": self.person_id,
                    "now": NOW,
                },
            )
        snapshot = self.repository.ensure_line_link_candidate(
            f"ignore-candidate-{self.id()}", "Candidate", "pending-ignore-race", NOW
        )
        codec = IdentityLinkProofCodec(b"l" * 32)
        candidate = codec.verify_candidate(
            codec.issue_candidate(
                identity_id=snapshot["identity_id"],
                provider="line",
                identity_updated_at=snapshot["updated_at"],
                assertion_hash="a" * 64,
                attempt_hash="b" * 64,
                binding_hash="c" * 64,
                jti="candidate-ignore-123456",
                now=NOW,
            ),
            NOW,
        )
        proof = codec.verify_fresh_proof(
            codec.issue_fresh_proof(
                identity_id=google_id,
                person_id=self.person_id,
                provider="google",
                identity_updated_at=NOW,
                candidate_jti=candidate.jti,
                attempt_hash="d" * 64,
                binding_hash="c" * 64,
                jti="proof-ignore-123456789",
                now=NOW,
            ),
            NOW,
        )
        barrier = threading.Barrier(2)

        def confirm():
            try:
                MobileRepository(self.engine).confirm_identity_link(
                    codec=codec,
                    candidate=candidate,
                    proof=proof,
                    now=NOW + timedelta(seconds=1),
                    outcome="self_link",
                    current_person_id=self.person_id,
                    recovery=None,
                    session_mode="web",
                    lock_boundary=lambda: barrier.wait(timeout=5),
                )
                return "linked"
            except IdentityLinkConflict:
                return "conflict"

        def ignore():
            try:
                IdentityLifecycleRepository(
                    self.engine, admin_member_ids=(self.admin_member_id,)
                ).set_ignored(
                    self.person_id,
                    snapshot["identity_id"],
                    True,
                    "race ignore",
                    "ignore-race",
                    at=NOW + timedelta(seconds=1),
                    lock_boundary=lambda: barrier.wait(timeout=5),
                )
                return "ignored"
            except ConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(confirm), executor.submit(ignore)]
            try:
                outcomes = [future.result(timeout=10) for future in futures]
            finally:
                for future in futures:
                    future.cancel()
        self.assertIn(
            sorted(outcomes), (["conflict", "ignored"], ["conflict", "linked"])
        )
        with self.engine.connect() as connection:
            state = connection.execute(
                text(
                    "SELECT i.status, u.ignored FROM ntubtob.auth_identities i JOIN ntubtob.line_users u ON u.line_user_id=i.provider_subject WHERE i.id=:id"
                ),
                {"id": snapshot["identity_id"]},
            ).one()
            counts = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM ntubtob.mobile_sessions), "
                    "(SELECT count(*) FROM ntubtob.access_audit WHERE auth_identity_id=:id AND action='identity_linked'), "
                    "(SELECT count(*) FROM ntubtob.access_audit WHERE auth_identity_id=:id AND action='identity_ignored')"
                ),
                {"id": snapshot["identity_id"]},
            ).one()
        self.assertIn(tuple(state), (("linked", False), ("pending", True)))
        self.assertIn(tuple(counts), ((0, 1, 0), (0, 0, 1)))

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE ntubtob.people RESTART IDENTITY CASCADE"))

    def test_security_tables_have_rls_and_revision_is_exact(self):
        expected = {
            "mobile_sessions",
            "mobile_refresh_tokens",
            "mobile_refresh_attempts",
            "mobile_idempotency_records",
            "mobile_auth_exchanges",
            "apple_provider_code_exchanges",
            "apple_provider_credentials",
            "apple_provider_notifications",
        }
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0010_apple_provider_lifecycle",
            )
            tables = set(
                connection.scalars(
                    text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='ntubtob' AND c.relname = ANY(:tables) AND c.relrowsecurity"
                    ),
                    {"tables": list(expected)},
                )
            )
        self.assertEqual(tables, expected)
        model_tables = {
            name: set(PortalDataBase.metadata.tables[f"ntubtob.{name}"].columns.keys())
            for name in expected
        }
        with self.engine.connect() as connection:
            database_columns = {
                name: set(
                    connection.scalars(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='ntubtob' AND table_name=:table"
                        ),
                        {"table": name},
                    )
                )
                for name in expected
            }
        self.assertEqual(database_columns, model_tables)

    def test_refresh_rotation_exact_retry_and_family_replay_revoke(self):
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="a" * 64,
            login_attempt_hash="b" * 64,
            installation_id_hash="c" * 64,
            platform="ios",
            refresh_hash="d" * 64,
            now=NOW,
        )
        values = dict(
            refresh_hash="d" * 64,
            attempt_id_hash="e" * 64,
            request_hash="f" * 64,
            installation_id_hash="c" * 64,
            successor_hash="1" * 64,
            successor="successor",
            cipher=FakeCipher(),
            token_codec=HmacAccessTokenCodec(b"x" * 32),
            now=NOW + timedelta(seconds=1),
        )
        first = self.repository.rotate(**values)
        retry = self.repository.rotate(**values)
        self.assertEqual(first[0].refresh_token, "successor")
        self.assertEqual(first[0], retry[0])
        self.assertFalse(first[1])
        self.assertTrue(retry[1])
        with self.assertRaises(Conflict):
            self.repository.rotate(
                **{
                    **values,
                    "attempt_id_hash": "2" * 64,
                    "now": NOW + timedelta(seconds=2),
                }
            )
        self.assertIsNone(
            self.repository.principal(
                principal.session_id,
                principal.person_id,
                principal.identity_id,
                principal.access_epoch,
                NOW + timedelta(seconds=3),
            )
        )

    def test_apple_code_credential_and_notification_revocation_are_atomic(self):
        subject = f"apple-{self.id()}"
        with self.engine.begin() as connection:
            apple_identity_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('apple', :subject, :person, 'linked', :now, :now) "
                    "RETURNING id"
                ),
                {"subject": subject, "person": self.person_id, "now": NOW},
            )
        self.repository.reserve_apple_code(
            code_hash="a" * 64,
            login_attempt_hash="b" * 64,
            now=NOW,
        )
        principal = self.repository.exchange(
            provider="apple",
            subject=subject,
            assertion_hash="c" * 64,
            login_attempt_hash="b" * 64,
            installation_id_hash="d" * 64,
            platform="ios",
            refresh_hash="e" * 64,
            provider_code_hash="a" * 64,
            encrypted_provider_refresh=b"fictional-ciphertext-only",
            provider_refresh_hash="f" * 64,
            now=NOW,
        )
        changed = self.repository.apply_apple_notification(
            jti_hash="1" * 64,
            event_type="consent-revoked",
            subject=subject,
            event_at=NOW + timedelta(seconds=1),
            now=NOW + timedelta(seconds=2),
        )
        replay = self.repository.apply_apple_notification(
            jti_hash="1" * 64,
            event_type="consent-revoked",
            subject=subject,
            event_at=NOW + timedelta(seconds=1),
            now=NOW + timedelta(seconds=3),
        )

        self.assertTrue(changed)
        self.assertFalse(replay)
        self.assertIsNone(
            self.repository.principal(
                principal.session_id,
                principal.person_id,
                principal.identity_id,
                1,
                NOW + timedelta(seconds=4),
            )
        )
        with self.engine.connect() as connection:
            state = connection.execute(
                text(
                    "SELECT i.status, c.status, c.encrypted_refresh_token, x.state "
                    "FROM ntubtob.auth_identities i "
                    "JOIN ntubtob.apple_provider_credentials c "
                    "ON c.auth_identity_id=i.id "
                    "JOIN ntubtob.apple_provider_code_exchanges x "
                    "ON x.auth_identity_id=i.id WHERE i.id=:identity"
                ),
                {"identity": apple_identity_id},
            ).one()
            receipt_count = connection.scalar(
                text("SELECT count(*) FROM ntubtob.apple_provider_notifications")
            )
        self.assertEqual(
            (*state[:2], bytes(state[2]), state[3]),
            (
                "disabled",
                "revoked",
                b"fictional-ciphertext-only",
                "completed",
            ),
        )
        self.assertEqual(receipt_count, 1)

    def test_pending_apple_identity_retains_consumed_credential_without_session(self):
        subject = f"pending-apple-{self.id()}"
        with self.engine.begin() as connection:
            identity_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.auth_identities "
                    "(provider, provider_subject, person_id, status, created_at, updated_at) "
                    "VALUES ('apple', :subject, NULL, 'pending', :now, :now) "
                    "RETURNING id"
                ),
                {"subject": subject, "now": NOW},
            )
        self.repository.reserve_apple_code(
            code_hash="2" * 64,
            login_attempt_hash="3" * 64,
            now=NOW,
        )
        self.repository.complete_apple_code_for_pending(
            code_hash="2" * 64,
            identity_id=identity_id,
            subject=subject,
            encrypted_provider_refresh=b"fictional-pending-ciphertext",
            provider_refresh_hash="4" * 64,
            now=NOW + timedelta(seconds=1),
        )

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT x.state, x.auth_identity_id, c.status, "
                    "c.encrypted_refresh_token, count(s.id) "
                    "FROM ntubtob.apple_provider_code_exchanges x "
                    "JOIN ntubtob.apple_provider_credentials c "
                    "ON c.auth_identity_id=x.auth_identity_id "
                    "LEFT JOIN ntubtob.mobile_sessions s "
                    "ON s.auth_identity_id=x.auth_identity_id "
                    "WHERE x.code_hash=:code "
                    "GROUP BY x.state, x.auth_identity_id, c.status, "
                    "c.encrypted_refresh_token"
                ),
                {"code": "2" * 64},
            ).one()
        self.assertEqual(
            (*row[:3], bytes(row[3]), row[4]),
            (
                "completed",
                identity_id,
                "active",
                b"fictional-pending-ciphertext",
                0,
            ),
        )

    def test_current_device_logout_and_family_expiry_fail_closed(self):
        first = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="1" * 64,
            login_attempt_hash="2" * 64,
            installation_id_hash="3" * 64,
            platform="ios",
            refresh_hash="4" * 64,
            now=NOW,
        )
        self.repository.logout(first.session_id, NOW + timedelta(seconds=1))
        self.assertIsNone(
            self.repository.principal(
                first.session_id,
                first.person_id,
                first.identity_id,
                1,
                NOW + timedelta(seconds=2),
            )
        )

        second = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="5" * 64,
            login_attempt_hash="6" * 64,
            installation_id_hash="7" * 64,
            platform="android",
            refresh_hash="8" * 64,
            now=NOW,
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.mobile_sessions SET refresh_family_expires_at=:expired WHERE id=:session"
                ),
                {"expired": NOW + timedelta(seconds=1), "session": second.session_id},
            )
        self.assertIsNone(
            self.repository.principal(
                second.session_id,
                second.person_id,
                second.identity_id,
                1,
                NOW + timedelta(seconds=2),
            )
        )

    def test_concurrent_refresh_replay_revokes_family(self):
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="9" * 64,
            login_attempt_hash="a" * 64,
            installation_id_hash="b" * 64,
            platform="ios",
            refresh_hash="c" * 64,
            now=NOW,
        )

        def rotate(suffix):
            try:
                return self.repository.rotate(
                    refresh_hash="c" * 64,
                    attempt_id_hash=suffix * 64,
                    request_hash=("d" if suffix == "1" else "e") * 64,
                    installation_id_hash="b" * 64,
                    successor_hash=("f" if suffix == "1" else "0") * 64,
                    successor=f"successor-{suffix}",
                    cipher=FakeCipher(),
                    token_codec=HmacAccessTokenCodec(b"x" * 32),
                    now=NOW + timedelta(seconds=1),
                )
            except Conflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(rotate, ("1", "2")))
        self.assertEqual(sum(result == "conflict" for result in results), 1)
        self.assertIsNone(
            self.repository.principal(
                principal.session_id,
                principal.person_id,
                principal.identity_id,
                1,
                NOW + timedelta(seconds=2),
            )
        )

    def test_idempotency_exact_replay_and_body_conflict(self):
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="3" * 64,
            login_attempt_hash="4" * 64,
            installation_id_hash="5" * 64,
            platform="android",
            refresh_hash="6" * 64,
            now=NOW,
        )
        values = dict(
            session_id=principal.session_id,
            person_id=principal.person_id,
            method="PUT",
            route="/api/v1/games/44/attendance",
            key_hash="7" * 64,
            request_hash="8" * 64,
            mutation=lambda: (200, {"reply": 1, "changed": True}),
            now=NOW,
        )
        self.assertFalse(self.repository.idempotent(**values)[2])
        self.assertTrue(self.repository.idempotent(**values)[2])
        with self.assertRaises(Conflict):
            self.repository.idempotent(**{**values, "request_hash": "9" * 64})

    def test_concurrent_same_idempotency_key_mutates_once_and_replays(self):
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="a" * 63 + "1",
            login_attempt_hash="b" * 63 + "1",
            installation_id_hash="c" * 63 + "1",
            platform="ios",
            refresh_hash="d" * 63 + "1",
            now=NOW,
        )
        entered, release = threading.Event(), threading.Event()
        calls = []

        def mutation():
            calls.append(1)
            entered.set()
            release.wait(5)
            return 200, {"reply": "attending", "changed": True}

        values = dict(
            session_id=principal.session_id,
            person_id=principal.person_id,
            method="PUT",
            route="/api/v1/games/45/attendance-reply",
            key_hash="e" * 64,
            request_hash="f" * 64,
            mutation=mutation,
            now=NOW,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.repository.idempotent, **values)
            self.assertTrue(entered.wait(5))
            second = pool.submit(self.repository.idempotent, **values)
            release.set()
            results = (first.result(10), second.result(10))
        self.assertEqual(len(calls), 1)
        self.assertEqual({result[2] for result in results}, {False, True})
        self.assertEqual(results[0][1], results[1][1])

    def test_finalize_failure_reconciles_saved_mutation_without_repeating_it(self):
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="1" * 63 + "a",
            login_attempt_hash="2" * 63 + "a",
            installation_id_hash="3" * 63 + "a",
            platform="android",
            refresh_hash="4" * 63 + "a",
            now=NOW,
        )
        saved, calls = {"value": None}, []

        def mutation():
            calls.append("mutation-and-notification")
            saved["value"] = "attending"
            return 200, {"reply": "attending", "notification": "succeeded"}

        def reconcile():
            if saved["value"] == "attending":
                return 200, {"reply": "attending", "notification": "unknown"}
            return None

        original = self.repository._complete_idempotency
        finalize_calls = []

        def fail_once(record, result, now):
            finalize_calls.append(1)
            if len(finalize_calls) == 1:
                raise RuntimeError("simulated finalize disconnect")
            return original(record, result, now)

        self.repository._complete_idempotency = fail_once
        try:
            values = dict(
                session_id=principal.session_id,
                person_id=principal.person_id,
                method="PUT",
                route="/api/v1/games/46/attendance-reply",
                key_hash="5" * 64,
                request_hash="6" * 64,
                mutation=mutation,
                reconcile=reconcile,
                now=NOW,
            )
            first = self.repository.idempotent(**values)
            replay = self.repository.idempotent(**values)
        finally:
            self.repository._complete_idempotency = original
        self.assertEqual(calls, ["mutation-and-notification"])
        self.assertTrue(first[2])
        self.assertTrue(replay[2])
        self.assertEqual(first[1], replay[1])
        self.assertEqual(first[1]["notification"], "succeeded")

    def test_post_commit_application_failure_recovers_unknown_outcome(self):
        principal = self.repository.exchange(
            provider="line",
            subject=f"mobile-{self.id()}",
            assertion_hash="7" * 63 + "b",
            login_attempt_hash="8" * 63 + "b",
            installation_id_hash="9" * 63 + "b",
            platform="ios",
            refresh_hash="a" * 63 + "b",
            now=NOW,
        )
        saved, calls = {"value": None}, []

        def mutation():
            calls.append("saved")
            saved["value"] = "attending"
            raise RuntimeError("simulated response construction failure")

        def reconcile():
            if saved["value"] == "attending":
                return 200, {
                    "reply": "attending",
                    "changed": None,
                    "notification": "unknown",
                }
            return None

        values = dict(
            session_id=principal.session_id,
            person_id=principal.person_id,
            method="PUT",
            route="/api/v1/games/47/attendance-reply",
            key_hash="b" * 64,
            request_hash="c" * 64,
            mutation=mutation,
            reconcile=reconcile,
            now=NOW,
        )
        first = self.repository.idempotent(**values)
        replay = self.repository.idempotent(**values)
        self.assertEqual(calls, ["saved"])
        self.assertIsNone(first[1]["changed"])
        self.assertTrue(first[2])
        self.assertEqual(first[1], replay[1])


if __name__ == "__main__":
    unittest.main()
