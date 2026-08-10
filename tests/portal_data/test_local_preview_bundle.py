import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.portal_data_local_preview import (
    MODEL_BY_TABLE,
    TABLE_ORDER,
    PreviewBundleError,
    import_bundle,
    pseudonymize_bundle,
    seal_raw_bundle,
    validate_bundle,
)
from tools.setup_portal_data_legacy import LEGACY_FIXTURE_SQL

NOW = "2026-08-01T10:00:00+00:00"


def raw_rows():
    return {
        "people": [
            {
                "id": 10,
                "display_name": "Production Nickname",
                "formal_name": "Production Name",
                "portal_access_level": "admin",
                "portal_status": "active",
                "version": 1,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "members": [
            {
                "id": 20,
                "name": "Production Member",
                "enroll_year": 2010,
                "major": "Production Major",
                "number": 18,
                "positions": "P,IF",
                "person_id": 10,
            }
        ],
        "games": [
            {
                "id": 30,
                "year": 2026,
                "season": 1,
                "start_datetime": "2026-08-15T02:00:00+00:00",
                "duration": 180,
                "location": "Production Field",
                "home_team": "Production Home",
                "away_team": "Production Away",
                "invitation_time": NOW,
                "cancellation_time": None,
                "cancellation_announcement_time": None,
            }
        ],
        "auth_identities": [
            {
                "id": 40,
                "provider": "line",
                "person_id": 10,
                "status": "linked",
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "person_qualifications": [
            {
                "id": 50,
                "person_id": 10,
                "qualification": "team_player",
                "status": "active",
                "valid_from": None,
                "valid_until": None,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "game_attendance_replies": [
            {
                "id": 60,
                "game_id": 30,
                "member_id": 20,
                "person_id": 10,
                "reply": 1,
                "updated_at": NOW,
            }
        ],
    }


def write_raw_bundle(directory: Path, rows=None):
    rows = rows or raw_rows()
    directory.mkdir()
    for table in TABLE_ORDER:
        with (directory / f"{table}.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        ) as stream:
            for row in rows[table]:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    seal_raw_bundle(directory)


class LocalPreviewBundleTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.derived = self.root / "derived"
        write_raw_bundle(self.raw)

    def tearDown(self):
        self.temporary.cleanup()

    def pseudonymize(self, destination=None):
        target = destination or self.derived
        pseudonymize_bundle(
            self.raw,
            target,
            b"a-private-test-seed-that-is-long-enough",
            date(2026, 8, 20),
        )
        return target

    def test_fixed_export_contract_is_read_only_and_excludes_sensitive_columns(self):
        export_directory = Path("tools/portal_preview_export")
        self.assertEqual(
            {path.stem for path in export_directory.glob("*.sql")},
            set(TABLE_ORDER),
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(export_directory.glob("*.sql"))
        ).lower()
        self.assertEqual(combined.count("begin transaction read only"), 6)
        for forbidden in (
            "provider_subject",
            "admin_note",
            "granted_by_person_id",
            "reason",
            "user_id",
            "password",
            "token",
            "secret",
        ):
            self.assertNotIn(forbidden, combined)
        for mutation in ("insert into", "update ", "delete from", "alter ", "drop "):
            self.assertNotIn(mutation, combined)

    def test_pseudonymization_is_deterministic_and_preserves_relationships(self):
        first = self.pseudonymize()
        second = self.pseudonymize(self.root / "derived-two")
        for table in TABLE_ORDER:
            self.assertEqual(
                (first / f"{table}.jsonl").read_bytes(),
                (second / f"{table}.jsonl").read_bytes(),
            )
        rows = validate_bundle(first, "derived")
        person_id = rows["people"][0]["id"]
        self.assertEqual(rows["members"][0]["person_id"], person_id)
        self.assertEqual(rows["members"][0]["name"], rows["people"][0]["formal_name"])
        self.assertEqual(rows["auth_identities"][0]["person_id"], person_id)
        self.assertEqual(rows["person_qualifications"][0]["person_id"], person_id)
        self.assertEqual(rows["game_attendance_replies"][0]["person_id"], person_id)
        self.assertEqual(rows["members"][0]["number"], 18)
        self.assertNotEqual(rows["members"][0]["enroll_year"], 2010)
        rendered = "".join(
            (first / f"{table}.jsonl").read_text(encoding="utf-8")
            for table in TABLE_ORDER
        )
        for production_value in (
            "Production Nickname",
            "Production Name",
            "Production Member",
            "Production Major",
            "Production Field",
            "Production Home",
            "Production Away",
        ):
            self.assertNotIn(production_value, rendered)

    def test_checksum_unknown_field_revision_and_foreign_key_fail_closed(self):
        self.pseudonymize()
        people = self.derived / "people.jsonl"
        people.write_text(people.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        with self.assertRaisesRegex(PreviewBundleError, "checksum"):
            validate_bundle(self.derived, "derived")

        manifest_path = self.raw / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["revision"] = "unknown"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(PreviewBundleError, "revision"):
            validate_bundle(self.raw, "raw")

        bad = raw_rows()
        bad["members"][0]["person_id"] = 999
        bad_directory = self.root / "bad-reference"
        with self.assertRaisesRegex(PreviewBundleError, "unknown person"):
            write_raw_bundle(bad_directory, bad)

    def test_remote_database_is_rejected_before_engine_creation(self):
        self.pseudonymize()
        called = False

        def factory(_url):
            nonlocal called
            called = True

        with self.assertRaisesRegex(RuntimeError, "isolated local database"):
            import_bundle(
                self.derived,
                "postgresql://user:password@db.example/ntubtob_portal_local",
                factory,
            )
        self.assertFalse(called)

    def test_repository_paths_are_rejected_for_private_artifacts(self):
        with self.assertRaisesRegex(PreviewBundleError, "outside the repository"):
            validate_bundle(Path("portal-preview-bundles/private"), "raw")


@unittest.skipUnless(
    os.environ.get("PORTAL_DATA_TEST_DATABASE_URL"),
    "isolated PostgreSQL URL is not configured",
)
class LocalPreviewPostgresIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["PORTAL_DATA_TEST_DATABASE_URL"]
        cls.engine = create_engine(require_local_database_url(cls.url))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.derived = self.root / "derived"
        self._prepare_repository_fixture()

    def tearDown(self):
        self.temporary.cleanup()

    def _prepare_repository_fixture(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
            connection.execute(text(LEGACY_FIXTURE_SQL))
        with patch.dict(os.environ, {"PORTAL_DATA_DATABASE_URL": self.url}):
            config = Config("alembic.ini")
            command.stamp(config, "0001_legacy_baseline")
            command.upgrade(config, "0004_phase_c_identity_lifecycle")

    def _assert_repository_fixture(self):
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalars(
                    select(MODEL_BY_TABLE["members"].id).order_by(
                        MODEL_BY_TABLE["members"].id
                    )
                ).all(),
                [9201, 9202],
            )
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(MODEL_BY_TABLE["people"])
                ),
                1,
            )
            self.assertEqual(
                session.scalar(text("SELECT count(*) FROM ntubtob.access_audit")),
                1,
            )
            self.assertEqual(
                session.scalars(
                    text("SELECT id FROM ntubtob.attendance_reply_types ORDER BY id")
                ).all(),
                [9101, 9102, 9103],
            )

    def _derive(self, rows=None):
        write_raw_bundle(self.raw, rows)
        pseudonymize_bundle(
            self.raw,
            self.derived,
            b"integration-test-seed-that-is-private",
            date(2026, 8, 20),
        )

    def test_transactional_import_and_relational_readback(self):
        self._assert_repository_fixture()
        self._derive()
        import_bundle(self.derived, self.url)
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(MODEL_BY_TABLE["people"])
                ),
                1,
            )
            attendance = session.scalar(
                select(MODEL_BY_TABLE["game_attendance_replies"])
            )
            member = session.scalar(select(MODEL_BY_TABLE["members"]))
            self.assertEqual(attendance.person_id, member.person_id)
            self.assertEqual(attendance.member_id, member.id)
        repository = IdentityLifecycleRepository(self.engine, ())
        identities = repository.local_preview_identities()
        self.assertEqual(len(identities), 1)
        self.assertNotIn("provider_subject", identities[0])
        principal = repository.local_preview_principal(identities[0]["identity_id"])
        self.assertIsNotNone(principal)
        self.assertEqual(principal.person.member_id, identities[0]["member_id"])

    def test_late_constraint_failure_rolls_back_every_table(self):
        rows = raw_rows()
        duplicate = dict(rows["person_qualifications"][0])
        duplicate["id"] = 51
        rows["person_qualifications"].append(duplicate)
        self._derive(rows)
        with self.assertRaisesRegex(PreviewBundleError, "rolled back"):
            import_bundle(self.derived, self.url)
        self._assert_repository_fixture()
        retry_raw = self.root / "retry-raw"
        retry_derived = self.root / "retry-derived"
        write_raw_bundle(retry_raw)
        pseudonymize_bundle(
            retry_raw,
            retry_derived,
            b"integration-test-seed-that-is-private",
            date(2026, 8, 20),
        )
        import_bundle(retry_derived, self.url)
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(MODEL_BY_TABLE["people"])
                ),
                1,
            )

    def test_nonempty_drift_is_rejected_without_changes(self):
        self._derive()
        with Session(self.engine) as session, session.begin():
            member = session.get(MODEL_BY_TABLE["members"], 9201)
            member.name = "unexpected local data"
        with self.assertRaisesRegex(PreviewBundleError, "must be empty"):
            import_bundle(self.derived, self.url)
        with Session(self.engine) as session:
            self.assertEqual(
                session.get(MODEL_BY_TABLE["members"], 9201).name,
                "unexpected local data",
            )
            self.assertIsNone(session.get(MODEL_BY_TABLE["people"], 1_000_010))


if __name__ == "__main__":
    unittest.main()
