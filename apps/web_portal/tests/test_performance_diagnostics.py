import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
if str(WEB_PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_PORTAL_DIR))


from performance_diagnostics import (  # noqa: E402
    MAX_ATTENDANCE_TIMING_MS,
    AttendanceTiming,
)


class AttendanceTimingTest(unittest.TestCase):
    def test_deterministic_clock_emits_only_allowlisted_milliseconds(self):
        clock_values = iter((10.000, 10.003, 10.008, 10.021, 10.023, 10.030))
        logger = MagicMock()
        timing = AttendanceTiming(clock=lambda: next(clock_values))

        timing.finish("member_lookup")
        timing.finish("games_query")
        timing.finish("attendance_analysis")
        timing.finish("render")
        timing.emit(logger)

        logger.info.assert_called_once_with(
            "attendance_timing member_lookup_ms=%d games_query_ms=%d "
            "attendance_analysis_ms=%d render_ms=%d total_ms=%d",
            3,
            5,
            13,
            2,
            30,
        )

    def test_unknown_or_duplicate_stage_fails_closed(self):
        timing = AttendanceTiming(clock=MagicMock(side_effect=(0.0, 0.1, 0.2)))

        with self.assertRaises(ValueError):
            timing.finish("member-id=sentinel")
        timing.finish("member_lookup")
        with self.assertRaises(ValueError):
            timing.finish("member_lookup")

    def test_backward_and_extreme_clock_jumps_are_bounded(self):
        logger = MagicMock()
        timing = AttendanceTiming(
            clock=MagicMock(
                side_effect=(100, 99, 1_000_000, 2_000_000, 3_000_000, 4_000_000)
            )
        )
        for stage in (
            "member_lookup",
            "games_query",
            "attendance_analysis",
            "render",
        ):
            timing.finish(stage)

        timing.emit(logger)

        logger.info.assert_called_once_with(
            "attendance_timing member_lookup_ms=%d games_query_ms=%d "
            "attendance_analysis_ms=%d render_ms=%d total_ms=%d",
            0,
            MAX_ATTENDANCE_TIMING_MS,
            MAX_ATTENDANCE_TIMING_MS,
            MAX_ATTENDANCE_TIMING_MS,
            MAX_ATTENDANCE_TIMING_MS,
        )

    def test_clock_failure_disables_diagnostic_without_logging(self):
        logger = MagicMock()
        timing = AttendanceTiming(clock=MagicMock(side_effect=RuntimeError("secret")))

        timing.finish("member_lookup")
        timing.emit(logger)

        logger.info.assert_not_called()

    def test_non_numeric_clock_disables_diagnostic_without_logging(self):
        logger = MagicMock()
        timing = AttendanceTiming(clock=MagicMock(return_value="clock-sentinel"))

        timing.finish("member_lookup")
        timing.emit(logger)

        logger.info.assert_not_called()

    def test_logging_failure_is_best_effort(self):
        timing = AttendanceTiming(clock=MagicMock(side_effect=(0, 1, 2, 3, 4, 5)))
        for stage in (
            "member_lookup",
            "games_query",
            "attendance_analysis",
            "render",
        ):
            timing.finish(stage)

        timing.emit(MagicMock(info=MagicMock(side_effect=RuntimeError("secret"))))


if __name__ == "__main__":
    unittest.main()
