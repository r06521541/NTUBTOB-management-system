from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.portal_data_phase_c_migration import (
    ARTIFACT,
    PhaseCMigrationError,
    verify_artifact as verify_migration_artifact,
    verify_sql,
)
from tools.portal_data_phase_c_readiness import (
    FIELDS,
    INVENTORY_SCHEMA,
    INVENTORY_SQL_PATH,
    POSTCHECK_SCHEMA,
    POSTCHECK_SQL_PATH,
    PhaseCReadinessError,
    compare_evidence,
    validate_rows,
    verify_repository_artifacts,
    verify_sql as verify_evidence_sql,
)


DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


def valid_rows(schema):
    rows = []
    for section, metric in sorted(schema):
        spec = schema[(section, metric)]
        value = "0"
        if spec.field == "boolean_value":
            value = "false" if spec.status == "risk" else "true"
        elif spec.field == "text_value":
            value = (
                "0003_legacy_bigint_activity_game"
                if metric == "revision" and schema is INVENTORY_SCHEMA
                else (
                    "0004_phase_c_identity_lifecycle"
                    if metric == "revision"
                    else "not_checked_by_database"
                )
            )
        elif not spec.gate(value):
            for candidate in ("1", "2", "3", "10", "13"):
                if spec.gate(candidate):
                    value = candidate
                    break
        row = dict.fromkeys(FIELDS, "")
        row.update(section=section, metric=metric, status=spec.status)
        row[spec.field] = value
        rows.append(row)
    return rows


class PhaseCReadinessArtifactTests(unittest.TestCase):
    def test_readiness_artifacts_are_canonical_and_checksummed(self):
        verify_repository_artifacts()

    def test_read_only_artifact_rejects_mutation_and_line_ending_drift(self):
        source = INVENTORY_SQL_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / INVENTORY_SQL_PATH.name
            path.write_bytes(
                source.replace("ROLLBACK;", "DELETE FROM ntubtob.people;").encode()
            )
            path.with_suffix(".sql.sha256").write_text(
                "0" * 64 + f"  {path.name}\n", encoding="ascii"
            )
            with self.assertRaises(PhaseCReadinessError):
                verify_evidence_sql(path)
            path.write_bytes(source.replace("\n", "\r\n").encode())
            with self.assertRaises(PhaseCReadinessError):
                verify_evidence_sql(path)

    def test_validator_rejects_reordered_unknown_and_sensitive_values(self):
        rows = valid_rows(INVENTORY_SCHEMA)
        validate_rows(rows, "inventory")
        changed = [dict(row) for row in rows]
        changed[0] = {**changed[0], "metric": "unexpected"}
        with self.assertRaises(PhaseCReadinessError):
            validate_rows(changed, "inventory")
        changed = [dict(row) for row in rows]
        key = next(index for index, row in enumerate(changed) if row["text_value"])
        changed[key]["text_value"] = "postgresql://fake.invalid/db"
        with self.assertRaises(PhaseCReadinessError):
            validate_rows(changed, "inventory")

    def test_compare_classifies_pass_retry_ambiguity_and_drift(self):
        inventory = validate_rows(valid_rows(INVENTORY_SCHEMA), "inventory")
        postcheck = validate_rows(valid_rows(POSTCHECK_SCHEMA), "postcheck")
        for key, spec in INVENTORY_SCHEMA.items():
            if spec.status == "compare" and key in postcheck:
                postcheck[key] = inventory[key]
        self.assertEqual(compare_evidence(inventory, postcheck), "pass")
        rollback = dict(inventory)
        self.assertEqual(
            compare_evidence(inventory, rollback), "safe_retry_after_confirmed_rollback"
        )
        ambiguous = dict(postcheck)
        ambiguous[("01_contract", "revision")] = "unexpected_revision"
        with self.assertRaisesRegex(PhaseCReadinessError, "ambiguous_commit_state"):
            compare_evidence(inventory, ambiguous)
        drift = dict(postcheck)
        drift[("02_phase_b", "member_count")] = str(
            int(drift[("02_phase_b", "member_count")]) + 1
        )
        with self.assertRaisesRegex(PhaseCReadinessError, "semantic drift"):
            compare_evidence(inventory, drift)

    def test_migration_verifier_rejects_placeholders_and_unexpected_sql(self):
        sql = ARTIFACT.read_text(encoding="utf-8")
        with self.assertRaises(PhaseCMigrationError):
            verify_sql(sql.replace("COMMIT;", "SELECT '{{VALUE}}';\nCOMMIT;"))
        with self.assertRaises(PhaseCMigrationError):
            verify_sql(sql.replace("COMMIT;", "DROP TABLE ntubtob.people;\nCOMMIT;"))
        with self.assertRaises(PhaseCMigrationError):
            verify_sql(sql.replace("\n", "\r\n"))

    def test_migration_verifier_rejects_an_additional_head(self):
        scripts = Mock()
        scripts.get_heads.return_value = [
            "0004_phase_c_identity_lifecycle",
            "fake_additional_head",
        ]
        with patch(
            "tools.portal_data_phase_c_migration.ScriptDirectory.from_config",
            return_value=scripts,
        ):
            with self.assertRaisesRegex(
                PhaseCMigrationError, "unexpected Alembic heads"
            ):
                verify_migration_artifact()


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PhaseCReadinessPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))
        cls.config = Config("alembic.ini")

    @classmethod
    def tearDownClass(cls):
        command.upgrade(cls.config, "head")
        cls.engine.dispose()

    def setUp(self):
        command.upgrade(self.config, "head")
        command.downgrade(self.config, "0003_legacy_bigint_activity_game")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                TRUNCATE TABLE ntubtob.access_audit,ntubtob.person_qualifications,
                  ntubtob.auth_identities,ntubtob.game_attendance_replies,
                  ntubtob.line_users,ntubtob.games,ntubtob.members,ntubtob.people
                RESTART IDENTITY CASCADE;
                INSERT INTO ntubtob.attendance_reply_types (id,description)
                VALUES (1,'yes') ON CONFLICT (id) DO NOTHING;
            """
                )
            )
            person_id = connection.scalar(
                text(
                    """
                INSERT INTO ntubtob.people
                  (display_name,portal_access_level,portal_status,version,created_at,updated_at)
                VALUES ('Fake Person','basic','inactive',1,now(),now()) RETURNING id
            """
                )
            )
            connection.execute(
                text(
                    """
                INSERT INTO ntubtob.members(id,name,person_id) VALUES (7101,'Fake Member',:person_id);
                INSERT INTO ntubtob.line_users
                  (nickname,line_user_id,member_id,has_replied,ignored)
                  VALUES ('Fake Nickname','fake-subject',7101,false,false);
                INSERT INTO ntubtob.auth_identities(provider,provider_subject,person_id,status,created_at,updated_at)
                  VALUES ('line','fake-subject',:person_id,'linked',now(),now());
                INSERT INTO ntubtob.person_qualifications(person_id,qualification,status,reason,created_at,updated_at)
                  VALUES (:person_id,'team_player','active','Fake Phase B fixture',now(),now());
                INSERT INTO ntubtob.games(start_datetime) VALUES (now()+interval '1 day');
                INSERT INTO ntubtob.game_attendance_replies(game_id,user_id,member_id,reply,updated_at)
                  SELECT id,NULL,7101,1,now() FROM ntubtob.games;
            """
                ),
                {"person_id": person_id},
            )

    def _execute(self, path: Path, kind: str):
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                sql = path.read_text(encoding="utf-8")
                cursor.execute(sql.rsplit("ROLLBACK;", 1)[0])
                rows = cursor.fetchall()
                fields = [column.name for column in cursor.description]
                cursor.execute("ROLLBACK")
        finally:
            raw.close()
        return validate_rows(
            (
                dict(
                    zip(
                        fields,
                        (
                            (
                                ""
                                if value is None
                                else (
                                    str(value).lower()
                                    if isinstance(value, bool)
                                    else str(value)
                                )
                            )
                            for value in row
                        ),
                    )
                )
                for row in rows
            ),
            kind,
        )

    def test_clean_0003_to_0004_inventory_postcheck_and_compare(self):
        inventory = self._execute(INVENTORY_SQL_PATH, "inventory")
        command.upgrade(self.config, "0004_phase_c_identity_lifecycle")
        postcheck = self._execute(POSTCHECK_SQL_PATH, "postcheck")
        self.assertEqual(compare_evidence(inventory, postcheck), "pass")

    def test_inventory_rejects_forced_rls_and_exact_audit_drift(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE ntubtob.people FORCE ROW LEVEL SECURITY")
            )
        try:
            with self.assertRaises(PhaseCReadinessError):
                self._execute(INVENTORY_SQL_PATH, "inventory")
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE ntubtob.people NO FORCE ROW LEVEL SECURITY")
                )
        with self.engine.begin() as connection:
            person_id = connection.scalar(text("SELECT min(id) FROM ntubtob.people"))
            connection.execute(
                text(
                    "INSERT INTO ntubtob.access_audit "
                    "(action,target_person_id,after_state,reason,request_id,created_at) "
                    "VALUES ('member_backfilled',:person_id,'{}','Fake drift',"
                    "'fake-wrong-relationship',now())"
                ),
                {"person_id": person_id},
            )
        with self.assertRaises(PhaseCReadinessError):
            self._execute(INVENTORY_SQL_PATH, "inventory")

    def test_postcheck_rejects_unexpected_policy(self):
        command.upgrade(self.config, "0004_phase_c_identity_lifecycle")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE POLICY fake_unexpected_policy "
                    "ON ntubtob.identity_review_threads USING (true)"
                )
            )
        try:
            with self.assertRaises(PhaseCReadinessError):
                self._execute(POSTCHECK_SQL_PATH, "postcheck")
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "DROP POLICY fake_unexpected_policy "
                        "ON ntubtob.identity_review_threads"
                    )
                )

    def test_lock_timeout_rolls_back_and_retry_succeeds(self):
        blocker = self.engine.connect()
        transaction = blocker.begin()
        blocker.execute(text("LOCK TABLE ntubtob.people IN ACCESS EXCLUSIVE MODE"))
        raw = self.engine.raw_connection()
        try:
            with self.assertRaises(Exception):
                with raw.cursor() as cursor:
                    cursor.execute(ARTIFACT.read_text(encoding="utf-8"))
        finally:
            raw.rollback()
            raw.close()
            transaction.rollback()
            blocker.close()
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0003_legacy_bigint_activity_game",
            )
        command.upgrade(self.config, "0004_phase_c_identity_lifecycle")

    def test_injected_mid_migration_failure_is_atomic(self):
        sql = ARTIFACT.read_text(encoding="utf-8").replace(
            "CREATE TABLE ntubtob.identity_review_messages (",
            "CREATE TABLE ntubtob.people (",
            1,
        )
        raw = self.engine.raw_connection()
        try:
            with self.assertRaises(Exception):
                with raw.cursor() as cursor:
                    cursor.execute(sql)
            raw.rollback()
        finally:
            raw.close()
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0003_legacy_bigint_activity_game",
            )
            self.assertFalse(
                connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema='ntubtob' AND table_name='people' "
                        "AND column_name='formal_name')"
                    )
                )
            )
