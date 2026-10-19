"""Generation contract; optional disposable PostgreSQL tests never imply rollout."""

import importlib.util
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import AuthIdentityRecord, PersonRecord
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("ACCOUNT_GENERATIONS_TEST_DATABASE_URL")


def migration():
    spec = importlib.util.spec_from_file_location(
        "account_generations", ROOT / "migrations/versions/0015_account_generations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenerationContractTests(unittest.TestCase):
    def test_models_use_server_uuid_not_application_generation(self):
        for model in (PersonRecord, AuthIdentityRecord):
            column = model.__table__.c.account_generation
            self.assertFalse(column.nullable)
            self.assertEqual(str(column.type), "UUID")
            self.assertIsNone(column.default)
            self.assertEqual(
                str(column.server_default.arg), "pg_catalog.gen_random_uuid()"
            )

    def test_additive_backfill_and_fixed_guards(self):
        module = migration()
        self.assertEqual(module.down_revision, "0014_account_erasure_ledger")
        with patch.object(module.op, "execute") as execute:
            module.upgrade()
        sql = "\n".join(str(c.args[0]) for c in execute.call_args_list)
        for table in ("people", "auth_identities"):
            self.assertIn(f"ALTER TABLE ntubtob.{table}", sql)
            self.assertIn(f"BEFORE INSERT OR UPDATE ON ntubtob.{table}", sql)
        self.assertIn("NOT NULL DEFAULT pg_catalog.gen_random_uuid()", sql)
        for field in ("provider", "provider_subject", "person_id"):
            self.assertIn(f"NEW.{field} IS DISTINCT FROM OLD.{field}", sql)
        self.assertIn(
            "NEW.account_generation IS DISTINCT FROM OLD.account_generation", sql
        )
        self.assertNotRegex(
            sql.upper(), r"\b(GRANT|CREATE POLICY|DELETE|DROP|SECURITY DEFINER)\b"
        )
        self.assertNotIn("NEW.status", sql)
        self.assertNotIn("NEW.updated_at", sql)
        with patch.object(module.op, "execute") as execute:
            module.downgrade()
        execute.assert_not_called()

    def test_legacy_orm_excludes_generation_from_select_and_flush_defaults(self):
        for model in (PersonRecord, AuthIdentityRecord):
            mapper = inspect(model)
            self.assertNotIn("account_generation", mapper.attrs)
            self.assertNotIn("account_generation", str(select(model)))
            defaults = mapper._server_default_cols[model.__table__]
            self.assertNotIn(model.__table__.c.account_generation, defaults)
            self.assertIn(
                "account_generation", str(select(model.__table__.c.account_generation))
            )


@unittest.skipUnless(
    DATABASE_URL, "explicit disposable local PostgreSQL opt-in required"
)
class GenerationPostgresTests(unittest.TestCase):
    """Normalize retained candidate fixtures; per-case DDL/data always roll back."""

    @classmethod
    def setUpClass(cls):
        engine = create_engine(require_local_database_url(DATABASE_URL))
        try:
            remove_retained_erasure_ledger_from_isolated_test_database(engine)
            with engine.begin() as connection:
                config = Config(str(ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "0014_account_erasure_ledger")
        finally:
            engine.dispose()

    def setUp(self):
        self.engine = create_engine(require_local_database_url(DATABASE_URL))
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.transaction.rollback)
        revision = (
            self.connection.execute(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )
            .scalars()
            .all()
        )
        self.assertEqual(revision, ["0014_account_erasure_ledger"])
        # Real ORM flush/RETURNING and SELECT against the old physical schema.
        # The source-only tests above are not a substitute for this PG case.
        with Session(
            bind=self.connection, join_transaction_mode="create_savepoint"
        ) as session:
            now = datetime.now(timezone.utc)
            legacy_person = PersonRecord(
                display_name="Fictional old-schema ORM",
                portal_access_level="basic",
                portal_status="active",
                version=1,
                created_at=now,
                updated_at=now,
            )
            legacy_identity = AuthIdentityRecord(
                provider="apple",
                provider_subject="fictional-old-schema-orm",
                status="pending",
                created_at=now,
                updated_at=now,
            )
            session.add_all([legacy_person, legacy_identity])
            session.flush()
            self.assertIsNotNone(legacy_person.id)
            self.assertIsNotNone(legacy_identity.id)
            self.assertIsNotNone(
                session.scalar(
                    select(PersonRecord).where(PersonRecord.id == legacy_person.id)
                )
            )
            self.assertIsNotNone(
                session.scalar(
                    select(AuthIdentityRecord).where(
                        AuthIdentityRecord.id == legacy_identity.id
                    )
                )
            )
            session.rollback()
        self.person = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.people (display_name,portal_access_level,portal_status,version,created_at,updated_at) VALUES ('Fictional generation person','basic','active',1,now(),now()) RETURNING id"
            )
        )
        self.identity = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at) VALUES ('apple','fictional-generation-subject','pending',now(),now()) RETURNING id"
            )
        )
        module = migration()
        with patch.object(module.op, "execute", self.connection.exec_driver_sql):
            module.upgrade()

    def value(self, table, row):
        return self.connection.scalar(
            text(f"SELECT account_generation FROM ntubtob.{table} WHERE id=:id"),
            {"id": row},
        )

    def test_backfill_retention_and_binding_rotation(self):
        person = self.value("people", self.person)
        identity = self.value("auth_identities", self.identity)
        self.assertIsNotNone(person)
        self.assertIsNotNone(identity)
        self.assertNotEqual(person, identity)
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET status='disabled',updated_at=now() WHERE id=:id"
            ),
            {"id": self.identity},
        )
        self.assertEqual(identity, self.value("auth_identities", self.identity))
        for assignment in (
            "provider='google'",
            "provider_subject='fictional-changed'",
            f"person_id={self.person}",
            "person_id=NULL",
        ):
            self.connection.execute(
                text(f"UPDATE ntubtob.auth_identities SET {assignment} WHERE id=:id"),
                {"id": self.identity},
            )
            changed = self.value("auth_identities", self.identity)
            self.assertNotEqual(identity, changed)
            identity = changed
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_status='inactive',updated_at=now() WHERE id=:id"
            ),
            {"id": self.person},
        )
        self.assertEqual(person, self.value("people", self.person))

    def test_manual_rewrites_rejected_even_during_remap(self):
        for table, row in (("people", self.person), ("auth_identities", self.identity)):
            for value in ("NULL", "pg_catalog.gen_random_uuid()"):
                with self.assertRaises(DBAPIError):
                    with self.connection.begin_nested():
                        self.connection.execute(
                            text(
                                f"UPDATE ntubtob.{table} SET account_generation={value} WHERE id=:id"
                            ),
                            {"id": row},
                        )
        with self.assertRaises(DBAPIError):
            with self.connection.begin_nested():
                self.connection.execute(
                    text(
                        "UPDATE ntubtob.auth_identities SET provider='google',account_generation=pg_catalog.gen_random_uuid() WHERE id=:id"
                    ),
                    {"id": self.identity},
                )

    def test_insert_cannot_reuse_previous_generation(self):
        old = self.value("auth_identities", self.identity)
        self.connection.execute(
            text("DELETE FROM ntubtob.auth_identities WHERE id=:id"),
            {"id": self.identity},
        )
        new = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at,account_generation) VALUES ('apple','fictional-generation-subject','pending',now(),now(),:old) RETURNING account_generation"
            ),
            {"old": old},
        )
        self.assertNotEqual(old, new)
