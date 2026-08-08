import unittest

from shared_lib.shared_module.portal_data.runtime import (
    IDENTITY_MAINTENANCE_ENV,
    PHASE_C_ENABLED_ENV,
    ROLLOUT_SERVICES,
    classify_phase_c_rollout,
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
            },
            demo_mode=True,
        )

        self.assertTrue(state.valid)
        self.assertEqual(state.mode, "demo")
        self.assertFalse(state.phase_c_enabled)
        self.assertFalse(state.identity_maintenance_enabled)

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


if __name__ == "__main__":
    unittest.main()
