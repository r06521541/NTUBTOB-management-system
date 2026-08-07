from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.portal_data_restore_rehearsal import (
    ACKNOWLEDGEMENT,
    CATALOG_SQL,
    CONTAINER_PREFIX,
    DATABASE_NAME,
    DOCKER_IMAGE_ID,
    EXPECTED_COLUMNS,
    LEGACY_TABLES,
    OWNERSHIP_FORMAT,
    RESULT_KEYS,
    DockerRestoreRehearsal,
    RestoreRehearsalError,
    main,
    preflight_artifacts,
)

FAKE_CONTAINER_ID = "a" * 64
EXPECTED_OWNERSHIP = f"{FAKE_CONTAINER_ID}|TASK-057|{DOCKER_IMAGE_ID}"


class FakeDocker:
    def __init__(self):
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.overrides: dict[str, subprocess.CompletedProcess[str] | BaseException] = {}

    def __call__(self, command, **kwargs):
        command = list(command)
        self.calls.append((command, kwargs))
        operation = self._operation(command)
        override = self.overrides.get(operation)
        if isinstance(override, BaseException):
            raise override
        if override is not None:
            return override
        if operation == "existence_check":
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation == "ownership_inspect":
            return subprocess.CompletedProcess(
                command, 0, f"{EXPECTED_OWNERSHIP}\n", ""
            )
        if operation == "catalog":
            output = "\n".join(f"{key}=t" for key in RESULT_KEYS) + "\n"
            return subprocess.CompletedProcess(command, 0, output, "")
        return subprocess.CompletedProcess(command, 0, "", "")

    @staticmethod
    def _operation(command: list[str]) -> str:
        if command[1:3] == ["container", "inspect"]:
            return "ownership_inspect"
        if command[1] == "run":
            return "start"
        if command[1:3] == ["rm", "--force"]:
            return "cleanup"
        if command[1:3] == ["ps", "--all"]:
            return "existence_check"
        if "pg_isready" in command:
            return "ready"
        if "pg_restore" in command:
            return "restore"
        if "psql" in command:
            return "catalog"
        raise AssertionError(f"unexpected fake Docker command: {command!r}")

    def commands(self, operation: str) -> list[list[str]]:
        return [
            command
            for command, _ in self.calls
            if self._operation(command) == operation
        ]


class RestoreRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task057-fake-")
        self.directory = Path(self.temporary.name).resolve()
        stem = "portal-data-backup-20260102T030405Z"
        self.archive = self.directory / f"{stem}.dump"
        self.manifest = self.directory / f"{stem}.manifest.json"
        self.checksum = self.directory / f"{stem}.sha256"
        self.archive.write_bytes(b"conspicuously fake custom archive")
        self.manifest.write_text("{}", encoding="utf-8")
        self.checksum.write_text("fake", encoding="ascii")

    def tearDown(self):
        self.temporary.cleanup()

    def _rehearsal(self, docker=None, name=None, attempts=2):
        return DockerRestoreRehearsal(
            self.archive,
            self.manifest,
            self.checksum,
            run=docker or FakeDocker(),
            sleep=lambda _seconds: None,
            name_factory=lambda: name or f"{CONTAINER_PREFIX}0123abcdef45",
            readiness_attempts=attempts,
        )

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_execute_uses_fixed_ephemeral_restore_contract(self, verify, _which):
        docker = FakeDocker()
        rehearsal = self._rehearsal(docker)
        with patch.dict(
            "os.environ",
            {"PATH": "fake-path", "PGPASSWORD": "must-not-pass", "SECRET": "no"},
            clear=True,
        ):
            result = rehearsal.execute(ACKNOWLEDGEMENT)

        self.assertTrue(all(result.__dict__.values()))
        self.assertEqual(verify.call_count, 2)
        start = docker.commands("start")[0]
        self.assertEqual(start[0:3], ["docker", "run", "--detach"])
        self.assertIn("--pull", start)
        self.assertIn("never", start)
        self.assertIn("--network", start)
        self.assertIn("none", start)
        self.assertIn("--read-only", start)
        self.assertIn("--cap-drop", start)
        self.assertIn("ALL", start)
        self.assertIn("no-new-privileges", start)
        self.assertEqual(start.count("--tmpfs"), 3)
        self.assertIn(
            f"type=bind,source={self.directory},target=/backup,readonly", start
        )
        self.assertIn(DOCKER_IMAGE_ID, start)
        for forbidden in (
            "-p",
            "--publish",
            "-v",
            "--volume",
            "--env-file",
            "/var/run/docker.sock",
        ):
            self.assertNotIn(forbidden, start)
        restore = docker.commands("restore")[0]
        for required in (
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            DATABASE_NAME,
            f"/backup/{self.archive.name}",
        ):
            self.assertIn(required, restore)
        for forbidden in ("--clean", "--create", "--if-exists", "--jobs"):
            self.assertNotIn(forbidden, restore)
        self.assertEqual(len(docker.commands("cleanup")), 1)
        self.assertEqual(
            docker.commands("cleanup")[0],
            ["docker", "rm", "--force", FAKE_CONTAINER_ID],
        )
        ownership = docker.commands("ownership_inspect")[0]
        self.assertEqual(
            ownership,
            [
                "docker",
                "container",
                "inspect",
                "--format",
                OWNERSHIP_FORMAT,
                f"{CONTAINER_PREFIX}0123abcdef45",
            ],
        )
        cleanup_index = next(
            index
            for index, (command, _kwargs) in enumerate(docker.calls)
            if FakeDocker._operation(command) == "cleanup"
        )
        ownership_index = next(
            index
            for index, (command, _kwargs) in enumerate(docker.calls)
            if FakeDocker._operation(command) == "ownership_inspect"
        )
        self.assertLess(ownership_index, cleanup_index)

        for _command, kwargs in docker.calls:
            self.assertFalse(kwargs["shell"])
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(kwargs["env"], {"PATH": "fake-path"})

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_missing_acknowledgement_stops_before_docker(self, verify, _which):
        docker = FakeDocker()
        with self.assertRaisesRegex(RestoreRehearsalError, "acknowledgement"):
            self._rehearsal(docker).execute("")
        verify.assert_not_called()
        self.assertEqual(docker.calls, [])

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_preexisting_container_is_preserved_and_fails_closed(
        self, verify, _which
    ):
        docker = FakeDocker()
        docker.overrides["existence_check"] = subprocess.CompletedProcess(
            [], 0, f"{CONTAINER_PREFIX}0123abcdef45\n", ""
        )
        with self.assertRaisesRegex(RestoreRehearsalError, "already exists"):
            self._rehearsal(docker).execute(ACKNOWLEDGEMENT)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(docker.commands("start"), [])
        self.assertEqual(docker.commands("ownership_inspect"), [])
        self.assertEqual(docker.commands("cleanup"), [])

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_foreign_same_name_race_is_never_removed(self, _verify, _which):
        mismatches = (
            f"{FAKE_CONTAINER_ID}|FOREIGN-TASK|{DOCKER_IMAGE_ID}\n",
            f"{FAKE_CONTAINER_ID}|TASK-057|sha256:{'0' * 64}\n",
        )
        for mismatch in mismatches:
            with self.subTest(mismatch=mismatch.split("|")[1]):
                docker = FakeDocker()
                docker.overrides["start"] = subprocess.CompletedProcess(
                    [], 2, "foreign-id", "name conflict"
                )
                docker.overrides["ownership_inspect"] = subprocess.CompletedProcess(
                    [], 0, mismatch, ""
                )

                with self.assertRaisesRegex(RestoreRehearsalError, "cleanup failed"):
                    self._rehearsal(docker).execute(ACKNOWLEDGEMENT)

                self.assertEqual(len(docker.commands("ownership_inspect")), 1)
                self.assertEqual(docker.commands("cleanup"), [])

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_ambiguous_start_failures_require_proven_ownership(
        self, _verify, _which
    ):
        failures = (
            subprocess.CompletedProcess([], 2, "unknown", "unknown"),
            subprocess.TimeoutExpired("docker run", 30),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                docker = FakeDocker()
                docker.overrides["start"] = failure
                docker.overrides["ownership_inspect"] = subprocess.CompletedProcess(
                    [], 1, "", "not found"
                )
                with self.assertRaisesRegex(RestoreRehearsalError, "cleanup failed"):
                    self._rehearsal(docker).execute(ACKNOWLEDGEMENT)
                self.assertEqual(docker.commands("cleanup"), [])

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_ambiguous_timeout_cleans_only_verified_owned_container(
        self, _verify, _which
    ):
        docker = FakeDocker()
        docker.overrides["start"] = subprocess.TimeoutExpired("docker run", 30)
        with self.assertRaisesRegex(RestoreRehearsalError, "timed out"):
            self._rehearsal(docker).execute(ACKNOWLEDGEMENT)
        self.assertEqual(len(docker.commands("ownership_inspect")), 1)
        self.assertEqual(len(docker.commands("cleanup")), 1)

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_restore_readiness_and_catalog_failures_always_cleanup(
        self, _verify, _which
    ):
        failures = (
            ("start", subprocess.CompletedProcess([], 2, "path", "secret")),
            ("ready", subprocess.CompletedProcess([], 1, "path", "secret")),
            ("restore", subprocess.CompletedProcess([], 2, "path", "secret")),
            (
                "catalog",
                subprocess.CompletedProcess([], 0, "schema=f\nrow-value\n", ""),
            ),
        )
        for operation, failure in failures:
            with self.subTest(operation=operation):
                docker = FakeDocker()
                docker.overrides[operation] = failure
                with self.assertRaises(RestoreRehearsalError) as caught:
                    self._rehearsal(docker).execute(ACKNOWLEDGEMENT)
                self.assertEqual(len(docker.commands("cleanup")), 1)
                message = str(caught.exception)
                self.assertNotIn("secret", message)
                self.assertNotIn("row-value", message)

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_cleanup_failure_is_a_terminal_failure(self, _verify, _which):
        docker = FakeDocker()
        docker.overrides["cleanup"] = subprocess.CompletedProcess(
            [], 2, "container-id", "secret"
        )
        with self.assertRaisesRegex(RestoreRehearsalError, "cleanup failed") as caught:
            self._rehearsal(docker).execute(ACKNOWLEDGEMENT)
        self.assertNotIn("secret", str(caught.exception))

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    @patch("tools.portal_data_restore_rehearsal.verify_evidence")
    def test_timeout_is_sanitized_and_cleanup_is_attempted(self, _verify, _which):
        docker = FakeDocker()
        docker.overrides["restore"] = subprocess.TimeoutExpired(
            "contains-secret-and-path", 1
        )
        with self.assertRaises(RestoreRehearsalError) as caught:
            self._rehearsal(docker).execute(ACKNOWLEDGEMENT)
        self.assertEqual(len(docker.commands("cleanup")), 1)
        self.assertNotIn("secret", str(caught.exception))

    @patch(
        "tools.portal_data_restore_rehearsal.shutil.which", return_value="docker"
    )
    def test_invalid_generated_name_stops_before_inspection(self, _which):
        docker = FakeDocker()
        rehearsal = self._rehearsal(docker, name="unowned-container")
        with patch("tools.portal_data_restore_rehearsal.verify_evidence") as verify:
            with self.assertRaisesRegex(RestoreRehearsalError, "name is invalid"):
                rehearsal.execute(ACKNOWLEDGEMENT)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(docker.calls, [])

    def test_catalog_contract_is_fixed_and_deidentified(self):
        self.assertEqual(len(EXPECTED_COLUMNS), 53)
        for table in LEGACY_TABLES:
            self.assertIn(f"ntubtob.{table}", CATALOG_SQL)
        for key in RESULT_KEYS:
            self.assertIn(f"'{key}'", CATALOG_SQL)
        for forbidden in (
            "line_user_id ||",
            "nickname ||",
            "webhook_identifier ||",
            "token ||",
            "SELECT * FROM ntubtob",
        ):
            self.assertNotIn(forbidden, CATALOG_SQL)

    def test_preflight_rejects_nonadjacent_and_repository_artifacts(self):
        other = Path(tempfile.mkdtemp(prefix="task057-sidecar-"))
        try:
            other_manifest = other / self.manifest.name
            other_manifest.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RestoreRehearsalError, "adjacent"):
                preflight_artifacts(self.archive, other_manifest, self.checksum)
            repository_archive = (
                Path(__file__).resolve().parents[2]
                / "portal-data-backup-20260102T030405Z.dump"
            )
            repository_archive.write_bytes(b"fake")
            try:
                with self.assertRaisesRegex(Exception, "outside the repository"):
                    preflight_artifacts(
                        repository_archive,
                        repository_archive.with_suffix(".manifest.json"),
                        repository_archive.with_suffix(".sha256"),
                    )
            finally:
                repository_archive.unlink()
        finally:
            other_manifest.unlink(missing_ok=True)
            other.rmdir()

    @patch("tools.portal_data_restore_rehearsal.shutil.which")
    @patch("tools.portal_data_restore_rehearsal.subprocess.run")
    def test_cli_preflight_never_resolves_or_starts_docker(self, run, which):
        argv = [
            "portal_data_restore_rehearsal.py",
            "preflight",
            str(self.archive),
            str(self.manifest),
            str(self.checksum),
        ]
        with patch.object(sys, "argv", argv), patch("builtins.print"):
            main()
        which.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
