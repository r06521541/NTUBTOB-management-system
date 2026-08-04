import os
from urllib.parse import urljoin

web_portal_url = os.environ.get("WEB_PORTAL_URL")
match_member_path = 'match-member' 
full_match_member_url = urljoin(web_portal_url, match_member_path)

member_come_back = '{nickname}（{note}）已重返追蹤'
new_user = '{nickname}已加入！\n認證新成員網址：{full_match_member_url}'
user_left = '{nickname}已退追蹤'

member_reply_attendance = '新回覆！\n{game_short_summary}\n{member}已回覆：{reply}'
member_rush_reply_attendance = '緊急！{member}臨時回覆{game_short_summary}這場：\n{reply}'
