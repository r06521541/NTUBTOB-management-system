from __future__ import annotations

import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHARED_LIB_ROOT = Path(__file__).resolve().parents[2] / "shared_lib"
if str(SHARED_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_LIB_ROOT))

from shared_module.mobile_api import Conflict, HmacAccessTokenCodec
from shared_module.portal_data.mobile_repository import MobileRepository
from shared_module.portal_data.models import PortalDataBase
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)
NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


class FakeCipher:
    def seal(self, value):
        return b"fake:" + value[::-1]

    def open(self, value):
        return value.removeprefix(b"fake:")[::-1]


@unittest.skipUnless(DATABASE_URL, "portal-data PostgreSQL URL is required")
class MobileApiFoundationIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)

    def setUp(self):
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
        self.person_id, self.identity_id = person_id, identity_id
        self.repository = MobileRepository(self.engine)

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE ntubtob.mobile_auth_exchanges, "
                    "ntubtob.mobile_idempotency_records, "
                    "ntubtob.mobile_refresh_attempts, "
                    "ntubtob.mobile_refresh_tokens, ntubtob.mobile_sessions CASCADE"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM ntubtob.auth_identities WHERE id = :identity; "
                    "DELETE FROM ntubtob.people WHERE id = :person"
                ),
                {"identity": self.identity_id, "person": self.person_id},
            )

    def test_five_tables_have_rls_and_revision_is_exact(self):
        expected = {
            "mobile_sessions",
            "mobile_refresh_tokens",
            "mobile_refresh_attempts",
            "mobile_idempotency_records",
            "mobile_auth_exchanges",
        }
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0005_mobile_auth_api_foundation",
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
