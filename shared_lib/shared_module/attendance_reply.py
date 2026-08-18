"""Application service for server-owned game attendance replies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol


class AttendanceReplyRepository(Protocol):
    def reply_to_game(
        self,
        person_id: int,
        game_id: int,
        reply: int,
        user_id: int | None = None,
    ) -> bool:
        """Persist a valid reply and return whether the reply changed."""


@dataclass(frozen=True)
class AttendanceReplyNotification:
    game_summary: str
    person_name: str
    reply_label: str

    def management_message(self) -> str:
        return (
            f"緊急！{self.person_name}臨時回覆{self.game_summary}這場：\n"
            f"{self.reply_label}"
        )


class AttendanceReplyNotifier(Protocol):
    def __call__(self, notification: AttendanceReplyNotification) -> None:
        """Send an urgent attendance reply notification."""


@dataclass(frozen=True)
class AttendanceReplyCommand:
    person_id: int
    game_id: int
    reply: int
    game_start: datetime
    notification: AttendanceReplyNotification
    user_id: int | None = None


class NotificationStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class AttendanceReplyResult:
    changed: bool
    urgent: bool
    notification_status: NotificationStatus
    notification_error: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceReplyService:
    """Persist an attendance reply, then best-effort notify when urgent."""

    def __init__(
        self,
        repository: AttendanceReplyRepository,
        notifier: AttendanceReplyNotifier,
        *,
        clock: Callable[[], datetime] = utc_now,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._notifier = notifier
        self._clock = clock
        self._logger = logger or logging.getLogger(__name__)

    def reply(self, command: AttendanceReplyCommand) -> AttendanceReplyResult:
        game_start = self._as_utc(command.game_start, "game_start")
        now = self._as_utc(self._clock(), "clock")
        urgent = game_start - timedelta(hours=12) < now < game_start
        if command.user_id is None:
            changed = self._repository.reply_to_game(
                command.person_id,
                command.game_id,
                command.reply,
            )
        else:
            changed = self._repository.reply_to_game(
                command.person_id,
                command.game_id,
                command.reply,
                command.user_id,
            )
        if not changed:
            return AttendanceReplyResult(
                changed=False,
                urgent=False,
                notification_status=NotificationStatus.NOT_REQUIRED,
            )

        if not urgent:
            return AttendanceReplyResult(
                changed=True,
                urgent=False,
                notification_status=NotificationStatus.NOT_REQUIRED,
            )

        try:
            self._notifier(command.notification)
        except Exception:
            self._log_notification_failure()
            return AttendanceReplyResult(
                changed=True,
                urgent=True,
                notification_status=NotificationStatus.FAILED,
                notification_error="attendance_notification_failed",
            )
        return AttendanceReplyResult(
            changed=True,
            urgent=True,
            notification_status=NotificationStatus.SUCCEEDED,
        )

    @staticmethod
    def _as_utc(value: datetime, field: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field} must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _log_notification_failure(self) -> None:
        try:
            self._logger.warning("attendance_reply_notification_failed")
        except Exception:
            pass
