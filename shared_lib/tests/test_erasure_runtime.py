"""Runtime privacy checks cannot silently turn into legacy access."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shared_module.portal_data import runtime

KEY = "PORTAL_DATA_ERASURE_CHECKS_ENABLED"


class ErasureRuntimeTests(unittest.TestCase):
    def test_parser_defaults_missing_only_and_accepts_exact_boolean_strings(self):
        for environment, expected in (
            ({}, False),
            ({KEY: "false"}, False),
            ({KEY: "true"}, True),
        ):
            with self.subTest(environment=environment):
                self.assertIs(runtime.erasure_checks_enabled(environment), expected)
        for value in (
            "",
            None,
            True,
            False,
            "TRUE",
            " true",
            "false ",
            "private-value",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure checks configuration$"
                ) as caught:
                    runtime.erasure_checks_enabled({KEY: value})
                self.assertNotIn("private-value", str(caught.exception))

    def test_explicit_checks_never_fall_back_to_legacy_or_demo(self):
        for phase in (None, "false", "TRUE", " true"):
            environment = {KEY: "true"}
            if phase is not None:
                environment[runtime.PHASE_C_ENABLED_ENV] = phase
            with self.subTest(phase=phase):
                with self.assertRaisesRegex(
                    RuntimeError, "^erasure checks require Phase C$"
                ):
                    runtime.is_phase_c_enabled(environment)
        with self.assertRaisesRegex(
            RuntimeError, "^erasure checks cannot run in demo mode$"
        ):
            runtime.phase_c_runtime_state(
                {KEY: "true", runtime.PHASE_C_ENABLED_ENV: "true"}, demo_mode=True
            )
        self.assertTrue(
            runtime.is_phase_c_enabled(
                {KEY: "true", runtime.PHASE_C_ENABLED_ENV: "true"}
            )
        )

    def test_invalid_checks_stop_before_database_import(self):
        with patch.dict("os.environ", {KEY: "private-value"}, clear=True):
            with patch(
                "builtins.__import__",
                side_effect=AssertionError("database import reached"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "^invalid erasure checks configuration$"
                ):
                    runtime.get_identity_lifecycle_repository()

    def test_factory_passes_policy_without_callers_overriding_it(self):
        engine = object()
        database = SimpleNamespace(engine=engine)
        for enabled in ("false", "true"):
            with (
                self.subTest(enabled=enabled),
                patch.dict(
                    "os.environ",
                    {KEY: enabled, runtime.PHASE_C_ENABLED_ENV: "true"},
                    clear=True,
                ),
                patch.dict("sys.modules", {"shared_module.models.db": database}),
            ):
                repo = runtime.get_identity_lifecycle_repository(
                    authority_mode="persistent"
                )
                self.assertIs(repo.engine, engine)
                self.assertIs(repo.erasure_checks_enabled, enabled == "true")
                self.assertEqual(repo.authority_mode, "persistent")
