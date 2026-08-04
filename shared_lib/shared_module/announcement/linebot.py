
from ..models.line_groups import LineGroup
from ..announcement.announcement_helper import AnnouncementHelper
from linebot.v3.messaging import (
    TextMessage
)
from ..line_messaging_api import (
    push
)


class LineBotAnnouncementHelper(AnnouncementHelper):
    groups: list[LineGroup]

    def __init__(self):
        self.groups = LineGroup.search_groups_to_broadcast()

    def announce(self, message_text: str):
        message = TextMessage(text=message_text)
        for group in self.groups:
            push(group.line_group_id, [message])
