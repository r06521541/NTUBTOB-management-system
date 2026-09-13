import unittest

from tools import ios_testflight_diagnostics as diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_main_contracts_and_independent_copies(self):
        for stage, check, reason in (
            ("journal_preflight", "journal_path", "JOURNAL_REJECTED"),
            ("journal_preflight", "existing_journal", "EXISTING_OPERATION"),
            ("journal_open", "journal_path", "JOURNAL_REJECTED"),
            ("journal_start", "journal_write", "JOURNAL_REJECTED"),
            ("recovery", "journal_integrity", "JOURNAL_REJECTED"),
            ("recovery", "existing_journal", "LEGACY_REASON_UNAVAILABLE"),
            ("cleanup", "journal_write", "JOURNAL_REJECTED"),
            ("cleanup", "retention", "UNEXPECTED_INTERNAL_ERROR"),
            ("dispatch_preflight", "unexpected", "CHECK_REJECTED"),
        ):
            expected = dict(stage=stage, check=check, reason=reason)
            self.assertTrue(diagnostics.valid(expected))
            self.assertEqual(diagnostics.failure(stage, check, reason), expected)
            copy = diagnostics.sanitize(expected)
            copy["stage"] = "private-sentinel"
            self.assertEqual(expected["stage"], stage)

    def test_unknown_values_keys_types_and_incompatible_combinations(self):
        for value in (
            None,
            [],
            "private-sentinel",
            {},
            dict(stage="cleanup", check="source", reason="CHECK_REJECTED"),
            dict(stage="journal_start", check="journal_write", reason="HTTP_FORBIDDEN"),
            dict(stage="unknown", check="unexpected", reason="private-sentinel"),
            dict(stage="unknown", check="unexpected", reason=[]),
            dict(
                stage="unknown",
                check="unexpected",
                reason="CHECK_REJECTED",
                raw="private-sentinel",
            ),
        ):
            self.assertFalse(diagnostics.valid(value))
            self.assertIsNone(diagnostics.sanitize(value))
        for values in (
            ([], {}, None),
            ("private-sentinel", "source", "CHECK_REJECTED"),
            ("cleanup", "source", "CHECK_REJECTED"),
        ):
            safe = diagnostics.failure(*values)
            self.assertTrue(diagnostics.valid(safe))
            self.assertNotIn("private-sentinel", repr(safe))

    def test_every_return_is_finite_and_has_no_authority_flags(self):
        for stage in diagnostics.STAGES:
            for reason in diagnostics.REASONS:
                result = diagnostics.failure(stage, "unexpected", reason)
                self.assertTrue(diagnostics.valid(result))
                self.assertEqual(set(result), {"stage", "check", "reason"})


if __name__ == "__main__":
    unittest.main()
