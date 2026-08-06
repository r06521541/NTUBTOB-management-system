from datetime import datetime, timezone
import unittest

from shared_lib.shared_module.portal_data.legacy_attendance import (
    LegacyAttendanceReply,
    attendance_projection_counts,
    project_current_attendance,
)


class LegacyAttendanceProjectionTests(unittest.TestCase):
    def test_latest_changed_reply_wins_and_same_reply_remains_one_state(self):
        initial = datetime(2037, 1, 1, tzinfo=timezone.utc)
        changed = datetime(2037, 1, 2, tzinfo=timezone.utc)
        history = (
            LegacyAttendanceReply(1, 10, 20, 3, initial),
            LegacyAttendanceReply(2, 10, 20, 1, changed),
            LegacyAttendanceReply(3, 11, 20, 2, initial),
            LegacyAttendanceReply(4, 11, 20, 2, changed),
        )

        projected = project_current_attendance(history)

        self.assertEqual(projected[(10, 20)].reply, 1)
        self.assertEqual(projected[(11, 20)].reply, 2)
        self.assertEqual(
            attendance_projection_counts(history),
            {"history_rows": 4, "current_states": 2},
        )

    def test_larger_id_breaks_equal_timestamp_tie(self):
        same_time = datetime(2037, 1, 1, tzinfo=timezone.utc)
        projected = project_current_attendance(
            (
                LegacyAttendanceReply(8, 10, 20, 1, same_time),
                LegacyAttendanceReply(9, 10, 20, 2, same_time),
            )
        )

        self.assertEqual(projected[(10, 20)].id, 9)
        self.assertEqual(projected[(10, 20)].reply, 2)
