import unittest

from shared_lib.shared_module.portal_data.runtime import (
    IDENTITY_MAINTENANCE_ENV,
    PHASE_C_ENABLED_ENV,
    ROLLOUT_FREEZE_ENV,
    ROLLOUT_SERVICES,
    classify_phase_c_rollout,
    classify_phase_c_transition,
    is_rollout_freeze_enabled,
    phase_c_runtime_state,
)


class PhaseCRuntimeStateTests(unittest.TestCase):
    def test_only_exact_true_enables_each_flag(self):
        off_values = (None, "", "false", "False", "TRUE", "1", " true")
        for value in off_values:
            environment = {}
            if value is not None:
                environment[PHASE_C_ENABLED_ENV] = value
            with self.subTest(flag="phase_c", value=value):
                self.assertEqual(phase_c_runtime_state(environment).mode, "legacy")

        state = phase_c_runtime_state({PHASE_C_ENABLED_ENV: "true"})
        self.assertTrue(state.phase_c_enabled)
        self.assertFalse(state.identity_maintenance_enabled)
        self.assertEqual(state.mode, "phase_c")

        for value in off_values:
            environment = {}
            if value is not None:
                environment[ROLLOUT_FREEZE_ENV] = value
            with self.subTest(flag="rollout_freeze", value=value):
                self.assertFalse(is_rollout_freeze_enabled(environment))
        self.assertTrue(is_rollout_freeze_enabled({ROLLOUT_FREEZE_ENV: "true"}))

    def test_maintenance_without_phase_c_is_invalid_and_effectively_off(self):
        state = phase_c_runtime_state({IDENTITY_MAINTENANCE_ENV: "true"})

        self.assertFalse(state.valid)
        self.assertFalse(state.phase_c_enabled)
        self.assertFalse(state.identity_maintenance_enabled)
        self.assertTrue(state.maintenance_requested)
        self.assertEqual(state.mode, "invalid")

    def test_demo_mode_never_enables_database_runtime_or_maintenance(self):
        state = phase_c_runtime_state(
            {
                PHASE_C_ENABLED_ENV: "true",
                IDENTITY_MAINTENANCE_ENV: "true",
                ROLLOUT_FREEZE_ENV: "true",
            },
            demo_mode=True,
        )

        self.assertTrue(state.valid)
        self.assertEqual(state.mode, "demo")
        self.assertFalse(state.phase_c_enabled)
        self.assertFalse(state.identity_maintenance_enabled)
        self.assertFalse(state.rollout_freeze_enabled)

    def test_full_maintenance_requires_both_exact_opt_ins(self):
        state = phase_c_runtime_state(
            {
                PHASE_C_ENABLED_ENV: "true",
                IDENTITY_MAINTENANCE_ENV: "true",
            }
        )

        self.assertTrue(state.valid)
        self.assertTrue(state.phase_c_enabled)
        self.assertTrue(state.identity_maintenance_enabled)
        self.assertEqual(state.mode, "phase_c_maintenance")


class PhaseCRolloutStateTests(unittest.TestCase):
    def flags(self, *enabled):
        return {service: service in enabled for service in ROLLOUT_SERVICES}

    def test_all_off_all_on_and_final_maintenance_are_safe(self):
        legacy = classify_phase_c_rollout(self.flags())
        phase_c = classify_phase_c_rollout(self.flags(*ROLLOUT_SERVICES))
        maintenance = classify_phase_c_rollout(
            self.flags(*ROLLOUT_SERVICES), identity_maintenance=True
        )

        self.assertEqual((legacy.safe, legacy.mode), (True, "legacy"))
        self.assertEqual((phase_c.safe, phase_c.mode), (True, "phase_c"))
        self.assertEqual(
            (maintenance.safe, maintenance.mode), (True, "phase_c_maintenance")
        )

    def test_every_single_service_and_two_service_mix_is_forbidden(self):
        combinations = (
            ("web_portal",),
            ("line_webhook",),
            ("notify_cron",),
            ("web_portal", "line_webhook"),
            ("web_portal", "notify_cron"),
            ("line_webhook", "notify_cron"),
        )
        for enabled in combinations:
            with self.subTest(enabled=enabled):
                state = classify_phase_c_rollout(self.flags(*enabled))
                self.assertFalse(state.safe)
                self.assertEqual(state.mode, "forbidden_mixed_mode")

    def test_unknown_or_missing_service_fails_closed(self):
        state = classify_phase_c_rollout({"web_portal": False, "line_webhook": False})
        self.assertFalse(state.safe)
        self.assertEqual(state.mode, "invalid_service_set")

    def test_transition_state_distinguishes_every_freeze_stage(self):
        all_off = self.flags()
        all_on = self.flags(*ROLLOUT_SERVICES)
        all_frozen = self.flags(*ROLLOUT_SERVICES)
        all_unfrozen = self.flags()

        cases = (
            (all_off, all_unfrozen, False, "legacy_unfrozen", True),
            (all_off, all_frozen, False, "legacy_frozen", True),
            (
                self.flags("web_portal"),
                all_frozen,
                False,
                "mixed_frozen",
                True,
            ),
            (all_on, all_frozen, False, "phase_c_frozen", True),
            (all_on, all_unfrozen, False, "phase_c_unfrozen", True),
            (all_on, all_frozen, True, "maintenance_frozen", True),
            (all_on, all_unfrozen, True, "maintenance_unfrozen", True),
        )
        for phase_flags, freeze_flags, maintenance, mode, safe in cases:
            with self.subTest(mode=mode):
                state = classify_phase_c_transition(
                    phase_flags,
                    freeze_flags,
                    identity_maintenance=maintenance,
                )
                self.assertEqual((state.mode, state.safe), (mode, safe))

    def test_every_mixed_unfrozen_state_is_unsafe(self):
        mixed_phase_vectors = (
            self.flags("web_portal"),
            self.flags("line_webhook"),
            self.flags("notify_cron"),
            self.flags("web_portal", "line_webhook"),
            self.flags("web_portal", "notify_cron"),
            self.flags("line_webhook", "notify_cron"),
        )
        freeze_vectors = (
            self.flags(),
            self.flags("web_portal"),
            self.flags("line_webhook", "notify_cron"),
        )
        for phase_flags in mixed_phase_vectors:
            for freeze_flags in freeze_vectors:
                with self.subTest(phase=phase_flags, freeze=freeze_flags):
                    state = classify_phase_c_transition(phase_flags, freeze_flags)
                    self.assertFalse(state.safe)
                    self.assertEqual(state.mode, "mixed_unfrozen")

    def test_partial_freeze_is_only_safe_outside_mixed_phase_c(self):
        partial = self.flags("web_portal")
        legacy = classify_phase_c_transition(self.flags(), partial)
        phase_c = classify_phase_c_transition(self.flags(*ROLLOUT_SERVICES), partial)
        maintenance = classify_phase_c_transition(
            self.flags(*ROLLOUT_SERVICES),
            partial,
            identity_maintenance=True,
        )

        self.assertEqual((legacy.mode, legacy.safe), ("legacy_freeze_transition", True))
        self.assertEqual(
            (phase_c.mode, phase_c.safe), ("phase_c_freeze_transition", True)
        )
        self.assertEqual(
            (maintenance.mode, maintenance.safe),
            ("maintenance_partial_freeze", False),
        )

    def test_transition_rejects_missing_unknown_and_non_boolean_values(self):
        invalid_cases = (
            (
                {"web_portal": False, "line_webhook": False},
                self.flags(),
                "invalid_service_set",
            ),
            (
                {**self.flags(), "unknown": False},
                self.flags(),
                "invalid_service_set",
            ),
            (
                {**self.flags(), "web_portal": "false"},
                self.flags(),
                "invalid_flag_value",
            ),
        )
        for phase_flags, freeze_flags, mode in invalid_cases:
            with self.subTest(mode=mode):
                state = classify_phase_c_transition(phase_flags, freeze_flags)
                self.assertEqual((state.mode, state.safe), (mode, False))


if __name__ == "__main__":
    unittest.main()
