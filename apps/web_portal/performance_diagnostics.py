from math import isfinite
from time import monotonic


ATTENDANCE_TIMING_STAGES = (
    "member_lookup",
    "games_query",
    "attendance_analysis",
    "render",
)


class AttendanceTiming:
    """Best-effort, bounded timing for one successful attendance response."""

    def __init__(self, clock=monotonic):
        self._clock = clock
        self._started_at = self._read_clock()
        self._last_at = self._started_at
        self._durations = {}
        self._enabled = self._started_at is not None

    def _read_clock(self):
        try:
            value = float(self._clock())
            return value if isfinite(value) else None
        except Exception:
            return None

    def finish(self, stage):
        if stage not in ATTENDANCE_TIMING_STAGES:
            raise ValueError("Unknown attendance timing stage")
        if stage in self._durations:
            raise ValueError("Attendance timing stage already finished")
        if not self._enabled:
            return

        finished_at = self._read_clock()
        if finished_at is None:
            self._enabled = False
            self._durations.clear()
            return
        self._durations[stage] = max(
            0, round((finished_at - self._last_at) * 1000)
        )
        self._last_at = finished_at

    def emit(self, logger):
        if not self._enabled or tuple(self._durations) != ATTENDANCE_TIMING_STAGES:
            return
        finished_at = self._read_clock()
        if finished_at is None:
            return
        total_ms = max(0, round((finished_at - self._started_at) * 1000))
        try:
            logger.info(
                "attendance_timing member_lookup_ms=%d games_query_ms=%d "
                "attendance_analysis_ms=%d render_ms=%d total_ms=%d",
                self._durations["member_lookup"],
                self._durations["games_query"],
                self._durations["attendance_analysis"],
                self._durations["render"],
                total_ms,
            )
        except Exception:
            # Observability must not become an availability dependency.
            pass
