import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_lib.shared_module import attendance_analyzer


class PhaseCAttendanceAnalyzerTests(unittest.TestCase):
    def test_phase_c_maps_person_participants_for_existing_callers(self):
        repository = MagicMock()
        repository.attendance_summary.return_value = SimpleNamespace(
            participants=(
                {
                    "person_id": 44,
                    "member_id": None,
                    "name": "Fake Guest Formal",
                    "reply": 1,
                    "qualification": "guest_player",
                },
            )
        )
        with patch.object(
            attendance_analyzer, "is_phase_c_enabled", return_value=True
        ), patch.object(
            attendance_analyzer,
            "get_identity_lifecycle_repository",
            return_value=repository,
        ), patch.object(
            attendance_analyzer,
            "_legacy_attendance",
            side_effect=AssertionError("legacy attendance must not be queried"),
        ):
            mapping = attendance_analyzer.get_attendance_of_game(23)

        repository.attendance_summary.assert_called_once_with(23)
        self.assertEqual(mapping[1][0].name, "Fake Guest Formal")
        self.assertEqual(mapping[1][0].qualification, "guest_player")
        self.assertIsNone(mapping[1][0].member_id)

    def test_default_off_preserves_legacy_analyzer(self):
        member = SimpleNamespace(name="Fake Member")
        with patch.object(
            attendance_analyzer, "is_phase_c_enabled", return_value=False
        ), patch.object(
            attendance_analyzer, "_legacy_attendance", return_value={1: [member]}
        ):
            mapping = attendance_analyzer.get_attendance_of_game(23)
        self.assertEqual(mapping, {1: [member]})
