from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from tools.portal_data_logical_backup import (
    ROOT,
    BackupArtifactError,
    DOCKER_IMAGE_ID,
    DockerInspectionRunner,
    _reject_unsafe_path,
    _run_pg_restore,
    create_evidence,
    inspection_runner,
    main,
    validate_planned_paths,
    verify_evidence,
)

LISTING_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "task055_pg_restore_list_fake.txt"
)
SAFE_LISTING = LISTING_FIXTURE.read_text(encoding="utf-8")
VERSION = "pg_restore (PostgreSQL) 15.9\n"
LEGACY_TABLE_NAMES = {
    "attendance_reply_types",
    "ballparks",
    "cancellations",
    "discord_webhooks",
    "game_attendance_replies",
    "games",
    "line_groups",
    "line_notify_tokens",
    "line_users",
    "members",
}


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

    def test_accepts_pg16_header_and_expected_toc_shapes(self):
        self._create(FakeRunner(SAFE_LISTING))
        verify_evidence(
            self.archive, self.manifest, self.checksum, run=FakeRunner(SAFE_LISTING)
        )
        for table_name in LEGACY_TABLE_NAMES:
            with self.subTest(table_name=table_name):
                self.assertIn(
                    f"TABLE ntubtob {table_name} fake_owner",
                    SAFE_LISTING,
                )

    def test_sensitive_terms_require_identifier_boundaries(self):
        for sensitive in ("token", "secret", "password", "token-value"):
            listing = SAFE_LISTING.replace("fake_owner", sensitive, 1)
            with self.subTest(sensitive=sensitive):
                with self.assertRaisesRegex(BackupArtifactError, "sanitized-content"):
                    self._create(FakeRunner(listing))

    def test_rejects_unknown_or_injected_comment_metadata(self):
        listings = (
            SAFE_LISTING.replace(
                ";     TOC Entries: 27",
                ";     Unknown Header: fake",
            ),
            SAFE_LISTING.replace(
                ";     dbname: task055_fake_local",
                ";     password: fake-value",
            ),
        )
        for listing in listings:
            with self.subTest(listing=listing[:120]):
                with self.assertRaises(BackupArtifactError):
                    self._create(FakeRunner(listing))

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


class DockerInspectionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task056-fake-")
        self.directory = Path(self.temporary.name).resolve()
        self.archive = self.directory / "portal-data-backup-20260102T030405Z.dump"
        self.manifest = (
            self.directory / "portal-data-backup-20260102T030405Z.manifest.json"
        )
        self.checksum = self.directory / "portal-data-backup-20260102T030405Z.sha256"
        self.archive.write_bytes(b"fake archive")

    def tearDown(self):
        self.temporary.cleanup()

    @patch("tools.portal_data_logical_backup.shutil.which", return_value="docker")
    @patch("tools.portal_data_logical_backup.subprocess.run")
    def test_list_uses_exact_fixed_image_and_security_argv(self, run, _which):
        run.return_value = Mock(returncode=0, stdout=SAFE_LISTING)
        runner = DockerInspectionRunner(self.archive)

        with patch.dict(
            "os.environ",
            {"PATH": "fake-path", "PGPASSWORD": "must-not-pass", "SECRET": "no"},
            clear=True,
        ):
            output = runner(("--list", str(self.archive)), 17)

        self.assertEqual(output, SAFE_LISTING)
        self.assertEqual(
            run.call_args.args[0],
            [
                "docker",
                "run",
                "--rm",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                f"type=bind,source={self.directory},target=/backup,readonly",
                DOCKER_IMAGE_ID,
                "pg_restore",
                "--list",
                f"/backup/{self.archive.name}",
            ],
        )
        kwargs = run.call_args.kwargs
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], 17)
        self.assertEqual(kwargs["env"], {"PATH": "fake-path"})
        command = run.call_args.args[0]
        self.assertNotIn("--env-file", command)
        self.assertNotIn("-e", command)
        self.assertNotIn("/var/run/docker.sock", " ".join(command))

    @patch("tools.portal_data_logical_backup.shutil.which", return_value="docker")
    @patch("tools.portal_data_logical_backup.subprocess.run")
    def test_version_uses_same_sandbox_and_no_archive_argument(self, run, _which):
        run.return_value = Mock(returncode=0, stdout=VERSION)
        output = DockerInspectionRunner(self.archive)(("--version",), 9)

        self.assertEqual(output, VERSION)
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["pg_restore", "--version"])
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertNotIn(str(self.archive), command)

    @patch("tools.portal_data_logical_backup.subprocess.run")
    def test_rejects_arbitrary_backend_archive_and_options(self, run):
        self.assertIs(inspection_runner("host", self.archive), _run_pg_restore)
        with self.assertRaisesRegex(BackupArtifactError, "backend"):
            inspection_runner("arbitrary", self.archive)
        other = self.directory / "portal-data-backup-20260102T030406Z.dump"
        other.write_bytes(b"other fake")
        runner = DockerInspectionRunner(self.archive)
        for args in (
            ("--list", str(other)),
            ("--list", str(self.archive), "--clean"),
            ("--dbname", "fake"),
        ):
            with self.subTest(args=args):
                with self.assertRaises(BackupArtifactError):
                    runner(args, 1)
        with patch("tools.portal_data_logical_backup.HOME", self.directory):
            with self.assertRaisesRegex(BackupArtifactError, "home directory"):
                runner(("--version",), 1)
        run.assert_not_called()

    @patch("tools.portal_data_logical_backup.shutil.which", return_value="docker")
    @patch("tools.portal_data_logical_backup.subprocess.run")
    def test_hides_timeout_nonzero_and_docker_output(self, run, _which):
        failures = (
            subprocess.TimeoutExpired("contains-path-and-secret", 1),
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
                    DockerInspectionRunner(self.archive)(("--version",), 1)
                message = str(caught.exception)
                self.assertNotIn("secret", message)
                self.assertNotIn("archive listing", message)
                self.assertNotIn(str(self.directory), message)

    @patch("tools.portal_data_logical_backup.shutil.which")
    def test_preflight_with_docker_backend_does_not_start_docker(self, which):
        self.archive.unlink()
        argv = [
            "portal_data_logical_backup.py",
            "preflight",
            str(self.archive),
            str(self.manifest),
            str(self.checksum),
            "--backend",
            "docker",
        ]
        with patch.object(sys, "argv", argv), patch("builtins.print"):
            main()
        which.assert_not_called()


if __name__ == "__main__":
    unittest.main()
