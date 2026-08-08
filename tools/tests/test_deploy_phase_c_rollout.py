import io
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import phase_c_rollout_preflight as preflight

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class PhaseCRolloutPreflightTests(unittest.TestCase):
    def rollout(self, **overrides):
        values = {
            "web_portal": "false",
            "line_webhook": "false",
            "notify_cron": "false",
        }
        values.update(overrides)
        return values

    def test_repository_default_off_and_context_contract_passes_offline(self):
        result = preflight.verify_rollout(
            REPOSITORY_ROOT,
            self.rollout(),
            "false",
            require_artifacts=False,
        )
        self.assertEqual(result.mode, "legacy_unfrozen")

    def test_every_mixed_service_vector_fails_closed(self):
        vectors = (
            {"web_portal": "true"},
            {"line_webhook": "true"},
            {"notify_cron": "true"},
            {"web_portal": "true", "line_webhook": "true"},
            {"web_portal": "true", "notify_cron": "true"},
            {"line_webhook": "true", "notify_cron": "true"},
        )
        for vector in vectors:
            with self.subTest(vector=vector), self.assertRaises(
                preflight.RolloutPreflightError
            ):
                preflight.verify_rollout(
                    REPOSITORY_ROOT,
                    self.rollout(**vector),
                    "false",
                    require_artifacts=False,
                )

    def test_identity_maintenance_requires_all_services_on(self):
        with self.assertRaises(preflight.RolloutPreflightError):
            preflight.verify_rollout(
                REPOSITORY_ROOT,
                self.rollout(),
                "true",
                require_artifacts=False,
            )

        result = preflight.verify_rollout(
            REPOSITORY_ROOT,
            self.rollout(web_portal="true", line_webhook="true", notify_cron="true"),
            "true",
            require_artifacts=False,
        )
        self.assertEqual(result.mode, "maintenance_unfrozen")

    def test_mixed_phase_c_is_accepted_only_when_every_service_is_frozen(self):
        all_frozen = {service: "true" for service in preflight.ROLLOUT_SERVICES}
        result = preflight.verify_rollout(
            REPOSITORY_ROOT,
            self.rollout(web_portal="true"),
            "false",
            freeze_values=all_frozen,
            require_artifacts=False,
        )
        self.assertEqual(result.mode, "mixed_frozen")

        for service in preflight.ROLLOUT_SERVICES:
            with self.subTest(service=service), self.assertRaises(
                preflight.RolloutPreflightError
            ):
                preflight.verify_rollout(
                    REPOSITORY_ROOT,
                    self.rollout(web_portal="true"),
                    "false",
                    freeze_values={**all_frozen, service: "false"},
                    require_artifacts=False,
                )

    def test_environment_typo_or_context_gap_fails_without_showing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_repository_contract(root, phase_c_value="TRUE")
            with self.assertRaisesRegex(
                preflight.RolloutPreflightError,
                "Phase C example must remain explicitly false",
            ):
                preflight.verify_rollout(
                    root, self.rollout(), "false", require_artifacts=False
                )

            self._write_repository_contract(root)
            requirements = root / preflight.SERVICE_REQUIREMENTS["line_webhook"]
            requirements.write_text("shared_lib\n", encoding="utf-8")
            with self.assertRaisesRegex(
                preflight.RolloutPreflightError,
                "does not reference the exact shared library artifact",
            ):
                preflight.verify_rollout(
                    root, self.rollout(), "false", require_artifacts=False
                )

            self._write_repository_contract(root)
            (root / "apps/web_portal/.dockerignore").write_text(
                ".env.yaml\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                preflight.RolloutPreflightError,
                "build context does not satisfy",
            ):
                preflight.verify_rollout(
                    root, self.rollout(), "false", require_artifacts=False
                )

    def test_each_artifact_must_match_current_shared_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_repository_contract(root)
            source_files = {
                "setup.py": b"VERSION = '0.0.1'\n",
                "shared_module/__init__.py": b"",
                "shared_module/portal_data/runtime.py": b"SAFE = True\n",
            }
            self._write_source(root, source_files)
            for relative in (
                Path("shared_lib/dist") / preflight.ARTIFACT_NAME,
                *preflight.ARTIFACT_TARGETS.values(),
            ):
                self._write_artifact(root / relative, source_files)

            fingerprint, artifacts = preflight.verify_artifacts(root)
            self.assertEqual(len(fingerprint), 64)
            self.assertEqual({value for _, value in artifacts}, {fingerprint})

            mutated = dict(source_files)
            mutated["shared_module/portal_data/runtime.py"] = b"SAFE = False\n"
            self._write_artifact(
                root / preflight.ARTIFACT_TARGETS["line_webhook"], mutated
            )
            with self.assertRaisesRegex(
                preflight.RolloutPreflightError, "does not match source"
            ):
                preflight.verify_artifacts(root)

    def test_cli_reports_only_mode_and_source_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_repository_contract(root)
            source_files = {
                "setup.py": b"VERSION = '0.0.1'\n",
                "shared_module/__init__.py": b"",
            }
            self._write_source(root, source_files)
            for relative in (
                Path("shared_lib/dist") / preflight.ARTIFACT_NAME,
                *preflight.ARTIFACT_TARGETS.values(),
            ):
                self._write_artifact(root / relative, source_files)
            output = io.StringIO()
            with patch.object(
                preflight, "repository_root", return_value=root
            ), redirect_stdout(output):
                result = preflight.main(
                    [
                        "--web-portal",
                        "false",
                        "--line-webhook",
                        "false",
                        "--notify-cron",
                        "false",
                        "--identity-maintenance",
                        "false",
                        "--web-portal-freeze",
                        "false",
                        "--line-webhook-freeze",
                        "false",
                        "--notify-cron-freeze",
                        "false",
                    ]
                )
            self.assertEqual(result, 0)
            self.assertIn("mode=legacy_unfrozen", output.getvalue())
            self.assertNotIn(".env", output.getvalue())

    @staticmethod
    def _write_repository_contract(root: Path, phase_c_value: str = "false"):
        envs = {
            "web_portal": (
                f'PORTAL_DATA_PHASE_C_ENABLED: "{phase_c_value}"\n'
                'PORTAL_DATA_ROLLOUT_FREEZE_ENABLED: "false"\n'
                'WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED: "false"\n'
            ),
            "line_webhook_handler": (
                f'PORTAL_DATA_PHASE_C_ENABLED: "{phase_c_value}"\n'
                'PORTAL_DATA_ROLLOUT_FREEZE_ENABLED: "false"\n'
            ),
            "notify_cronjob_service": (
                f'PORTAL_DATA_PHASE_C_ENABLED: "{phase_c_value}"\n'
                'PORTAL_DATA_ROLLOUT_FREEZE_ENABLED: "false"\n'
            ),
        }
        for directory, content in envs.items():
            path = root / "envs" / directory / ".env_example.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        rules = "\n".join(sorted(preflight.REQUIRED_CONTEXT_RULES)) + "\n"
        for path in preflight.CONTEXT_IGNORE_FILES.values():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rules, encoding="utf-8")
        for path in preflight.SERVICE_REQUIREMENTS.values():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"dist/{preflight.ARTIFACT_NAME}\n", encoding="utf-8")

    @staticmethod
    def _write_source(root: Path, files):
        for relative, content in files.items():
            path = root / "shared_lib" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    @staticmethod
    def _write_artifact(path: Path, files):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, "w:gz") as archive:
            root_info = tarfile.TarInfo(f"{preflight.ARTIFACT_ROOT}/")
            root_info.type = tarfile.DIRTYPE
            archive.addfile(root_info)
            for relative, content in files.items():
                info = tarfile.TarInfo(f"{preflight.ARTIFACT_ROOT}/{relative}")
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))


if __name__ == "__main__":
    unittest.main()
