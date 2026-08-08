import sys
import types
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

        repository.attendance_summary.assert_called_once_with(
            23, use_display_name=False
        )
        self.assertEqual(mapping[1][0].name, "Fake Guest Formal")
        self.assertEqual(mapping[1][0].qualification, "guest_player")
        self.assertIsNone(mapping[1][0].member_id)

    def test_phase_c_forwards_display_name_choice(self):
        repository = MagicMock()
        repository.attendance_summary.return_value = SimpleNamespace(participants=())
        with patch.object(
            attendance_analyzer, "is_phase_c_enabled", return_value=True
        ), patch.object(
            attendance_analyzer,
            "get_identity_lifecycle_repository",
            return_value=repository,
        ):
            attendance_analyzer.get_attendance_of_game(23, use_display_name=True)

        repository.attendance_summary.assert_called_once_with(23, use_display_name=True)

    def test_default_off_preserves_legacy_analyzer(self):
        member = SimpleNamespace(name="Fake Member")
        with patch.object(
            attendance_analyzer, "is_phase_c_enabled", return_value=False
        ), patch.object(
            attendance_analyzer, "_legacy_attendance", return_value={1: [member]}
        ):
            mapping = attendance_analyzer.get_attendance_of_game(23)
        self.assertEqual(mapping, {1: [member]})

    def test_legacy_reader_ignores_phase_c_guest_without_member(self):
        guest = SimpleNamespace(reply=1, member_id=None, updated_at=2)
        member_reply = SimpleNamespace(reply=1, member_id=7, updated_at=1)
        member = SimpleNamespace(name="Fake Member")
        reply_model = MagicMock()
        reply_model.search_by_game_id.return_value = [guest, member_reply]
        member_model = MagicMock()
        member_model.search_by_id.return_value = member
        reply_module = types.ModuleType("game_attendance_replies")
        reply_module.GameAttendanceReply = reply_model
        member_module = types.ModuleType("members")
        member_module.Member = member_model
        with patch.dict(
            sys.modules,
            {
                "shared_lib.shared_module.models": types.ModuleType("models"),
                "shared_lib.shared_module.models.game_attendance_replies": reply_module,
                "shared_lib.shared_module.models.members": member_module,
            },
        ):
            mapping = attendance_analyzer._legacy_attendance(23)

        self.assertEqual(mapping, {1: [member]})
        member_model.search_by_id.assert_called_once_with(7)
