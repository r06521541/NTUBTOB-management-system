from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from tools.portal_data_logical_backup import (
    ROOT,
    BackupArtifactError,
    _reject_unsafe_path,
    _run_pg_restore,
    create_evidence,
    validate_planned_paths,
    verify_evidence,
)

SAFE_LISTING = """;
; Archive created at 2026-01-02 03:04:05 UTC
;     dbname: fake_local_database
;     Format: CUSTOM
;
10; 2615 123 SCHEMA - ntubtob fake_owner
11; 1259 124 TABLE ntubtob members fake_owner
12; 0 124 TABLE DATA ntubtob members fake_owner
13; 0 0 ACL ntubtob TABLE members fake_owner
"""
VERSION = "pg_restore (PostgreSQL) 15.9\n"


class FakeRunner:
    def __init__(self, listing: str = SAFE_LISTING, version: str = VERSION):
        self.listing = listing
        self.version = version
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def __call__(self, args, timeout):
        self.calls.append((tuple(args), timeout))
        if tuple(args) == ("--version",):
            return self.version
        return self.listing


class LogicalBackupArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task055-fake-")
        self.directory = Path(self.temporary.name).resolve()
        self.archive = self.directory / "portal-data-backup-20260102T030405Z.dump"
        self.manifest = (
            self.directory / "portal-data-backup-20260102T030405Z.manifest.json"
        )
        self.checksum = self.directory / "portal-data-backup-20260102T030405Z.sha256"
        self.archive.write_bytes(b"FAKE CUSTOM ARCHIVE\x00" * 8)

    def tearDown(self):
        self.temporary.cleanup()

    def _create(self, runner=None):
        create_evidence(
            self.archive,
            self.manifest,
            self.checksum,
            run=runner or FakeRunner(),
            now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

    def test_create_and_verify_fixed_sanitized_evidence(self):
        runner = FakeRunner()
        self._create(runner)
        verify_evidence(self.archive, self.manifest, self.checksum, run=runner)

        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(
            tuple(manifest),
            (
                "format_version",
                "purpose",
                "created_at_utc",
                "archive_basename",
                "archive_bytes",
                "sha256",
                "pg_restore_client_major",
                "validation",
            ),
        )
        self.assertEqual(manifest["pg_restore_client_major"], 15)
        self.assertEqual(runner.calls[0][0][0], "--list")
        self.assertNotIn("restore", runner.calls[0][0])

    def test_rejects_repository_traversal_and_bad_names(self):
        with self.assertRaisesRegex(BackupArtifactError, "outside the repository"):
            _reject_unsafe_path(ROOT / "fake.dump", must_exist=False)
        with self.assertRaisesRegex(BackupArtifactError, "traversal"):
            _reject_unsafe_path(self.directory / ".." / "fake.dump", must_exist=False)
        bad_archive = self.directory / "backup.dump"
        bad_archive.write_bytes(b"fake")
        with self.assertRaisesRegex(BackupArtifactError, "filename"):
            create_evidence(bad_archive, self.manifest, self.checksum, run=FakeRunner())

    def test_planned_outputs_must_all_be_absent(self):
        self.archive.unlink()
        validate_planned_paths(self.archive, self.manifest, self.checksum)
        with patch(
            "pathlib.Path.is_symlink",
            autospec=True,
            side_effect=lambda candidate: candidate == self.manifest,
        ):
            with self.assertRaisesRegex(BackupArtifactError, "symlink"):
                validate_planned_paths(self.archive, self.manifest, self.checksum)
        self.archive.write_bytes(b"already exists")
        with self.assertRaisesRegex(BackupArtifactError, "existing planned output"):
            validate_planned_paths(self.archive, self.manifest, self.checksum)

    def test_rejects_reparse_empty_non_regular_and_existing_outputs(self):
        with patch(
            "tools.portal_data_logical_backup._is_reparse_point",
            side_effect=lambda path: path == self.archive,
        ):
            with self.assertRaisesRegex(BackupArtifactError, "reparse"):
                create_evidence(
                    self.archive, self.manifest, self.checksum, run=FakeRunner()
                )

        self.archive.write_bytes(b"")
        with self.assertRaisesRegex(BackupArtifactError, "non-empty"):
            create_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )
        self.archive.write_bytes(b"fake")
        self.manifest.write_text("existing", encoding="utf-8")
        with self.assertRaisesRegex(BackupArtifactError, "overwrite"):
            create_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )

    def test_rejects_checksum_manifest_and_archive_drift(self):
        self._create()
        self.archive.write_bytes(b"changed fake archive")
        with self.assertRaisesRegex(BackupArtifactError, "manifest"):
            verify_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )

        self.archive.write_bytes(b"FAKE CUSTOM ARCHIVE\x00" * 8)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["unexpected"] = "fake"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BackupArtifactError, "fields"):
            verify_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )

    def test_rejects_checksum_and_client_major_mismatch(self):
        self._create()
        self.checksum.write_text(
            f"{'0' * 64}  {self.archive.name}\n", encoding="ascii"
        )
        with self.assertRaisesRegex(BackupArtifactError, "checksum"):
            verify_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )

        self._create_after_removing_outputs()
        runner = FakeRunner(version="pg_restore (PostgreSQL) 16.1\n")
        with self.assertRaisesRegex(BackupArtifactError, "client major"):
            verify_evidence(self.archive, self.manifest, self.checksum, run=runner)

    def _create_after_removing_outputs(self):
        self.manifest.unlink(missing_ok=True)
        self.checksum.unlink(missing_ok=True)
        self._create()

    def test_rejects_sensitive_manifest_content(self):
        self._create()
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["purpose"] = "postgresql://fake.invalid/db"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BackupArtifactError, "sensitive"):
            verify_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )

    def test_rejects_manifest_type_confusion(self):
        self._create()
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["archive_bytes"] = True
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BackupArtifactError, "size type"):
            verify_evidence(
                self.archive, self.manifest, self.checksum, run=FakeRunner()
            )

    def test_rejects_foreign_schema_and_listing_injection(self):
        listings = (
            SAFE_LISTING.replace("TABLE ntubtob members", "TABLE public members"),
            SAFE_LISTING + "SELECT fake_secret FROM ntubtob.members;\n",
            SAFE_LISTING + "forged listing line\n",
            SAFE_LISTING.replace("Format: CUSTOM", "Format: PLAIN"),
        )
        for listing in listings:
            with self.subTest(listing=listing[-50:]):
                with self.assertRaises(BackupArtifactError):
                    create_evidence(
                        self.archive,
                        self.manifest,
                        self.checksum,
                        run=FakeRunner(listing),
                    )


class PgRestoreBoundaryTests(unittest.TestCase):
    @patch("tools.portal_data_logical_backup.shutil.which", return_value="pg_restore")
    @patch("tools.portal_data_logical_backup.subprocess.run")
    def test_uses_argument_list_timeout_capture_and_restricted_environment(
        self, run, _which
    ):
        run.return_value = Mock(returncode=0, stdout=SAFE_LISTING)
        with patch.dict(
            "os.environ",
            {"PATH": "fake-path", "PGPASSWORD": "must-not-pass", "SECRET": "no"},
            clear=True,
        ):
            output = _run_pg_restore(("--list", "C:/fake/archive.dump"), 7)
        self.assertEqual(output, SAFE_LISTING)
        kwargs = run.call_args.kwargs
        self.assertEqual(run.call_args.args[0][0], "pg_restore")
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], 7)
        self.assertEqual(kwargs["env"], {"PATH": "fake-path"})

    @patch("tools.portal_data_logical_backup.shutil.which", return_value="pg_restore")
    @patch("tools.portal_data_logical_backup.subprocess.run")
    def test_hides_timeout_nonzero_and_process_details(self, run, _which):
        failures = (
            subprocess.TimeoutExpired("contains-secret", 1),
            Mock(returncode=2, stdout="archive listing", stderr="contains-secret"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                if isinstance(failure, BaseException):
                    run.side_effect = failure
                else:
                    run.side_effect = None
                    run.return_value = failure
                with self.assertRaises(BackupArtifactError) as caught:
                    _run_pg_restore(("--list", "C:/fake/archive.dump"), 1)
                self.assertNotIn("secret", str(caught.exception))
                self.assertNotIn("archive listing", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
