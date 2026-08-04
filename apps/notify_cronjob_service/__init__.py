
# from shared_module.models.line_groups import LineGroup

# groups = LineGroup.search_groups_to_broadcast()
# print()


from shared_module.announcement.linebot import LineBotAnnouncementHelper

helper = LineBotAnnouncementHelper()
helper.announce('Hi')