import os
from datetime import datetime, timezone, timedelta
from shared_module.settings import (
    local_timezone
)

#print(os.urandom(24))

# now = datetime.now(local_timezone)
# game = datetime(2024, 8, 24, 12, tzinfo=local_timezone)
# _12_hours = timedelta(0, 0, 0, 0, 0, 9)

# result = now > game - _12_hours


# print(now)
# print(game)
# print(result)

now = datetime.now(local_timezone).strftime("%Y年%-m月%-d日 %H:%M:%S")

print(now)