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

# from shared_module.notify.discord_notify import DiscordNotifyHelper
# notify_helper = DiscordNotifyHelper()
# notify_helper.notify_successful_log('測試成功訊息')

# from shared_module.notify.line_notify import LineNotifyHelper
# notify_helper = LineNotifyHelper()
# notify_helper.notify_successful_log('測試成功訊息')


# import shared_module.line_messaging_api as line_messaging_api
# from linebot.v3.messaging import (
#     TextMessage,
# )
# id = 'U4c1e1e62f06d5f367347ee13d820e782'
# text = "Hi"
# line_messaging_api.push(id, [TextMessage(text=text)])


# import shared_module.line_messaging_api as line_messaging_api
# from linebot.v3.messaging import (
#     TextMessage,
# )
# id = 'U4c1e1e62f06d5f367347ee13d820e782'
# text = "Hi"
# line_messaging_api.push(id, [TextMessage(text=text)])
