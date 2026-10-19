"""Candidate metadata and guarded disposable-only rewind evidence."""

import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, text

from shared_lib.shared_module.portal_data.models import PortalDataBase
from tests.portal_data import test_erasure_cancellation_schema as fixture
from tests.portal_data._erasure_ledger_test_harness import (
    _constraint_shape,
    _privacy_inventory,
    _privacy_migration,
    _sealed_plan_inventory,
    remove_retained_erasure_ledger_from_isolated_test_database,
)


class ErasurePrivacyMetadataTests(unittest.TestCase):
    def test_constraint_comparison_preserves_boolean_grouping(self):
        self.assertNotEqual(
            _constraint_shape("CHECK ((a OR b) AND c)"),
            _constraint_shape("CHECK (a OR (b AND c))"),
        )

    def test_nullable_actor_columns_match_candidate_and_keep_restrict(self):
        module = _privacy_migration()
        self.assertEqual(len(module.NULLABLE), 8)
        self.assertEqual(module.NULLABLE["identity_review_threads"], "auth_identity_id")
        self.assertEqual(
            module.FIELDS["identity_review_threads"], ("auth_identity_id",)
        )
        self.assertEqual(module.FIELDS["activities"], ("title",))
        for table, name in module.NULLABLE.items():
            column = PortalDataBase.metadata.tables[f"ntubtob.{table}"].c[name]
            self.assertTrue(column.nullable, (table, name))
            self.assertEqual(next(iter(column.foreign_keys)).ondelete, "RESTRICT")

    def test_private_permit_table_is_core_only_with_exact_columns(self):
        table = PortalDataBase.metadata.tables["ntubtob.erasure_privacy_permits"]
        self.assertEqual(
            list(table.c.keys()),
            [
                "backend",
                "transaction_id",
                "table_name",
                "row_id",
                "operation",
                "old_hash",
                "new_hash",
            ],
        )
        self.assertEqual(
            list(table.primary_key.columns.keys()),
            ["backend", "transaction_id", "table_name", "row_id"],
        )
        self.assertEqual(
            {column.name for column in table.c if column.nullable}, {"new_hash"}
        )
        self.assertFalse(
            any(
                mapper.local_table is table
                for mapper in PortalDataBase.registry.mappers
            )
        )

    def test_relaxed_checks_only_remove_actor_requirement(self):
        def check(table, name):
            return next(
                str(c.sqltext)
                for c in PortalDataBase.metadata.tables[f"ntubtob.{table}"].constraints
                if isinstance(c, CheckConstraint) and c.name == name
            )

        invitee = check("event_invitees", "ck_event_invitee_source_fields")
        review = check("identity_review_messages", "ck_identity_review_sender")
        self.assertNotIn("actor_person_id IS NOT NULL", invitee)
        self.assertIn("actor_person_id IS NULL", invitee)
        self.assertIn("length(reason) BETWEEN 3 AND 300", invitee)
        self.assertEqual(
            review,
            "(sender_role = 'applicant' AND sender_person_id IS NULL) OR sender_role = 'admin'",
        )


@unittest.skipUnless(fixture.DATABASE_URL, "isolated erasure URL not configured")
class ErasurePrivacyRewindPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        fixture.ErasureCancellationPostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        fixture.ErasureCancellationPostgresTests.tearDownClass.__func__
    )

    def setUp(self):
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            config = Config(str(fixture.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_erasure_privacy_mutation")

    def tearDown(self):
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)

    def test_full_privacy_rewind_restores_original_guards_and_columns(self):
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0013_account_deletion_requests",
            )
            self.assertIsNone(
                connection.scalar(
                    text("SELECT to_regclass('ntubtob.erasure_privacy_permits')")
                )
            )
            for table, column in _privacy_migration().NULLABLE.items():
                self.assertTrue(
                    connection.scalar(
                        text(
                            """
                  SELECT a.attnotnull FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                  JOIN pg_namespace n ON n.oid=c.relnamespace
                  WHERE n.nspname='ntubtob' AND c.relname=:table AND a.attname=:column
                """
                        ),
                        {"table": table, "column": column},
                    )
                )
            triggers = set(
                connection.scalars(
                    text(
                        """
              SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
              JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob'
            """
                    )
                )
            )
            self.assertTrue(
                set(_privacy_migration().OLD_TRIGGERS.values()).issubset(triggers)
            )
            self.assertNotIn("erasure_privacy_guard", triggers)

    def test_retained_downgrade_marker_is_supported(self):
        with self.engine.begin() as connection:
            config = Config(str(fixture.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.downgrade(config, "0013_account_deletion_requests")
            self.assertTrue(
                _privacy_inventory(connection, "0013_account_deletion_requests")
            )
            self.assertTrue(
                _sealed_plan_inventory(connection, "0013_account_deletion_requests")
            )
        remove_retained_erasure_ledger_from_isolated_test_database(self.engine)

    def test_sealed_plan_catalog_drift_never_authorizes_cleanup(self):
        for sql in (
            "DROP TRIGGER erasure_sealed_plan_insert_guard ON ntubtob.account_erasure_sealed_plans",
            "ALTER TABLE ntubtob.account_erasure_jobs DISABLE TRIGGER erasure_sealed_plan_job_binding",
            "ALTER TABLE ntubtob.account_erasure_sealed_plans DISABLE ROW LEVEL SECURITY",
            "GRANT SELECT ON ntubtob.account_erasure_sealed_plans TO PUBLIC",
            "GRANT EXECUTE ON FUNCTION ntubtob.guard_erasure_sealed_plan() TO PUBLIC",
            "ALTER TABLE ntubtob.account_erasure_sealed_plans DROP CONSTRAINT ck_erasure_plan_size",
            "ALTER TABLE ntubtob.account_erasure_sealed_plans DROP CONSTRAINT account_erasure_sealed_plans_job_id_fkey",
            "CREATE OR REPLACE FUNCTION ntubtob.guard_erasure_sealed_plan() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RETURN NEW; END; $$",
        ):
            with self.subTest(sql=sql), self.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text(sql))
                    with self.assertRaises(RuntimeError):
                        _sealed_plan_inventory(
                            connection, "0018_erasure_privacy_mutation"
                        )
                    self.assertIsNotNone(
                        connection.scalar(
                            text("SELECT to_regclass('ntubtob.account_erasure_jobs')")
                        )
                    )
                finally:
                    transaction.rollback()

    def test_partial_trigger_inventory_fails_closed(self):
        for table in ("events", "identity_review_threads", "activities"):
            with self.subTest(table=table), self.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text(f"DROP TRIGGER erasure_privacy_guard ON ntubtob.{table}")
                    )
                    with self.assertRaisesRegex(RuntimeError, "complete exact"):
                        _privacy_inventory(connection, "0018_erasure_privacy_mutation")
                    self.assertIsNotNone(
                        connection.scalar(
                            text("SELECT to_regclass('ntubtob.account_erasure_items')")
                        )
                    )
                finally:
                    transaction.rollback()

    def test_changed_function_body_fails_closed(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                  CREATE OR REPLACE FUNCTION ntubtob.guard_erasure_privacy_mutation() RETURNS trigger
                  LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN RETURN NEW; END; $$
                """
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "function drift"):
                    _privacy_inventory(connection, "0018_erasure_privacy_mutation")
            finally:
                transaction.rollback()

    def test_private_permit_must_be_empty(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.erasure_privacy_permits VALUES (1,1,'events',1,'UPDATE','fake','fake')"
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "no active permits"):
                    _privacy_inventory(connection, "0018_erasure_privacy_mutation")
            finally:
                transaction.rollback()

    def test_redacted_attribution_prevents_destructive_rewind(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                person = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.people (display_name,portal_access_level,portal_status,version,created_at,updated_at) "
                        "VALUES ('Fictional rewind person','basic','active',1,:now,:now) RETURNING id"
                    ),
                    {"now": fixture.NOW},
                )
                event = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.events (title,event_type,status,start_at,created_by_person_id,version,created_at,updated_at) "
                        "VALUES ('Fictional rewind event','practice','draft',:now,:person,1,:now,:now) RETURNING id"
                    ),
                    {"now": fixture.NOW, "person": person},
                )
                # The isolated owner seeds an already-redacted row through the
                # exact permit, without disabling the trigger or changing DDL.
                connection.execute(
                    text(
                        """
                  INSERT INTO ntubtob.erasure_privacy_permits
                  SELECT pg_backend_pid(),txid_current(),'events',id,'UPDATE',
                    encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),
                    encode(sha256(convert_to((to_jsonb(t)||jsonb_build_object('created_by_person_id',NULL))::text,'UTF8')),'hex')
                  FROM ntubtob.events t WHERE id=:id
                """
                    ),
                    {"id": event},
                )
                connection.execute(
                    text(
                        "UPDATE ntubtob.events SET created_by_person_id=NULL WHERE id=:id"
                    ),
                    {"id": event},
                )
                with self.assertRaisesRegex(RuntimeError, "cannot restore attribution"):
                    _privacy_inventory(connection, "0018_erasure_privacy_mutation")
                self.assertIsNotNone(
                    connection.scalar(
                        text("SELECT to_regclass('ntubtob.erasure_privacy_permits')")
                    )
                )
            finally:
                transaction.rollback()

    def test_detached_review_thread_prevents_destructive_rewind(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                identity = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at) "
                        "VALUES ('apple',:subject,'pending',:now,:now) RETURNING id"
                    ),
                    {"subject": "fictional-rewind-" + uuid4().hex, "now": fixture.NOW},
                )
                thread = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.identity_review_threads (auth_identity_id,status,last_activity_at,created_at,updated_at) "
                        "VALUES (:identity,'open',:now,:now,:now) RETURNING id"
                    ),
                    {"identity": identity, "now": fixture.NOW},
                )
                # Only seed a retained historical state; this is not proof that a
                # pending target is allowed to invoke the Person-only capability.
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.erasure_privacy_permits "
                        "SELECT pg_backend_pid(),txid_current(),'identity_review_threads',id,'UPDATE',"
                        "encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),"
                        "encode(sha256(convert_to((to_jsonb(t)||jsonb_build_object('auth_identity_id',NULL))::text,'UTF8')),'hex') "
                        "FROM ntubtob.identity_review_threads t WHERE id=:id"
                    ),
                    {"id": thread},
                )
                connection.execute(
                    text(
                        "UPDATE ntubtob.identity_review_threads SET auth_identity_id=NULL WHERE id=:id"
                    ),
                    {"id": thread},
                )
                with self.assertRaisesRegex(RuntimeError, "cannot restore attribution"):
                    _privacy_inventory(connection, "0018_erasure_privacy_mutation")
                self.assertEqual(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM ntubtob.identity_review_threads WHERE id=:id"
                        ),
                        {"id": thread},
                    ),
                    1,
                )
            finally:
                transaction.rollback()
