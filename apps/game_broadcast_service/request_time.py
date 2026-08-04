from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Callable


@dataclass(frozen=True)
class RequestTimeWindow:
    now: datetime
    today_begin: datetime
    end_time: datetime


def get_request_time_window(
    local_timezone: tzinfo,
    clock: Callable[[tzinfo], datetime] = datetime.now,
) -> RequestTimeWindow:
    now = clock(local_timezone)
    today_begin = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return RequestTimeWindow(
        now=now,
        today_begin=today_begin,
        end_time=today_begin + timedelta(days=11),
    )
