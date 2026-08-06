"""Read-only helpers for local legacy attendance rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class LegacyAttendanceReply:
    id: int
    game_id: int
    member_id: int | None
    reply: int
    updated_at: datetime


def project_current_attendance(
    history: Iterable[LegacyAttendanceReply],
) -> dict[tuple[int, int | None], LegacyAttendanceReply]:
    """Select one current reply per legacy game/member deterministically."""
    current: dict[tuple[int, int | None], LegacyAttendanceReply] = {}
    for row in history:
        key = (row.game_id, row.member_id)
        existing = current.get(key)
        if existing is None or (row.updated_at, row.id) > (
            existing.updated_at,
            existing.id,
        ):
            current[key] = row
    return current


def attendance_projection_counts(
    history: Iterable[LegacyAttendanceReply],
) -> dict[str, int]:
    """Return aggregate-only counts suitable for local rehearsal output."""
    rows = tuple(history)
    return {
        "history_rows": len(rows),
        "current_states": len(project_current_attendance(rows)),
    }
